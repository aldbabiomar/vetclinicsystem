"""
Confirming an audit that counts a consignment item short says so (audit P7).

A distributor is owed for consigned units SOLD. A unit that vanished rather
than sold owes nothing, and nobody accounts for it unless it is logged as
shrinkage — so a count below what the records expect is worth a nudge.
Informational: the count is confirmed either way.
"""
from datetime import date

import pytest

from conftest import ADMIN_ID, needs_db
from test_supplier_routes import consignment_item, distributor  # noqa: F401  (50 counted on its last audit)

pytestmark = needs_db


@pytest.fixture
def draft(db):
    sid = db.execute("INSERT INTO audit_sessions (audit_date, performed_by, status, created_at) "
                     "VALUES (?,?,'Draft',now()) RETURNING id", (date(2001, 1, 3), ADMIN_ID)).fetchone()["id"]
    db.commit()
    yield sid
    db.execute("DELETE FROM audit_log WHERE table_name='audit_sessions' AND record_id=?", (str(sid),))
    db.execute("DELETE FROM audit_session_lines WHERE session_id=?", (sid,))
    db.execute("DELETE FROM audit_sessions WHERE id=?", (sid,))
    db.commit()


def _confirm(client, sid, item_id, counted):
    return client.post(f"/audit-history/session/{sid}/confirm", data={f"stock_{item_id}": counted},
                       follow_redirects=True).get_data(as_text=True)


def test_a_consignment_item_counted_short_is_flagged_at_confirm(client, db, consignment_item, draft):
    """GUARD. 50 expected, 45 counted."""
    page = _confirm(client, draft, consignment_item["id"], "45")
    assert "came in under the expected count" in page
    assert f"Consign {consignment_item['id']}" in page and "short 5" in page
    assert db.execute("SELECT status FROM audit_sessions WHERE id=?", (draft,)).fetchone()["status"] == "Confirmed"


def test_control_a_full_count_is_not_flagged(client, consignment_item, draft):
    assert "came in under the expected count" not in _confirm(client, draft, consignment_item["id"], "50")
