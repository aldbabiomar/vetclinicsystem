"""
A restocked refund of a consigned item is credited exactly as its sale was
charged: same cost, same distributor, and in the right period (audit B9's
consignment half, and B13's restock term).

consignment_balance() used to reverse a restocked refund at the item's
CURRENT cost and against its CURRENT distributor — so a later cost change or
re-pointing the item moved the credit — and compared the refund's DATE with
the settlement's timestamp, so a restock on the same day as a settlement fell
out of every period.
"""
from decimal import Decimal as D

import pytest

from vcs.domain import consignment
from conftest import needs_db
from test_money_routes import _latest_sale, _refund_retail
from test_supplier_routes import _settle, consignment_item, distributor, sell_consigned  # noqa: F401

pytestmark = needs_db


def _owed(db, dist):
    return consignment.consignment_balance(db, dist)["amount_owed"]


@pytest.fixture
def restock_one(client, db, consignment_item):
    """restock_one() -> refunds one unit of the latest sale, back to the shelf."""
    refunded = []

    def restock():
        sale = _latest_sale(db)
        line = db.execute("SELECT id FROM sale_items WHERE sale_id=%s AND item_id=%s",
                          (sale["id"], consignment_item["id"])).fetchone()
        resp = _refund_retail(client, sale["id"], line["id"], 1, restock="on")
        assert resp.status_code == 302, "the restocked refund was refused — the test would prove nothing"
        refunded.append(sale["id"])

    yield restock
    for sale_id in refunded:
        db.execute("DELETE FROM inventory_transactions WHERE reason='refund' AND ref_id IN "
                   "(SELECT id::text FROM refunds WHERE sale_id=%s)", (sale_id,))
        db.execute("DELETE FROM refund_items WHERE refund_id IN (SELECT id FROM refunds WHERE sale_id=%s)", (sale_id,))
        db.execute("DELETE FROM refunds WHERE sale_id=%s", (sale_id,))
    db.commit()


def test_the_credit_stays_with_the_distributor_the_sale_was_charged_to(db, sell_consigned, consignment_item,
                                                                       restock_one):
    """GUARD. Sold under A, item then re-pointed to B, then one unit
    returned: A's bill goes down, B's is untouched."""
    a = consignment_item["distributor_id"]
    assert sell_consigned(2, "2.000", "3.500") == D("4.000")
    b = db.execute("INSERT INTO distributors (name) VALUES ('B9 Distributor B') RETURNING id").fetchone()["id"]
    db.execute("UPDATE inventory_list SET distributor_id=%s WHERE id=%s", (b, consignment_item["id"]))
    db.commit()
    try:
        restock_one()
        assert _owed(db, a) == D("2.000"), "the credit left the distributor the sale was charged to"
        assert _owed(db, b) == 0, "the credit landed on a distributor that sold nothing"
    finally:
        db.execute("UPDATE inventory_list SET distributor_id=%s WHERE id=%s", (a, consignment_item["id"]))
        db.execute("DELETE FROM distributors WHERE id=%s", (b,))
        db.commit()


def test_the_credit_is_at_the_cost_the_sale_was_charged_at(db, sell_consigned, consignment_item, restock_one):
    """GUARD. Sold at a cost of 2.000; the cost is 5.000 by the time it
    comes back. The distributor is credited 2.000, not 5.000."""
    a = consignment_item["distributor_id"]
    sell_consigned(2, "2.000", "3.500")
    db.execute("UPDATE inventory_list SET cost_price=%s WHERE id=%s", (D("5.000"), consignment_item["id"]))
    db.commit()
    restock_one()
    assert _owed(db, a) == D("2.000")


def test_a_restock_on_the_day_of_a_settlement_is_in_the_next_period(client, db, sell_consigned, consignment_item,
                                                                    restock_one):
    """GUARD (B13). Sold, settled in full, then one unit comes back the same
    day: the distributor now owes the clinic that unit — a credit of 2.000
    in the new period. By DATE it was "not after" the settlement's day and
    so counted in no period at all."""
    a = consignment_item["distributor_id"]
    owed = sell_consigned(2, "2.000", "3.500")
    assert _settle(client, a, str(owed)).status_code == 302
    assert _owed(db, a) == 0
    restock_one()
    assert _owed(db, a) == D("-2.000")


def test_control_a_sale_with_no_return_is_owed_in_full(db, sell_consigned, consignment_item):
    assert sell_consigned(2, "2.000", "3.500") == D("4.000")
    assert _owed(db, consignment_item["distributor_id"]) == D("4.000")
