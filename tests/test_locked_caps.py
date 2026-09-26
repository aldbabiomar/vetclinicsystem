"""
Two caps that were checked without the lock that makes them caps (audit B15).

Each test plays the race deterministically: the test's own connection is
the FIRST request — it takes the lock the route takes and writes its payout
or refund, and does not commit yet. The route is then called from another
thread as the SECOND request. With the lock it must wait, and once the
first commits, see it and refuse. Without the lock it does not wait, reads
the total without the first's write, and the two together break the cap.
"""
import threading
import time
from decimal import Decimal as D

from vcs import clock
from vcs.domain import logic
from conftest import ADMIN_ID, needs_db
from vcs.web.blueprints import sales as sales_routes
from test_money_routes import _checkout, sellable  # noqa: F401

pytestmark = needs_db

WAIT = 0.8   # seconds the second request is given to prove it is waiting


def _in_background(call):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("resp", call()), daemon=True)
    t.start()
    return t, out


def test_two_payouts_cannot_together_take_more_than_the_drawer(client, db, sellable):
    """GUARD. The first payout takes all but 1.000 of the drawer; the second
    asks for 2.000."""
    today = clock.today()
    assert _checkout(client, sellable["inv_id"], qty=1, payment_method="Cash").status_code == 302
    drawer = logic.cash_register_totals(db, today.isoformat())["Cash"]
    assert drawer >= D("2.000"), "no cash in the drawer — the test would prove nothing"
    try:
        db.execute("SELECT pg_advisory_xact_lock(?, ?)", (sales_routes.DRAWER_LOCK_NAMESPACE, today.toordinal()))
        db.execute("INSERT INTO cash_register_payouts (payout_date, amount, reason, logged_by, created_at) "
                   "VALUES (?,?,?,?,now())", (today, drawer - D("1.000"), "B15 first payout", ADMIN_ID))
        t, out = _in_background(lambda: client.post("/cash-register/payout", data={
            "day": today.isoformat(), "amount": "2.000", "reason": "B15 second payout"}))
        time.sleep(WAIT)
        waited = t.is_alive()
        db.commit()
        t.join(15)
        taken = db.execute("SELECT COALESCE(SUM(amount), 0) s FROM cash_register_payouts "
                           "WHERE payout_date=? AND reason LIKE ?", (today, "B15 %")).fetchone()["s"]
        assert waited, "the second payout did not wait for the first"
        assert taken <= drawer, f"{taken} paid out of a drawer holding {drawer}"
        assert out["resp"].status_code == 200, "the second payout should have been refused"
    finally:
        db.rollback()
        db.execute("DELETE FROM audit_log WHERE table_name='cash_register_payouts' AND record_id IN "
                   "(SELECT id::text FROM cash_register_payouts WHERE reason LIKE ?)", ("B15 %",))
        db.execute("DELETE FROM cash_register_payouts WHERE reason LIKE ?", ("B15 %",))
        db.commit()


def test_control_one_payout_within_the_drawer_is_logged(client, db, sellable):
    today = clock.today()
    assert _checkout(client, sellable["inv_id"], qty=1, payment_method="Cash").status_code == 302
    try:
        resp = client.post("/cash-register/payout", data={"day": today.isoformat(), "amount": "1.000",
                                                            "reason": "B15 control payout"})
        assert resp.status_code == 302
    finally:
        db.execute("DELETE FROM audit_log WHERE table_name='cash_register_payouts' AND record_id IN "
                   "(SELECT id::text FROM cash_register_payouts WHERE reason LIKE ?)", ("B15 %",))
        db.execute("DELETE FROM cash_register_payouts WHERE reason LIKE ?", ("B15 %",))
        db.commit()


def test_two_refunds_of_different_lines_cannot_together_exceed_the_sale(client, db, sellable):
    """GUARD. Two lines of 10.000, a 5.000 Clean Up at the till: the sale
    collected 15.000. The first refund (line A, 10.000) is held open; the
    second (line B, 10.000) locks only ITS line's row — the sale-level cap is
    what must stop it."""
    inv = sellable["inv_id"]
    sale_id = db.execute(
        "INSERT INTO sales (sold_at, cashier_id, subtotal, discount_percent, total, payment_method, cleanup_amount) "
        "VALUES (now(),?,?,0,?,'Cash',?) RETURNING id", (ADMIN_ID, D("20.000"), D("15.000"), D("5.000"))).fetchone()["id"]
    line_a, line_b = [db.execute(
        "INSERT INTO sale_items (sale_id, item_id, quantity, unit_price, line_total, discountable) "
        "VALUES (?,?,1,?,?,true) RETURNING id", (sale_id, inv, D("10.000"), D("10.000"))).fetchone()["id"] for _ in "ab"]
    db.commit()
    try:
        db.execute("SELECT id FROM sales WHERE id=? FOR UPDATE", (sale_id,))
        refund_id = db.execute(
            "INSERT INTO refunds (refund_type, refund_date, amount, restocked, sale_id, reason, refund_method, "
            "processed_by, created_at) VALUES ('retail', ?, ?, false, ?, 'B15 first refund', 'Cash', ?, now()) "
            "RETURNING id", (clock.today(), D("10.000"), sale_id, ADMIN_ID)).fetchone()["id"]
        db.execute("INSERT INTO refund_items (refund_id, item_id, quantity, unit_price, line_total, sale_item_id) "
                   "VALUES (?,?,1,?,?,?)", (refund_id, inv, D("10.000"), D("10.000"), line_a))
        t, out = _in_background(lambda: client.post("/refunds/retail", data={
            "sale_id": str(sale_id), "sale_item_id": str(line_b), "quantity": "1",
            "refund_method": "Cash", "reason": "B15 second refund"}))
        time.sleep(WAIT)
        waited = t.is_alive()
        db.commit()
        t.join(15)
        refunded = db.execute("SELECT COALESCE(SUM(amount), 0) s FROM refunds WHERE sale_id=?", (sale_id,)).fetchone()["s"]
        assert waited, "the second refund did not wait for the first"
        assert refunded <= D("15.000"), f"{refunded} refunded on a sale that collected 15.000"
    finally:
        db.rollback()
        db.execute("DELETE FROM audit_log WHERE table_name='refunds' AND record_id IN "
                   "(SELECT id::text FROM refunds WHERE sale_id=?)", (sale_id,))
        db.execute("DELETE FROM refund_items WHERE refund_id IN (SELECT id FROM refunds WHERE sale_id=?)", (sale_id,))
        db.execute("DELETE FROM refunds WHERE sale_id=?", (sale_id,))
        db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
        db.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        db.commit()
