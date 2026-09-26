"""
Stock: the audit sessions (only confirmed ones count as history), the
Inventory Status and Ordering Sheet built on them, and an item's sale
price.
"""
import math
from collections import defaultdict
from decimal import Decimal

from vcs import auth as authmod
from vcs import clock
from vcs.domain import dates, settings


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
        "INSERT INTO audit_sessions (audit_date, performed_by, status, created_at) VALUES (%s,%s,'Draft',%s) "
        "ON CONFLICT (audit_date) WHERE status = 'Draft' DO NOTHING RETURNING id",
        (audit_date, user_id, clock.now()),
    ).fetchone()
    if row:
        authmod.log_change(db, "audit_sessions", str(row["id"]), "create")
        return row["id"]
    return db.execute("SELECT id FROM audit_sessions WHERE audit_date=%s AND status='Draft'",
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
    rows = db.execute(q + " LIMIT %s OFFSET %s", [limit, offset]).fetchall()
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
    cutoffs = {item_id: r["confirmed_at"] or dates.day_bounds(dates.as_date(r["audit_date"]))[0]
               for item_id, r in latest_confirmed.items()}
    if not cutoffs:
        return {}
    out = defaultdict(Decimal)
    for t in db.execute("SELECT item_id, change_qty, timestamp FROM inventory_transactions "
                        "WHERE reason = 'consignment_receipt' AND timestamp > %s", (min(cutoffs.values()),)).fetchall():
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
        q += " AND l.item_id=%s"
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
                days = (dates.as_date(r["audit_date"]) - dates.as_date(prior["audit_date"])).days
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
    values_sql = ",".join("(%s,%s)" for _ in items)
    params = [v for pair in items for v in pair]
    rows = db.execute(
        f"SELECT t.item_id, COALESCE(SUM(t.change_qty), 0) AS net FROM inventory_transactions t "
        f"JOIN (VALUES {values_sql}) AS cutoffs(item_id, cutoff) ON cutoffs.item_id = t.item_id "
        f"WHERE t.timestamp > cutoffs.cutoff GROUP BY t.item_id",
        params,
    ).fetchall()
    return {r["item_id"]: r["net"] or 0 for r in rows}


# Each item's latest confirmed audit line, and what confirmed_audit_rows_by_item()
# derives for it from the item's whole history -- worked out in SQL, so the
# history is not shipped to Python on every page (audit D3: the sidebar badge
# did exactly that). "Latest" is the last by (audit_date, id), as
# confirmed_audit_rows_by_item() sorts its output; the carried-forward values
# and the audit before it follow the order the sessions were CONFIRMED in, as
# it walks them. The COUNT/FIRST_VALUE pair is "last non-null so far":
# COUNT(x) goes up at each row that sets x, so each group opens with one.
_LATEST_AUDIT_SQL = """
WITH lines AS (
    SELECT l.id, l.item_id, l.stock_counted, l.received_since_prior, l.nearest_expiry_date,
           l.reorder_threshold, l.critical_item, l.target_coverage_days,
           s.audit_date, s.confirmed_at,
           COALESCE(s.confirmed_at, s.audit_date::timestamptz) AS confirmed_order
    FROM audit_session_lines l JOIN audit_sessions s ON s.id = l.session_id
    WHERE s.status = 'Confirmed' AND l.stock_counted IS NOT NULL {item_filter}
), walked AS (
    SELECT lines.*,
           LAG(id) OVER w AS prior_id,
           LAG(stock_counted) OVER w AS prior_stock,
           LAG(audit_date) OVER w AS prior_audit_date,
           COUNT(reorder_threshold) OVER w AS threshold_group,
           COUNT(critical_item) OVER w AS critical_group,
           COUNT(target_coverage_days) OVER w AS target_group,
           ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY audit_date DESC, id DESC) AS recency
    FROM lines
    WINDOW w AS (PARTITION BY item_id ORDER BY confirmed_order, id)
), carried AS (
    SELECT walked.*,
           FIRST_VALUE(reorder_threshold) OVER (PARTITION BY item_id, threshold_group ORDER BY confirmed_order, id)
               AS effective_reorder_threshold,
           FIRST_VALUE(critical_item) OVER (PARTITION BY item_id, critical_group ORDER BY confirmed_order, id)
               AS effective_critical_item,
           FIRST_VALUE(target_coverage_days) OVER (PARTITION BY item_id, target_group ORDER BY confirmed_order, id)
               AS effective_target_coverage_days
    FROM walked
)
SELECT * FROM carried WHERE recency = 1
"""


def latest_audit_state(db, item_ids=None):
    """{item_id: its latest confirmed audit line} with the fields
    inventory_status() reads: stock_counted, audit_date, confirmed_at,
    nearest_expiry_date, and -- as confirmed_audit_rows_by_item() computes
    them -- effective_reorder_threshold, effective_critical_item,
    effective_target_coverage_days (30 when never set) and daily_usage_rate.
    `item_ids` limits it to those items (audit D4)."""
    item_filter, params = "", []
    if item_ids is not None:
        item_filter, params = "AND l.item_id = ANY(%s)", [list(item_ids)]
    out = {}
    for r in db.execute(_LATEST_AUDIT_SQL.format(item_filter=item_filter), params).fetchall():
        r = dict(r)
        if r["effective_target_coverage_days"] is None:
            r["effective_target_coverage_days"] = 30
        r["daily_usage_rate"] = None
        if r["prior_id"] is not None:
            usage = r["prior_stock"] + r["received_since_prior"] - r["stock_counted"]
            days = (dates.as_date(r["audit_date"]) - dates.as_date(r["prior_audit_date"])).days
            r["daily_usage_rate"] = round(usage / days, 4) if days > 0 else None
        out[r["item_id"]] = r
    return out


# ---------------------------------------------------------------------------
# Inventory Status
# ---------------------------------------------------------------------------
def inventory_status(db, item_ids=None):
    """Every active item's stock, expiry and audit status -- or, with
    `item_ids`, those items' (audit D4: the POS and the audit confirm needed
    a handful and computed the whole catalogue)."""
    audit_overdue_days = settings.int_setting(db, "audit_overdue_days", 35)
    expiry_soon_days = settings.int_setting(db, "expiry_soon_days", 60)
    today = clock.today()

    if item_ids is None:
        items = db.execute("SELECT * FROM inventory_list WHERE active=true ORDER BY name").fetchall()
    else:
        items = db.execute("SELECT * FROM inventory_list WHERE active=true AND id = ANY(%s) ORDER BY name",
                           (list(item_ids),)).fetchall()
    items = [dict(r) for r in items]
    latest_by_item = latest_audit_state(db, item_ids)

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
        latest = latest_by_item.get(it["id"])
        if latest:
            cutoffs[it["id"]] = latest["confirmed_at"] or dates.day_bounds(dates.as_date(latest["audit_date"]))[0]
    txn_since = _txn_qty_since_batch(db, cutoffs)

    status = []
    for it in items:
        latest = latest_by_item.get(it["id"])

        base_stock = latest["stock_counted"] if latest else None
        latest_audit_date = dates.as_date(latest["audit_date"]) if latest else None
        nearest_expiry = dates.as_date(latest["nearest_expiry_date"]) if latest else None
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
            "track_expiry": bool(it["track_expiry"]), "latest_audit_date": dates.fmt_date(latest_audit_date),
            "current_stock": current_stock, "nearest_expiry_date": dates.fmt_date(nearest_expiry),
            "daily_usage_rate": daily_usage_rate, "days_since_audit": days_since_audit,
            "days_to_expiry": days_to_expiry, "stock_status": stock_status, "expiry_status": expiry_status,
            "audit_status": audit_status, "critical_item": critical_item,
            "target_coverage_days": target_coverage_days, "distributor_id": it["distributor_id"],
            "ownership_type": it["ownership_type"],
        })
    return status


def inventory_status_by_id(db, item_id):
    rows = inventory_status(db, [item_id])
    return rows[0] if rows else None


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
# Point of sale (Retail only)
# ---------------------------------------------------------------------------
def item_sale_price(db, item_id):
    row = db.execute("SELECT sale_price FROM price_list WHERE linked_item_id=%s AND active=true LIMIT 1", (item_id,)).fetchone()
    return row["sale_price"] if row else None
