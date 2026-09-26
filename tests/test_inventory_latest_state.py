"""
inventory_status() reads each item's latest audit state from SQL instead of
from the item's whole audit history (audit D3/D4), and has to say exactly
what the history says.

confirmed_audit_rows_by_item() walks every confirmed audit line in Python and
is still what the Audit History page and the Ordering Sheet use, so it is the
reference: for each item, its last row by (audit_date, id) is what
inventory_status() used to read. These tests build the histories where the
two could part -- a threshold set once and carried forward, an audit dated
earlier but confirmed later, two audits the same day, a confirmation with no
confirmed_at -- and compare every field.
"""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from vcs import clock
from vcs.domain import inventory
from conftest import ADMIN_ID, needs_db, new_id

pytestmark = needs_db

FIELDS = ("stock_counted", "audit_date", "confirmed_at", "nearest_expiry_date", "effective_reorder_threshold",
          "effective_critical_item", "effective_target_coverage_days", "daily_usage_rate")


def _reference(db, item_ids):
    """{item_id: fields} from the full-history walk, as inventory_status()
    used to take them."""
    by_item = {}
    for r in inventory.confirmed_audit_rows_by_item(db):   # sorted by (audit_date, id)
        if r["item_id"] in item_ids:
            by_item[r["item_id"]] = r                        # so the last one wins
    return {i: {f: r[f] for f in FIELDS} for i, r in by_item.items()}


def _new(db, item_ids):
    got = inventory.latest_audit_state(db, item_ids)
    return {i: {f: r[f] for f in FIELDS} for i, r in got.items()}


@pytest.fixture
def history(db):
    """Items, and a function that adds an audit session with lines."""
    made = {"items": [], "sessions": []}
    today = clock.today()

    def item(name):
        iid = new_id()
        db.execute("INSERT INTO inventory_list (id, name, category, unit, track_expiry, active) "
                   "VALUES (%s,%s,'Medical','unit',true,true)", (iid, f"{name} {iid}"))
        made["items"].append(iid)
        return iid

    def audit(days_ago, lines, status="Confirmed", confirmed_hours_ago=None, no_confirmed_at=False):
        """lines: {item_id: dict of line columns}."""
        sid = new_id()
        confirmed_at = None
        if status == "Confirmed" and not no_confirmed_at:
            hours = confirmed_hours_ago if confirmed_hours_ago is not None else days_ago * 24
            confirmed_at = clock.now() - timedelta(hours=hours)
        db.execute("INSERT INTO audit_sessions (id, audit_date, performed_by, status, created_at, confirmed_at) "
                   "VALUES (%s,%s,%s,%s,%s,%s)",
                   (sid, today - timedelta(days=days_ago), ADMIN_ID, status, clock.now(), confirmed_at))
        for iid, cols in lines.items():
            cols = {"stock_counted": None, "received_since_prior": 0, **cols}
            names = ", ".join(cols)
            db.execute(f"INSERT INTO audit_session_lines (id, session_id, item_id, {names}) "
                       f"VALUES (%s,%s,%s,{', '.join(['%s'] * len(cols))})",
                       (new_id(), sid, iid, *cols.values()))
        made["sessions"].append(sid)
        return sid

    yield item, audit
    db.rollback()
    for sid in made["sessions"]:
        db.execute("DELETE FROM audit_session_lines WHERE session_id=%s", (sid,))
        db.execute("DELETE FROM audit_sessions WHERE id=%s", (sid,))
    for iid in made["items"]:
        db.execute("DELETE FROM inventory_transactions WHERE item_id=%s", (iid,))
        db.execute("DELETE FROM inventory_list WHERE id=%s", (iid,))
    db.commit()


