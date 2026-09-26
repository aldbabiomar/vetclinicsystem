"""
When something goes wrong, the clinic still gets a proper page.

  B11 — a POST naming a record that is not there (a distributor deleted in
        another tab, a crafted URL) reached the foreign key as a 500. The
        audit found three by sweeping every parameterised POST route; the
        sweep below is that audit, kept, so a fourth cannot be added.
  B12 — after an error inside Postgres, the 500 page rendered on the aborted
        transaction: an Arabic clinic got an English page under the default
        clinic name, and a second traceback was logged.
"""
import pytest

from vcs import clock
from conftest import needs_db
from test_money_routes import inpatient_case, visit  # noqa: F401

pytestmark = needs_db

MISSING = 2147483647          # an id no row will ever have (the largest INTEGER)

# Plausible values for every field name the forms use, so a route gets past
# its own validation and reaches the database — an empty form is refused
# before the missing parent matters, and the sweep would prove nothing.
PAYLOAD = {
    "note": "sweep", "notes": "sweep", "reason": "sweep", "name": "Sweep", "full_name": "Sweep",
    "amount": "1.000", "amount_paid": "1.000", "total_amount": "1.000", "manual_amount": "1.000",
    "cleanup_amount": "0", "discount_percent": "0", "quantity": "1", "price_per_day": "1.000",
    "method": "Cash", "payment_method": "Cash", "refund_method": "Cash",
    "date": clock.today().isoformat(), "bill_date": clock.today().isoformat(),
    "payment_date": clock.today().isoformat(), "refund_date": clock.today().isoformat(),
    "entry_date": clock.today().isoformat(), "appt_date": clock.today().isoformat(),
    "billing_type": "Manual", "status": "Done", "picked_up": "yes", "issue": "sweep",
    "contact_method": "Phone Call", "response": "sweep", "bill_reference": "SWEEP",
    "case_status": "Ongoing", "visit_type": "Outpatient", "expected_updated_at": "",
}


def _post_routes_with_an_id(flask_app):
    out = []
    for rule in flask_app.url_map.iter_rules():
        if "POST" not in rule.methods or not rule.arguments:
            continue
        if not all(type(conv).__name__ == "IntegerConverter" for conv in rule._converters.values()):
            continue
        out.append(rule)
    return out


def test_no_post_route_answers_500_for_a_record_that_is_not_there(client, flask_app):
    """GUARD (B11), over every parameterised POST route there is."""
    rules = _post_routes_with_an_id(flask_app)
    assert len(rules) >= 45, f"found only {len(rules)} routes — the sweep has drifted"
    failures = []
    for rule in rules:
        url = rule.build({arg: MISSING for arg in rule.arguments})[1]
        resp = client.post(url, data=PAYLOAD)
        if resp.status_code >= 500:
            failures.append(f"{resp.status_code} POST {rule.rule}")
    assert not failures, "answered with a server error for a missing record:\n  " + "\n  ".join(failures)


def test_a_bill_for_a_deleted_distributor_says_so(client, db):
    """GUARD (B11): the case the audit could reach from the UI — the page left
    open in another tab while the distributor was deleted."""
    resp = client.post(f"/distributors/{MISSING}/bills/new", data=PAYLOAD, follow_redirects=True)
    assert resp.status_code == 200
    assert "Distributor not found" in resp.get_data(as_text=True)


@pytest.fixture
def arabic_clinic(db):
    keys = ("language", "clinic_name")
    saved = {k: (db.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or {}).get("value")
             for k in keys}
    for k, v in (("language", "ar"), ("clinic_name", "Error Page Clinic 7Q")):
        db.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT (key) DO UPDATE SET value=excluded.value",
                   (k, v))
    db.commit()
    yield
    for k, v in saved.items():
        if v is None:
            db.execute("DELETE FROM settings WHERE key=?", (k,))
        else:
            db.execute("UPDATE settings SET value=? WHERE key=?", (v, k))
    db.commit()


def test_the_error_page_after_a_database_error_is_the_clinics_own(client, flask_app, arabic_clinic, monkeypatch):
    """GUARD (B12). A view that fails inside Postgres: the 500 page must still
    be in the clinic's language, under the clinic's name."""
    from vcs.web.core import get_db

    def fails_in_postgres():
        get_db().execute("SELECT 1/0")

    monkeypatch.setitem(flask_app.view_functions, "dashboard", fails_in_postgres)
    resp = client.get("/")
    assert resp.status_code == 500, "the view did not fail — the test would prove nothing"
    page = resp.get_data(as_text=True)
    assert 'lang="ar"' in page, "the error page fell back to English"
    assert "Error Page Clinic 7Q" in page, "the error page fell back to the default clinic name"


def test_control_the_same_page_without_an_error(client, arabic_clinic):
    page = client.get("/").get_data(as_text=True)
    assert 'lang="ar"' in page and "Error Page Clinic 7Q" in page


@pytest.mark.parametrize("url,data,table", [
    ("/inpatient/{}/update", {"note": "Audit id note"}, "inpatient_updates"),
    ("/inpatient/{}/contact", {"picked_up": "no", "notes": "Audit id call"}, "inpatient_contact_log"),
])
def test_a_daily_update_or_call_is_audited_under_its_own_id(client, db, inpatient_case, url, data, table):
    """B11's footnote: both routes logged the CASE id as the record created,
    so the audit log named a record that was never created."""
    resp = client.post(url.format(inpatient_case["id"]), data=data)
    assert resp.status_code == 302
    row_id = db.execute(f"SELECT max(id) AS id FROM {table} WHERE case_id=?", (inpatient_case["id"],)).fetchone()["id"]
    logged = db.execute("SELECT record_id FROM audit_log WHERE table_name=? AND action='create' ORDER BY id DESC LIMIT 1",
                        (table,)).fetchone()["record_id"]
    assert logged == str(row_id)
