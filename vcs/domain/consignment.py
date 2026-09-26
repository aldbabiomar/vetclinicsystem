"""
Consignment: a distributor's stock on the clinic's shelf — receiving,
shrinkage, returns, and what the clinic owes for what sold.
"""
from decimal import Decimal

from flask_babel import gettext

from vcs import clock
from vcs import money
from vcs.domain import dates, display, inventory


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
    # confirmed_at write in the inventory blueprint; this writes an
    # inventory_transactions row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_receipts (item_id, distributor_id, quantity, unit_cost_at_receipt, "
        "received_date, delivery_reference, notes, received_by, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (item_id, distributor_id, quantity, unit_cost_at_receipt, received_date,
         delivery_reference, notes, received_by, now),
    )
    receipt_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
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
    db.execute("SELECT id FROM inventory_list WHERE id=%s FOR UPDATE", (item_id,))
    status = inventory.inventory_status_by_id(db, item_id)
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
            stock=display.display_qty(current_stock), quantity=display.display_qty(quantity))
    item = db.execute("SELECT cost_price FROM inventory_list WHERE id=%s", (item_id,)).fetchone()
    unit_cost = (item["cost_price"] or 0) if item else 0
    # Microsecond precision — see the comment on audit_session_confirm()'s
    # confirmed_at write in the inventory blueprint; this writes an
    # inventory_transactions row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_shrinkage (item_id, distributor_id, quantity, reason, liable_party, "
        "liability_overridden, unit_cost, notes, logged_by, logged_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (item_id, distributor_id, quantity, reason, liable_party,
         bool(liability_overridden), unit_cost, notes, logged_by, now),
    )
    shrinkage_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
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
    db.execute("SELECT id FROM inventory_list WHERE id=%s FOR UPDATE", (item_id,))
    status = inventory.inventory_status_by_id(db, item_id)
    if status and status["current_stock"] is None:
        return False, None, gettext(
            "This item hasn't been through an inventory audit yet — run an audit before returning stock.")
    current_stock = status["current_stock"] if status else 0
    if quantity > current_stock:
        return False, None, gettext(
            "Only %(stock)s unit(s) on the shelf — can't return %(quantity)s.",
            stock=display.display_qty(current_stock), quantity=display.display_qty(quantity))
    item = db.execute("SELECT cost_price FROM inventory_list WHERE id=%s", (item_id,)).fetchone()
    unit_cost = (item["cost_price"] or 0) if item else 0
    # Microsecond precision — see the comment on audit_session_confirm()'s
    # confirmed_at write in the inventory blueprint; this writes an
    # inventory_transactions row too, which that column gets compared against.
    now = clock.now().isoformat(timespec="microseconds")
    cur = db.execute(
        "INSERT INTO consignment_returns (item_id, distributor_id, quantity, unit_cost_at_return, "
        "return_date, reason, notes, returned_by, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (item_id, distributor_id, quantity, unit_cost, return_date, reason, notes, returned_by, now),
    )
    return_id = cur.fetchone()["id"]
    db.execute(
        "INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
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
        "SELECT * FROM consignment_settlements WHERE distributor_id=%s ORDER BY created_at DESC LIMIT 1",
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
            "  SELECT MIN(created_at) AS x FROM consignment_receipts WHERE distributor_id=%s"
            "  UNION ALL SELECT MIN(logged_at) FROM consignment_shrinkage WHERE distributor_id=%s"
            "  UNION ALL SELECT MIN(created_at) FROM consignment_returns WHERE distributor_id=%s"
            "  UNION ALL SELECT MIN(consignment_since) FROM inventory_list"
            "    WHERE distributor_id=%s AND ownership_type='Consignment'"
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
        "WHERE i.ownership_type='Consignment' AND COALESCE(si.distributor_id, i.distributor_id)=%s "
        # GREATEST ignores a NULL argument; both NULL (no period yet, item
        # never flagged) means no lower bound, not "nothing" -- hence -infinity.
        "AND s.sold_at > COALESCE(GREATEST(%s::timestamptz, i.consignment_since), '-infinity'::timestamptz) "
        "AND s.sold_at <= %s"
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
        "WHERE i.ownership_type='Consignment' AND COALESCE(si.distributor_id, i.distributor_id)=%s AND r.restocked=true "
        "AND r.created_at > COALESCE(GREATEST(%s::timestamptz, i.consignment_since), '-infinity'::timestamptz) "
        "AND r.created_at <= %s",
        [distributor_id, period_start, period_end],
    ).fetchone()["cost"] or 0

    shrink_where = "WHERE distributor_id=%s AND liable_party='Clinic' AND logged_at <= %s"
    shrink_params = [distributor_id, period_end]
    if period_start:
        shrink_where += " AND logged_at > %s"
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
    status_by_item = {s["item_id"]: s for s in inventory.inventory_status(db)}
    distributors = db.execute(
        "SELECT DISTINCT d.id, d.name FROM distributors d "
        "JOIN inventory_list i ON i.distributor_id = d.id "
        "WHERE i.ownership_type='Consignment' ORDER BY d.name"
    ).fetchall()
    this_month = clock.today().isoformat()[:7]
    out = []
    for d in distributors:
        items = db.execute(
            "SELECT id, cost_price FROM inventory_list WHERE distributor_id=%s AND ownership_type='Consignment'",
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
            "WHERE i.distributor_id=%s AND i.ownership_type='Consignment' AND s.sold_at >= %s AND s.sold_at < %s",
            (d["id"], *dates.month_bounds(this_month)),
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
        where.append("d.id = %s")
        params.append(distributor_id)
    if date_from:
        where.append("s.sold_at >= %s")
        params.append(dates.day_bounds(date_from)[0])
    if date_to:
        where.append("s.sold_at < %s")
        params.append(dates.day_bounds(date_to)[0])
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
    if db.execute("SELECT 1 FROM consignment_receipts WHERE item_id=%s", (item_id,)).fetchone():
        return True
    item = db.execute("SELECT ownership_type FROM inventory_list WHERE id=%s", (item_id,)).fetchone()
    if item and item["ownership_type"] == "Consignment":
        if db.execute("SELECT 1 FROM sale_items WHERE item_id=%s", (item_id,)).fetchone():
            return True
    if db.execute("SELECT 1 FROM consignment_shrinkage WHERE item_id=%s", (item_id,)).fetchone():
        return True
    if db.execute("SELECT 1 FROM consignment_returns WHERE item_id=%s", (item_id,)).fetchone():
        return True
    return False
