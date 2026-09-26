"""
An item with no sale price is not billed.

The billing search offers only priced items, but the routes did not agree:
a crafted form, or a price cleared while a bill was open, reached a visit bill
as `quantity * None` (a 500) and an inpatient bill as a line with no price.
That line was billed at 0 and stored at 0 -- and priced later from the live
Price List, so setting the item's price afterwards changed a past bill's page
while the stored total the reports read stayed at 0. Now both routes skip the
item and say so, and an inpatient line must carry its price (NOT NULL).
"""
from decimal import Decimal as D

import psycopg
import pytest

from conftest import needs_db
from test_money_routes import _uid, inpatient_case, priced_service, visit  # noqa: F401

pytestmark = needs_db
MESSAGE = "no sale price in the Price List"


@pytest.fixture
def unpriced_service(db):
    pl_id = _uid("PL")
    db.execute("INSERT INTO price_list (id, name, category, cost_price, sale_price, active, can_discount) "
               "VALUES (%s,%s,'Service',NULL,NULL,true,true)", (pl_id, f"Unpriced Service {pl_id}"))
    db.commit()
    yield pl_id
    for sql in ("DELETE FROM inpatient_billing WHERE price_id=%s", "DELETE FROM visit_billing_lines WHERE price_id=%s",
                "DELETE FROM price_list WHERE id=%s"):
        db.execute(sql, (pl_id,))
    db.commit()


def _visit_lines(db, visit_id):
    return {r["price_id"] for r in db.execute("SELECT price_id FROM visit_billing_lines WHERE visit_id=%s",
                                               (visit_id,)).fetchall()}


def test_a_visit_bill_skips_an_unpriced_item_and_says_so(client, db, visit, priced_service, unpriced_service):
    """GUARD, with the priced item beside it as the control."""
    resp = client.post(f"/visits/{visit['visit_id']}/billing", follow_redirects=True, data={
        "billing_type": "Automatic", "price_id": [priced_service["id"], unpriced_service],
        f"qty_{priced_service['id']}": "1", f"qty_{unpriced_service}": "1"})
    assert resp.status_code == 200
    assert _visit_lines(db, visit["visit_id"]) == {priced_service["id"]}
    assert MESSAGE in resp.get_data(as_text=True)
    total = db.execute("SELECT total FROM billing WHERE visit_id=%s", (visit["visit_id"],)).fetchone()["total"]
    assert total == priced_service["price"]


def test_a_visit_bill_of_only_unpriced_items_is_refused_not_a_500(client, db, visit, unpriced_service):
    resp = client.post(f"/visits/{visit['visit_id']}/billing", follow_redirects=True, data={
        "billing_type": "Automatic", "price_id": unpriced_service, f"qty_{unpriced_service}": "1"})
    assert resp.status_code == 200
    assert _visit_lines(db, visit["visit_id"]) == set()
    assert MESSAGE in resp.get_data(as_text=True)


def test_an_inpatient_bill_skips_an_unpriced_item_and_says_so(client, db, inpatient_case, priced_service,
                                                               unpriced_service):
    """GUARD, with the control beside it."""
    resp = client.post(f"/inpatient/{inpatient_case['id']}/billing", follow_redirects=True, data={
        "price_id": [priced_service["id"], unpriced_service],
        f"qty_{priced_service['id']}": "2", f"qty_{unpriced_service}": "1"})
    assert resp.status_code == 200
    rows = db.execute("SELECT price_id, unit_price FROM inpatient_billing WHERE case_id=%s",
                      (inpatient_case["id"],)).fetchall()
    assert [(r["price_id"], r["unit_price"]) for r in rows] == [(priced_service["id"], priced_service["price"])]
    assert MESSAGE in resp.get_data(as_text=True)
    total = db.execute("SELECT total FROM inpatient_cases WHERE id=%s", (inpatient_case["id"],)).fetchone()["total"]
    assert total == priced_service["price"] * 2


def test_an_inpatient_line_cannot_be_stored_without_its_price(db, inpatient_case, unpriced_service):
    """GUARD, the database's half: the snapshot is required."""
    with pytest.raises(psycopg.errors.NotNullViolation):
        db.execute("INSERT INTO inpatient_billing (case_id, price_id, quantity, unit_price, discountable, timestamp) "
                   "VALUES (%s,%s,1,NULL,true,now())", (inpatient_case["id"], unpriced_service))
    db.rollback()
    db.execute("INSERT INTO inpatient_billing (case_id, price_id, quantity, unit_price, discountable, timestamp) "
               "VALUES (%s,%s,1,%s,true,now())", (inpatient_case["id"], unpriced_service, D("0")))
    db.rollback()
