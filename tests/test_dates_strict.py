"""
A date that arrives in a request is exactly YYYY-MM-DD (audit B1).

Since Python 3.11, date.fromisoformat() accepts the whole ISO 8601 family:
2026-W39-4 (an ISO week), 20260925 (basic), 2026-09-25T10:00. The routes
validated with it and passed the raw text on to Postgres, which rejects the
week form — a 500 on the visits list, refunds, the cash register and the
appointment book — and compares the others as text, so the audit log and POS
history came back silently EMPTY: read as "nothing happened that day".

core.strict_date() is now the one parser for request input; the lenient
reader, renamed dates.as_date(), is for stored values only.
"""
import uuid
from datetime import date

import pytest

from vcs.web import core
from vcs.domain import dates
from conftest import ADMIN_ID, needs_db

# Every shape fromisoformat() accepts that is not the date's own spelling,
# plus the classics. Each must be refused by strict_date().
NOT_A_DATE = ["2026-W39-4", "2026W394", "20260925", "2026-9-5", "2026-09-25T10:00",
              "2026-09-25 10:00", "2026-02-30", "2026-13-01", "2026-08-25garbage", "abc", "2026-268"]


# ---------------------------------------------------------------------------
# The parsers themselves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", NOT_A_DATE)
def test_strict_date_refuses_every_other_iso_spelling(raw):
    with pytest.raises(ValueError):
        core.strict_date(raw)


def test_control_strict_date_reads_a_plain_date_and_treats_blank_as_absent():
    assert core.strict_date("2026-09-25") == date(2026, 9, 25)
    assert core.strict_date(" 2026-09-25 ") == date(2026, 9, 25)
    assert core.strict_date("") is None and core.strict_date(None) is None and core.strict_date("  ") is None


def test_the_lenient_reader_would_have_let_them_through():
    """The premise of the finding, pinned: if this ever stops being true, the
    strict parser is no longer the only thing between these and Postgres,
    and that is worth knowing."""
    assert dates.as_date("2026-W39-4") == date(2026, 9, 24)
    assert dates.as_date("20260925") == date(2026, 9, 25)


@pytest.mark.parametrize("raw", ["2026-13", "2026-00", "2026-9", "202609", "2026-W39", "2026-09-01", "abcd-ef"])
def test_strict_month_refuses_anything_but_a_real_month(raw):
    with pytest.raises(ValueError):
        core.strict_month(raw)


def test_control_strict_month_reads_a_real_month():
    assert core.strict_month("2026-09") == "2026-09"
    assert core.strict_month("") is None


@pytest.mark.parametrize("raw", ["2026-9-5", "2026-W39-4", "20260925"])
def test_clean_date_refuses_them_on_the_write_side(raw):
    with pytest.raises(core.BadDate):
        core.clean_date(raw)


def test_control_clean_date_returns_the_iso_text():
    assert core.clean_date("2026-09-05") == "2026-09-05"
    assert core.clean_date("") is None


# ---------------------------------------------------------------------------
# The pages the audit measured
# ---------------------------------------------------------------------------

PAGES = ["/visits?date=", "/refunds?date=", "/cash-register?date=", "/appointments?day=",
         "/appointments?week=", "/pos/history?date=", "/admin/logs?date=",
         "/consignment/sales?date_from=", "/consignment/sales?date_to="]
BAD_INPUTS = ["2026-W39-4", "20260925", "2026-09-25T10:00"]


@needs_db
@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("raw", BAD_INPUTS)
def test_a_non_plain_date_is_refused_out_loud_not_a_500_or_an_empty_page(client, page, raw):
    """GUARD. Before: a 500 on four of these pages, and a silently empty
    result (no warning) on the rest."""
    resp = client.get(page + raw, follow_redirects=True)
    assert resp.status_code == 200, f"{page}{raw} answered {resp.status_code}"
    html = resp.get_data(as_text=True)
    assert "wasn&#39;t valid" in html or "wasn't valid" in html, f"{page}{raw}: no warning shown"


