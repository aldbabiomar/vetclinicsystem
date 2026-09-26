"""
Patient care lists and history: follow-ups, wellness reminders (most
urgent first, D-16), the grooming queue, and a patient's visits and
stays.
"""
from datetime import date, timedelta

from vcs import clock
from vcs.domain import dates


MISSED_WINDOW_DAYS = 14   # 2 weeks — used for follow-ups, wellness, and Lost to Follow Up


WELLNESS_LEAD_DAYS = 5    # remind 5 days before the next-dose date


def boarding_sessions_for_patient(db, patient_id):
    return db.execute(
        "SELECT * FROM boarding_sessions WHERE patient_id=%s ORDER BY entry_date DESC", (patient_id,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Follow-ups (method, not type)
# ---------------------------------------------------------------------------
def _annotate_followup(r, today):
    """Computes the two per-row display fields (reminder_call_date,
    missed) shared by followups() and followups_page() — factored out so
    both the full (unpaginated, used by the dashboard's missed-items
    summary) and paginated (used by the Follow-ups list page) code paths
    compute them identically, from the same function, rather than two
    copies that could quietly drift apart."""
    reminder_call_date = None
    if r["followup_method"] == "Physical Visit" and r["followup_date"]:
        reminder_call_date = dates.fmt_date(dates.as_date(r["followup_date"]) - timedelta(days=1))
    r["reminder_call_date"] = reminder_call_date
    r["missed"] = False
    if r["followup_status"] == "Pending" and r["followup_date"]:
        fdate = dates.as_date(r["followup_date"])
        if fdate and (today - fdate).days >= MISSED_WINDOW_DAYS:
            r["missed"] = True
    return r


def followups(db, only_pending=False, on_dates=None):
    """Follow-ups, newest date first. `on_dates` limits them to those days
    (the Dashboard wants today's and tomorrow's, not every pending one ever)."""
    params = []
    q = """
    SELECT v.id as visit_id, v.followup_method, v.followup_reason, v.followup_date,
           v.followup_status, v.doctor, v.created_by, v.date as visit_date,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE v.followup_needed = 'Y'
    """
    if only_pending:
        q += " AND v.followup_status = 'Pending'"
    if on_dates is not None:
        q += " AND v.followup_date = ANY(%s)"
        params.append(list(on_dates))
    rows = [dict(r) for r in db.execute(q, params).fetchall()]
    today = clock.today()
    out = [_annotate_followup(r, today) for r in rows]
    out.sort(key=lambda r: (r["followup_date"] or date.min), reverse=True)
    return out


def followups_page(db, only_pending=False, limit=20, offset=0):
    """
    Same rows and same per-row fields as followups(), but paginated at
    the database level (ORDER BY + LIMIT/OFFSET) instead of fetching
    every matching visit and slicing the list in Python — used by the
    Follow-ups list page. Returns (rows, total_count).

    Deliberately a separate function rather than adding limit/offset to
    followups() itself: followups() is also called unpaginated by the
    dashboard's missed-items summary (alerts.missed_items()), which needs
    every matching row to scan for "missed", not just one page of them.
    "missed" is a per-row display flag here, not something rows are
    filtered or ordered by, so paginating first and annotating only the
    resulting page is exactly equivalent to the old fetch-everything-
    then-slice approach for what this page actually shows.
    """
    where = "v.followup_needed = 'Y'"
    if only_pending:
        where += " AND v.followup_status = 'Pending'"
    total = db.execute(f"SELECT COUNT(*) c FROM visits v WHERE {where}").fetchone()["c"]
    q = f"""
    SELECT v.id as visit_id, v.followup_method, v.followup_reason, v.followup_date,
           v.followup_status, v.doctor, v.created_by, v.date as visit_date,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE {where}
    ORDER BY COALESCE(v.followup_date, '0001-01-01') DESC, v.id DESC
    LIMIT %s OFFSET %s
    """
    rows = [dict(r) for r in db.execute(q, [limit, offset]).fetchall()]
    today = clock.today()
    rows = [_annotate_followup(r, today) for r in rows]
    return rows, total


# ---------------------------------------------------------------------------
# Wellness reminders
# ---------------------------------------------------------------------------
def _annotate_wellness(r, today):
    """Shared by wellness_reminders() and wellness_reminders_page() — see
    _annotate_followup() above for why this is factored out."""
    next_dose = dates.as_date(r["wellness_next_dose_date"])
    remind_from = next_dose - timedelta(days=WELLNESS_LEAD_DAYS) if next_dose else None
    missed = bool(next_dose and (today - next_dose).days >= MISSED_WINDOW_DAYS and r["wellness_contacted"] != "Y")
    # "Due" ends where "missed" begins (audit B19). It used to last forever,
    # so every uncontacted reminder since the clinic opened stayed in the
    # Dashboard's "due" list and the sidebar badge; a missed one belongs on
    # the Missed Items list, for an admin to review.
    due = bool(remind_from and today >= remind_from and r["wellness_contacted"] != "Y" and not missed)
    r["remind_from_date"] = dates.fmt_date(remind_from)
    r["due"] = due
    r["missed"] = missed
    return r


# The wellness entries that are reminders: a next dose recorded, and not
# replaced by a NEWER entry for the same pet and the same type (audit B19) --
# the pet came back and the next dose was set again, so the old date is no
# longer owed. Before, the old entry went on being "due", then "missed".
_WELLNESS_CURRENT = """
    v.wellness_needed = 'Y' AND v.wellness_next_dose_date IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM visits v2
        WHERE v2.patient_id = v.patient_id AND v2.wellness_needed = 'Y'
          AND v2.wellness_next_dose_date IS NOT NULL
          AND v2.wellness_type IS NOT DISTINCT FROM v.wellness_type
          AND (COALESCE(v2.date, '0001-01-01'::date), v2.id) > (COALESCE(v.date, '0001-01-01'::date), v.id))
"""


def _wellness_urgency(r, today):
    """Most urgent first (owner decision D-16): open reminders by the earliest
    next dose, then the closed ones -- contacted, or past the missed window --
    newest first, so years-old history does not sit above this week's."""
    dose = dates.as_date(r["wellness_next_dose_date"]) or date.max
    closed = r["wellness_contacted"] == "Y" or (today - dose).days >= MISSED_WINDOW_DAYS
    return (1, -dose.toordinal(), -r["visit_id"]) if closed else (0, dose.toordinal(), r["visit_id"])


def wellness_reminders(db, only_due=False):
    q = """
    SELECT v.id as visit_id, v.wellness_type, v.wellness_next_dose_date, v.wellness_contacted,
           v.wellness_contact_method, v.doctor, v.created_by,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE """ + _WELLNESS_CURRENT
    today = clock.today()
    params = []
    if only_due:
        # Only the doses that can be due, so the Dashboard (on every page, for
        # the badge) does not read every reminder ever set (audit D3). Due is
        # decided below; this window is one day wider than it on the missed
        # side, so it can only let through more, never fewer.
        q += " AND v.wellness_next_dose_date BETWEEN %s AND %s"
        params += [today - timedelta(days=MISSED_WINDOW_DAYS), today + timedelta(days=WELLNESS_LEAD_DAYS)]
    rows = [dict(r) for r in db.execute(q, params).fetchall()]
    out = []
    for r in rows:
        r = _annotate_wellness(r, today)
        # only_due depends on "due", which is computed from today's date
        # at request time — not a stored column — so unlike followups()'s
        # only_pending this can't move into the WHERE clause; kept as a
        # post-fetch filter exactly as before.
        if only_due and not r["due"]:
            continue
        out.append(r)
    out.sort(key=lambda r: _wellness_urgency(r, today))
    return out


def wellness_reminders_page(db, limit=20, offset=0):
    """
    Same rows and fields as wellness_reminders(only_due=False) — the only
    mode the Wellness list page actually uses — paginated at the database
    level. Returns (rows, total_count).

    Deliberately doesn't support only_due=True: "due" depends on today's
    date at request time, not a stored column, so filtering by it can't
    move into SQL the way only_pending could for followups — and the one
    only_due=True caller (alerts.dashboard_snapshot()) wants every matching
    row for its count, not one page, so it keeps calling
    wellness_reminders() directly, unpaginated, exactly as before.
    """
    total = db.execute("SELECT COUNT(*) c FROM visits v WHERE " + _WELLNESS_CURRENT).fetchone()["c"]
    today = clock.today()
    # The same order as _wellness_urgency(), in SQL so it pages correctly:
    # open reminders (not contacted, not past the missed window) by the
    # earliest next dose, then the closed ones newest first.
    missed_before = today - timedelta(days=MISSED_WINDOW_DAYS)
    closed = "(COALESCE(v.wellness_contacted, 'N') = 'Y' OR v.wellness_next_dose_date <= %s)"
    q = f"""
    SELECT v.id as visit_id, v.wellness_type, v.wellness_next_dose_date, v.wellness_contacted,
           v.wellness_contact_method, v.doctor, v.created_by,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE {_WELLNESS_CURRENT}
    ORDER BY CASE WHEN {closed} THEN 1 ELSE 0 END,
             CASE WHEN {closed} THEN NULL ELSE v.wellness_next_dose_date END ASC,
             CASE WHEN {closed} THEN NULL ELSE v.id END ASC,
             v.wellness_next_dose_date DESC, v.id DESC
    LIMIT %s OFFSET %s
    """
    rows = [dict(r) for r in db.execute(q, [missed_before] * 3 + [limit, offset]).fetchall()]
    rows = [_annotate_wellness(r, today) for r in rows]
    return rows, total


# ---------------------------------------------------------------------------
# Grooming queue (lives on the visit record itself)
# ---------------------------------------------------------------------------
GROOMING_SERVICES = ["Bath", "Haircut", "De-shedding", "Nail Trim", "Ear Cleaning", "Ear Mites Cleaning",
                      "Paw Clipping", "Nail Caps", "Anal Gland Emptying", "Zoning"]


def grooming_queue(db, include_finished=False):
    q = """
    SELECT v.id as visit_id, v.date, v.grooming_services, v.grooming_notes, v.grooming_admitted_items,
           v.grooming_status, v.grooming_contacted, p.id as patient_id, p.animal_name,
           o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE v.grooming_needed='Y'
    """
    if not include_finished:
        q += " AND (v.grooming_status IS NULL OR v.grooming_status != 'Finished')"
    q += " ORDER BY v.date DESC"
    return [dict(r) for r in db.execute(q).fetchall()]


def grooming_queue_page(db, include_finished=False, limit=20, offset=0):
    """
    Same rows as grooming_queue(), paginated at the database level.
    Returns (rows, total_count). A separate function rather than adding
    limit/offset to grooming_queue() itself, matching the same reasoning
    as followups_page()/wellness_reminders_page() above: grooming_queue()
    is also called unpaginated by alerts.dashboard_snapshot() for its queue
    count, which needs every matching row.
    """
    where = "v.grooming_needed='Y'"
    if not include_finished:
        where += " AND (v.grooming_status IS NULL OR v.grooming_status != 'Finished')"
    total = db.execute(f"SELECT COUNT(*) c FROM visits v WHERE {where}").fetchone()["c"]
    q = f"""
    SELECT v.id as visit_id, v.date, v.grooming_services, v.grooming_notes, v.grooming_admitted_items,
           v.grooming_status, v.grooming_contacted, p.id as patient_id, p.animal_name,
           o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE {where}
    ORDER BY v.date DESC, v.id DESC
    LIMIT %s OFFSET %s
    """
    rows = [dict(r) for r in db.execute(q, [limit, offset]).fetchall()]
    return rows, total


def patient_outpatient_visits(db, patient_id, cases, order="DESC"):
    """A patient's visits, minus each one that is just the admitting
    encounter of an inpatient stay listed beside it (audit P4). The stay
    already shows that encounter -- same complaint, exam and treatment -- so
    the patient's history showed it twice.

    A case opened from a visit names it (inpatient_cases.visit_id), which is
    exact. A case opened directly has no link, so as the predecessor IQ app
    did, a visit marked "Inpatient" on that case's admission date is the
    same encounter. A visit marked "Inpatient" with no stay to match stays in
    the list rather than disappearing."""
    linked = {c["visit_id"] for c in cases if c["visit_id"]}
    unlinked_dates = {c["admission_date"] for c in cases if not c["visit_id"]}
    order = "ASC" if str(order).upper() == "ASC" else "DESC"
    visits = db.execute(f"SELECT * FROM visits WHERE patient_id=%s ORDER BY date {order}, id {order}",
                        (patient_id,)).fetchall()
    return [v for v in visits
            if v["id"] not in linked and not (v["visit_type"] == "Inpatient" and v["date"] in unlinked_dates)]


def patient_history(db, patient_id):
    cases = db.execute("SELECT * FROM inpatient_cases WHERE patient_id=%s ORDER BY admission_date DESC", (patient_id,)).fetchall()
    visits = patient_outpatient_visits(db, patient_id, cases)
    boarding = boarding_sessions_for_patient(db, patient_id)
    events = []
    for v in visits:
        events.append({"kind": "Visit", "date": v["date"], "record": dict(v), "summary": v["complaint"] or v["visit_type"]})
    for c in cases:
        events.append({"kind": "Inpatient stay", "date": c["admission_date"], "record": dict(c),
                        "summary": c["complaint"] or "Inpatient stay"})
    for b in boarding:
        events.append({"kind": "Boarding", "date": b["entry_date"], "record": dict(b),
                        "summary": f"Boarding — {b['room']}" if b["room"] else "Boarding stay"})
    events.sort(key=lambda e: e["date"] or date.min, reverse=True)
    return events
