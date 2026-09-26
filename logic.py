"""
VetClinicSystem — computation engine (v3).
Pure computation over Postgres tables; no Flask imports.
"""
import calendar
import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask_babel import gettext
from collections import defaultdict

import auth as authmod
import money
import reports
import clock

MISSED_WINDOW_DAYS = 14   # 2 weeks — used for follow-ups, wellness, and Lost to Follow Up
WELLNESS_LEAD_DAYS = 5    # remind 5 days before the next-dose date


def as_date(v):
    """A STORED value as a date: a DATE column's date as is, a timestamptz's
    moment as the clinic-zone day it fell on, or the ISO text of either (a
    date computed in code, a stamp kept in a JSON job result).

    Never for a date that arrives in a request -- that is core.strict_date(),
    which accepts exactly YYYY-MM-DD. This one is lenient on purpose (it
    reads a whole ISO timestamp), and it was the request parser until audit
    B1: since Python 3.11 date.fromisoformat() also accepts 2026-W39-4 and
    20260925, which the routes then passed raw to Postgres (a 500 on four
    pages, silently empty results on three). Renamed from parse_date so the
    two cannot be confused.

    It still validates the whole value, never a prefix: "2026-08-25garbage"
    raises (it once parsed clean from a blind str(v)[:10])."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return clock.aware(v).date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s).date()


def fmt_date(d):
    """A date for display: a date as is, a stored moment (timestamptz) as the
    clinic-zone day it fell on."""
    if not d:
        return None
    if isinstance(d, datetime):
        return clock.aware(d).date().isoformat()
    return d.isoformat()


def fmt_datetime(v, fmt="%Y-%m-%d %H:%M"):
    """A stored moment for display, in the clinic's zone: a timestamptz read
    back, or an ISO string held in a setting or a job result. Digits only —
    the |localtime filter adds Arabic-Indic ones."""
    if not v:
        return ""
    return clock.parse(v).strftime(fmt)


def month_key(d):
    """Returns the 'YYYY-MM' of a date value: an ISO date string, a date, or
    a datetime (a timestamptz read back) — the last taken in the clinic's
    zone, so a sale at 01:00 on the 1st is not filed under last month
    because the connection happened to be in UTC. None for a falsy input."""
    if not d:
        return None
    if isinstance(d, datetime):
        return clock.aware(d).strftime("%Y-%m")
    if hasattr(d, "isoformat"):
        return d.isoformat()[:7]
    return str(d)[:7]


def _first_of_next_month(first):
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def month_dates(month):
    """'YYYY-MM' -> (first day, first day of the next month), for a DATE
    column: `col >= ? AND col < ?`. Never `col::text LIKE 'YYYY-MM%'` — that
    cannot use an index and, on a timestamp, does not work at all."""
    first = date.fromisoformat(f"{month}-01")
    return first, _first_of_next_month(first)


def month_bounds(month):
    """'YYYY-MM' -> the first instant of that month and of the next, in the
    clinic's zone, for a timestamptz column: `col >= ? AND col < ?`."""
    first, nxt = month_dates(month)
    z = clock.zone()
    return (datetime.combine(first, datetime.min.time(), tzinfo=z),
            datetime.combine(nxt, datetime.min.time(), tzinfo=z))


def day_bounds(day):
    """A date (or ISO date string) -> the first instant of that day and of
    the next, in the clinic's zone, for a timestamptz column."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    z = clock.zone()
    start = datetime.combine(day, datetime.min.time(), tzinfo=z)
    return start, datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=z)


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def int_setting(db, key, default):
    """Never raises. Settings can arrive unvalidated (a restored backup, a
    hand edit), so a stored non-numeric value must degrade to the default
    rather than take down every page that reads it. See ERROR_500_AUDIT.md
    E-13."""
    try:
        return int(get_setting(db, key, default))
    except (TypeError, ValueError):
        return int(default)


# ---------------------------------------------------------------------------
# Rewards card — membership, the rate, and the term
# (features/REWARDS_CARD_PLAN.md)
# ---------------------------------------------------------------------------
MEMBER_RATE_MAX = 50            # A6 — 0 means the programme is off
MEMBER_TERM_MONTHS_DEFAULT = 12
MEMBER_TERM_MONTHS_MAX = 120
MEMBER_EXPIRING_SOON_DAYS = 30  # when the owner page starts warning


def is_active_member(owner):
    """Does this owner hold a rewards card that is valid TODAY?

    THE one place that answers this. Everything that prices a bill, badges a
    name or shows the Rewards panel goes through here, so "active member"
    cannot come to mean two different things in two places.

    Deliberately a read-time comparison and NOT a nightly job that flips
    is_member: a job that quietly stops running leaves every lapsed card
    still discounting, and nothing would say so. A comparison cannot stop
    running. is_member therefore stays TRUE on a lapsed card, which is also
    what keeps "lapsed" distinguishable from "never joined".

    NULL member_expires_on means the card never expires. The comparison is
    `>=`, so the card works THROUGH its expiry date — an off-by-one here is a
    card that dies a day early, which nobody reports as a bug.

    clock.today() is naive on purpose, matching every other date site in this
    app: it runs on the clinic's own PC, so local time IS clinic time.
    """
    if owner is None:
        return False
    try:
        if not owner["is_member"]:
            return False
        expires = owner["member_expires_on"]
    except (KeyError, IndexError, TypeError):
        # A row selected without the membership columns is not evidence of
        # membership.
        return False
    if not expires:
        return True
    expires = as_date(expires)
    if not expires:
        return True
    return expires >= clock.today()


def member_discount_rate(db):
    """The clinic's rewards-card percentage. 0 means the programme is off.

    Read through here by all four bill-creation sites so they cannot parse
    the setting four different ways.

    Returns DECIMAL, because this is JO — IQ's copy returns float
    (COMPARISON.md §1.1). Mixing the two raises TypeError here rather than
    silently losing fils, which is the property that makes JO's money code
    safe to change; do not "simplify" this to float.

    A stored value outside the allowed range degrades to 0 (programme off)
    rather than raising: settings can arrive from a restored backup or a
    hand edit, so this fails closed the same way int_setting() does.
    """
    raw = get_setting(db, "member_discount_percent", "0") or "0"
    try:
        rate = Decimal(str(raw))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)
    if not Decimal(0) <= rate <= Decimal(MEMBER_RATE_MAX):
        return Decimal(0)
    return rate


def member_term_months(db):
    """How long a newly issued card lasts, in whole months."""
    n = int_setting(db, "member_term_months", MEMBER_TERM_MONTHS_DEFAULT)
    return n if 1 <= n <= MEMBER_TERM_MONTHS_MAX else MEMBER_TERM_MONTHS_DEFAULT


def add_months(d, months):
    """Calendar-month arithmetic, clamping the day to the target month.

    31 January + 1 month is 28 (or 29) February, not an invalid date — which
    is what d.replace(month=...) alone would raise on.
    """
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def member_default_expiry(db, start=None):
    """What the enroll form pre-fills: today + the clinic's term."""
    return add_months(start or clock.today(), member_term_months(db))


def member_expires_in_days(owner):
    """Days until this card lapses, or None if it never does / is not a
    member. Negative once it has lapsed, so a caller can tell the two apart."""
    if owner is None:
        return None
    try:
        if not owner["is_member"]:
            return None
        expires = as_date(owner["member_expires_on"])
    except (KeyError, IndexError, TypeError):
        return None
    if not expires:
        return None
    return (expires - clock.today()).days


def owner_for_patient(db, patient_id):
    """The owner a patient belongs to — how visits, inpatient and boarding
    find the customer whose card applies."""
    return db.execute(
        "SELECT o.* FROM owners o JOIN patients p ON p.owner_id = o.id WHERE p.id=?",
        (patient_id,)).fetchone()


def member_discount_for(db, owner):
    """(discount_percent, discount_source) for a bill being created for this
    owner. ('staff' defaults when there is no active card, or the programme
    is switched off with a rate of 0.)

    THE one place the card is turned into a discount, called by all four
    bill-creation sites so they cannot disagree about what "a member" means
    or read the rate four different ways.

    Note what does NOT happen here: the rate is never checked against
    auth.discount_cap_for(). That cap exists to bound STAFF discretion, and
    this is clinic policy rather than a staff decision — routing it through
    the cap would stop a receptionist whose cap is below the member rate from
    creating a member's bill at all. See features/REWARDS_CARD_PLAN.md §6.
    """
    if not is_active_member(owner):
        return Decimal(0), "staff"
    rate = member_discount_rate(db)
    if rate <= 0:
        return Decimal(0), "staff"
    return rate, "member"


_MAX_ID = 2_147_483_647  # an INTEGER column's ceiling
_ID_RE = re.compile(r"^\s*(?:([A-Za-z]{1,4})\s*-?\s*)?0*(\d{1,10})\s*$")


