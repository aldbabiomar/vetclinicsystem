"""
Medicine can be billed to an inpatient case, from the page (audit P2).

The billing tab was a checkbox list of category='Service' rows, rendered —
the whole service catalogue — into every case page: a medicine given to an
admitted patient could not be put on the bill from the UI at all. It is now
the visit bill's search-and-cart, over services and medicines.
"""
from decimal import Decimal as D

import pytest

from conftest import needs_db
from test_money_routes import _uid, inpatient_case, priced_service, visit  # noqa: F401

pytestmark = needs_db


@pytest.fixture
def medicine(db):
    pl_id = _uid("PL")
    db.execute("INSERT INTO price_list (id, name, category, cost_price, sale_price, active, can_discount) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s)", (pl_id, f"Ward Medicine {pl_id}", "Medicine", D("1.000"), D("4.000"), True, True))
    db.commit()
    yield {"id": pl_id, "name": f"Ward Medicine {pl_id}"}
    db.execute("DELETE FROM inpatient_billing WHERE price_id=%s", (pl_id,))
    db.execute("DELETE FROM price_list WHERE id=%s", (pl_id,))
    db.commit()


def test_the_billing_tab_searches_rather_than_listing_the_catalogue(client, inpatient_case, priced_service, medicine):
    page = client.get(f"/inpatient/{inpatient_case['id']}").get_data(as_text=True)
    assert 'id="inpatientBillSearch"' in page
    assert "category=Service&category=Medicine" in page, "the search does not cover medicines"
    for name in (medicine["name"],):
        assert name not in page, "the Price List is still rendered into the case page"


def test_the_price_list_search_finds_a_medicine(client, medicine):
    found = client.get(f"/api/price-list/lookup?q={medicine['name']}&category=Service&category=Medicine").get_json()
    assert [f["id"] for f in found] == [medicine["id"]]


def test_a_medicine_is_billed_to_the_case(client, db, inpatient_case, medicine):
    resp = client.post(f"/inpatient/{inpatient_case['id']}/billing",
                       data={"price_id": medicine["id"], f"qty_{medicine['id']}": "2"})
    assert resp.status_code == 302
    row = db.execute("SELECT quantity, unit_price FROM inpatient_billing WHERE case_id=%s AND price_id=%s",
                     (inpatient_case["id"], medicine["id"])).fetchone()
    assert row and row["quantity"] == 2 and row["unit_price"] == D("4.000")
