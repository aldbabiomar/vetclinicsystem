"""
The Cash Register: every place money changes hands in a day, by
method, and the drawer counts.
"""
from datetime import timedelta

from vcs import clock
from vcs import money
from vcs.domain import dates


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
        "FROM sales s LEFT JOIN users u ON u.id = s.cashier_id WHERE s.sold_at >= %s AND s.sold_at < %s "
        "UNION ALL "
        "SELECT p.date::text, u.full_name, p.amount, 0.0, p.amount, p.method, "
        "CASE WHEN p.visit_id IS NOT NULL THEN 'Visit Payment' "
        "     WHEN p.inpatient_case_id IS NOT NULL THEN 'Inpatient Payment' "
        "     WHEN p.boarding_id IS NOT NULL THEN 'Boarding Payment' "
        "     ELSE 'Payment' END, "
        "p.id "
        "FROM payments p LEFT JOIN users u ON u.id = p.user_id WHERE p.date = %s "
        "UNION ALL "
        "SELECT r.refund_date::text, u.full_name, -r.amount, 0.0, -r.amount, r.refund_method, "
        "CASE WHEN r.refund_type='retail' THEN 'Retail Refund' ELSE 'Service Refund' END, "
        "r.id "
        "FROM refunds r LEFT JOIN users u ON u.id = r.processed_by WHERE r.refund_date = %s "
        "ORDER BY event_date DESC",
        (*dates.day_bounds(day), day, day),
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
        "SELECT COALESCE(SUM(amount), 0) AS s FROM cash_register_payouts WHERE payout_date=%s", (day,)
    ).fetchone()["s"]
    totals["Cash"] = money.to_store(totals["Cash"] - payouts_total)
    for k in ("Card", "Transfer", "other"):
        totals[k] = money.to_store(totals[k])
    totals["all"] = money.to_store(totals["Cash"] + totals["Card"] + totals["Transfer"] + totals["other"])
    return totals


def cash_register_payouts_for_day(db, day):
    return db.execute(
        "SELECT p.*, u.full_name AS logged_by_name FROM cash_register_payouts p "
        "LEFT JOIN users u ON u.id = p.logged_by WHERE p.payout_date=%s ORDER BY p.id DESC",
        (day,),
    ).fetchall()


def cash_register_latest_audit(db, day):
    return db.execute(
        "SELECT a.*, u.full_name AS performed_by_name FROM cash_register_audits a "
        "LEFT JOIN users u ON u.id = a.performed_by WHERE a.audit_date=%s ORDER BY a.id DESC LIMIT 1",
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