def parse_id(raw, prefix=None):
    """A record ID from a form field or query string -> int, or None.

    Accepts the number itself ("123", "00123") and, when `prefix` is given,
    the display code staff read and type ("V-00123", "v123"; logic.code()).
    Anything else is None — never an exception and never a value that
    reaches an INTEGER column as text, where Postgres would refuse it with a
    500. A code with the WRONG prefix (a patient code typed into a visit
    field) is None too, so it cannot silently name a different record."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if 0 < raw <= _MAX_ID else None
    m = _ID_RE.match(str(raw))
    if not m:
        return None
    if m.group(1) and (prefix is None or m.group(1).upper() != prefix.upper()):
        return None
    val = int(m.group(2))
    return val if 0 < val <= _MAX_ID else None


# The code staff read and type for a record: its numeric id with a prefix
# (V-00123). One definition, used by the |code filter, messages and PDFs;
# core.parse_id() reads it back. Western digits always — a code is an
# identifier, not a quantity (ARABIC_LOCALIZATION_PLAN.md §7.1).
CODE_PREFIX = {"owners": "OW", "patients": "PT", "visits": "V", "inventory_list": "INV",
               "price_list": "PL", "distributors": "D", "distributor_bills": "DB"}


def code(prefix, record_id):
    """code("V", 123) -> "V-00123"; blank for no id."""
    if record_id is None or record_id == "":
        return ""
    return f"{prefix}-{int(record_id):05d}"


def format_quantity(v):
    """A count, measurement or percentage on its way into display text:
    Decimal("12.000") -> "12", Decimal("2.500") -> "2.5", 10 -> "10".

    Every such column is NUMERIC, so a whole number arrives with the column's
    decimal tail ("× 1.000" on a receipt, "4.500 kg"). f"{x:g}" does NOT fix
    that for a Decimal — it keeps the zeros. Never scientific notation.

    Digits only; Arabic-Indic conversion stays with core.display_number() and
    the |qty filter, the boundaries that decide that. Not for a value that
    will be put back into an <input> in Arabic — that one stays Western.
    """
    if v is None or v == "":
        return ""
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    if not d.is_finite():
        return str(d)
    d = d.normalize()
    return "0" if d == 0 else format(d, "f")


_ARABIC_INDIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_arabic_indic_digits(s):
    """Substitute Eastern Arabic-Indic digits into an ALREADY-FORMATTED string.

    Display only, and the boundary is not decoration -- see
    ARABIC_LOCALIZATION_PLAN.md §7.1:

      - never on a value that will be parsed back (parse_money, a submitted
        form value). Every calculation happens in Western digits and this runs
        at the very last step, on its way into a template.
      - never on an editable <input>'s value. A number input's underlying
        value is a Western-digit string in every browser regardless of locale,
        so converting what is displayed risks a mismatch with what the
        keyboard types and what gets submitted.
      - never on an ID or reference code (V0001, INV301). Those are
        identifiers, matched elsewhere as literal strings, not quantities.
      - never inside pdf_export.py. PDFs stay English with Western digits,
        permanently (§0). If this helper is ever tempting to call from that
        module, something has been wired wrong.
    """
    if s is None:
        return s
    return str(s).translate(_ARABIC_INDIC_DIGITS)


def _display_qty(v):
    """format_quantity() for a message: Arabic-Indic digits under Arabic."""
    text = format_quantity(v)
    try:
        from flask_babel import get_locale
        if str(get_locale()) == "ar":
            return to_arabic_indic_digits(text)
    except RuntimeError:
        pass
    return text


def format_percent(v):
    """A percentage on its way into display text: 10.00 -> "10", 12.5 -> "12.5"
    (a clinic may legitimately set 12.5%)."""
    return format_quantity(v)


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
    started = as_date(last_backup_row["started_at"])
    if started and (clock.today() - started).days >= 2:
        return _alert(N_("The database hasn't been backed up in 2+ days — check "
                         "the Settings page."))
    return None


def fmt_money(amount):
    """Display form of an amount under the clinic's money setting — whole
    dinars under IQ, three decimals under JO. See money.fmt()."""
    return money.fmt(amount)


# ---------------------------------------------------------------------------
# Audit sessions (Save / Confirm) — only Confirmed sessions count as history
# ---------------------------------------------------------------------------
def get_or_create_draft_session(db, audit_date, user_id):
    """The day's draft audit, created if there is none.

    One per day, held by the audit_sessions_one_draft_per_day index (audit
    B20): this used to look first and insert second, so two people pressing
    Start at once each created one. The insert now yields to a draft that
    exists or is being created, and waits for it rather than duplicating it.
    Does not commit -- the caller does, with the rest of its request (D11)."""
    row = db.execute(
        "INSERT INTO audit_sessions (audit_date, performed_by, status, created_at) VALUES (?,?,'Draft',?) "
        "ON CONFLICT (audit_date) WHERE status = 'Draft' DO NOTHING RETURNING id",
        (audit_date, user_id, clock.now()),
    ).fetchone()
    if row:
        authmod.log_change(db, "audit_sessions", str(row["id"]), "create")
        return row["id"]
    return db.execute("SELECT id FROM audit_sessions WHERE audit_date=? AND status='Draft'",
                      (audit_date,)).fetchone()["id"]


def list_audit_sessions(db, limit, offset=0):
    """One page of audit sessions, newest first: (rows, total_count). It
    used to return a tuple or a plain list depending on whether `limit` was
    given (audit §4); its one caller always pages."""
    q = (
        "SELECT s.*, u.full_name as performed_by_name, "
        "(SELECT COUNT(*) FROM audit_session_lines l WHERE l.session_id=s.id AND l.stock_counted IS NOT NULL) as lines_filled "
        "FROM audit_sessions s LEFT JOIN users u ON u.id=s.performed_by ORDER BY s.audit_date DESC, s.id DESC"
    )
    total = db.execute("SELECT COUNT(*) c FROM audit_sessions").fetchone()["c"]
    rows = db.execute(q + " LIMIT ? OFFSET ?", [limit, offset]).fetchall()
    return rows, total


def consignment_received_since_audit(db, latest_confirmed):
    """{item_id: quantity} received through Consignment Receiving since each
    item's latest confirmed audit -- the audit sheet's default for "received
    since prior" (audit B18).

    Usage is computed as prior count + received since prior - count, and
    "received since prior" is typed by hand. Stock that came in through
    Consignment Receiving was already in inventory_transactions but never
    offered there, so unless staff typed it a second time the item's usage
    came out understated or negative, and so did the Ordering Sheet's
    suggestion. `latest_confirmed` is {item_id: that item's latest confirmed
    audit row}; the cutoff is the one inventory_status() uses."""
    cutoffs = {item_id: r["confirmed_at"] or day_bounds(as_date(r["audit_date"]))[0]
               for item_id, r in latest_confirmed.items()}
    if not cutoffs:
        return {}
    out = defaultdict(Decimal)
    for t in db.execute("SELECT item_id, change_qty, timestamp FROM inventory_transactions "
                        "WHERE reason = 'consignment_receipt' AND timestamp > ?", (min(cutoffs.values()),)).fetchall():
        cutoff = cutoffs.get(t["item_id"])
        if cutoff is not None and t["timestamp"] > clock.aware(cutoff):
            out[t["item_id"]] += t["change_qty"]
    return {k: v for k, v in out.items() if v}


def confirmed_audit_rows_by_item(db, item_id=None):
    """
    Flattened, chronological, per-item rows from CONFIRMED sessions only — the
    equivalent of the old audit_history table — annotated with prior-audit usage,
    daily rate, and carried-forward threshold/critical/target values.
    """
    q = """
    SELECT l.*, s.audit_date as audit_date, s.confirmed_at as confirmed_at
    FROM audit_session_lines l JOIN audit_sessions s ON s.id = l.session_id
    WHERE s.status='Confirmed' AND l.stock_counted IS NOT NULL
    """
    params = []
    if item_id:
        q += " AND l.item_id=?"
        params.append(item_id)
    # confirmed_at (a full timestamp) orders same-day confirmations
    # correctly; audit_date alone (date-only) can't tell two same-day
    # audits apart. See inventory_status()'s use of confirmed_at as the
    # transaction cutoff for why this distinction matters.
    q += " ORDER BY l.item_id, COALESCE(s.confirmed_at, s.audit_date::timestamptz), l.id"
    rows = [dict(r) for r in db.execute(q, params).fetchall()]

    by_item = defaultdict(list)
    for r in rows:
        by_item[r["item_id"]].append(r)

    out = []
    for iid, item_rows in by_item.items():
        eff_threshold = eff_critical = eff_target = None
        prior = None
        for r in item_rows:
            if r["reorder_threshold"] is not None:
                eff_threshold = r["reorder_threshold"]
            if r["critical_item"] is not None:
                eff_critical = r["critical_item"]
            if r["target_coverage_days"] is not None:
                eff_target = r["target_coverage_days"]
            r["effective_reorder_threshold"] = eff_threshold
            r["effective_critical_item"] = eff_critical
            r["effective_target_coverage_days"] = eff_target if eff_target is not None else 30

            if prior is not None:
                r["prior_audit_date"] = prior["audit_date"]
                r["prior_stock"] = prior["stock_counted"]
                usage = prior["stock_counted"] + r["received_since_prior"] - r["stock_counted"]
                r["usage_since_prior"] = usage
                days = (as_date(r["audit_date"]) - as_date(prior["audit_date"])).days
                r["days_since_prior"] = days
                r["daily_usage_rate"] = round(usage / days, 4) if days > 0 else None
            else:
                r["prior_audit_date"] = r["prior_stock"] = r["usage_since_prior"] = None
                r["days_since_prior"] = r["daily_usage_rate"] = None

            out.append(r)
            prior = r

    out.sort(key=lambda r: (r["audit_date"], r["id"]))
    return out


def _txn_qty_since_batch(db, cutoffs):
    """For every item at once — cutoffs is {item_id: cutoff_timestamp},
    each item compared against its *own* cutoff (they're not all the
    same, since each item's latest confirmed audit happened at a
    different time) in a single query instead of one round-trip per
    item. Returns {item_id: net_change_since_cutoff}, omitting items
    with no net change."""
    if not cutoffs:
        return {}
    items = list(cutoffs.items())
    values_sql = ",".join("(?,?)" for _ in items)
    params = [v for pair in items for v in pair]
    rows = db.execute(
        f"SELECT t.item_id, COALESCE(SUM(t.change_qty), 0) AS net FROM inventory_transactions t "
        f"JOIN (VALUES {values_sql}) AS cutoffs(item_id, cutoff) ON cutoffs.item_id = t.item_id "
        f"WHERE t.timestamp > cutoffs.cutoff GROUP BY t.item_id",
        params,
    ).fetchall()
    return {r["item_id"]: r["net"] or 0 for r in rows}


# ---------------------------------------------------------------------------
# Inventory Status
# ---------------------------------------------------------------------------
def inventory_status(db):
    audit_overdue_days = int_setting(db, "audit_overdue_days", 35)
    expiry_soon_days = int_setting(db, "expiry_soon_days", 60)
    today = clock.today()

    items = [dict(r) for r in db.execute("SELECT * FROM inventory_list WHERE active=true ORDER BY name").fetchall()]
    all_confirmed = confirmed_audit_rows_by_item(db)
    by_item = defaultdict(list)
    for r in all_confirmed:
        by_item[r["item_id"]].append(r)

    # Cutoff is confirmed_at (a full timestamp), never audit_date alone
    # (date-only) — a same-day sale/refund/shrinkage that happened
    # *before* the physical count was taken (completely normal: the
    # clinic sells all morning, then does the shelf walk in the
    # afternoon) would otherwise still be "after" a date-only cutoff and
    # get double-counted on top of a stock_counted figure that already
    # reflects it. Falls back to audit_date only for a pre-existing
    # confirmed session that somehow has no confirmed_at.
    cutoffs = {}
    for it in items:
        rows = by_item.get(it["id"], [])
        if rows:
            latest = rows[-1]
            cutoffs[it["id"]] = latest["confirmed_at"] or day_bounds(as_date(latest["audit_date"]))[0]
    txn_since = _txn_qty_since_batch(db, cutoffs)

    status = []
    for it in items:
        rows = by_item.get(it["id"], [])
        latest = rows[-1] if rows else None

        base_stock = latest["stock_counted"] if latest else None
        latest_audit_date = as_date(latest["audit_date"]) if latest else None
        nearest_expiry = as_date(latest["nearest_expiry_date"]) if latest else None
        daily_usage_rate = latest["daily_usage_rate"] if latest else None
        reorder_threshold = latest["effective_reorder_threshold"] if latest else None
        critical_item = bool(latest["effective_critical_item"]) if latest else False
        target_coverage_days = latest["effective_target_coverage_days"] if latest else 30

        current_stock = base_stock
        if base_stock is not None:
            current_stock = round(base_stock + txn_since.get(it["id"], 0), 3)

        days_since_audit = (today - latest_audit_date).days if latest_audit_date else None
        days_to_expiry = (nearest_expiry - today).days if nearest_expiry else None

        if latest is None:
            stock_status = "No audits yet"
        elif reorder_threshold is not None and current_stock is not None and current_stock <= reorder_threshold:
            stock_status = "LOW STOCK"
        else:
            stock_status = "OK"

        if not it["track_expiry"] or nearest_expiry is None:
            expiry_status = None
        elif days_to_expiry < 0:
            expiry_status = "EXPIRED"
        elif days_to_expiry <= expiry_soon_days:
            expiry_status = "EXPIRING SOON"
        else:
            expiry_status = "OK"

        if latest is None:
            audit_status = "Never audited"
        elif days_since_audit > audit_overdue_days:
            audit_status = "OVERDUE"
        else:
            audit_status = "OK"

        status.append({
            "item_id": it["id"], "name": it["name"], "unit": it["unit"], "category": it["category"],
            "barcode": it["barcode"], "reorder_threshold": reorder_threshold,
            "track_expiry": bool(it["track_expiry"]), "latest_audit_date": fmt_date(latest_audit_date),
            "current_stock": current_stock, "nearest_expiry_date": fmt_date(nearest_expiry),
            "daily_usage_rate": daily_usage_rate, "days_since_audit": days_since_audit,
            "days_to_expiry": days_to_expiry, "stock_status": stock_status, "expiry_status": expiry_status,
            "audit_status": audit_status, "critical_item": critical_item,
            "target_coverage_days": target_coverage_days, "distributor_id": it["distributor_id"],
            "ownership_type": it["ownership_type"],
        })
    return status


def inventory_status_by_id(db, item_id):
    for r in inventory_status(db):
        if r["item_id"] == item_id:
            return r
    return None


# ---------------------------------------------------------------------------
# Ordering Sheet
# ---------------------------------------------------------------------------
def ordering_sheet(db):
    inv_status = inventory_status(db)
    all_confirmed = confirmed_audit_rows_by_item(db)
    by_item = defaultdict(list)
    for r in all_confirmed:
        by_item[r["item_id"]].append(r)

    dists = {d["id"]: dict(d) for d in db.execute("SELECT * FROM distributors").fetchall()}

    rows = []
    for s in inv_status:
        stock, rate = s["current_stock"], s["daily_usage_rate"]
        days_left = (stock / rate) if (stock is not None and rate and rate > 0) else None
        urgency = -1 if s["critical_item"] else (days_left if days_left is not None else 9999)

        if s["critical_item"]:
            priority = "CRITICAL"
        elif days_left is None:
            priority = "No data"
        elif days_left <= 7:
            priority = "URGENT"
        elif days_left <= 21:
            priority = "SOON"
        else:
            priority = "OK"

        target = s["target_coverage_days"] or 30
        suggested_qty = None
        if rate and rate > 0 and stock is not None:
            # math.ceil, not -(-x // 1): on a Decimal `//` truncates toward
            # zero, so that idiom rounds a positive shortfall DOWN.
            suggested_qty = max(0, math.ceil((target * rate) - stock))

        item_rows = by_item.get(s["item_id"], [])
        trend, trend_note = "Not enough data", "Not enough audit history yet (need 2+ confirmed audits)"
        if len(item_rows) >= 2:
            prior_rate = item_rows[-2]["daily_usage_rate"]
            if rate is not None and prior_rate is not None:
                if rate > prior_rate * Decimal("1.15"):
                    trend, trend_note = "Increasing", "Usage rising - consider more coverage days"
                elif rate < prior_rate * Decimal("0.85"):
                    trend, trend_note = "Decreasing", "Usage falling - consider fewer coverage days"
                else:
                    trend, trend_note = "Steady", "Usage steady - keep current target"

        dist = dists.get(s["distributor_id"]) if s["distributor_id"] else None
        rows.append({
            **s, "days_of_stock_left": round(days_left, 1) if days_left is not None else None,
            "urgency_score": urgency, "priority": priority, "suggested_order_qty": suggested_qty,
            "usage_trend": trend, "trend_recommendation": trend_note,
            "distributor_name": dist["name"] if dist else None,
            "lead_time_days": dist["lead_time_days"] if dist else None,
            "catalog_link": dist["catalog_link"] if dist else None,
        })

    rows.sort(key=lambda r: (r["urgency_score"] if r["urgency_score"] is not None else 9999))
    for i, r in enumerate(rows, start=1):
        r["priority_rank"] = i
    return rows


# ---------------------------------------------------------------------------
# Billing (Automatic line-items OR Manual lump sum) + discount + payment status
# ---------------------------------------------------------------------------
def retail_consistency_flags(db):
    """
    Cross-checks the Retail category between Inventory Catalog and Price
    List. Returns (flagged_price_ids, flagged_inventory_ids):
      - a Price List Retail row is flagged if its linked item doesn't exist
        or isn't an active Retail inventory item
      - an active Retail inventory item is flagged if no active Price List
        Retail row links to it
    """
    price_rows = db.execute(
        "SELECT id, linked_item_id FROM price_list WHERE active=true AND category='Retail'"
    ).fetchall()
    inv_ids = {r["id"] for r in db.execute(
        "SELECT id FROM inventory_list WHERE active=true AND category='Retail'"
    ).fetchall()}

    flagged_price = {r["id"] for r in price_rows if not r["linked_item_id"] or r["linked_item_id"] not in inv_ids}
    linked_ids = {r["linked_item_id"] for r in price_rows if r["linked_item_id"]}
    flagged_inventory = inv_ids - linked_ids

    return flagged_price, flagged_inventory


def non_discountable_line_names(db, price_ids):
    """Given a set/list of price_list IDs on a bill, returns the display
    names of any that are marked as not discountable (can_discount=false)."""
    if not price_ids:
        return []
    ids = [i for i in price_ids if i]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT name FROM price_list WHERE id IN ({placeholders}) AND can_discount=false",
        tuple(ids),
    ).fetchall()
    return [r["name"] for r in rows]


def non_discountable_line_names_for_items(db, inventory_item_ids):
    """Same as non_discountable_line_names(), but for POS carts, which
    reference inventory_list IDs rather than price_list IDs directly —
    looks up each item's linked Retail price_list entry."""
    ids = [i for i in inventory_item_ids if i]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT name FROM price_list WHERE linked_item_id IN ({placeholders}) AND can_discount=false",
        tuple(ids),
    ).fetchall()
    return [r["name"] for r in rows]


