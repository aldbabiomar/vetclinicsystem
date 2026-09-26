"""
The audit sheet counts stock received through Consignment Receiving
(audit B18).

An item's usage is prior count + received since prior - count, and
"received since prior" was typed by hand. Consignment receipts were already
recorded but never offered there, so unless staff typed them twice, usage
came out understated or negative, and so did the Ordering Sheet.
"""
import re
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from vcs import clock
from conftest import ADMIN_ID, needs_db
from test_money_routes import sellable  # noqa: F401  (an item with a confirmed audit)

pytestmark = needs_db


@pytest.fixture
def draft(db):
    sid = db.execute("INSERT INTO audit_sessions (audit_date, performed_by, status, created_at) "
                     "VALUES (%s,%s,'Draft',now()) RETURNING id", (date(2001, 1, 2), ADMIN_ID)).fetchone()["id"]
    db.commit()
    yield sid
    db.execute("DELETE FROM audit_session_lines WHERE session_id=%s", (sid,))
    db.execute("DELETE FROM audit_sessions WHERE id=%s", (sid,))
    db.commit()


def _txn(db, item_id, qty, reason, when):
    db.execute("INSERT INTO inventory_transactions (item_id, change_qty, reason, ref_id, timestamp, user_id) "
               "VALUES (%s,%s,%s,%s,%s,%s)", (item_id, D(qty), reason, "B18", when, ADMIN_ID))
    db.commit()


def _received_default(client, sid, item_id):
    page = client.get(f"/audit-history/session/{sid}").get_data(as_text=True)
    m = re.search(rf'name="received_{item_id}" value="([^"]*)"', page)
    assert m, "the item is not on the audit sheet — the test would prove nothing"
    return m.group(1), page


def test_a_consignment_receipt_since_the_last_audit_is_offered(client, db, sellable, draft):
    """GUARD. 6 received through Consignment Receiving after the last count."""
    _txn(db, sellable["inv_id"], "6", "consignment_receipt", clock.now() + timedelta(seconds=1))
    value, page = _received_default(client, draft, sellable["inv_id"])
    assert value == "6"
    assert "Includes 6 from Consignment Receiving" in page


def test_control_receipts_before_the_last_audit_and_other_movements_are_not(client, db, sellable, draft):
    """A receipt before the last confirmed count is already in that count; a
    sale is not a receipt."""
    _txn(db, sellable["inv_id"], "4", "consignment_receipt", clock.now() - timedelta(days=2))
    _txn(db, sellable["inv_id"], "-1", "sale", clock.now() + timedelta(seconds=1))
    value, _page = _received_default(client, draft, sellable["inv_id"])
    assert value == "0"
