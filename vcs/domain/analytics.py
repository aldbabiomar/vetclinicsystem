"""
Insights and Retention: revenue by category, vet performance, client
value, weekday load, occupancy, and the cohort retention grid.
"""
from collections import defaultdict

from vcs import clock
from vcs import money
from vcs.domain import dates, members, reports, settings


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
    raw = settings.get_setting(db, "weekend_days")
    if raw:
        try:
            weekend_set = {int(d) for d in raw.split(",") if d.strip() != ""}
        except ValueError:
            weekend_set = DEFAULT_WEEKEND_DAYS
    else:
        weekend_set = DEFAULT_WEEKEND_DAYS
    return [dow in weekend_set for dow in range(7)]


def revenue_by_category(db, months_back=12):
    """
    Revenue per month per category (Service/Medicine/Retail, plus
    Boarding), net of that month's refunds. The same lines the Monthly P&L
    sums (reports.py) — so for any month the categories add up to the P&L's
    revenue exactly, which is what audit B3 found they did not.
    """
    months = dates.month_list(months_back)
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
    months = dates.month_list(months_back)
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
               -- billing.bill_changed().
               COALESCE(SUM(vt.total),0) AS revenue
        FROM visits v
        LEFT JOIN visit_totals vt ON vt.visit_id = v.id
        WHERE v.doctor IS NOT NULL AND v.doctor <> '' AND v.date >= %s
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
    months = dates.month_list(months_back)
    cutoff = months[0] + "-01"
    rows = db.execute(
        """
        WITH owner_amounts AS (
          -- Money in: payments against a visit, an inpatient case or a stay.
          SELECT pa.owner_id, p.amount AS amount, 1 AS payments
          FROM payments p JOIN visits v ON v.id = p.visit_id JOIN patients pa ON pa.id = v.patient_id
          WHERE p.visit_id IS NOT NULL AND p.date >= %s::date
          UNION ALL
          SELECT pa.owner_id, p.amount, 1
          FROM payments p JOIN inpatient_cases ic ON ic.id = p.inpatient_case_id JOIN patients pa ON pa.id = ic.patient_id
          WHERE p.inpatient_case_id IS NOT NULL AND p.date >= %s::date
          UNION ALL
          SELECT pa.owner_id, p.amount, 1
          FROM payments p JOIN boarding_sessions bs ON bs.id = p.boarding_id JOIN patients pa ON pa.id = bs.patient_id
          WHERE p.boarding_id IS NOT NULL AND p.date >= %s::date
          UNION ALL
          -- Retail, but only where a customer was identified at the till.
          SELECT s.owner_id, s.total, 1
          FROM sales s WHERE s.owner_id IS NOT NULL AND s.sold_at >= %s
          UNION ALL
          -- Money back out. Not counted as a payment, so payment_count stays
          -- a count of visits paid for rather than going negative.
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN visits v ON v.id = r.visit_id JOIN patients pa ON pa.id = v.patient_id
          WHERE r.visit_id IS NOT NULL AND r.refund_date >= %s::date
          UNION ALL
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN inpatient_cases ic ON ic.id = r.inpatient_case_id JOIN patients pa ON pa.id = ic.patient_id
          WHERE r.inpatient_case_id IS NOT NULL AND r.refund_date >= %s::date
          UNION ALL
          SELECT pa.owner_id, -r.amount, 0
          FROM refunds r JOIN boarding_sessions bs ON bs.id = r.boarding_id JOIN patients pa ON pa.id = bs.patient_id
          WHERE r.boarding_id IS NOT NULL AND r.refund_date >= %s::date
          UNION ALL
          SELECT s.owner_id, -r.amount, 0
          FROM refunds r JOIN sales s ON s.id = r.sale_id
          WHERE s.owner_id IS NOT NULL AND r.refund_date >= %s::date
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
               "is_member": members.is_active_member(r),
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
    months = dates.month_list(months_back)
    cutoff = months[0] + "-01"
    appt_rows = db.execute(
        "SELECT EXTRACT(DOW FROM appt_date::date)::int AS dow, COUNT(*) AS c "
        "FROM appointments WHERE appt_date >= %s GROUP BY 1",
        (cutoff,),
    ).fetchall()
    visit_rows = db.execute(
        "SELECT EXTRACT(DOW FROM date::date)::int AS dow, COUNT(*) AS c "
        "FROM visits WHERE date IS NOT NULL AND date >= %s GROUP BY 1",
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
          FROM generate_series(0, %s) g
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
          WHERE month_offset BETWEEN 0 AND %s
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