def discountable_by_item_ids(db, inventory_item_ids):
    """Discount eligibility per POS cart item, as {inventory_item_id: bool}.

    Same linked_item_id join as non_discountable_line_names_for_items(), but
    it returns the flag for every id rather than the names of the ineligible
    ones -- POS needs the value itself, both to price the cart per line and
    to snapshot it onto each sale_items row.

    Filters active=true to match item_sale_price(), deliberately: eligibility
    must come from the same price_list row the PRICE came from, or a stale
    inactive row could discount a line priced from a different one.
    non_discountable_line_names_for_items() does not filter active; it feeds
    the staff-discount guard and is left as-is rather than changed underneath
    that guard. An id with no active linked row is simply absent -- callers
    treat missing as not discountable.
    """
    ids = [i for i in inventory_item_ids if i]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT linked_item_id, can_discount FROM price_list "
        f"WHERE linked_item_id IN ({placeholders}) AND active=true",
        tuple(ids),
    ).fetchall()
    return {r["linked_item_id"]: bool(r["can_discount"]) for r in rows}


def save_visit_billing_lines(db, visit_id, lines):
    """
    Replaces every visit_billing_lines row for this visit with a fresh
    snapshot of what's in the cart at Save time \u2014 price_id/name/category/
    quantity/unit_price/unit_cost per line, from the search-and-add
    billing UI (visit_billing_save() in app.py builds this list). Does
    not commit (caller's job, same convention as every other write in
    this module).
    """
    db.execute("DELETE FROM visit_billing_lines WHERE visit_id=?", (visit_id,))
    now_str = clock.now().isoformat(timespec="seconds")
    for l in lines:
        db.execute(
            "INSERT INTO visit_billing_lines (visit_id, price_id, name, category, quantity, unit_price, unit_cost, discountable, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (visit_id, l["price_id"], l["name"], l["category"], l["quantity"],
             l["unit_price"], l["unit_cost"], l["discountable"], now_str),
        )


def discounted_raw_total(subtotal, discountable_subtotal, discount_percent):
    """The bill before rounding: the discount comes off the eligible part of
    the subtotal only, and the rest is charged in full.

    Lives in one function that BOTH compute_bill_totals() and pos_checkout()
    call, rather than being written out at each — one rule spelled out in two
    places is exactly the shape every entry in SEAM_RULES.md came from. The
    arithmetic itself is money.discounted().

    On a staff discount `discountable_subtotal == subtotal` always (the
    guards refuse a staff discount on a bill holding a non-discountable
    line), so this returns exactly `subtotal * (1 - d)`.
    """
    return money.discounted(subtotal or 0, discountable_subtotal or 0, discount_percent or 0)


def compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0, *,
                        discountable_subtotal):
    """
    Shared by visit_billing_summary() and inpatient_billing_summary() so the
    money math (total/balance/status) is defined in exactly one place instead
    of being duplicated per billing type.

    `discountable_subtotal` is the part of `subtotal` the discount may
    actually come off; the remainder is charged in full. It is KEYWORD-ONLY,
    REQUIRED and has NO DEFAULT, deliberately: a default of `subtotal` would
    let any caller that forgot it silently treat a non-discountable item as
    discountable, and a silently wrong total is the one failure this feature
    cannot afford. Forgetting it is a TypeError instead. See
    features/REWARDS_CARD_PLAN.md §2.2 and seam rule 6.

    The payable total is the discounted figure rounded to the money
    setting's cash unit by money.payable() — to the nearest 250-dinar note
    under IQ, never rounding a real bill down to free; unchanged under JO.
    Applied ONCE, to the whole total, never per line: rounding each line
    separately would drift the bill away from its own subtotal.

    cleanup_amount is a capped, explicit staff write-off (see
    CLEANUP_FEATURE_PLAN.md) applied AFTER that rounding, on top of whatever
    it produced — not a replacement for it.

    Returns (total, paid, balance, status, pre_cleanup_total). That last one
    is the payable total BEFORE Clean Up comes off: receipts print it instead
    of re-deriving `subtotal * (1 - d)`, which does not match on a bill
    holding non-discountable lines — returning it from here is what keeps
    `subtotal - discount - Clean Up = total` true on every export.
    """
    discount_percent = discount_percent or 0
    pre_cleanup_total = money.payable(
        discounted_raw_total(subtotal, discountable_subtotal, discount_percent), discount_percent)
    total = money.to_store(max(pre_cleanup_total - (cleanup_amount or 0), 0))
    paid = money.to_store(paid or 0)
    # What is still owed, at the cash unit: a remainder smaller than half a
    # 250-dinar note is not collectable under IQ and reads as settled. There
    # is deliberately no tolerance constant in the status test below — the
    # predecessor apps carried `<= 0.5` (noise in IQD, real money in JOD).
    balance = money.balance_due(total, paid)
    if total <= 0:
        status = "N/A"
    elif paid <= 0:
        status = "Unpaid"
    elif money.is_settled(balance):
        status = "Fully Paid"
    else:
        status = "Partially Paid"
    return total, paid, balance, status, pre_cleanup_total


def visit_billing_summary(db, visit_id):
    b = db.execute("SELECT * FROM billing WHERE visit_id=?", (visit_id,)).fetchone()
    if not b:
        return {"billing_type": "Automatic", "lines": [], "subtotal": 0, "discount_percent": 0,
                "discount_source": "staff", "discountable_subtotal": 0, "pre_cleanup_total": 0,
                "cleanup_amount": 0, "total": 0, "paid": 0, "balance": 0, "status": "N/A"}

    if b["billing_type"] == "Manual":
        lines = [{"id": None, "name": "Veterinary Services", "category": "Service",
                  "price": b["manual_amount"] or 0, "discountable": True}] if b["manual_amount"] else []
        subtotal = b["manual_amount"] or 0
        # A Manual bill is one typed figure with no item lines to check, and
        # staff discounts already applied to the whole of it — so the card
        # does too. features/REWARDS_CARD_PLAN.md A4.
        discountable_subtotal = subtotal
    else:
        snapshot_rows = db.execute(
            "SELECT price_id, name, category, quantity, unit_price, discountable FROM visit_billing_lines WHERE visit_id=? ORDER BY id",
            (visit_id,),
        ).fetchall()
        # Priced from the snapshot taken when this bill was saved (via the
        # search-and-add billing UI) — doesn't change if someone edits the
        # Price List afterward. Mirrors inpatient_billing_summary()'s shape
        # exactly (quantity + line_total per line).
        lines = [{"id": r["price_id"], "name": r["name"], "category": r["category"],
                  "price": r["unit_price"], "quantity": r["quantity"],
                  "line_total": money.to_store(r["unit_price"] * r["quantity"]),
                  "discountable": bool(r["discountable"])}
                 for r in snapshot_rows]
        subtotal = sum(l["line_total"] for l in lines)
        discountable_subtotal = sum(l["line_total"] for l in lines if l["discountable"])

    discount_percent = b["discount_percent"] or 0
    cleanup_amount = b["cleanup_amount"] or 0
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE visit_id=?", (visit_id,)).fetchone()
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid_row["s"], cleanup_amount,
        discountable_subtotal=discountable_subtotal)
    return {"billing_type": b["billing_type"], "lines": lines, "subtotal": money.to_store(subtotal),
            "discount_percent": discount_percent, "cleanup_amount": cleanup_amount,
            "discount_source": b["discount_source"], "pre_cleanup_total": pre_cleanup_total,
            "discountable_subtotal": money.to_store(discountable_subtotal),
            "total": total, "paid": paid, "balance": balance, "status": status}


def refresh_visit_billing_total(db, visit_id):
    """Recomputes and persists billing.total after any change to this
    bill's lines, discount, or manual amount. Call this in the same
    transaction right after such a change, before commit — so reports
    can read the stored total instead of re-deriving it independently."""
    total = visit_billing_summary(db, visit_id)["total"]
    db.execute("UPDATE billing SET total=? WHERE visit_id=?", (total, visit_id))


# ---------------------------------------------------------------------------
# Inpatient billing (procedures only — never touches stock)
# ---------------------------------------------------------------------------
def inpatient_billing_summary(db, case_id):
    rows = db.execute(
        "SELECT ib.*, p.name, p.sale_price, p.category FROM inpatient_billing ib "
        "JOIN price_list p ON p.id = ib.price_id WHERE ib.case_id=? ORDER BY ib.timestamp",
        (case_id,),
    ).fetchall()
    lines, subtotal, discountable_subtotal = [], 0, 0
    for r in rows:
        # Prefer the snapshot taken when this line was added (unit_price)
        # — falls back to the live Price List join (p.sale_price) only if
        # that specific line's snapshot is NULL (e.g. added before this
        # column existed, or the price_list item had no sale_price set at
        # the moment it was billed).
        unit_price = r["unit_price"] if r["unit_price"] is not None else (r["sale_price"] or 0)
        line_total = unit_price * r["quantity"]
        subtotal += line_total
        if r["discountable"]:
            discountable_subtotal += line_total
        lines.append({"id": r["id"], "name": r["name"], "quantity": r["quantity"],
                       "unit_price": unit_price, "line_total": money.to_store(line_total),
                       "discountable": bool(r["discountable"])})
    case = db.execute("SELECT discount_percent, discount_source, cleanup_amount FROM inpatient_cases WHERE id=?", (case_id,)).fetchone()
    discount_percent = case["discount_percent"] if case else 0
    cleanup_amount = (case["cleanup_amount"] if case else 0) or 0
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE inpatient_case_id=?", (case_id,)).fetchone()
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid_row["s"], cleanup_amount,
        discountable_subtotal=discountable_subtotal)
    return {"lines": lines, "subtotal": money.to_store(subtotal), "discount_percent": discount_percent,
            "discount_source": case["discount_source"] if case else "staff",
            "discountable_subtotal": money.to_store(discountable_subtotal),
            "pre_cleanup_total": pre_cleanup_total,
            "cleanup_amount": cleanup_amount, "total": total, "paid": paid, "balance": balance, "status": status}


def refresh_inpatient_total(db, case_id):
    """Recomputes and persists inpatient_cases.total after any change to
    this case's procedures or discount. Call this in the same transaction
    right after such a change, before commit — see
    refresh_visit_billing_total()."""
    total = inpatient_billing_summary(db, case_id)["total"]
    db.execute("UPDATE inpatient_cases SET total=? WHERE id=?", (total, case_id))


# ---------------------------------------------------------------------------
# Boarding
# ---------------------------------------------------------------------------
def boarding_nights(entry_date, dismissal_date):
    """Nights stayed so far (or planned), at least 1."""
    start = as_date(entry_date)
    end = as_date(dismissal_date) if dismissal_date else clock.today()
    if not start:
        return 1
    return max(1, (end - start).days)


def boarding_suggested_total(price_per_day, entry_date, dismissal_date):
    if not price_per_day:
        return None
    return money.to_store(price_per_day * boarding_nights(entry_date, dismissal_date))


def boarding_billing_summary_from_fields(b, paid):
    """Same computation as boarding_billing_summary(), factored out so a
    caller that already has the boarding_sessions row in hand (e.g. a list
    page rendering many rows at once) can skip re-fetching it and the
    per-row payments query — see boarding_page() in app.py, which batches
    `paid` across the whole page in one query instead of one per row.
    `b` needs total, total_is_auto, price_per_day, entry_date,
    dismissal_date, dismissed, cleanup_amount, discount_percent,
    discount_source."""
    if not b:
        subtotal = 0
    elif b["total_is_auto"] and not b["dismissed"] and b["price_per_day"]:
        # Still an active stay, and `total` has never been overridden with
        # a deliberately-typed figure — the stored value is only ever the
        # suggestion computed once, back when the stay was created/last
        # edited (usually 1 night, since dismissal_date is normally still
        # unknown then). Recompute live from price_per_day x nights-so-far
        # so the bill never sits frozen at a stale night count while the
        # animal is still boarding. Once dismissed, boarding_dismiss()
        # locks in the final figure and this branch no longer applies.
        subtotal = boarding_suggested_total(b["price_per_day"], b["entry_date"], b["dismissal_date"]) or 0
    else:
        subtotal = b["total"] or 0
    cleanup_amount = (b["cleanup_amount"] if b else 0) or 0
    discount_percent = (b["discount_percent"] if b else 0) or 0
    # A stay is one amount with no item lines to check, and staff discounts
    # already applied to the whole of it — so the card does too. A4.
    total, paid, balance, status, pre_cleanup_total = compute_bill_totals(
        subtotal, discount_percent, paid, cleanup_amount,
        discountable_subtotal=subtotal)
    return {"total": total, "paid": paid, "balance": balance, "status": status,
            "cleanup_amount": cleanup_amount, "discount_percent": discount_percent,
            "discount_source": (b["discount_source"] if b else "staff") or "staff",
            "discountable_subtotal": subtotal, "pre_cleanup_total": pre_cleanup_total,
            "subtotal": subtotal}


