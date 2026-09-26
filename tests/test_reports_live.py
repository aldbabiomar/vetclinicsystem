"""
The P&L and Insights, computed on read from the stored bill totals (plan D-3).

Each test puts its bill in a month of its own (in 2001) so the month's
figure is exactly what the test created, whatever else the database holds.

The audit findings these pin:
  B2  a Clean Up or discount taken with a payment left the month's P&L stale
      until someone pressed Rebuild;
  B3  boarding was booked at its pre-discount total and inpatient without its
      Clean Up, and Insights re-derived revenue and disagreed with the P&L;
  B9  a restocked refund reversed COGS at TODAY's cost, not the sale's;
  B14 the Rebuild button itself could erase a concurrent sale.
"""
from datetime import date
from decimal import Decimal as D

import pytest

from vcs import clock
from vcs.domain import logic
from vcs.domain import reports
from conftest import ADMIN_ID, needs_db
# Fixtures and helpers from the money route tests, reused rather than copied.
from test_money_routes import (_bill, _checkout, _latest_sale, _pay, _pay_visit, _refund_retail,  # noqa: F401
                               boarding, inpatient_case, priced_service, sellable, visit)

pytestmark = needs_db


def _month(db, month):
    return reports.by_month(db, only_month=month).get(month, (D(0), D(0)))


# ---------------------------------------------------------------------------
# B2 — the month follows every change to a bill, with nothing to rebuild
# ---------------------------------------------------------------------------

def test_a_clean_up_taken_at_payment_lowers_the_months_revenue_at_once(client, db, visit):
    """GUARD. The P&L used to read a summary row that the payment route never
    refreshed; the Clean Up only reached it after a Rebuild."""
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="100.000", date_billed="2001-01-15")
    assert _month(db, "2001-01")[0] == D("100.000")
    _pay_visit(client, visit["visit_id"], amount="99.000", method="Cash", cleanup_amount="1.000")
    assert _month(db, "2001-01")[0] == D("99.000"), "the Clean Up did not reach the month's revenue"


def test_a_boarding_discount_at_payment_is_booked_at_the_discounted_total(client, db, boarding):
    """GUARD (B3). The stay's revenue is what it was billed after the
    discount — billed_total — not the pre-discount subtotal."""
    db.execute("UPDATE boarding_sessions SET entry_date=? WHERE id=?", (date(2001, 2, 10), boarding["id"]))
    db.commit()
    resp = _pay(client, boarding["id"], amount="10.000", discount_percent="10", method="Cash")
    assert resp.status_code == 302, "the discounted payment was refused — the test would prove nothing"
    billed = db.execute("SELECT billed_total FROM boarding_sessions WHERE id=?", (boarding["id"],)).fetchone()["billed_total"]
    assert billed == D("180.000")
    assert _month(db, "2001-02")[0] == D("180.000")


def test_an_inpatient_clean_up_lowers_the_cases_revenue(client, db, inpatient_case, priced_service):
    """GUARD (B3). The case's revenue is its stored total — after its Clean
    Up — spread over the months its procedures were logged."""
    client.post(f"/inpatient/{inpatient_case['id']}/billing",
                data={"price_id": priced_service["id"], f"qty_{priced_service['id']}": "1"},
                follow_redirects=False)
    db.execute("UPDATE inpatient_billing SET timestamp=? WHERE case_id=?",
               ("2001-03-10T10:00:00+03:00", inpatient_case["id"]))
    db.commit()
    client.post(f"/inpatient/{inpatient_case['id']}/payment",
                data={"amount": "11.000", "method": "Cash", "cleanup_amount": "1.000"}, follow_redirects=False)
    total = db.execute("SELECT total FROM inpatient_cases WHERE id=?", (inpatient_case["id"],)).fetchone()["total"]
    assert total == D("11.000"), "the Clean Up was not applied — the test would prove nothing"
    assert _month(db, "2001-03")[0] == D("11.000")


def test_insights_categories_add_up_to_the_pnl_for_every_month(client, db, visit, boarding):
    """GUARD (B3). Two reports, one set of lines: for each month, the
    categories Insights shows sum exactly to the P&L's revenue."""
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="40.000", date_billed="2001-05-03")
    db.execute("UPDATE boarding_sessions SET entry_date=? WHERE id=?", (date(2001, 5, 4), boarding["id"]))
    db.commit()
    _pay(client, boarding["id"], amount="10.000", discount_percent="5", method="Cash")
    by_cat = reports.by_month_and_category(db, since_month="2001-05")
    by_month = reports.by_month(db, since_month="2001-05")
    assert "2001-05" in by_month
    for month, (revenue, cogs) in by_month.items():
        assert revenue == sum(r for r, _ in by_cat[month].values()), month
        assert cogs == sum(c for _, c in by_cat[month].values()), month
    assert by_cat["2001-05"]["Service"][0] == D("40.000")
    assert by_cat["2001-05"]["Boarding"][0] == D("190.000")


