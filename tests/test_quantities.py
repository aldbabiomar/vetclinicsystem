"""
Counts and measurements are exact decimals (NUMERIC), like money.

Until phase 2b, stock counts, stock movements and weights were floats while
the quantities beside them (sale lines, refunds, receipts) were NUMERIC — so
one stock comparison mixed the two types, and every display had its own idea
of how to print a number ("× 1.000" on a receipt, "2.0" in consignment, a
fractional refund quantity truncated by |int). These pin the one formatter,
the one wire format, the arithmetic that changes meaning on a Decimal, and
the schema rule that no numeric column accepts NaN.
"""
from vcs import clock
import json
import pathlib
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal as D

import pytest

from vcs.web import core
from vcs.domain import display, inventory
from conftest import new_id, ADMIN_ID, needs_db

SNAPSHOT = pathlib.Path(__file__).parent / "schema_snapshot.json"


# ---------------------------------------------------------------------------
# The formatter and the wire format (no database)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,shown", [
    (D("12.000"), "12"), (D("2.500"), "2.5"), (D("0.125"), "0.125"), (D("1E+1"), "10"),
    (D("0.000"), "0"), (D("-0"), "0"), (10, "10"), (12.5, "12.5"), (None, ""),
])
def test_a_quantity_is_shown_without_its_column_tail(value, shown):
    assert display.format_quantity(value) == shown


def test_control_the_g_format_is_why_the_formatter_exists():
    """f"{x:g}" was the idiom before; on a Decimal read from a NUMERIC(10,3)
    column it keeps every zero. If this ever stops being true, the formatter
    is still right — but the reason for it is gone."""
    assert f"{D('12.000'):g}" == "12.000"


# ---------------------------------------------------------------------------
# The schema: no floats, and no numeric column that accepts NaN
# ---------------------------------------------------------------------------

def _snapshot():
    return json.loads(SNAPSHOT.read_text())


def test_no_column_is_a_float():
    snap = _snapshot()
    floats = [f"{t}.{c}" for t, d in snap.items() for c, col in d["columns"].items()
              if col["type"] in ("double precision", "real")]
    assert not floats, f"float columns: {floats} — counts and money are NUMERIC"


# Tables whose numeric columns may skip the rule, each with a reason. None.
_EXEMPT_TABLES = set()


def _nan_guarded(defs, column):
    """A CHECK that names the column and excludes NaN — either explicitly, or
    by an upper bound (NaN sorts above every number, so `<= 100` excludes
    it; `>= 0` does NOT)."""
    for d in defs:
        if not d.startswith("CHECK") or column not in d:
            continue
        if "'NaN'" in d or f"{column} <= " in d:
            return True
    return False


def test_control_the_nan_rule_reads_the_way_postgres_writes_it():
    assert _nan_guarded(["CHECK (((total >= (0)::numeric) AND (total <> 'NaN'::numeric)))"], "total")
    assert _nan_guarded(["CHECK (((discount_percent >= (0)::numeric) AND "
                         "(discount_percent <= (100)::numeric)))"], "discount_percent")
    assert not _nan_guarded(["CHECK ((total >= (0)::numeric))"], "total")


def test_every_numeric_column_refuses_nan():
    """GUARD (plan §4.1). Postgres NUMERIC can hold NaN, and NaN passes
    `>= 0`. A column added later without a CHECK fails here, so this is a
    ratchet as much as a test."""
    snap = _snapshot()
    missing = []
    for t, d in sorted(snap.items()):
        if t in _EXEMPT_TABLES:
            continue
        defs = list(d["constraints"].values())
        for c, col in d["columns"].items():
            if col["type"].startswith("numeric") and not _nan_guarded(defs, c):
                missing.append(f"{t}.{c}")
    assert not missing, f"numeric columns with no NaN-excluding CHECK: {missing}"


@needs_db
@pytest.mark.parametrize("bad", ["NaN", "-1"])
def test_the_database_itself_refuses_a_nan_or_negative_amount(db, bad):
    """The snapshot check above says what the constraints ARE; this proves
    one of them does what it says, against the real database."""
    import psycopg
    month = f"1999-{uuid.uuid4().int % 12 + 1:02d}"
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute("INSERT INTO monthly_opex (month, rent, salaries, utilities, marketing, other) "
                       "VALUES (?,?,0,0,0,0)", (month, D(bad)))


@needs_db
def test_control_a_zero_operating_cost_is_accepted(db):
    month = "1998-01"
    try:
        with db.transaction():
            db.execute("DELETE FROM monthly_opex WHERE month=?", (month,))
            db.execute("INSERT INTO monthly_opex (month, rent, salaries, utilities, marketing, other) "
                       "VALUES (?,0,0,0,0,0)", (month,))
    finally:
        db.execute("DELETE FROM monthly_opex WHERE month=?", (month,))
        db.commit()


# ---------------------------------------------------------------------------
# Arithmetic that changes meaning on a Decimal: the ordering sheet
# ---------------------------------------------------------------------------