def boarding_billing_summary(db, boarding_id):
    b = db.execute(
        "SELECT total, total_is_auto, price_per_day, entry_date, dismissal_date, dismissed, cleanup_amount, "
        "discount_percent, discount_source "
        "FROM boarding_sessions WHERE id=?", (boarding_id,)
    ).fetchone()
    paid_row = db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE boarding_id=?", (boarding_id,)).fetchone()
    return boarding_billing_summary_from_fields(b, paid_row["s"])


def refresh_boarding_total(db, boarding_id):
    """Recomputes and persists boarding_sessions.billed_total — the figure
    boarding_page()'s batched list view and any report read instead of
    recomputing per row. Call this in the same transaction right after the
    session is saved, before commit. See refresh_visit_billing_total()."""
    total = boarding_billing_summary(db, boarding_id)["total"]
    db.execute("UPDATE boarding_sessions SET billed_total=? WHERE id=?", (total, boarding_id))


def boarding_sessions_for_patient(db, patient_id):
    return db.execute(
        "SELECT * FROM boarding_sessions WHERE patient_id=? ORDER BY entry_date DESC", (patient_id,)
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
        reminder_call_date = fmt_date(as_date(r["followup_date"]) - timedelta(days=1))
    r["reminder_call_date"] = reminder_call_date
    r["missed"] = False
    if r["followup_status"] == "Pending" and r["followup_date"]:
        fdate = as_date(r["followup_date"])
        if fdate and (today - fdate).days >= MISSED_WINDOW_DAYS:
            r["missed"] = True
    return r


def followups(db, only_pending=False):
    q = """
    SELECT v.id as visit_id, v.followup_method, v.followup_reason, v.followup_date,
           v.followup_status, v.doctor, v.created_by, v.date as visit_date,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE v.followup_needed = 'Y'
    """
    if only_pending:
        q += " AND v.followup_status = 'Pending'"
    rows = [dict(r) for r in db.execute(q).fetchall()]
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
    dashboard's missed-items summary (logic.missed_items()), which needs
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
    LIMIT ? OFFSET ?
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
    next_dose = as_date(r["wellness_next_dose_date"])
    remind_from = next_dose - timedelta(days=WELLNESS_LEAD_DAYS) if next_dose else None
    missed = bool(next_dose and (today - next_dose).days >= MISSED_WINDOW_DAYS and r["wellness_contacted"] != "Y")
    # "Due" ends where "missed" begins (audit B19). It used to last forever,
    # so every uncontacted reminder since the clinic opened stayed in the
    # Dashboard's "due" list and the sidebar badge; a missed one belongs on
    # the Missed Items list, for an admin to review.
    due = bool(remind_from and today >= remind_from and r["wellness_contacted"] != "Y" and not missed)
    r["remind_from_date"] = fmt_date(remind_from)
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
    dose = as_date(r["wellness_next_dose_date"]) or date.max
    closed = r["wellness_contacted"] == "Y" or (today - dose).days >= MISSED_WINDOW_DAYS
    return (1, -dose.toordinal(), -r["visit_id"]) if closed else (0, dose.toordinal(), r["visit_id"])


def wellness_reminders(db, only_due=False):
    q = """
    SELECT v.id as visit_id, v.wellness_type, v.wellness_next_dose_date, v.wellness_contacted,
           v.wellness_contact_method, v.doctor, v.created_by,
           p.animal_name, o.id as owner_id, o.name as owner_name, o.phone
    FROM visits v JOIN patients p ON p.id = v.patient_id JOIN owners o ON o.id = p.owner_id
    WHERE """ + _WELLNESS_CURRENT
    rows = [dict(r) for r in db.execute(q).fetchall()]
    today = clock.today()
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
    only_due=True caller (logic.dashboard_counts()) wants every matching
    row for its count, not one page, so it keeps calling
    wellness_reminders() directly, unpaginated, exactly as before.
    """
    total = db.execute("SELECT COUNT(*) c FROM visits v WHERE " + _WELLNESS_CURRENT).fetchone()["c"]
    today = clock.today()
    # The same order as _wellness_urgency(), in SQL so it pages correctly:
    # open reminders (not contacted, not past the missed window) by the
    # earliest next dose, then the closed ones newest first.
    missed_before = today - timedelta(days=MISSED_WINDOW_DAYS)
    closed = "(COALESCE(v.wellness_contacted, 'N') = 'Y' OR v.wellness_next_dose_date <= ?)"
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
    LIMIT ? OFFSET ?
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
    is also called unpaginated by logic.dashboard_counts() for its queue
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
    LIMIT ? OFFSET ?
    """
    rows = [dict(r) for r in db.execute(q, [limit, offset]).fetchall()]
    return rows, total


# ---------------------------------------------------------------------------
# Missed items — for the admin dashboard
# ---------------------------------------------------------------------------
def missed_items(db):
    out = []
    for f in followups(db, only_pending=True):
        if f["missed"]:
            out.append({"kind": "Follow-up", "visit_id": f["visit_id"], "animal_name": f["animal_name"],
                        "deadline": f["followup_date"], "responsible": f["doctor"] or f["created_by"]})
    for w in wellness_reminders(db):
        if w["missed"]:
            out.append({"kind": "Wellness", "visit_id": w["visit_id"], "animal_name": w["animal_name"],
                        "deadline": w["wellness_next_dose_date"], "responsible": w["doctor"] or w["created_by"]})

    today = clock.today()
    rows = db.execute(
        "SELECT v.id, v.case_status_changed_at, v.doctor, v.created_by, p.animal_name FROM visits v "
        "JOIN patients p ON p.id=v.patient_id WHERE v.case_status='Lost to Follow Up'"
    ).fetchall()
    for r in rows:
        changed = as_date(r["case_status_changed_at"]) if r["case_status_changed_at"] else None
        if changed and (today - changed).days >= MISSED_WINDOW_DAYS:
            out.append({"kind": "Lost to Follow Up", "visit_id": r["id"], "animal_name": r["animal_name"],
                        "deadline": fmt_date(changed), "responsible": r["doctor"] or r["created_by"]})
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

    fu = followups(db, only_pending=True)
    due_today = [f for f in fu if as_date(f["followup_date"]) == today]
    reminders_tomorrow = [f for f in fu if as_date(f["followup_date"]) == tomorrow and f["followup_method"] == "Physical Visit"]

    wr = wellness_reminders(db, only_due=True)
    grooming = grooming_queue(db)

    inv = inventory_status(db)
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


# ---------------------------------------------------------------------------
# Monthly / Yearly P&L (admin-only; enforced at the route level)
# ---------------------------------------------------------------------------
def monthly_pl(db, months_back=12):
    today = clock.today()
    months = []
    y, m = today.year, today.month
    for i in range(months_back - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append(f"{yy:04d}-{mm:02d}")

    # Computed on read from the stored bill totals (reports.py); there is no
    # summary table to go stale (plan D-3, audit B2/B14).
    summary_rows = reports.by_month(db, since_month=months[0])
    opex_rows = {r["month"]: dict(r) for r in db.execute("SELECT * FROM monthly_opex").fetchall()}

    out = []
    prior_net = None
    for month in months:
        revenue, cogs = summary_rows.get(month, (0, 0))
        gross_profit = money.to_store(revenue - cogs)
        opex = opex_rows.get(month, {"rent": 0, "salaries": 0, "utilities": 0, "marketing": 0, "other": 0})
        total_opex = money.to_store(sum(opex.get(k, 0) or 0 for k in ("rent", "salaries", "utilities", "marketing", "other")))
        net_profit = money.to_store(gross_profit - total_opex)
        net_margin = round(net_profit / revenue, 4) if revenue else None

        mom_change = None
        if prior_net not in (None, 0):
            mom_change = round((net_profit - prior_net) / abs(prior_net) * 100, 1)
        prior_net = net_profit

        out.append({
            "month": month, "revenue": revenue, "cogs": cogs, "gross_profit": gross_profit,
            "rent": opex.get("rent", 0), "salaries": opex.get("salaries", 0), "utilities": opex.get("utilities", 0),
            "marketing": opex.get("marketing", 0), "other": opex.get("other", 0), "total_opex": total_opex,
            "net_profit": net_profit, "net_margin": net_margin, "mom_change": mom_change,
        })
    return out


def yearly_pl(db):
    """
    Every year that has ever had revenue/COGS or opex activity, oldest
    first, from the same per-month figures as the Monthly P&L (reports.py).
    """
    by_year = defaultdict(lambda: {"revenue": 0, "cogs": 0, "total_opex": 0})
    for month, (revenue, cogs) in reports.by_month(db).items():
        y = month[:4]
        by_year[y]["revenue"] += revenue
        by_year[y]["cogs"] += cogs
    for r in db.execute("SELECT * FROM monthly_opex").fetchall():
        y = r["month"][:4]
        by_year[y]["total_opex"] += sum((r[k] or 0) for k in ("rent", "salaries", "utilities", "marketing", "other"))

    out = []
    prior_net = None
    for y in sorted(by_year.keys()):
        d = by_year[y]
        gross_profit = money.to_store(d["revenue"] - d["cogs"])
        net_profit = money.to_store(gross_profit - d["total_opex"])
        net_margin = round(net_profit / d["revenue"], 4) if d["revenue"] else None
        yoy_change = None
        if prior_net not in (None, 0):
            yoy_change = round((net_profit - prior_net) / abs(prior_net) * 100, 1)
        prior_net = net_profit
        out.append({"year": y, "revenue": money.to_store(d["revenue"]), "cogs": money.to_store(d["cogs"]),
                    "gross_profit": gross_profit, "total_opex": money.to_store(d["total_opex"]),
                    "net_profit": net_profit, "net_margin": net_margin, "yoy_change": yoy_change})
    return out


# ---------------------------------------------------------------------------
# Refunds (Admin only)
# ---------------------------------------------------------------------------
def refundable_sale_items(db, sale_id):
    """Returns (sale_row_or_None, [line dicts]) for a POS sale — each line's
    unit_price is what was actually PAID per unit (sale_items.unit_price,
    the pre-discount snapshot taken at checkout, with the sale's
    discount_percent applied) — not today's Price List price. pos_checkout()
    only applies discount_percent once, to the sale's aggregate total, so
    sale_items.unit_price alone overstates what was paid on any discounted
    sale; the same percentage applies uniformly to every line (there's no
    per-line discount) so it's applied the same way here.
    `remaining` = quantity minus whatever's already been refunded against
    that exact sale_items row across every prior refund. This is what
    refund_retail_save() uses both to render the refund pick list and,
    server-side, to enforce a refund can never exceed what was actually
    sold — see refunds.sale_id / refund_items.sale_item_id."""
    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if not sale:
        return None, []
    discount_percent = sale["discount_percent"] or 0
    rows = db.execute(
        "SELECT si.id AS sale_item_id, si.item_id, il.name, si.quantity, si.unit_price, si.discountable, "
        "COALESCE((SELECT SUM(ri.quantity) FROM refund_items ri WHERE ri.sale_item_id = si.id), 0) AS already_refunded "
        "FROM sale_items si JOIN inventory_list il ON il.id = si.item_id "
        "WHERE si.sale_id=? ORDER BY si.id",
        (sale_id,),
    ).fetchall()
    lines = []
    for r in rows:
        remaining = round(r["quantity"] - r["already_refunded"], 6)
        # Per line, from the snapshot taken at checkout. A member's sale can
        # hold both discounted and full-price lines, so refunding every line
        # at the discounted rate would underpay a returned full-price item.
        # On a staff discount every line is discountable, so this stays
        # exactly the old uniform behaviour.
        line_discount = discount_percent if r["discountable"] else 0
        unit_price = money.to_store(r["unit_price"] * (1 - line_discount / Decimal(100)))
        lines.append({
            "sale_item_id": r["sale_item_id"], "item_id": r["item_id"], "name": r["name"],
            "unit_price": unit_price, "quantity": r["quantity"],
            "already_refunded": r["already_refunded"], "remaining": max(remaining, 0),
        })
    return sale, lines


def recent_refunds(db, limit=100, offset=0, date_filter=None):
    where = ""
    params = []
    if date_filter:
        where = "WHERE r.refund_date = ? "
        params.append(date_filter)
    rows = db.execute(
        "SELECT r.*, u.full_name AS processed_by_name FROM refunds r "
        "LEFT JOIN users u ON u.id = r.processed_by " + where +
        "ORDER BY r.refund_date DESC, r.id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["refund_type"] == "retail":
            d["refund_lines"] = db.execute(
                "SELECT ri.*, il.name FROM refund_items ri JOIN inventory_list il ON il.id = ri.item_id "
                "WHERE ri.refund_id=?",
                (r["id"],),
            ).fetchall()
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Owners / Patients
# ---------------------------------------------------------------------------
# The one definition of what counts as noise inside a microchip number:
# spaces, hyphens (including the en/em dashes a paste can carry) and dots.
# app.py's normalize_microchip() strips exactly this before storing, and
# search_patients() strips exactly this before matching -- the two must agree
# or a chip typed the way it is printed would not find the record it is on.
_MICROCHIP_SEPARATORS = re.compile(r"[\s\-\u2013\u2014.]")


def like_pattern(term):
    """A substring pattern for LIKE/ILIKE, with the wildcards in `term`
    escaped so they match themselves.

    Every search box in this app built f"%{term}%" and passed it straight in.
    The query is parameterised, so this was never an injection route -- but %
    and _ are wildcards inside the pattern regardless of how it got there, so
    someone searching for "50%" matched every row and an item called "A_B"
    also matched "AxB". Wrong results, quietly.

    Postgres treats backslash as LIKE's escape character by default (verified
    against the live database: 'axb' ILIKE '%a\\_b%' is false), so no ESCAPE
    clause is needed at the call sites -- escaping the pattern is enough.
    Backslash is escaped first, or it would double-escape the two below it.
    """
    escaped = (term or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def strip_microchip_separators(raw):
    if raw is None:
        return ""
    return _MICROCHIP_SEPARATORS.sub("", str(raw)).upper()


def search_patients(db, term):
    # Microchip numbers are stored normalized, so the term has to be
    # normalized too before it can match one: staff type a chip the way it is
    # grouped on the scanner ("985 141 000 123456") and that string appears
    # nowhere in the database. Every other field is matched on the term as
    # typed, which is why this is a second parameter rather than a change to
    # the first.
    chip_term = like_pattern(strip_microchip_separators(term))
    id_term = parse_id(term, "PT")
    term = like_pattern(term)
    return db.execute(
        "SELECT p.*, o.name as owner_name, o.phone as owner_phone FROM patients p "
        "JOIN owners o ON o.id = p.owner_id "
        "WHERE p.animal_name ILIKE ? OR p.id = ? OR p.microchip ILIKE ? "
        "OR o.name ILIKE ? OR o.phone ILIKE ? "
        "ORDER BY p.animal_name LIMIT 25",
        # A typed code ("PT-00012") or number finds that patient exactly.
        (term, id_term, chip_term, term, term),
    ).fetchall()


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
    visits = db.execute(f"SELECT * FROM visits WHERE patient_id=? ORDER BY date {order}, id {order}",
                        (patient_id,)).fetchall()
    return [v for v in visits
            if v["id"] not in linked and not (v["visit_type"] == "Inpatient" and v["date"] in unlinked_dates)]


def patient_history(db, patient_id):
    cases = db.execute("SELECT * FROM inpatient_cases WHERE patient_id=? ORDER BY admission_date DESC", (patient_id,)).fetchall()
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


# ---------------------------------------------------------------------------
# Audit / login log pages
# ---------------------------------------------------------------------------
def changes_on_date(db, day_str):
    start, end = day_bounds(day_str)
    return db.execute("SELECT * FROM audit_log WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC",
                      (start, end)).fetchall()


def logins_on_date(db, day_str):
    start, end = day_bounds(day_str)
    rows = db.execute("SELECT * FROM login_log WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC",
                      (start, end)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["device"] = authmod.describe_device(r["user_agent"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Point of sale (Retail only)
# ---------------------------------------------------------------------------
def item_sale_price(db, item_id):
    row = db.execute("SELECT sale_price FROM price_list WHERE linked_item_id=? AND active=true LIMIT 1", (item_id,)).fetchone()
    return row["sale_price"] if row else None


# ---------------------------------------------------------------------------
# Distributor Ledger — manual bookkeeping for what you've been billed by a
# distributor and what you've paid them: a lump-sum charge per bill,
# payments recorded against it, balance always computed (never stored).
# Not linked to inventory, POS, or any report; every bill is a manual
# entry, same as the paper/memory tracking this replaces.
# ---------------------------------------------------------------------------
def distributor_bill_balance(bill, payments):
    """payments: list of payment rows for this bill."""
    paid = sum(p["amount"] for p in payments)
    balance = bill["total_amount"] - paid
    if balance <= 0:
        status = "Paid"
    elif paid > 0:
        status = "Partial"
    else:
        status = "Unpaid"
    return {"paid": paid, "balance": balance, "status": status}


def distributor_ledger(db, distributor_id):
    """Bills for a distributor, each annotated with paid/balance/status,
    plus distributor-level totals. Used by the distributor detail page."""
    bills = [dict(r) for r in db.execute(
        "SELECT * FROM distributor_bills WHERE distributor_id=? ORDER BY bill_date DESC, id DESC",
        (distributor_id,)
    ).fetchall()]
    all_payments = db.execute(
        "SELECT * FROM distributor_bill_payments WHERE bill_id IN "
        "(SELECT id FROM distributor_bills WHERE distributor_id=?) ORDER BY payment_date, id",
        (distributor_id,)
    ).fetchall()
    by_bill = {}
    for p in all_payments:
        by_bill.setdefault(p["bill_id"], []).append(dict(p))

    total_billed = total_paid = 0
    for b in bills:
        pmts = by_bill.get(b["id"], [])
        calc = distributor_bill_balance(b, pmts)
        b.update(calc)
        b["payments"] = pmts
        total_billed += b["total_amount"]
        total_paid += calc["paid"]

    return {
        "bills": bills,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "total_outstanding": total_billed - total_paid,
    }


def distributor_outstanding_totals(db):
    """distributor_id -> outstanding balance, for the Distributors list column."""
    rows = db.execute(
        "SELECT b.distributor_id, b.id AS bill_id, b.total_amount, "
        "COALESCE(SUM(p.amount),0) AS paid "
        "FROM distributor_bills b "
        "LEFT JOIN distributor_bill_payments p ON p.bill_id = b.id "
        "GROUP BY b.distributor_id, b.id, b.total_amount"
    ).fetchall()
    totals = {}
    for r in rows:
        totals[r["distributor_id"]] = totals.get(r["distributor_id"], 0) + (r["total_amount"] - r["paid"])
    return totals


def distributor_payables_summary(db):
    """Rolled up across every distributor, for the Distributors list
    page's payables block — total owed, how many distributors have a
    balance, how many bills haven't seen a single payment yet, and a
    small ranked "who you owe most" table."""
    totals = distributor_outstanding_totals(db)  # {distributor_id: balance}
    names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM distributors").fetchall()}

    with_balance = {did: bal for did, bal in totals.items() if bal > 0}
    ranked = sorted(
        ({"id": did, "name": names.get(did, did), "balance": bal} for did, bal in with_balance.items()),
        key=lambda r: r["balance"], reverse=True,
    )[:5]

    unpaid_bill_count = db.execute(
        "SELECT COUNT(*) AS n FROM distributor_bills b WHERE NOT EXISTS "
        "(SELECT 1 FROM distributor_bill_payments p WHERE p.bill_id = b.id)"
    ).fetchone()["n"]

    return {
        "total_outstanding": sum(with_balance.values()),
        "distributors_with_balance": len(with_balance),
        "unpaid_bill_count": unpaid_bill_count,
        "top_outstanding": ranked,
    }


# ---------------------------------------------------------------------------
# Consignment — a distributor's stock sitting on your shelf; they're owed
# cost_price per unit once it sells, you keep the markup. Consignment
# items are ordinary Retail inventory_list rows (ownership_type=
# 'Consignment'), so they already flow through pos_checkout / audit
# sessions / P&L exactly like owned stock with zero special-casing there.
# This section is the distributor-facing receiving/shrinkage/returns/
# settlement layer on top of that shared data.
# ---------------------------------------------------------------------------
def record_consignment_receipt(db, item_id, distributor_id, quantity, unit_cost_at_receipt,
                                received_date, delivery_reference, notes, received_by):
    """Logs stock a distributor drops off. Paired with an
    inventory_transactions row (+quantity), same pattern pos_checkout and
    refund restocking already use — this is what makes the new stock
    immediately visible on Inventory Status and the next audit walk with
    zero changes to inventory_status(). Does not commit."""
    # Microsecond precision — see the comment on audit_session_confirm()'s
    # confirmed_at write in app.py; this writes an inventory_transactions
    # row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_receipts (item_id, distributor_id, quantity, unit_cost_at_receipt, "
        "received_date, delivery_reference, notes, received_by, created_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
        (item_id, distributor_id, quantity, unit_cost_at_receipt, received_date,
         delivery_reference, notes, received_by, now),
    )
    receipt_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (?,?,?,?,?,?)",
        (item_id, quantity, "consignment_receipt", str(receipt_id), now, received_by),
    )
    return receipt_id


def record_consignment_shrinkage(db, item_id, distributor_id, quantity, reason, liable_party,
                                  liability_overridden, notes, logged_by):
    """
    Writes off damaged/expired consignment stock before it ever sold.
    Locks the item's inventory_list row (SELECT ... FOR UPDATE) before
    checking quantity against current shelf stock — same race this app's
    POS checkout should also close (two concurrent write-offs could
    otherwise both read the same "before" stock and together take it
    negative). unit_cost is snapshotted from the item's current
    cost_price at the moment of write-off. Paired with an
    inventory_transactions row (-quantity), same shelf-count effect as a
    sale. Does not commit.

    Returns (ok, shrinkage_id_or_None, error_message_or_None).
    """
    db.execute("SELECT id FROM inventory_list WHERE id=? FOR UPDATE", (item_id,))
    status = inventory_status_by_id(db, item_id)
    # current_stock is None until this item has a confirmed audit — fail
    # closed rather than let `quantity > None` either silently pass or
    # raise a TypeError.
    if status and status["current_stock"] is None:
        return False, None, gettext(
            "This item hasn't been through an inventory audit yet — run an audit before writing off stock.")
    current_stock = status["current_stock"] if status else 0
    if quantity > current_stock:
        return False, None, gettext(
            "Only %(stock)s unit(s) on the shelf — can't write off %(quantity)s.",
            stock=_display_qty(current_stock), quantity=_display_qty(quantity))
    item = db.execute("SELECT cost_price FROM inventory_list WHERE id=?", (item_id,)).fetchone()
    unit_cost = (item["cost_price"] or 0) if item else 0
    # Microsecond precision — see the comment on audit_session_confirm()'s
    # confirmed_at write in app.py; this writes an inventory_transactions
    # row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_shrinkage (item_id, distributor_id, quantity, reason, liable_party, "
        "liability_overridden, unit_cost, notes, logged_by, logged_at) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
        (item_id, distributor_id, quantity, reason, liable_party,
         bool(liability_overridden), unit_cost, notes, logged_by, now),
    )
    shrinkage_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (?,?,?,?,?,?)",
        (item_id, -quantity, "shrinkage", str(shrinkage_id), now, logged_by),
    )
    return True, shrinkage_id, None


def record_consignment_return(db, item_id, distributor_id, quantity, return_date, reason, notes, returned_by):
    """
    Logs unsold stock physically handed back to the distributor — mirror
    image of receiving. Same locking/capping pattern as
    record_consignment_shrinkage() above (can't return more than what's
    actually on the shelf). unit_cost_at_return is snapshotted from the
    item's current cost_price. Paired with an inventory_transactions row
    (-quantity). No revenue/COGS/settlement impact — nothing sold, so
    nothing owed either way; returns never appear in
    consignment_balance()'s formula. Does not commit.

    Returns (ok, return_id_or_None, error_message_or_None).
    """
    db.execute("SELECT id FROM inventory_list WHERE id=? FOR UPDATE", (item_id,))
    status = inventory_status_by_id(db, item_id)
    if status and status["current_stock"] is None:
        return False, None, gettext(
            "This item hasn't been through an inventory audit yet — run an audit before returning stock.")
    current_stock = status["current_stock"] if status else 0
    if quantity > current_stock:
        return False, None, gettext(
            "Only %(stock)s unit(s) on the shelf — can't return %(quantity)s.",
            stock=_display_qty(current_stock), quantity=_display_qty(quantity))
    item = db.execute("SELECT cost_price FROM inventory_list WHERE id=?", (item_id,)).fetchone()
    unit_cost = (item["cost_price"] or 0) if item else 0
    # Microsecond precision — see the comment on audit_session_confirm()'s
    # confirmed_at write in app.py; this writes an inventory_transactions
    # row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_returns (item_id, distributor_id, quantity, unit_cost_at_return, "
        "return_date, reason, notes, returned_by, created_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
        (item_id, distributor_id, quantity, unit_cost, return_date, reason, notes, returned_by, now),
    )
    return_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (?,?,?,?,?,?)",
        (item_id, -quantity, "consignment_return", str(return_id), now, returned_by),
    )
    return True, return_id, None


def consignment_balance(db, distributor_id):
    """
    The payable balance for one distributor, as of right now.

        amount_owed = residual_from_last_settlement + new_activity_since

    residual_from_last_settlement: (last_settlement.amount_owed -
    amount_paid) — 0 if there's no prior settlement, or it was paid in
    full. A confirmed partial settlement's unpaid remainder carries
    forward exactly this way into the next period.

    new_activity_since, restricted to this distributor's Consignment
    items, uses sale_items.unit_cost — snapshotted at sale time, so this
    can't retroactively change if a Price List / Inventory cost is edited
    later (unlike a live join to inventory_list.cost_price would):
        + units sold                 sale_items.quantity * unit_cost
        - sales reversed & restocked refund_items.quantity * cost
        + Clinic-liable shrinkage    consignment_shrinkage.quantity * unit_cost
    Distributor-liable shrinkage adds nothing — they absorb that loss
    directly, not you. Returns never appear here — no money changes
    hands on a return.

    A restocked refund is reversed exactly as its sale was counted
    (audit B9): through refund_items.sale_item_id, at the sale line's
    snapshotted unit_cost and against its snapshotted distributor. It used
    to take the item's CURRENT cost and CURRENT distributor, so a later
    re-point moved the refund's credit to another distributor, and it
    compared the refund's DATE with a timestamp, so a restock on the same
    day as the previous settlement fell out of every period (B13). Refunds
    are now placed by the moment they were recorded (created_at), with the
    same bounds as sales.

    period_start/period_end are exclusive/inclusive bounds matching
    consignment_settlements' own column semantics — a caller recording a
    new settlement should write this call's period_start/period_end
    straight into those columns.

    The sales/refund scan is additionally floored per item at
    inventory_list.consignment_since (when set) — GREATEST'd against
    period_start — so a sale from before that specific item was actually
    flagged Consignment (e.g. years of prior Retail sales on an item that
    only just got flagged) never counts toward what's owed. Without this,
    a brand-new distributor with no receiving logged yet has no
    period_start at all, and every historical sale of a newly-flagged
    item would be swept in.

    Returns a dict: residual, period_start, period_end, new_activity,
    amount_owed, units_sold_since, last_settlement_date.
    """
    last = db.execute(
        "SELECT * FROM consignment_settlements WHERE distributor_id=? ORDER BY created_at DESC LIMIT 1",
        (distributor_id,),
    ).fetchone()
    if last:
        residual = money.to_store((last["amount_owed"] or 0) - (last["amount_paid"] or 0))
        period_start = last["period_end"]
        last_settlement_date = last["created_at"]
    else:
        # No prior settlement — start from this distributor's earliest
        # consignment activity of any kind: receiving (when their stock
        # first became sellable), shrinkage, a return — or an item being
        # FLAGGED Consignment. The last one matters on its own: an item
        # already on the shelf can be flagged with no receiving at all,
        # and its sales count as owed from consignment_since (below).
        # Without it period_start stayed None, and the settlement route
        # refused the distributor's first settlement as "nothing to
        # settle" while showing an amount owed (CODE_AUDIT §10 M8).
        earliest = db.execute(
            "SELECT MIN(x) AS m FROM ("
            "  SELECT MIN(created_at) AS x FROM consignment_receipts WHERE distributor_id=?"
            "  UNION ALL SELECT MIN(logged_at) FROM consignment_shrinkage WHERE distributor_id=?"
            "  UNION ALL SELECT MIN(created_at) FROM consignment_returns WHERE distributor_id=?"
            "  UNION ALL SELECT MIN(consignment_since) FROM inventory_list"
            "    WHERE distributor_id=? AND ownership_type='Consignment'"
            ") t",
            (distributor_id, distributor_id, distributor_id, distributor_id),
        ).fetchone()
        residual = 0
        period_start = earliest["m"] if earliest else None
        last_settlement_date = None

    # Every sum below is bounded by this instant: with an unbounded (or a
    # seconds-truncated) period, a sale in the same second as a settlement
    # was counted in that settlement AND again in the next (CODE_AUDIT B13).
    period_end = clock.now()

    # si.distributor_id is a snapshot taken at checkout time (see
    # pos_checkout()) — this is what makes attribution historically stable:
    # re-pointing an item from Distributor A to B afterward (Inventory
    # Catalog's distributor field) no longer moves a past sale's cost to B.
    # COALESCE'd against the item's *current* distributor_id only for sales
    # that predate this column (si.distributor_id is NULL for those), so
    # existing history isn't silently dropped. See ORPHANED_RECORDS_AUDIT.md
    # F-07.
    sold_where = (
        "WHERE i.ownership_type='Consignment' AND COALESCE(si.distributor_id, i.distributor_id)=? "
        # GREATEST ignores a NULL argument; both NULL (no period yet, item
        # never flagged) means no lower bound, not "nothing" -- hence -infinity.
        "AND s.sold_at > COALESCE(GREATEST(?::timestamptz, i.consignment_since), '-infinity'::timestamptz) "
        "AND s.sold_at <= ?"
    )
    sold_params = [distributor_id, period_start, period_end]
    sold_row = db.execute(
        "SELECT COALESCE(SUM(si.quantity * COALESCE(si.unit_cost, 0)), 0) AS cost, "
        "COALESCE(SUM(si.quantity), 0) AS units "
        "FROM sale_items si JOIN sales s ON s.id = si.sale_id JOIN inventory_list i ON i.id = si.item_id "
        + sold_where,
        sold_params,
    ).fetchone()
    sold_cost = sold_row["cost"] or 0
    units_sold = sold_row["units"] or 0

    # The mirror of the sold term: the same line's cost and distributor, the
    # same bounds, placed by when the refund was recorded (see the docstring).
    restocked_cost = db.execute(
        "SELECT COALESCE(SUM(ri.quantity * COALESCE(si.unit_cost, 0)), 0) AS cost "
        "FROM refund_items ri JOIN refunds r ON r.id = ri.refund_id "
        "JOIN sale_items si ON si.id = ri.sale_item_id JOIN inventory_list i ON i.id = ri.item_id "
        "WHERE i.ownership_type='Consignment' AND COALESCE(si.distributor_id, i.distributor_id)=? AND r.restocked=true "
        "AND r.created_at > COALESCE(GREATEST(?::timestamptz, i.consignment_since), '-infinity'::timestamptz) "
        "AND r.created_at <= ?",
        [distributor_id, period_start, period_end],
    ).fetchone()["cost"] or 0

    shrink_where = "WHERE distributor_id=? AND liable_party='Clinic' AND logged_at <= ?"
    shrink_params = [distributor_id, period_end]
    if period_start:
        shrink_where += " AND logged_at > ?"
        shrink_params.append(period_start)
    shrink_row = db.execute(
        "SELECT COALESCE(SUM(quantity * unit_cost), 0) AS cost FROM consignment_shrinkage " + shrink_where,
        shrink_params,
    ).fetchone()
    shrinkage_cost = shrink_row["cost"] or 0

    new_activity = money.to_store(sold_cost - restocked_cost + shrinkage_cost)
    amount_owed = money.to_store(residual + new_activity)

    return {
        "residual": residual, "period_start": period_start, "period_end": period_end,
        "new_activity": new_activity, "amount_owed": amount_owed,
        "units_sold_since": units_sold, "last_settlement_date": last_settlement_date,
    }


def consignment_distributors_overview(db):
    """
    One row per distributor with >=1 Consignment item: shelf stock (units
    + value at their cost), amount owed right now, last settlement date,
    units sold this month. Calls consignment_balance() per distributor —
    fine at the scale this screen is for (a clinic's number of
    distributor relationships, not its transaction volume).

    inventory_status(db) is computed exactly ONCE up front and looked up
    by item_id from a dict — NOT via inventory_status_by_id() per
    Consignment item, which would recompute the whole catalog's status
    just to return one row (O(distributors x items-per-distributor x
    full-catalog-size) — fine with a handful of test rows, severe on a
    clinic's real inventory history).
    """
    status_by_item = {s["item_id"]: s for s in inventory_status(db)}
    distributors = db.execute(
        "SELECT DISTINCT d.id, d.name FROM distributors d "
        "JOIN inventory_list i ON i.distributor_id = d.id "
        "WHERE i.ownership_type='Consignment' ORDER BY d.name"
    ).fetchall()
    this_month = clock.today().isoformat()[:7]
    out = []
    for d in distributors:
        items = db.execute(
            "SELECT id, cost_price FROM inventory_list WHERE distributor_id=? AND ownership_type='Consignment'",
            (d["id"],),
        ).fetchall()
        shelf_units, shelf_value = 0, 0
        for it in items:
            status = status_by_item.get(it["id"])
            stock = (status["current_stock"] if status else 0) or 0
            shelf_units += stock
            # stock is a plain float (physical unit count, never itself a
            # currency amount — see the schema comment on why it stays
            # DOUBLE PRECISION), but cost_price is now Decimal, so it has
            # to be converted at this one crossover into money math or the
            # multiplication raises TypeError.
            shelf_value += Decimal(str(stock)) * (it["cost_price"] or 0)
        month_units = db.execute(
            "SELECT COALESCE(SUM(si.quantity), 0) AS u FROM sale_items si "
            "JOIN sales s ON s.id=si.sale_id JOIN inventory_list i ON i.id=si.item_id "
            "WHERE i.distributor_id=? AND i.ownership_type='Consignment' AND s.sold_at >= ? AND s.sold_at < ?",
            (d["id"], *month_bounds(this_month)),
        ).fetchone()["u"] or 0
        balance = consignment_balance(db, d["id"])
        out.append({
            "distributor_id": d["id"], "distributor_name": d["name"],
            "shelf_units": shelf_units, "shelf_value": money.to_store(shelf_value),
            "amount_owed": balance["amount_owed"], "last_settlement_date": balance["last_settlement_date"],
            "units_sold_this_month": month_units,
        })
    return out


def consignment_sales_by_distributor(db, distributor_id=None, date_from=None, date_to=None):
    """
    Sales-by-distributor report. Uses sale_items.unit_cost — the
    price/cost as it actually stood at the moment of that specific sale
    (snapshotted at sale time) — not a live join to inventory_list, so
    this always agrees with consignment_balance()'s own settlement math
    on the same number for the same sale.
    """
    where = ["i.ownership_type = 'Consignment'"]
    params = []
    if distributor_id:
        where.append("d.id = ?")
        params.append(distributor_id)
    if date_from:
        where.append("s.sold_at >= ?")
        params.append(day_bounds(date_from)[0])
    if date_to:
        where.append("s.sold_at < ?")
        params.append(day_bounds(date_to)[0])
    rows = db.execute(
        "SELECT d.id AS distributor_id, d.name AS distributor_name, "
        "to_char(s.sold_at, 'YYYY-MM') AS month, i.id AS item_id, i.name AS item_name, "
        "SUM(si.quantity) AS units_sold, SUM(si.line_total) AS revenue, "
        "SUM(si.quantity * COALESCE(si.unit_cost, 0)) AS owed_to_distributor, "
        "SUM(si.line_total) - SUM(si.quantity * COALESCE(si.unit_cost, 0)) AS your_markup "
        "FROM sale_items si JOIN sales s ON s.id = si.sale_id JOIN inventory_list i ON i.id = si.item_id "
        "JOIN distributors d ON d.id = i.distributor_id "
        "WHERE " + " AND ".join(where) +
        " GROUP BY d.id, d.name, month, i.id, i.name ORDER BY month DESC, d.name, i.name",
        params,
    ).fetchall()
    return rows


def consignment_item_locked(db, item_id):
    """
    True once a Consignment item has ever had a receipt, sale, or
    settlement-relevant activity against it — at that point its
    distributor_id becomes uneditable in the UI (an item never switches
    distributors mid-life; a supply-source change means a new
    inventory_list row, not a re-point of this one, so historical
    settlement math for the old distributor can't silently break).

    The sale_items check is deliberately scoped to items that are
    CURRENTLY ownership_type='Consignment' — consignment_balance() only
    ever sums a sale_items row into a distributor's balance while its
    item is presently Consignment (see that function's own query), so a
    plain Retail item's sale history from whenever it was Owned isn't
    "consignment-relevant activity" and shouldn't block it from being
    flagged as Consignment for the first time. Checking unconditionally
    would mean almost any actively-sold retail item could never be
    flagged at all. consignment_receipts/shrinkage/returns don't have
    this problem: those tables can only ever gain a row for an item that
    was Consignment at the moment it happened (each recording route
    itself requires ownership_type='Consignment' first), so an Owned item
    can never have false-positive rows there.
    """
    if db.execute("SELECT 1 FROM consignment_receipts WHERE item_id=?", (item_id,)).fetchone():
        return True
    item = db.execute("SELECT ownership_type FROM inventory_list WHERE id=?", (item_id,)).fetchone()
    if item and item["ownership_type"] == "Consignment":
        if db.execute("SELECT 1 FROM sale_items WHERE item_id=?", (item_id,)).fetchone():
            return True
    if db.execute("SELECT 1 FROM consignment_shrinkage WHERE item_id=?", (item_id,)).fetchone():
        return True
    if db.execute("SELECT 1 FROM consignment_returns WHERE item_id=?", (item_id,)).fetchone():
        return True
    return False


# ---------------------------------------------------------------------------
# Cash Register — unifies every place money actually changes hands: POS
# sales, Visit/Inpatient/Boarding payments, and refunds (negative, so they
# net out automatically). Distinct from every other billing table in this
# module, which tracks what's *owed*, not what's been *collected* — that
# distinction is the whole point of this feature: comparing what the
# system says came in against what's physically in the till, to catch
# poor documentation or leaking/stolen cash early.
#
# Distributor bill payments and consignment settlements are deliberately
# excluded — that's paying a supplier, not collecting from a customer. Cash
# paid to a supplier out of the till belongs in cash_register_payouts
# instead, logged explicitly with a reason, same as any other till payout.
# ---------------------------------------------------------------------------
CASH_REGISTER_METHODS = ("Cash", "Card", "Transfer")


def cash_register_ledger(db, day):
    """Every money-in/money-out ledger line for `day` ('YYYY-MM-DD').
    Returns a list of dicts: event_date, employee, subtotal,
    discount_percent, total, payment_method, event_type, ref_id."""
    rows = db.execute(
        "SELECT to_char(s.sold_at, 'YYYY-MM-DD HH24:MI') AS event_date, u.full_name AS employee, s.subtotal AS subtotal, "
        "s.discount_percent AS discount_percent, s.total AS total, s.payment_method AS payment_method, "
        "'POS Sale' AS event_type, s.id AS ref_id "
        "FROM sales s LEFT JOIN users u ON u.id = s.cashier_id WHERE s.sold_at >= ? AND s.sold_at < ? "
        "UNION ALL "
        "SELECT p.date::text, u.full_name, p.amount, 0.0, p.amount, p.method, "
        "CASE WHEN p.visit_id IS NOT NULL THEN 'Visit Payment' "
        "     WHEN p.inpatient_case_id IS NOT NULL THEN 'Inpatient Payment' "
        "     WHEN p.boarding_id IS NOT NULL THEN 'Boarding Payment' "
        "     ELSE 'Payment' END, "
        "p.id "
        "FROM payments p LEFT JOIN users u ON u.id = p.user_id WHERE p.date = ? "
        "UNION ALL "
        "SELECT r.refund_date::text, u.full_name, -r.amount, 0.0, -r.amount, r.refund_method, "
        "CASE WHEN r.refund_type='retail' THEN 'Retail Refund' ELSE 'Service Refund' END, "
        "r.id "
        "FROM refunds r LEFT JOIN users u ON u.id = r.processed_by WHERE r.refund_date = ? "
        "ORDER BY event_date DESC",
        (*day_bounds(day), day, day),
    ).fetchall()
    return [dict(r) for r in rows]


def cash_register_totals(db, day):
    """Net Cash/Card/Transfer for `day`: sales + payments - refunds (by
    whichever method the money actually moved through), minus same-day
    cash payouts (always cash — see cash_register_payouts). A payment
    method outside Cash/Card/Transfer (blank, legacy, unexpected) lands in
    'other' rather than being silently dropped from the day's total."""
    ledger = cash_register_ledger(db, day)
    # Plain int 0, not 0.0 — row["total"] comes back as Decimal (every
    # branch of the ledger UNION is now a NUMERIC column), and Decimal
    # mixes fine with int but raises TypeError against a float.
    totals = {"Cash": 0, "Card": 0, "Transfer": 0, "other": 0}
    for row in ledger:
        bucket = row["payment_method"] if row["payment_method"] in CASH_REGISTER_METHODS else "other"
        totals[bucket] += row["total"] or 0
    payouts_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM cash_register_payouts WHERE payout_date=?", (day,)
    ).fetchone()["s"]
    totals["Cash"] = money.to_store(totals["Cash"] - payouts_total)
    for k in ("Card", "Transfer", "other"):
        totals[k] = money.to_store(totals[k])
    totals["all"] = money.to_store(totals["Cash"] + totals["Card"] + totals["Transfer"] + totals["other"])
    return totals


