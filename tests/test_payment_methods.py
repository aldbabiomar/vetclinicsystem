"""
Every record of money changing hands names how: Cash, Card or Transfer
(audit B10).

Only the two refund routes checked it. The POS, the visit / boarding /
inpatient payment routes and the two supplier payment routes stored whatever
was posted, including nothing. The Cash Register sums the drawer by method,
so anything outside the three was money in no bucket — the day's cash total
wrong, with nothing on screen to say so. core.clean_payment_method() is now
the one check, and the database refuses anything else as well.
"""
from decimal import Decimal as D

import pytest

import core
from conftest import needs_db
from test_money_routes import (_bill, _checkout, _pay, _pay_visit, boarding, distributor_bill,  # noqa: F401
                               inpatient_case, priced_service, sellable, visit)
from test_supplier_routes import consignment_item, distributor, sell_consigned  # noqa: F401

REQUIRED_BAD = ["Bitcoin", "cash", "", None]      # None: the field left out entirely
OPTIONAL_BAD = ["Bitcoin", "cash"]


def _data(method, key="method", **rest):
    return rest if method is None else {**rest, key: method}


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["Bitcoin", "cash", "Other", "", None, "Cash;"])
def test_a_required_method_must_be_one_of_the_three(raw):
    with pytest.raises(core.BadPaymentMethod):
        core.clean_payment_method(raw)


def test_control_the_three_are_accepted_and_blank_is_allowed_where_optional():
    assert [core.clean_payment_method(m) for m in ("Cash", "Card", "Transfer", " Card ")] == \
        ["Cash", "Card", "Transfer", "Card"]
    assert core.clean_payment_method("", required=False) is None
    assert core.clean_payment_method(None, required=False) is None
    with pytest.raises(core.BadPaymentMethod):
        core.clean_payment_method("Bitcoin", required=False)


# ---------------------------------------------------------------------------
# The clinic's own payments: required
# ---------------------------------------------------------------------------

def _count(db, sql, arg):
    return db.execute(sql, (arg,)).fetchone()["c"]


@needs_db
@pytest.mark.parametrize("method", REQUIRED_BAD)
def test_a_visit_payment_needs_a_real_method(client, db, visit, method):
    """GUARD."""
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="100.000")
    resp = _pay_visit(client, visit["visit_id"], **_data(method, amount="10.000"))
    assert resp.status_code == 200
    assert _count(db, "SELECT COUNT(*) c FROM payments WHERE visit_id=?", visit["visit_id"]) == 0


@needs_db
def test_control_a_visit_payment_by_card(client, db, visit):
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="100.000")
    assert _pay_visit(client, visit["visit_id"], amount="10.000", method="Card").status_code == 302
    assert db.execute("SELECT method FROM payments WHERE visit_id=?", (visit["visit_id"],)).fetchone()["method"] == "Card"


@needs_db
@pytest.mark.parametrize("method", REQUIRED_BAD)
def test_a_boarding_payment_needs_a_real_method(client, db, boarding, method):
    """GUARD."""
    resp = _pay(client, boarding["id"], **_data(method, amount="10.000"))
    assert resp.status_code == 200
    assert _count(db, "SELECT COUNT(*) c FROM payments WHERE boarding_id=?", boarding["id"]) == 0


@needs_db
def test_control_a_boarding_payment_by_transfer(client, db, boarding):
    assert _pay(client, boarding["id"], amount="10.000", method="Transfer").status_code == 302
    assert _count(db, "SELECT COUNT(*) c FROM payments WHERE boarding_id=?", boarding["id"]) == 1


def _bill_case(client, case_id, service_id):
    resp = client.post(f"/inpatient/{case_id}/billing",
                       data={"price_id": service_id, f"qty_{service_id}": "1"}, follow_redirects=False)
    assert resp.status_code == 302, "the case could not be billed — the test would prove nothing"


@needs_db
@pytest.mark.parametrize("method", REQUIRED_BAD)
def test_an_inpatient_payment_needs_a_real_method(client, db, inpatient_case, priced_service, method):
    """GUARD."""
    _bill_case(client, inpatient_case["id"], priced_service["id"])
    resp = client.post(f"/inpatient/{inpatient_case['id']}/payment", data=_data(method, amount="1.000"))
    assert resp.status_code == 200
    assert _count(db, "SELECT COUNT(*) c FROM payments WHERE inpatient_case_id=?", inpatient_case["id"]) == 0