def test_the_latest_state_matches_the_full_history_walk(db, history):
    """GUARD. Each history is one way the SQL could disagree with the walk."""
    item, audit = history
    carried, backdated, same_day, unstamped, uncounted, never = (
        item("Carried"), item("Backdated"), item("Same day"), item("Unstamped"), item("Uncounted"), item("Never"))
    # carried: threshold set on the first audit only, critical on the second,
    # target never -- each must carry forward (target defaults to 30)
    audit(60, {carried: {"stock_counted": D("50"), "reorder_threshold": D("10")}})
    audit(30, {carried: {"stock_counted": D("35"), "received_since_prior": D("5"), "critical_item": 1}})
    audit(3, {carried: {"stock_counted": D("20"), "nearest_expiry_date": clock.today() + timedelta(days=90)}})
    # backdated: dated 20 days ago but confirmed an hour ago, after an audit
    # dated 10 days ago -- the latest by date is not the last confirmed
    audit(10, {backdated: {"stock_counted": D("40"), "reorder_threshold": D("8")}}, confirmed_hours_ago=240)
    audit(20, {backdated: {"stock_counted": D("44"), "reorder_threshold": D("12")}}, confirmed_hours_ago=1)
    audit(40, {backdated: {"stock_counted": D("60")}}, confirmed_hours_ago=960)
    # same day: two audits on one date, a rate over zero days is None
    audit(5, {same_day: {"stock_counted": D("9")}}, confirmed_hours_ago=121)
    audit(5, {same_day: {"stock_counted": D("7"), "target_coverage_days": D("14")}}, confirmed_hours_ago=120)
    # unstamped: confirmed with no confirmed_at -- ordered by its date
    audit(15, {unstamped: {"stock_counted": D("30")}}, no_confirmed_at=True)
    audit(8, {unstamped: {"stock_counted": D("21"), "reorder_threshold": D("5")}})
    # uncounted: a later draft and a later uncounted line are not audits
    audit(12, {uncounted: {"stock_counted": D("15")}})
    audit(2, {uncounted: {"stock_counted": D("1")}}, status="Draft")
    audit(1, {uncounted: {"stock_counted": None, "reorder_threshold": D("99")}})
    ids = [carried, backdated, same_day, unstamped, uncounted, never]

    ref, new = _reference(db, ids), _new(db, ids)
    assert new == ref
    assert set(new) == {carried, backdated, same_day, unstamped, uncounted}, "the never-audited item has no state"
    # the cases really are the cases
    assert new[carried]["effective_reorder_threshold"] == D("10") and new[carried]["effective_critical_item"] == 1
    assert new[carried]["effective_target_coverage_days"] == 30
    assert new[backdated]["stock_counted"] == D("40"), "latest by date, not by confirmation"
    assert new[backdated]["effective_reorder_threshold"] == D("8")
    assert new[same_day]["daily_usage_rate"] is None
    assert new[uncounted]["stock_counted"] == D("15") and new[uncounted]["effective_reorder_threshold"] is None


def test_the_latest_state_matches_on_everything_in_the_database(db):
    """GUARD over whatever the rest of the suite has left: real shapes too."""
    ids = [r["id"] for r in db.execute("SELECT id FROM inventory_list").fetchall()]
    assert _new(db, ids) == _reference(db, ids)


def test_a_scoped_status_is_the_full_status_of_those_items(db, history):
    """CONTROL for the item_ids scope (audit D4): same rows, fewer of them."""
    item, audit = history
    a, b, c = item("Scoped A"), item("Scoped B"), item("Scoped C")
    audit(9, {a: {"stock_counted": D("5"), "reorder_threshold": D("6")}, b: {"stock_counted": D("50")}})
    db.execute("INSERT INTO inventory_transactions (item_id, change_qty, reason, timestamp) VALUES (%s,%s,'sale',%s)",
               (b, D("-3"), clock.now()))
    full = {r["item_id"]: r for r in inventory.inventory_status(db) if r["item_id"] in (a, b, c)}
    scoped = {r["item_id"]: r for r in inventory.inventory_status(db, [a, b, c])}
    assert scoped == full and len(scoped) == 3
    assert scoped[a]["stock_status"] == "LOW STOCK" and scoped[b]["current_stock"] == D("47")
    assert inventory.inventory_status_by_id(db, b) == full[b]
    assert inventory.inventory_status(db, []) == []