def cash_register_payouts_for_day(db, day):
    return db.execute(
        "SELECT p.*, u.full_name AS logged_by_name FROM cash_register_payouts p "
        "LEFT JOIN users u ON u.id = p.logged_by WHERE p.payout_date=? ORDER BY p.id DESC",
        (day,),
    ).fetchall()


def cash_register_latest_audit(db, day):
    return db.execute(
        "SELECT a.*, u.full_name AS performed_by_name FROM cash_register_audits a "
        "LEFT JOIN users u ON u.id = a.performed_by WHERE a.audit_date=? ORDER BY a.id DESC LIMIT 1",
        (day,),
    ).fetchone()


def cash_register_last_30_days(db):
    """For Insights' Cash Register Health — the last 30 calendar days
    (today inclusive), each with its latest audit status, or 'Not
    Audited' if that day was never closed out. A gap here is exactly
    what this feature exists to surface: a day nobody ever audited is
    itself a documentation problem worth an admin's attention, same as a
    real Deficit."""
    out = []
    today = clock.today()
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        audit = cash_register_latest_audit(db, d)
        out.append({
            "date": d,
            "status": audit["status"] if audit else "Not Audited",
            "difference": audit["difference"] if audit else None,
        })
    return out


# ---------------------------------------------------------------------------
# Appointments — dynamic slot grid
# ---------------------------------------------------------------------------
def generate_slots(db):
    start = get_setting(db, "appt_start_time", "09:00")
    end = get_setting(db, "appt_end_time", "18:00")
    try:
        minutes = int(get_setting(db, "appt_slot_minutes", "30"))
    except (TypeError, ValueError):
        minutes = 30
    if minutes <= 0:
        minutes = 30
    try:
        t0 = datetime.strptime(start, "%H:%M")
        t1 = datetime.strptime(end, "%H:%M")
    except (TypeError, ValueError):
        # Settings is the only writer of these and validates HH:MM before
        # saving, but this stays defensive rather than letting a malformed
        # stored value 500 every page that renders the appointment grid
        # (Appointments, New Visit, Grooming, Inpatient's vet picker). See
        # ERROR_500_AUDIT.md E-02.
        t0 = datetime.strptime("09:00", "%H:%M")
        t1 = datetime.strptime("18:00", "%H:%M")
    if t1 <= t0:
        return []
    slots = []
    cur = t0
    while cur < t1:
        nxt = cur + timedelta(minutes=minutes)
        start_str = cur.strftime("%H:%M")
        # The slot's own start time doubles as its identifier (label) — this is
        # what gets stored in appointments.slot_label. It's just as good a key
        # as an arbitrary letter would be for conflict-checking/grouping, and
        # it's self-explanatory if you ever look at the raw data.
        slots.append({"label": start_str, "start": start_str, "end": min(nxt, t1).strftime("%H:%M")})
        cur = nxt
    return slots