@pytest.fixture
def audited_three_times(db):
    """One item counted 30 -> 20 -> 13 over twenty days: 1.0/day, then
    0.7/day. The latest line asks for 31 days of cover: 0.7 x 31 = 21.7
    needed, 13 on the shelf, 8.7 short."""
    inv_id = new_id()
    db.execute("INSERT INTO inventory_list (id, name, category, unit, track_expiry, cost_price, "
               "ownership_type, active) VALUES (?,?,?,?,?,?,?,?)",
               (inv_id, f"Ordering {inv_id}", "Retail", "unit", False, D("1.000"), "Owned", True))
    sessions = []
    today = clock.today()
    for days_ago, counted, target in ((20, "30", None), (10, "20", None), (0, "13", "31")):
        day = today - timedelta(days=days_ago)
        stamp = datetime.combine(day, datetime.min.time()).isoformat(timespec="microseconds")
        sid = db.execute("INSERT INTO audit_sessions (audit_date, performed_by, status, created_at, confirmed_at) "
                         "VALUES (?,?,?,?,?) RETURNING id",
                         (day.isoformat(), ADMIN_ID, "Confirmed", stamp, stamp)).fetchone()["id"]
        sessions.append(sid)
        db.execute("INSERT INTO audit_session_lines (session_id, item_id, stock_counted, "
                   "received_since_prior, target_coverage_days) VALUES (?,?,?,?,?)",
                   (sid, inv_id, D(counted), D(0), D(target) if target else None))
    db.commit()
    yield inv_id
    db.execute("DELETE FROM audit_session_lines WHERE item_id=?", (inv_id,))
    for sid in sessions:
        db.execute("DELETE FROM audit_sessions WHERE id=?", (sid,))
    db.execute("DELETE FROM inventory_list WHERE id=?", (inv_id,))
    db.commit()


@needs_db
def test_the_suggested_order_rounds_a_shortfall_up(db, audited_three_times):
    """GUARD. 8.7 short means order 9. The old idiom, -(-x // 1), is a
    ceiling on a float and a FLOOR on a positive Decimal (`//` truncates
    toward zero there) — it would have suggested 8, one short every time."""
    row = next(r for r in inventory.ordering_sheet(db) if r["item_id"] == audited_three_times)
    assert row["daily_usage_rate"] == D("0.7")
    assert row["suggested_order_qty"] == 9


@needs_db
def test_the_usage_trend_compares_decimals(db, audited_three_times, client):
    """GUARD. 0.7/day against 1.0/day is below the 0.85 band: Decreasing.
    `prior_rate * 0.85` with a Decimal rate raises TypeError — the whole
    Ordering Sheet page would 500 for any item with three audits."""
    row = next(r for r in inventory.ordering_sheet(db) if r["item_id"] == audited_three_times)
    assert row["usage_trend"] == "Decreasing"
    assert client.get("/ordering-sheet").status_code == 200


# ---------------------------------------------------------------------------
# What reaches the screen
# ---------------------------------------------------------------------------

@needs_db
def test_pos_lookup_sends_stock_as_a_number(client, db, audited_three_times):
    """The POS page does arithmetic on `stock` (`existing.qty + 1` after
    capping at it), so it must arrive as a number. It does because of the
    app's JSON provider (app._DecimalJSONProvider turns every Decimal into a
    number) — this pins that for the one API a page computes with."""
    pl_id = new_id()
    db.execute("INSERT INTO price_list (id, name, category, sale_price, active, linked_item_id, can_discount) "
               "VALUES (?,?,?,?,?,?,?)",
               (pl_id, "x", "Retail", D("5.000"), True, audited_three_times, True))
    db.commit()
    try:
        name = f"Ordering {audited_three_times}"
        found = client.get(f"/api/inventory/lookup?q={name}").get_json()
        hit = next(r for r in found if r["id"] == audited_three_times)
        assert hit["stock"] == 13 and isinstance(hit["stock"], (int, float))
    finally:
        db.execute("DELETE FROM price_list WHERE id=?", (pl_id,))
        db.commit()


@pytest.fixture
def sold_two(client, db):
    from test_money_routes import _checkout, _latest_sale
    inv_id, pl_id = new_id(), new_id()
    db.execute("INSERT INTO inventory_list (id, name, category, unit, track_expiry, cost_price, "
               "ownership_type, active) VALUES (?,?,?,?,?,?,?,?)",
               (inv_id, f"Receipt {inv_id}", "Retail", "unit", False, D("1.000"), "Owned", True))
    db.execute("INSERT INTO price_list (id, name, category, sale_price, active, linked_item_id, can_discount) "
               "VALUES (?,?,?,?,?,?,?)", (pl_id, f"Receipt {inv_id}", "Retail", D("5.000"), True, inv_id, True))
    sid = db.execute("INSERT INTO audit_sessions (audit_date, performed_by, status, created_at, confirmed_at) "
                     "VALUES (?,?,?,?,?) RETURNING id",
                     (clock.today().isoformat(), ADMIN_ID, "Confirmed", clock.now().isoformat(),
                      clock.now().isoformat(timespec="microseconds"))).fetchone()["id"]
    db.execute("INSERT INTO audit_session_lines (session_id, item_id, stock_counted, received_since_prior) "
               "VALUES (?,?,?,?)", (sid, inv_id, D(10), D(0)))
    db.commit()
    assert _checkout(client, inv_id, qty=2, payment_method="Card").status_code == 302
    sale = _latest_sale(db)
    yield sale["id"]
    for sql, arg in (("DELETE FROM inventory_transactions WHERE item_id=?", inv_id),
                     ("DELETE FROM sale_items WHERE item_id=?", inv_id),
                     ("DELETE FROM sales WHERE id=?", sale["id"]),
                     ("DELETE FROM audit_session_lines WHERE item_id=?", inv_id),
                     ("DELETE FROM audit_sessions WHERE id=?", sid),
                     ("DELETE FROM price_list WHERE id=?", pl_id),
                     ("DELETE FROM inventory_list WHERE id=?", inv_id)):
        db.execute(sql, (arg,))
    db.commit()


@needs_db
def test_the_receipt_quantity_has_no_column_tail(client, sold_two):
    """GUARD. The receipt printed `{{ i.quantity }}` — "× 2.000"."""
    html = client.get(f"/pos/receipt/{sold_two}").get_data(as_text=True)
    assert "× 2<" in html, "the quantity is not shown as 2"
    assert "× 2.000" not in html