@needs_db
@pytest.mark.parametrize("page", PAGES)
def test_control_a_plain_date_is_accepted_without_a_warning(client, page):
    resp = client.get(page + "2026-09-25", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "wasn&#39;t valid" not in html and "wasn't valid" not in html, page


# ---------------------------------------------------------------------------
# Two write paths that took a date with no check at all
# ---------------------------------------------------------------------------

@pytest.fixture
def draft_audit(db):
    item = db.execute("SELECT id FROM inventory_list WHERE active ORDER BY id LIMIT 1").fetchone()
    if item is None:
        pytest.skip("no active inventory item to count")
    sid = db.execute("INSERT INTO audit_sessions (audit_date, performed_by, status, created_at) "
                     "VALUES (?,?,'Draft',now()) RETURNING id", (date(2001, 1, 1), ADMIN_ID)).fetchone()["id"]
    db.commit()
    yield {"id": sid, "item": item["id"]}
    db.execute("DELETE FROM audit_session_lines WHERE session_id=?", (sid,))
    db.execute("DELETE FROM audit_log WHERE table_name='audit_sessions' AND record_id=?", (str(sid),))
    db.execute("DELETE FROM audit_sessions WHERE id=?", (sid,))
    db.commit()


def _line(db, audit):
    return db.execute("SELECT nearest_expiry_date FROM audit_session_lines WHERE session_id=? AND item_id=?",
                      (audit["id"], audit["item"])).fetchone()


@needs_db
@pytest.mark.parametrize("expiry", ["2026-02-30", "2026-W39-4", "soon"])
def test_an_audit_line_with_a_bad_expiry_is_refused_not_a_500(client, db, draft_audit, expiry):
    """GUARD. The expiry went raw into a DATE column: a cast error, a 500,
    and every count typed on the sheet lost."""
    i = draft_audit["item"]
    resp = client.post(f"/audit-history/session/{draft_audit['id']}/save",
                       data={f"stock_{i}": "5", f"expiry_{i}": expiry})
    assert resp.status_code == 200, resp.status_code
    assert "expiry date isn" in resp.get_data(as_text=True)
    assert _line(db, draft_audit) is None


@needs_db
def test_control_an_audit_line_with_a_real_expiry_is_saved(client, db, draft_audit):
    i = draft_audit["item"]
    resp = client.post(f"/audit-history/session/{draft_audit['id']}/save",
                       data={f"stock_{i}": "5", f"expiry_{i}": "2027-03-31"})
    assert resp.status_code == 302
    assert _line(db, draft_audit)["nearest_expiry_date"] == date(2027, 3, 31)


@pytest.fixture
def opex_months(db):
    made = []
    yield made
    for m in made:
        db.execute("DELETE FROM audit_log WHERE table_name='monthly_opex' AND record_id=?", (m,))
        db.execute("DELETE FROM monthly_opex WHERE month=?", (m,))
    db.commit()


def _opex(client, month):
    return client.post("/reports/opex", data={"month": month, "rent": "1", "salaries": "0", "utilities": "0",
                                              "marketing": "0", "other": "0"})


@needs_db
def test_operating_costs_for_month_13_are_refused(client, db, opex_months):
    """GUARD. `\\d{4}-\\d{2}` accepted 2026-13: stored under a month no
    report shows."""
    opex_months.append("1999-13")
    resp = _opex(client, "1999-13")
    assert resp.status_code == 200 and "not a valid month" in resp.get_data(as_text=True)
    assert db.execute("SELECT 1 FROM monthly_opex WHERE month='1999-13'").fetchone() is None


@needs_db
def test_control_operating_costs_for_a_real_month_are_saved(client, db, opex_months):
    opex_months.append("1999-12")
    assert _opex(client, "1999-12").status_code == 302
    assert db.execute("SELECT 1 FROM monthly_opex WHERE month='1999-12'").fetchone() is not None