def week_dates(anchor_iso):
    anchor = as_date(anchor_iso) or clock.today()
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def vet_users(db):
    """The staff who can be booked or assigned as the vet: active users whose
    role is marked "can be assigned as a vet". One query for the appointment
    grid, the orphaned-appointment check and every vet picker (audit P19) --
    it was written out three times, and a change to one would have made the
    grid and the pickers disagree about who is a vet."""
    return db.execute("SELECT id, full_name FROM users WHERE role_id IN (SELECT id FROM roles WHERE is_vet_role=true) "
                      "AND active=true ORDER BY full_name").fetchall()


def day_grid(db, day_iso):
    vets = vet_users(db)
    slots = generate_slots(db)
    appts = db.execute("SELECT * FROM appointments WHERE appt_date=?", (day_iso,)).fetchall()

    by_cell = defaultdict(list)
    for a in appts:
        by_cell[(a["slot_label"], a["resource_type"], a["resource_id"])].append(dict(a))

    columns = [{"resource_type": "vet", "resource_id": v["id"], "label": v["full_name"]} for v in vets]
    columns.append({"resource_type": "grooming", "resource_id": None, "label": "Grooming"})

    grid = []
    for slot in slots:
        row = {"slot": slot, "cells": []}
        for col in columns:
            cell_appts = by_cell.get((slot["label"], col["resource_type"], col["resource_id"]), [])
            row["cells"].append({"column": col, "appointments": cell_appts})
        grid.append(row)
    return columns, grid


