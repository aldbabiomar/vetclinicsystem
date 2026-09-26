"""
What the Dashboard warns about: the snapshot behind the sidebar badge,
missed items, the backup alert and the operating-costs reminder.
"""
import calendar
from datetime import timedelta

from vcs import clock
from vcs.domain import clinical, dates, inventory


def N_(text):
    """Mark for extraction without translating here — see selfcheck.N_."""
    return text


def _alert(msgid, args=None):
    """A dashboard alert, shaped like a self-check finding so one template
    filter renders both."""
    args = args or {}
    try:
        message = msgid % args if args else msgid
    except (KeyError, TypeError, ValueError):
        message = msgid
    return {"message": message, "msgid": msgid, "args": args}


def backup_alert_message(last_backup_row):
    """A warning for the Dashboard, or None if backups look healthy.

    Returns the same shape `selfcheck._finding()` does — `message` (rendered
    English, which is what callers and tests read), plus `msgid`/`args` for
    the `finding` template filter to translate at render time. It used to
    return a bare f-string, which meant the one banner a clinic sees when its
    backups are failing could never be translated: the interpolated value made
    every message unique, so no catalogue entry could ever match it.
    """
    if not last_backup_row:
        return _alert(N_("No database backup has ever run yet — set a backup folder "
                         "on the Settings page."))
    if last_backup_row["status"] == "failed":
        return _alert(N_("The last database backup failed: %(error)s."),
                      {"error": last_backup_row["error"] or "unknown error"})
    if last_backup_row["status"] == "running":
        # reap_stale_running() (backup.py, called at app boot) cleans up a
        # row stranded by a killed process — but within the same still-
        # running app session, a row that's been "running" unreasonably
        # long is the same signal, just not yet reaped. Left unflagged,
        # this status is neither "failed" nor 2+-days-old, so the checks
        # below would otherwise report healthy backups for as long as it
        # sits there. See ORPHANED_RECORDS_AUDIT.md F-21.
        try:
            started_dt = clock.parse(last_backup_row["started_at"])
        except (TypeError, ValueError):
            started_dt = None
        if started_dt and (clock.now() - started_dt).total_seconds() > 6 * 3600:
            return _alert(N_("The last backup started but never finished — check "
                             "the Settings page."))
        return None
    started = dates.as_date(last_backup_row["started_at"])
    if started and (clock.today() - started).days >= 2:
        return _alert(N_("The database hasn't been backed up in 2+ days — check "
                         "the Settings page."))
    return None


# ---------------------------------------------------------------------------
# Missed items — for the admin dashboard
# ---------------------------------------------------------------------------
def missed_items(db):
    out = []
    for f in clinical.followups(db, only_pending=True):
        if f["missed"]:
            out.append({"kind": "Follow-up", "visit_id": f["visit_id"], "animal_name": f["animal_name"],
                        "deadline": f["followup_date"], "responsible": f["doctor"] or f["created_by"]})
    for w in clinical.wellness_reminders(db):
        if w["missed"]:
            out.append({"kind": "Wellness", "visit_id": w["visit_id"], "animal_name": w["animal_name"],
                        "deadline": w["wellness_next_dose_date"], "responsible": w["doctor"] or w["created_by"]})

    today = clock.today()
    rows = db.execute(
        "SELECT v.id, v.case_status_changed_at, v.doctor, v.created_by, p.animal_name FROM visits v "
        "JOIN patients p ON p.id=v.patient_id WHERE v.case_status='Lost to Follow Up'"
    ).fetchall()
    for r in rows:
        changed = dates.as_date(r["case_status_changed_at"]) if r["case_status_changed_at"] else None
        if changed and (today - changed).days >= clinical.MISSED_WINDOW_DAYS:
            out.append({"kind": "Lost to Follow Up", "visit_id": r["id"], "animal_name": r["animal_name"],
                        "deadline": dates.fmt_date(changed), "responsible": r["doctor"] or r["created_by"]})
    # Newest missed deadline first — the three sources above are each
    # already sorted that way individually, but concatenating them
    # doesn't interleave them, so the combined list needs its own sort.
    # "deadline" is a date object for the first two sources (straight from
    # a DATE column) and a string for the third (fmt_date()'s output) —
    # normalize to ISO text so the comparison never mixes types.
    def _deadline_key(r):
        d = r["deadline"]
        return d.isoformat() if hasattr(d, "isoformat") else (d or "")
    out.sort(key=_deadline_key, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Dashboard snapshot
# ---------------------------------------------------------------------------
def dashboard_snapshot(db):
    today = clock.today()
    tomorrow = today + timedelta(days=1)

    total_patients = db.execute("SELECT COUNT(*) c FROM patients").fetchone()["c"]
    active_statuses = {"Ongoing", "Admitted to Inpatient", "Needs Filling"}
    all_visits = db.execute("SELECT case_status FROM visits").fetchall()
    active_cases = sum(1 for v in all_visits if v["case_status"] in active_statuses)
    admitted_now = db.execute("SELECT COUNT(*) c FROM inpatient_cases WHERE dismissed=false").fetchone()["c"]

    fu = clinical.followups(db, only_pending=True)
    due_today = [f for f in fu if dates.as_date(f["followup_date"]) == today]
    reminders_tomorrow = [f for f in fu if dates.as_date(f["followup_date"]) == tomorrow and f["followup_method"] == "Physical Visit"]

    wr = clinical.wellness_reminders(db, only_due=True)
    grooming = clinical.grooming_queue(db)

    inv = inventory.inventory_status(db)
    low_stock = [i for i in inv if i["stock_status"] == "LOW STOCK"]
    overdue_audit = [i for i in inv if i["audit_status"] in ("OVERDUE", "Never audited")]
    expiring = [i for i in inv if i["expiry_status"] in ("EXPIRING SOON", "EXPIRED")]

    return {
        "total_patients": total_patients, "active_cases": active_cases, "admitted_now": admitted_now,
        "due_today": due_today, "reminders_tomorrow": reminders_tomorrow, "wellness_due": wr,
        "grooming_queue": grooming, "low_stock": low_stock, "overdue_audit": overdue_audit, "expiring": expiring,
    }


def opex_reminder_due(db):
    """True in the last 3 days of the current month if that month's opex hasn't been entered."""
    today = clock.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    if last_day - today.day > 2:
        return False
    month = today.strftime("%Y-%m")
    row = db.execute("SELECT 1 FROM monthly_opex WHERE month=?", (month,)).fetchone()
    return row is None