# ---------------------------------------------------------------------------
# B9 — a restocked refund reverses the cost the sale carried
# ---------------------------------------------------------------------------

def test_a_restocked_refund_reverses_the_sale_lines_cost_not_todays(client, db, sellable):
    """GUARD. The item sold at a cost of 2.000; its cost is 5.000 by the time
    it is returned. Handing it back returns 2.000 of cost to the shelf, not
    5.000 — the cost of goods for the month of the refund falls by 2."""
    assert _checkout(client, sellable["inv_id"], qty=1, payment_method="Card").status_code == 302
    sale = _latest_sale(db)
    line = db.execute("SELECT id FROM sale_items WHERE sale_id=?", (sale["id"],)).fetchone()
    db.execute("UPDATE sales SET sold_at=? WHERE id=?", ("2001-06-05T10:00:00+03:00", sale["id"]))
    db.execute("UPDATE inventory_list SET cost_price=? WHERE id=?", (D("5.000"), sellable["inv_id"]))
    db.commit()
    try:
        resp = _refund_retail(client, sale["id"], line["id"], 1, restock="on", refund_date="2001-06-20")
        assert resp.status_code == 302, "the refund was refused — the test would prove nothing"
        revenue, cogs = _month(db, "2001-06")
        assert cogs == D("0.000"), f"sold at 2.000 cost and returned: net cost {cogs}, expected 0"
    finally:
        db.execute("DELETE FROM refund_items WHERE refund_id IN (SELECT id FROM refunds WHERE sale_id=?)", (sale["id"],))
        db.execute("DELETE FROM refunds WHERE sale_id=?", (sale["id"],))
        db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale["id"],))
        db.execute("DELETE FROM sales WHERE id=?", (sale["id"],))
        db.commit()


# ---------------------------------------------------------------------------
# B14 / D-3 — nothing to rebuild
# ---------------------------------------------------------------------------

def test_there_is_no_summary_table_and_no_rebuild(client, db):
    assert db.execute("SELECT to_regclass('public.monthly_financial_summary') AS t").fetchone()["t"] is None
    assert client.post("/reports/rebuild").status_code == 404
    html = client.get("/reports").get_data(as_text=True)
    assert "Rebuild" not in html


@pytest.fixture
def medicine(db):
    from test_money_routes import _uid
    pl_id = _uid("PL")
    db.execute("INSERT INTO price_list (id, name, category, cost_price, sale_price, active, can_discount) "
               "VALUES (?,?,?,?,?,?,?)", (pl_id, f"Report Medicine {pl_id}", "Medicine", D("3.000"), D("8.000"), True, True))
    db.commit()
    yield {"id": pl_id}
    db.execute("DELETE FROM visit_billing_lines WHERE price_id=?", (pl_id,))
    db.execute("DELETE FROM price_list WHERE id=?", (pl_id,))
    db.commit()


def test_an_itemised_bill_is_split_by_category_and_still_sums_to_what_was_charged(
        client, db, visit, priced_service, medicine):
    """GUARD. A 12.000 service and an 8.000 medicine, less a 1.000 Clean Up
    at payment: 19.000 charged. By category it is 11.400 + 7.600 — each
    line's share of the STORED total — never 12 + 8 = 20."""
    resp = _bill(client, visit["visit_id"], billing_type="Automatic", date_billed="2001-07-10",
                 price_id=[priced_service["id"], medicine["id"]],
                 **{f"qty_{priced_service['id']}": "1", f"qty_{medicine['id']}": "1"})
    assert resp.status_code == 302, "the itemised bill was refused — the test would prove nothing"
    _pay_visit(client, visit["visit_id"], amount="19.000", method="Cash", cleanup_amount="1.000")
    by_cat = reports.by_month_and_category(db, since_month="2001-07")["2001-07"]
    assert by_cat["Service"][0] == D("11.400") and by_cat["Medicine"][0] == D("7.600"), by_cat
    assert _month(db, "2001-07") == (D("19.000"), D("7.000")), "revenue 19 charged, cost 4 + 3"