def orphaned_appointments(db, include_past=False):
    """Upcoming appointments whose (slot_label, resource_type,
    resource_id) no longer matches anything day_grid() currently renders
    — either the vet they're booked against was deactivated since, or
    the slot-length/hours settings changed since they were booked.
    day_grid() only looks a cell up by exact key match against whatever
    generate_slots()/the active-vet list return *right now*, so a row
    like this is still perfectly valid in the database but was
    completely unreachable from the Appointments page — no cell ever
    renders it, and there's no other page listing appointments by id.
    This is the fallback that guarantees one always exists, regardless
    of what caused the mismatch (existing UI also warns at the two
    known trigger points — deactivating a vet, changing
    appt_start_time/appt_end_time/appt_slot_minutes — but this doesn't
    depend on that warning having been heeded, or on every possible
    future cause having been thought of ahead of time)."""
    # include_past=True is a deliberate, explicit opt-in (Appointments'
    # "Show past unreachable bookings" toggle) — a booking that became
    # unreachable *and* whose date has since passed would otherwise be
    # invisible permanently, with no other page listing appointments by
    # id. See ORPHANED_RECORDS_AUDIT.md F-18.
    valid_labels = {s["label"] for s in generate_slots(db)}
    active_vet_ids = {v["id"] for v in vet_users(db)}
    date_filter = "" if include_past else "WHERE a.appt_date >= ?"
    params = () if include_past else (clock.today().isoformat(),)
    rows = db.execute(
        "SELECT a.*, u.full_name AS vet_name FROM appointments a "
        "LEFT JOIN users u ON u.id = a.resource_id "
        f"{date_filter} ORDER BY a.appt_date, a.slot_label",
        params,
    ).fetchall()
    out = []
    for a in rows:
        stale_slot = a["slot_label"] not in valid_labels
        stale_vet = a["resource_type"] == "vet" and a["resource_id"] not in active_vet_ids
        if stale_slot or stale_vet:
            d = dict(a)
            d["reason"] = "Vet no longer active" if stale_vet else "Time slot no longer exists"
            out.append(d)
    return out


def slot_conflict(db, appt_date, slot_label, resource_type, resource_id):
    row = db.execute(
        "SELECT 1 FROM appointments WHERE appt_date=? AND slot_label=? AND resource_type=? AND "
        "(resource_id=? OR (resource_id IS NULL AND ?::text IS NULL))",
        (appt_date, slot_label, resource_type, resource_id, resource_id),
    ).fetchone()
    return bool(row)
# ---------------------------------------------------------------------------
# BI Insights & Retention (Admin only; enforced at the route level)
#
# All queries below are deliberately written as single set-based SQL
# statements (CTEs / unnest / window-style month math) rather than
# per-row Python loops, so they stay fast as billing/visit/sale history
# grows into the hundreds of thousands of rows — see
# migrate_add_bi_indexes_2026_08.py for the supporting indexes.
# ---------------------------------------------------------------------------
REVENUE_CATEGORIES = ["Service", "Medicine", "Retail", "Boarding"]

# Postgres EXTRACT(DOW) already returns 0=Sunday..6=Saturday, i.e. this order.
WEEKDAY_LABELS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
# Default matches Jordan's work week (Sunday-Thursday, so Friday/Saturday is
# the weekend) — overridable per-deployment via the settings.weekend_days row
# (comma-separated 0-6 indices, same numbering as EXTRACT(DOW) above) for a
# clinic running this app outside Jordan. See weekday_is_weekend().
DEFAULT_WEEKEND_DAYS = {5, 6}


def weekday_is_weekend(db):
    """Returns a 7-element bool list (index 0=Sunday..6=Saturday) — which
    days count as "weekend" for the Insights scheduling-demand chart.
    Reads settings.weekend_days if set, otherwise DEFAULT_WEEKEND_DAYS."""
    raw = get_setting(db, "weekend_days")
    if raw:
        try:
            weekend_set = {int(d) for d in raw.split(",") if d.strip() != ""}
        except ValueError:
            weekend_set = DEFAULT_WEEKEND_DAYS
    else:
        weekend_set = DEFAULT_WEEKEND_DAYS
    return [dow in weekend_set for dow in range(7)]


