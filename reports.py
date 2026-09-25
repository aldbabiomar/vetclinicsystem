"""
Revenue and cost of goods, computed on read from the stored bill totals.

One query produces every revenue line the clinic has — each with its month,
its category, its share of revenue and its cost — and every report sums
those same lines: the Monthly and Yearly P&L by month, Insights by month and
category. Two reports cannot disagree about a month because they read one
definition of it (audit B3 was the Insights and P&L disagreeing).

There is no summary table (plan decision D-3). The table it replaces was
kept in step by hand from ~30 call sites, three of which forgot (audit B2),
and had a Rebuild button that could erase a concurrent sale (B14). At a
clinic's scale this whole query is milliseconds.

Revenue is always the STORED total a person was charged, never re-derived:

  - a visit bill's `billing.total` (after its discount and Clean Up), spread
    over the bill's own lines by each line's discounted amount — so the
    lines keep their categories and still sum exactly to the bill;
  - a POS sale's `sales.total`, spread over its lines the same way;
  - an inpatient case's `inpatient_cases.total`, spread over its lines —
    which also spreads it over the MONTHS its procedures were logged;
  - a boarding stay's `billed_total` (after its discount and Clean Up);
  - minus every refund, in the month and category it was paid out.

Cost of goods comes from the costs snapshotted on each line when it was
billed; a restocked retail refund reverses the cost of the SALE LINE it
refunds (audit B9) -- every refund line names one (NOT NULL), and is valued
exactly as that line's sale was.

Months and days are the clinic's (clock.py): the connection's TimeZone is
the clinic zone, so `to_char` below names the clinic's month.
"""
from collections import defaultdict
from decimal import Decimal

import money

