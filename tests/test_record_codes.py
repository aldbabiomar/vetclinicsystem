"""
Record codes (plan D-2): numeric ids in the database, codes on the screen.

Staff read "V-00123" and type it back — into the refunds form, into a
search box. These pin the two directions (codes.code and parse_id), and that
the places staff actually meet a record show the code rather than a bare
number or an old-style id.
"""
from datetime import date
from decimal import Decimal as D

import pytest

from vcs import clock
from vcs.domain import codes
from conftest import ADMIN_ID, needs_db, new_id


# ---------------------------------------------------------------------------
# The two directions (no database)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prefix,record_id,shown", [
    ("V", 123, "V-00123"), ("PT", 7, "PT-00007"), ("OW", 123456, "OW-123456"), ("V", None, ""),
])
def test_a_record_is_shown_as_its_code(prefix, record_id, shown):
    assert codes.code(prefix, record_id) == shown


@pytest.mark.parametrize("typed,prefix,read", [
    ("V-00123", "V", 123), ("v123", "V", 123), ("V 00123", "V", 123), ("123", "V", 123), ("00123", None, 123),
])
def test_a_typed_code_or_number_is_read_back(typed, prefix, read):
    assert codes.parse_id(typed, prefix) == read


@pytest.mark.parametrize("typed,prefix", [
    ("PT-00123", "V"),          # the wrong kind of record — never silently another record
    ("V-00123", None),          # a code where only a number is expected
    ("V-0", "V"), ("abc", "V"), ("12a", "V"), ("", "V"), (None, "V"), ("99999999999", "V"), ("-5", None),
])
def test_anything_else_is_not_an_id(typed, prefix):
    assert codes.parse_id(typed, prefix) is None


def test_a_code_round_trips():
    for n in (1, 42, 99999, 100000, 2_000_000_000):
        assert codes.parse_id(codes.code("V", n), "V") == n


# ---------------------------------------------------------------------------
# Where staff meet a record
# ---------------------------------------------------------------------------

@pytest.fixture
def chain(db):
    o, p, v = new_id(), new_id(), new_id()
    db.execute("INSERT INTO owners (id, name) VALUES (?,?)", (o, "Code Owner"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (?,?,?)", (p, o, "Code Pet"))
    db.execute("INSERT INTO visits (id, patient_id, date, case_status) VALUES (?,?,?,?)",
               (v, p, clock.today(), "Ongoing"))
    db.execute("INSERT INTO billing (visit_id, billing_type, manual_amount, total, discount_percent, cleanup_amount) "
               "VALUES (?,?,?,?,?,?)", (v, "Manual", D(10), D(10), D(0), D(0)))
    db.execute("INSERT INTO payments (visit_id, amount, method, date, user_id) VALUES (?,?,?,?,?)",
               (v, D(10), "Cash", clock.today(), ADMIN_ID))
    db.commit()
    yield {"owner": o, "patient": p, "visit": v}
    for sql, arg in (("DELETE FROM refunds WHERE visit_id=?", v), ("DELETE FROM payments WHERE visit_id=?", v),
                     ("DELETE FROM billing WHERE visit_id=?", v), ("DELETE FROM visits WHERE id=?", v),
                     ("DELETE FROM patients WHERE id=?", p), ("DELETE FROM owners WHERE id=?", o)):
        db.execute(sql, (arg,))
    db.commit()


@needs_db
def test_pages_show_the_code_not_the_bare_number(client, chain):
    pages = {
        f"/visits/{chain['visit']}": codes.code("V", chain["visit"]),
        f"/patients/{chain['patient']}": codes.code("PT", chain["patient"]),
        f"/owners/{chain['owner']}": codes.code("OW", chain["owner"]),
    }
    for url, code in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert code in html, f"{url} does not show {code}"


@needs_db
def test_a_patient_is_found_by_its_code(client, chain):
    """GUARD. The search used to match `id ILIKE term`; the id is a number
    now, and staff search with the code they read on the screen."""
    found = client.get(f"/api/patients/search?q={codes.code('PT', chain['patient'])}").get_json()
    assert [r["id"] for r in found] == [chain["patient"]]
    assert found[0]["code"] == codes.code("PT", chain["patient"])


@needs_db
def test_a_service_refund_accepts_the_visit_code_staff_read(client, db, chain):
    """GUARD. The refunds form asks for the visit; staff type the code."""
    resp = client.post("/refunds/service", data={
        "visit_id": codes.code("V", chain["visit"]), "amount": "1", "refund_method": "Cash",
        "reason": "code typed"}, follow_redirects=False)
    assert resp.status_code == 302
    assert db.execute("SELECT count(*) AS n FROM refunds WHERE visit_id=?", (chain["visit"],)).fetchone()["n"] == 1


@needs_db
def test_control_a_code_for_another_kind_of_record_is_not_found(client, db, chain):
    resp = client.post("/refunds/service", data={
        "visit_id": codes.code("PT", chain["visit"]), "amount": "1", "refund_method": "Cash",
        "reason": "wrong kind"}, follow_redirects=True)
    assert "not found" in resp.get_data(as_text=True)
    assert db.execute("SELECT count(*) AS n FROM refunds WHERE visit_id=?", (chain["visit"],)).fetchone()["n"] == 0


# ---------------------------------------------------------------------------
# Attachment folders are named after the record, and read back from the name
# ---------------------------------------------------------------------------

def test_an_attachment_folder_name_round_trips():
    """attachments.record_key() names the folder a file is stored in;
    reconcile_attachments.resolve_record_key() reads it back to re-link an
    orphaned file. Visit ids became numbers (plan D-2), so both halves had to
    change together — "V42" and "IC7", no longer a visit's "V0042" as is."""
    from vcs.domain import attachments
    from vcs.ops import reconcile_attachments
    for kind, rid in (("visit", 42), ("inpatient", 7)):
        key = attachments.record_key(kind, rid)
        assert reconcile_attachments.resolve_record_key(key) == (kind, rid)
    assert attachments.record_key("visit", 42) == "V42"
    assert reconcile_attachments.resolve_record_key("Vabc") is None