@needs_db
def test_control_an_inpatient_payment_in_cash(client, db, inpatient_case, priced_service):
    _bill_case(client, inpatient_case["id"], priced_service["id"])
    resp = client.post(f"/inpatient/{inpatient_case['id']}/payment", data={"amount": "1.000", "method": "Cash"})
    assert resp.status_code == 302
    assert _count(db, "SELECT COUNT(*) c FROM payments WHERE inpatient_case_id=?", inpatient_case["id"]) == 1


@needs_db
@pytest.mark.parametrize("method", REQUIRED_BAD)
def test_a_pos_sale_needs_a_real_method(client, db, sellable, method):
    """GUARD."""
    extra = {} if method is None else {"payment_method": method}
    resp = _checkout(client, sellable["inv_id"], qty=1, **extra)
    assert resp.status_code == 200
    assert _count(db, "SELECT COUNT(*) c FROM sale_items WHERE item_id=?", sellable["inv_id"]) == 0


@needs_db
def test_control_a_pos_sale_by_card(client, db, sellable):
    assert _checkout(client, sellable["inv_id"], qty=1, payment_method="Card").status_code == 302
    assert _count(db, "SELECT COUNT(*) c FROM sale_items WHERE item_id=?", sellable["inv_id"]) == 1


# ---------------------------------------------------------------------------
# Supplier payments: optional, but never something else
# ---------------------------------------------------------------------------

def _pay_bill(client, d, method):
    return client.post(f"/distributors/{d['dist_id']}/bills/{d['bill_id']}/payments/new",
                       data=_data(method, amount="1.000"), follow_redirects=False)


@needs_db
@pytest.mark.parametrize("method", OPTIONAL_BAD)
def test_a_supplier_bill_payment_refuses_an_unknown_method(client, db, distributor_bill, method):
    """GUARD."""
    _pay_bill(client, distributor_bill, method)
    assert _count(db, "SELECT COUNT(*) c FROM distributor_bill_payments WHERE bill_id=?",
                  distributor_bill["bill_id"]) == 0


@needs_db
@pytest.mark.parametrize("method,stored", [("Transfer", "Transfer"), ("", None)])
def test_control_a_supplier_bill_payment_by_transfer_or_unrecorded(client, db, distributor_bill, method, stored):
    assert _pay_bill(client, distributor_bill, method).status_code == 302
    row = db.execute("SELECT method FROM distributor_bill_payments WHERE bill_id=?",
                     (distributor_bill["bill_id"],)).fetchone()
    assert row is not None and row["method"] == stored


def _settle(client, dist, amount, method):
    return client.post(f"/consignment/settlements/{dist}/new",
                       data=_data(method, key="payment_method", amount_paid=amount), follow_redirects=False)


@needs_db
@pytest.mark.parametrize("method", OPTIONAL_BAD)
def test_a_consignment_settlement_refuses_an_unknown_method(client, db, sell_consigned, consignment_item, method):
    """GUARD."""
    owed = sell_consigned(2, "2.000", "3.500")
    dist = consignment_item["distributor_id"]
    assert _settle(client, dist, str(owed), method).status_code == 200
    assert _count(db, "SELECT COUNT(*) c FROM consignment_settlements WHERE distributor_id=?", dist) == 0


@needs_db
def test_control_a_consignment_settlement_without_a_method(client, db, sell_consigned, consignment_item):
    owed = sell_consigned(2, "2.000", "3.500")
    dist = consignment_item["distributor_id"]
    assert _settle(client, dist, str(owed), "").status_code == 302
    assert _count(db, "SELECT COUNT(*) c FROM consignment_settlements WHERE distributor_id=?", dist) == 1


# ---------------------------------------------------------------------------
# The database holds the same line (defence in depth)
# ---------------------------------------------------------------------------

@needs_db
@pytest.mark.parametrize("table,column", [
    ("payments", "method"), ("sales", "payment_method"), ("refunds", "refund_method"),
    ("distributor_bill_payments", "method"), ("consignment_settlements", "payment_method")])
def test_the_database_refuses_any_other_method(db, table, column):
    checks = [r["def"] for r in db.execute(
        "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint WHERE conrelid = ?::regclass AND contype = 'c'",
        (table,)).fetchall()]
    assert any(column in c and all(f"'{m}'" in c for m in core.PAYMENT_METHODS) for c in checks), checks