def _lines_sql(where):
    """Every revenue/cost line, with its month and category. Apportioning
    uses a window over the WHOLE bill before `where` filters by month, so a
    case spanning two months is split correctly whichever month is asked
    for. A function, not a module constant, so the seam-rule scan of discount
    arithmetic (tests/test_seam_rules.py rule 8) reads it."""
    return """
WITH visit_auto AS (
    SELECT b.visit_id AS bill, to_char(b.date_billed, 'YYYY-MM') AS month, l.category AS category,
           l.unit_price * l.quantity
             * (1 - CASE WHEN l.discountable THEN COALESCE(b.discount_percent, 0) ELSE 0 END / 100.0) AS weight,
           b.total AS bill_total,
           COALESCE(l.unit_cost, 0) * l.quantity AS cost
    FROM billing b JOIN visit_billing_lines l ON l.visit_id = b.visit_id
    WHERE b.billing_type = 'Automatic' AND b.date_billed IS NOT NULL
),
visit_rev AS (
    SELECT month, category,
           CASE WHEN SUM(weight) OVER (PARTITION BY bill) > 0
                THEN weight * bill_total / SUM(weight) OVER (PARTITION BY bill) ELSE 0 END AS revenue,
           cost
    FROM visit_auto
    UNION ALL
    -- A Manual bill, or an Automatic one whose lines were all removed: the
    -- stored total, as a service.
    SELECT to_char(b.date_billed, 'YYYY-MM'), 'Service', b.total, 0
    FROM billing b
    WHERE b.date_billed IS NOT NULL
      AND (b.billing_type = 'Manual'
           OR NOT EXISTS (SELECT 1 FROM visit_billing_lines l WHERE l.visit_id = b.visit_id))
),
sale_lines AS (
    SELECT s.id AS bill, to_char(s.sold_at, 'YYYY-MM') AS month,
           si.line_total * (1 - CASE WHEN si.discountable THEN COALESCE(s.discount_percent, 0) ELSE 0 END / 100.0) AS weight,
           s.total AS bill_total,
           si.quantity * COALESCE(si.unit_cost, i.cost_price, 0) AS cost
    FROM sale_items si JOIN sales s ON s.id = si.sale_id
    LEFT JOIN inventory_list i ON i.id = si.item_id
),
sale_rev AS (
    SELECT month, 'Retail' AS category,
           CASE WHEN SUM(weight) OVER (PARTITION BY bill) > 0
                THEN weight * bill_total / SUM(weight) OVER (PARTITION BY bill) ELSE 0 END AS revenue,
           cost
    FROM sale_lines
),
inpatient_lines AS (
    SELECT ib.case_id AS bill, to_char(ib.timestamp, 'YYYY-MM') AS month, p.category AS category,
           COALESCE(ib.unit_price, p.sale_price, 0) * ib.quantity
             * (1 - CASE WHEN ib.discountable THEN COALESCE(ic.discount_percent, 0) ELSE 0 END / 100.0) AS weight,
           ic.total AS bill_total,
           COALESCE(ib.unit_cost, p.cost_price, 0) * ib.quantity AS cost
    FROM inpatient_billing ib
    JOIN price_list p ON p.id = ib.price_id
    JOIN inpatient_cases ic ON ic.id = ib.case_id
),
inpatient_rev AS (
    SELECT month, category,
           CASE WHEN SUM(weight) OVER (PARTITION BY bill) > 0
                THEN weight * bill_total / SUM(weight) OVER (PARTITION BY bill) ELSE 0 END AS revenue,
           cost
    FROM inpatient_lines
),
boarding_rev AS (
    SELECT to_char(entry_date, 'YYYY-MM') AS month, 'Boarding' AS category,
           COALESCE(billed_total, total) AS revenue, 0 AS cost
    FROM boarding_sessions
    WHERE COALESCE(billed_total, total) IS NOT NULL
),
refund_rev AS (
    SELECT to_char(r.refund_date, 'YYYY-MM') AS month,
           CASE WHEN r.refund_type = 'retail' THEN 'Retail'
                WHEN r.boarding_id IS NOT NULL THEN 'Boarding'
                ELSE 'Service' END AS category,
           -r.amount AS revenue, 0 AS cost
    FROM refunds r
    UNION ALL
    -- A restocked retail refund: the goods are back on the shelf, so their
    -- cost is no longer spent. At the cost the SALE LINE carried (B9).
    SELECT to_char(r.refund_date, 'YYYY-MM'), 'Retail', 0,
           -(ri.quantity * COALESCE(si.unit_cost, i.cost_price, 0))
    FROM refund_items ri
    JOIN refunds r ON r.id = ri.refund_id
    JOIN sale_items si ON si.id = ri.sale_item_id
    LEFT JOIN inventory_list i ON i.id = ri.item_id
    WHERE r.refund_type = 'retail' AND r.restocked
),
all_lines AS (
    SELECT * FROM visit_rev UNION ALL SELECT * FROM sale_rev UNION ALL SELECT * FROM inpatient_rev
    UNION ALL SELECT * FROM boarding_rev UNION ALL SELECT * FROM refund_rev
)
SELECT month, category, SUM(revenue) AS revenue, SUM(cost) AS cogs
FROM all_lines
WHERE month IS NOT NULL """ + where + """
GROUP BY month, category
"""


def _rows(db, since_month=None, only_month=None):
    where, params = "", []
    if only_month:
        where, params = "AND month = ?", [only_month]
    elif since_month:
        where, params = "AND month >= ?", [since_month]
    return db.execute(_lines_sql(where), params).fetchall()


def by_month_and_category(db, since_month=None):
    """{month: {category: (revenue, cogs)}} — Insights' breakdown."""
    out = defaultdict(dict)
    for r in _rows(db, since_month=since_month):
        out[r["month"]][r["category"]] = (money.to_store(r["revenue"] or 0), money.to_store(r["cogs"] or 0))
    return out


def by_month(db, since_month=None, only_month=None):
    """{month: (revenue, cogs)} — the P&L. Built FROM the per-category
    figures, not beside them, so the P&L for a month is exactly the sum of
    Insights' categories for that month, to the last fils."""
    out = {}
    rows = _rows(db, since_month=since_month, only_month=only_month)
    for r in rows:
        rev, cogs = money.to_store(r["revenue"] or 0), money.to_store(r["cogs"] or 0)
        m_rev, m_cogs = out.get(r["month"], (Decimal(0), Decimal(0)))
        out[r["month"]] = (m_rev + rev, m_cogs + cogs)
    return out
