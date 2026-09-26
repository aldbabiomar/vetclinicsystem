"""
Refunds: what is left to refund on a sale, and the refunds list.
"""
from decimal import Decimal

from vcs import money


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
    sale = db.execute("SELECT * FROM sales WHERE id=%s", (sale_id,)).fetchone()
    if not sale:
        return None, []
    discount_percent = sale["discount_percent"] or 0
    rows = db.execute(
        "SELECT si.id AS sale_item_id, si.item_id, il.name, si.quantity, si.unit_price, si.discountable, "
        "COALESCE((SELECT SUM(ri.quantity) FROM refund_items ri WHERE ri.sale_item_id = si.id), 0) AS already_refunded "
        "FROM sale_items si JOIN inventory_list il ON il.id = si.item_id "
        "WHERE si.sale_id=%s ORDER BY si.id",
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
        where = "WHERE r.refund_date = %s "
        params.append(date_filter)
    rows = db.execute(
        "SELECT r.*, u.full_name AS processed_by_name FROM refunds r "
        "LEFT JOIN users u ON u.id = r.processed_by " + where +
        "ORDER BY r.refund_date DESC, r.id DESC LIMIT %s OFFSET %s",
        params + [limit, offset],
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["refund_type"] == "retail":
            d["refund_lines"] = db.execute(
                "SELECT ri.*, il.name FROM refund_items ri JOIN inventory_list il ON il.id = ri.item_id "
                "WHERE ri.refund_id=%s",
                (r["id"],),
            ).fetchall()
        out.append(d)
    return out
