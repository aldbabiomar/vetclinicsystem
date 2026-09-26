"""
A refund is dated between the day the money came in and today, and a
payment is recorded on the day it is taken (audit B16).

A refund accepted any valid date: one before the sale put negative revenue
into a month the sale never touched, one in the future put money leaving the
drawer on a day that had not happened. The visit and inpatient payment
routes read an undocumented `date` field no form sends; boarding always used
today. Now all three use today.
"""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from vcs import clock
from conftest import ADMIN_ID, needs_db
from test_money_routes import (_bill, _checkout, _latest_sale, _pay_visit, _refund_retail,  # noqa: F401
                               completed_sale, sellable, visit)

pytestmark = needs_db


def _day(offset):
    return (clock.today() + timedelta(days=offset)).isoformat()


def _retail_refunds(db, sale_id):
    return db.execute("SELECT COUNT(*) c FROM refunds WHERE sale_id=?", (sale_id,)).fetchone()["c"]


@pytest.mark.parametrize("offset", [-1, 1])
def test_a_retail_refund_is_not_dated_before_the_sale_or_after_today(client, db, completed_sale, offset):
    """GUARD. The sale happened today: yesterday and tomorrow are refused."""
    sale = completed_sale["sale"]
    resp = _refund_retail(client, sale["id"], completed_sale["line"]["id"], 1, refund_date=_day(offset))
    assert resp.status_code == 200
    assert _retail_refunds(db, sale["id"]) == 0


def test_control_a_retail_refund_dated_today(client, db, completed_sale):
    sale = completed_sale["sale"]
    assert _refund_retail(client, sale["id"], completed_sale["line"]["id"], 1, refund_date=_day(0)).status_code == 302
    assert _retail_refunds(db, sale["id"]) == 1


@pytest.fixture
def paid_visit_five_days_ago(client, db, visit):
    db.execute("UPDATE visits SET date=? WHERE id=?", (_day(-5), visit["visit_id"]))
    db.commit()
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="100.000")
    db.execute("INSERT INTO payments (visit_id, amount, method, date, user_id) VALUES (?,?,?,?,?)",
               (visit["visit_id"], D("50.000"), "Cash", _day(-5), ADMIN_ID))
    db.commit()
    yield visit
    db.execute("DELETE FROM refunds WHERE visit_id=?", (visit["visit_id"],))
    db.commit()


def _service_refund(client, visit_id, refund_date):
    return client.post("/refunds/service", data={"visit_id": visit_id, "amount": "10.000", "refund_method": "Cash",
                                                  "reason": "dated refund", "refund_date": refund_date})


@pytest.mark.parametrize("offset", [-6, 1])
def test_a_service_refund_is_not_dated_before_the_visit_or_after_today(client, db, paid_visit_five_days_ago, offset):
    """GUARD. The visit was five days ago."""
    vid = paid_visit_five_days_ago["visit_id"]
    assert _service_refund(client, vid, _day(offset)).status_code == 200
    assert db.execute("SELECT COUNT(*) c FROM refunds WHERE visit_id=?", (vid,)).fetchone()["c"] == 0


@pytest.mark.parametrize("offset", [-5, 0])
def test_control_a_service_refund_dated_on_the_visit_or_since(client, db, paid_visit_five_days_ago, offset):
    vid = paid_visit_five_days_ago["visit_id"]
    assert _service_refund(client, vid, _day(offset)).status_code == 302


def test_a_visit_payment_is_recorded_today_whatever_date_is_posted(client, db, visit):
    """GUARD. No form sends `date`; a crafted one no longer back-dates it."""
    _bill(client, visit["visit_id"], billing_type="Manual", manual_amount="100.000")
    assert _pay_visit(client, visit["visit_id"], amount="10.000", method="Cash", date="2001-01-01").status_code == 302
    row = db.execute("SELECT date FROM payments WHERE visit_id=?", (visit["visit_id"],)).fetchone()
    assert row["date"] == clock.today()
