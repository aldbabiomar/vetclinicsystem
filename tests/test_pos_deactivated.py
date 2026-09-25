"""
POS never sells an item deactivated in the catalogue (audit B5).

The Price List row and the catalogue item are separate records, so
deactivating the item leaves its price active. The checkout priced the line
from that price, then checked stock through inventory_status(), which covers
active items only — no status, and `if status and ...` skipped both the
"never audited" and the oversell checks. Measured in both predecessor apps:
999 units of a deactivated item sold, stock driven to -999. Reachable from a
cart built before the deactivation, or a crafted POST.
"""
from conftest import needs_db
from test_money_routes import _checkout, _stock_now, sellable  # noqa: F401

pytestmark = needs_db


def _lines_sold(db, inv_id):
    return db.execute("SELECT COUNT(*) c FROM sale_items WHERE item_id=?", (inv_id,)).fetchone()["c"]


def _deactivate(db, inv_id):
    db.execute("UPDATE inventory_list SET active=false WHERE id=?", (inv_id,))
    db.commit()


def test_a_deactivated_item_is_not_sold_past_its_stock(client, db, sellable):
    """GUARD. The audit's repro: 999 units against a stock of 100."""
    _deactivate(db, sellable["inv_id"])
    stock = _stock_now(db, sellable["inv_id"])
    resp = _checkout(client, sellable["inv_id"], qty=999, payment_method="Card")
    assert resp.status_code != 302, "the checkout went through"
    assert "no longer sold" in resp.get_data(as_text=True)
    assert _lines_sold(db, sellable["inv_id"]) == 0
    assert _stock_now(db, sellable["inv_id"]) == stock


def test_a_deactivated_item_is_not_sold_at_all(client, db, sellable):
    """GUARD. Not only the oversell: one unit, well within stock, is refused
    too — the item is no longer sold."""
    _deactivate(db, sellable["inv_id"])
    resp = _checkout(client, sellable["inv_id"], qty=1, payment_method="Card")
    assert resp.status_code != 302
    assert _lines_sold(db, sellable["inv_id"]) == 0


def test_control_the_same_item_sells_while_active(client, db, sellable):
    """CONTROL. The price row was left active in the guards above; with the
    item active too, the same checkout goes through."""
    resp = _checkout(client, sellable["inv_id"], qty=1, payment_method="Card")
    assert resp.status_code == 302, resp.get_data(as_text=True)[:500]
    assert _lines_sold(db, sellable["inv_id"]) == 1