def month_list(months_back):
    """Returns ['YYYY-MM', ...] for the last N months, oldest first (incl. current)."""
    today = clock.today()
    months = []
    y, m = today.year, today.month
    for i in range(months_back - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append(f"{yy:04d}-{mm:02d}")
    return months


def revenue_by_category(db, months_back=12):
    """
    Revenue per month per category (Service/Medicine/Retail, plus
    Boarding), net of that month's refunds. The same lines the Monthly P&L
    sums (reports.py) — so for any month the categories add up to the P&L's
    revenue exactly, which is what audit B3 found they did not.
    """
    months = month_list(months_back)
    rows = reports.by_month_and_category(db, since_month=months[0])
    grid = {(m, c): rev for m, cats in rows.items() for c, (rev, _cogs) in cats.items()}
    return {
        "months": months,
        "categories": REVENUE_CATEGORIES,
        "grid": {m: {c: grid.get((m, c), 0) for c in REVENUE_CATEGORIES} for m in months},
        "totals_by_category": {c: money.to_store(sum(grid.get((m, c), 0) for m in months)) for c in REVENUE_CATEGORIES},
        "totals_by_month": {m: money.to_store(sum(grid.get((m, c), 0) for c in REVENUE_CATEGORIES)) for m in months},
    }


def vet_performance(db, months_back=12):
    """
    Per-vet visit count and total billings (after discount) over the
    trailing window, ranked by revenue. 'doctor' is free text on the visit
    (populated from a Vet-user dropdown), not a hard FK, matching how the
    rest of the app records it.
    """
    months = month_list(months_back)
    cutoff = months[0] + "-01"
    rows = db.execute(
        """
        WITH visit_totals AS (
          SELECT b.visit_id, COALESCE(b.total, 0) AS total
          FROM billing b
        )
        SELECT v.doctor, COUNT(DISTINCT v.id) AS visit_count,
               -- The STORED bill total, not a re-derivation. The old
               -- subtotal*(1-d) already drifted from the receipt (it ignored
               -- Clean Up entirely); a member's bill, where the discount comes
               -- off the eligible lines only, would have widened that
               -- silently. billing.total is kept in sync by
               -- refresh_visit_billing_total().
               COALESCE(SUM(vt.total),0) AS revenue
        FROM visits v
        LEFT JOIN visit_totals vt ON vt.visit_id = v.id
        WHERE v.doctor IS NOT NULL AND v.doctor <> '' AND v.date >= ?
        GROUP BY v.doctor
        ORDER BY revenue DESC
        """,
        (cutoff,),
    ).fetchall()
    out = []
    for r in rows:
        revenue = money.to_store(r["revenue"] or 0)
        visits = r["visit_count"] or 0
        out.append({
            "doctor": r["doctor"], "visit_count": visits, "revenue": revenue,
            "avg_revenue_per_visit": money.to_store(revenue / visits) if visits else 0,
        })
    return out


def client_value(db, limit=20, months_back=12):
    """
    Spend per owner over a TRAILING WINDOW, net of refunds, ranked by value.

    Three deliberate changes from the lifetime version this replaces, all so
    the list is a good one to pick rewards-card holders from:

    * **A window** (12 months by default). Lifetime spend ranked a client who
      spent heavily three years ago and never returned above a current
      regular.
    * **Refunds subtracted** — service refunds through visit / inpatient /
      boarding, and retail refunds on owner-linked sales. Money given back
      was being counted as money earned.
    * **POS sales included**, where staff identified the customer. That is
      opt-in at the till, so most sales carry no owner and are simply absent
      here — partial by design, not a bug to "fix" by requiring it.

    Returns (top_clients, average_spend_per_active_client, active_client_count).
    `is_member` on each row is the ACTIVE answer, so a lapsed card does not
    badge as current. Rounded to 3 places, JO's exact JOD precision.
    """
    months = month_list(months_back)
    cutoff = months[0] + "-01"
    rows = db.execute(
        """
        WITH owner_amounts AS (
          -- Money in: payments against a visit, an inpatient case or a stay.
          SELECT pa.owner_id, p.amount AS amount, 1 AS payments
          FROM payments p JOIN visits v ON v.id = p.visit_id JOIN patients pa ON pa.id = v.patient_id
          WHERE p.visit_id IS NOT NULL AND p.date >= ?::date
          UNION ALL
          SELECT pa.owner_id, p.amount, 1
          FROM payments p JOIN inpatient_cases ic ON ic.id = p.inpatient_case_id JOIN patients pa ON pa.id = ic.patient_id
          WHERE p.inpatient_case_id IS NOT NULL AND p.date >= ?::date
          UNION ALL
          SELECT pa.owner_id, p.amount, 1
          FROM payments p JOIN boarding_sessions bs ON bs.id = p.boarding_id JOIN patients pa ON pa.id = bs.patient_id
          WHERE p.boarding_id IS NOT NULL AND p.date >= ?::date
          UNION ALL
          -- Retail, but only where a customer was identified at the till.
          SELECT s.owner_id, s.total, 1
          FROM sales s WHERE s.owner_id IS NOT NULL AND s.sold_at >= ?
          UNION ALL
          -- Money back out. Not counted as a payment, so payment_count stays
          -- a count of visits paid for rather than going negative.
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN visits v ON v.id = r.visit_id JOIN patients pa ON pa.id = v.patient_id
          WHERE r.visit_id IS NOT NULL AND r.refund_date >= ?::date
          UNION ALL
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN inpatient_cases ic ON ic.id = r.inpatient_case_id JOIN patients pa ON pa.id = ic.patient_id
          WHERE r.inpatient_case_id IS NOT NULL AND r.refund_date >= ?::date
          UNION ALL
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN boarding_sessions bs ON bs.id = r.boarding_id JOIN patients pa ON pa.id = bs.patient_id
          WHERE r.boarding_id IS NOT NULL AND r.refund_date >= ?::date
          UNION ALL
          SELECT s.owner_id, -r.amount, 0
          FROM refunds r JOIN sales s ON s.id = r.sale_id
          WHERE s.owner_id IS NOT NULL AND r.refund_date >= ?::date
        )
        SELECT o.id, o.name, o.is_member, o.member_expires_on,
               SUM(oa.payments) AS payment_count, SUM(oa.amount) AS total_paid
        FROM owner_amounts oa JOIN owners o ON o.id = oa.owner_id
        GROUP BY o.id, o.name, o.is_member, o.member_expires_on
        ORDER BY total_paid DESC
        """,
        (cutoff,) * 8,
    ).fetchall()
    active = [{"id": r["id"], "name": r["name"], "payment_count": r["payment_count"],
               "is_member": is_active_member(r),
               "total_paid": money.to_store(r["total_paid"] or 0)} for r in rows]
    avg_spend = money.to_store(sum(r["total_paid"] for r in active) / len(active)) if active else 0
    return active[:limit], avg_spend, len(active)


def appointment_weekday_load(db, months_back=12):
    """
    Scheduling demand by day of week (Jordan work week: Sun-Thu, with
    Fri/Sat flagged as the weekend), plus a same-day visit count as a rough
    fulfillment signal. NOTE: appointments aren't linked to visits by ID in
    this schema (no visit_id on the appointments table), so "visits that
    day" is a date-level proxy for demand actually showing up — not a
    per-appointment no-show match. Framed as an approximation in the UI.
    """
    months = month_list(months_back)
    cutoff = months[0] + "-01"
    appt_rows = db.execute(
        "SELECT EXTRACT(DOW FROM appt_date::date)::int AS dow, COUNT(*) AS c "
        "FROM appointments WHERE appt_date >= ? GROUP BY 1",
        (cutoff,),
    ).fetchall()
    visit_rows = db.execute(
        "SELECT EXTRACT(DOW FROM date::date)::int AS dow, COUNT(*) AS c "
        "FROM visits WHERE date IS NOT NULL AND date >= ? GROUP BY 1",
        (cutoff,),
    ).fetchall()
    appt_by_dow = {r["dow"]: r["c"] for r in appt_rows}
    visit_by_dow = {r["dow"]: r["c"] for r in visit_rows}
    is_weekend = weekday_is_weekend(db)
    out = []
    for dow in range(7):
        appts = appt_by_dow.get(dow, 0)
        visits = visit_by_dow.get(dow, 0)
        out.append({
            "day": WEEKDAY_LABELS[dow], "is_weekend": is_weekend[dow],
            "appointments": appts, "visits_same_weekday": visits,
            "fulfillment_ratio": round(visits / appts, 2) if appts else None,
        })
    return out


def inpatient_boarding_occupancy(db, months_back=12):
    """
    Active inpatient cases and active boarding stays as of the first day of
    each of the last N months (bounded to N x row-count comparisons, so it
    stays cheap no matter how long a case's stay is), plus avg length of
    stay and admissions-per-month for each.
    """
    months_sql = db.execute(
        """
        WITH months AS (
          SELECT to_char(date_trunc('month', current_date) - (g || ' months')::interval, 'YYYY-MM') AS month,
                 (date_trunc('month', current_date) - (g || ' months')::interval)::date AS month_start,
                 (date_trunc('month', current_date) - (g || ' months')::interval + interval '1 month' - interval '1 day')::date AS month_end
          FROM generate_series(0, ?) g
        )
        SELECT m.month,
               (SELECT COUNT(*) FROM inpatient_cases ic
                WHERE ic.admission_date <= m.month_end
                  AND (ic.dismissal_date IS NULL OR ic.dismissal_date >= m.month_start)) AS active_inpatient,
               (SELECT COUNT(*) FROM boarding_sessions bs
                WHERE bs.entry_date <= m.month_end
                  AND (bs.dismissal_date IS NULL OR bs.dismissal_date >= m.month_start)) AS active_boarding
        FROM months m
        ORDER BY m.month
        """,
        (months_back - 1,),
    ).fetchall()

    avg_stay = db.execute(
        "SELECT AVG(dismissal_date - admission_date) AS d FROM inpatient_cases "
        "WHERE dismissed=true AND dismissal_date IS NOT NULL"
    ).fetchone()["d"]
    avg_boarding_stay = db.execute(
        "SELECT AVG(dismissal_date - entry_date) AS d FROM boarding_sessions "
        "WHERE dismissed=true AND dismissal_date IS NOT NULL"
    ).fetchone()["d"]

    return {
        "by_month": [dict(r) for r in months_sql],
        "avg_inpatient_stay_days": round(float(avg_stay), 1) if avg_stay is not None else None,
        "avg_boarding_stay_days": round(float(avg_boarding_stay), 1) if avg_boarding_stay is not None else None,
    }


def cohort_retention_grid(db, max_offset=11):
    """
    Classic cohort/retention grid: each row is the cohort of patients whose
    FIRST visit fell in that month; each column is 'N months after their
    first visit'; each cell is the % of that cohort with >=1 visit in that
    offset month. Columns are capped at max_offset (keeps the grid a fixed
    width no matter how long the clinic has been open); rows are NOT
    capped here — returns every cohort month on record, newest first, and
    it's the caller's job to paginate for display.
    """
    rows = db.execute(
        """
        WITH first_visit AS (
          SELECT patient_id, MIN(date) AS first_date
          FROM visits WHERE date IS NOT NULL
          GROUP BY patient_id
        ),
        cohorts AS (
          SELECT patient_id, to_char(first_date, 'YYYY-MM') AS cohort_month, first_date
          FROM first_visit
        ),
        cohort_sizes AS (
          SELECT cohort_month, COUNT(*) AS cohort_size FROM cohorts GROUP BY cohort_month
        ),
        visit_offsets AS (
          SELECT c.cohort_month, c.patient_id,
            ( (EXTRACT(YEAR FROM v.date) - EXTRACT(YEAR FROM c.first_date)) * 12
              + (EXTRACT(MONTH FROM v.date) - EXTRACT(MONTH FROM c.first_date)) )::int AS month_offset
          FROM visits v
          JOIN cohorts c ON c.patient_id = v.patient_id
          WHERE v.date IS NOT NULL
        ),
        retained AS (
          SELECT cohort_month, month_offset, COUNT(DISTINCT patient_id) AS retained_count
          FROM visit_offsets
          WHERE month_offset BETWEEN 0 AND ?
          GROUP BY cohort_month, month_offset
        )
        SELECT r.cohort_month, r.month_offset, r.retained_count, cs.cohort_size
        FROM retained r JOIN cohort_sizes cs ON cs.cohort_month = r.cohort_month
        ORDER BY r.cohort_month, r.month_offset
        """,
        (max_offset,),
    ).fetchall()

    by_cohort = defaultdict(dict)
    cohort_size = {}
    for r in rows:
        by_cohort[r["cohort_month"]][r["month_offset"]] = r["retained_count"]
        cohort_size[r["cohort_month"]] = r["cohort_size"]

    cohort_months = sorted(by_cohort.keys(), reverse=True)
    grid = []
    for cm in cohort_months:
        size = cohort_size[cm]
        row = {"cohort_month": cm, "cohort_size": size, "cells": []}
        for offset in range(max_offset + 1):
            retained = by_cohort[cm].get(offset)
            # Only show a cell once that much time has actually elapsed since the cohort started.
            months_elapsed = (
                (clock.today().year - int(cm[:4])) * 12 + (clock.today().month - int(cm[5:7]))
            )
            if offset > months_elapsed:
                row["cells"].append(None)
            else:
                pct = round(100 * (retained or 0) / size) if size else 0
                row["cells"].append(pct)
        grid.append(row)

    return {"cohort_months": cohort_months, "offsets": list(range(max_offset + 1)), "grid": grid}


# ---------------------------------------------------------------------------
# Log retention
# ---------------------------------------------------------------------------
# audit_log, login_log, backup_log and restore_log were never pruned. audit_log
# grows fastest -- log_change() writes one row per CHANGED FIELD on every
# update, plus one per create and delete -- and all four sit inside every
# pg_dump, so they inflate backup duration, backup size and restore time
# indefinitely. That interacts with two things already known: the shutdown
# backup that "may not finish" on a large database (COMPARISON.md §18) and the
# restore drill's runtime.
#
# self_check_log already had its own prune; these four are the ones that did
# not.
RETENTION_TABLES = [
    ("audit_log", "timestamp"),
    ("login_log", "timestamp"),
    ("backup_log", "started_at"),
    ("restore_log", "started_at"),
]

# Floor of 90 days is far above auth.LOCKOUT_LOOKBACK_HOURS, which reads
# login_log to decide whether an account is locked out -- pruning inside that
# window would silently disarm the lockout. test_log_retention.py asserts the
# relationship rather than trusting this comment.
LOG_RETENTION_MIN_DAYS = 90
LOG_RETENTION_MAX_DAYS = 3650
LOG_RETENTION_DEFAULT_DAYS = 730
PRUNE_BATCH = 5000


def prune_old_logs(db, now=None):
    """Delete log rows older than the configured window. Returns
    {table: rows_deleted}.

    Batched rather than one DELETE per table: a first run against years of
    history would otherwise hold a single long transaction over the tables the
    app writes to on every request. Each batch commits on its own, so an
    interrupted prune leaves a consistent database and simply resumes next time.
    """
    try:
        days = int(get_setting(db, "log_retention_days", LOG_RETENTION_DEFAULT_DAYS)
                   or LOG_RETENTION_DEFAULT_DAYS)
    except (TypeError, ValueError):
        days = LOG_RETENTION_DEFAULT_DAYS
    days = max(LOG_RETENTION_MIN_DAYS, min(days, LOG_RETENTION_MAX_DAYS))
    cutoff = ((now or clock.now()) - timedelta(days=days)).isoformat(timespec="seconds")

    deleted = {}
    for table, column in RETENTION_TABLES:
        total = 0
        while True:
            cur = db.execute(
                f"DELETE FROM {table} WHERE ctid IN ("
                f"  SELECT ctid FROM {table} WHERE {column} < ? LIMIT {PRUNE_BATCH})",
                (cutoff,),
            )
            n = cur.rowcount or 0
            db.commit()
            total += n
            if n < PRUNE_BATCH:
                break
        deleted[table] = total
    return deleted
