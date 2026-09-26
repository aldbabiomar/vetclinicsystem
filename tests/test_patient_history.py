"""
A patient's history shows an inpatient stay once (audit P4).

Admitting a patient marks the triggering visit "Inpatient" and opens a case
for the stay — so the same encounter (same complaint, exam, treatment) was
listed twice: once as a visit, once as the stay.
"""
from datetime import timedelta

import pytest

from vcs import clock
from vcs.domain import clinical
from conftest import ADMIN_ID, needs_db
from test_money_routes import _uid

pytestmark = needs_db


@pytest.fixture
def pet(db):
    o, p = _uid("O"), _uid("P")
    db.execute("INSERT INTO owners (id, name) VALUES (?,?)", (o, "History Owner"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (?,?,?)", (p, o, "History Pet"))
    db.commit()
    made = {"visits": [], "cases": []}

    def visit(days_ago, visit_type, complaint):
        v = _uid("V")
        db.execute("INSERT INTO visits (id, patient_id, date, case_status, visit_type, complaint) VALUES (?,?,?,?,?,?)",
                   (v, p, clock.today() - timedelta(days=days_ago), "Ongoing", visit_type, complaint))
        db.commit()
        made["visits"].append(v)
        return v

    def case(days_ago, visit_id=None):
        c = db.execute("INSERT INTO inpatient_cases (patient_id, visit_id, admission_date, dismissed, created_by) "
                       "VALUES (?,?,?,false,?) RETURNING id",
                       (p, visit_id, clock.today() - timedelta(days=days_ago), ADMIN_ID)).fetchone()["id"]
        db.commit()
        made["cases"].append(c)
        return c

    yield {"id": p, "visit": visit, "case": case}
    for c in made["cases"]:
        db.execute("DELETE FROM inpatient_cases WHERE id=?", (c,))
    for v in made["visits"]:
        db.execute("DELETE FROM visits WHERE id=?", (v,))
    db.execute("DELETE FROM patients WHERE id=?", (p,))
    db.execute("DELETE FROM owners WHERE id=?", (o,))
    db.commit()


def _visit_ids(db, pet):
    return [e["record"]["id"] for e in clinical.patient_history(db, pet["id"]) if e["kind"] == "Visit"]


def test_the_admitting_visit_of_a_stay_is_not_listed_again(db, pet):
    """GUARD. The case names its admitting visit."""
    admitting = pet["visit"](3, "Inpatient", "Collapsed at home")
    pet["case"](3, visit_id=admitting)
    assert admitting not in _visit_ids(db, pet)


def test_an_unlinked_stay_hides_the_inpatient_visit_on_its_admission_day(db, pet):
    """GUARD. A case opened directly has no link; the "Inpatient" visit on
    its admission date is the same encounter."""
    same_day = pet["visit"](5, "Inpatient", "Admitted from reception")
    pet["case"](5)
    assert same_day not in _visit_ids(db, pet)


def test_control_other_visits_stay_including_an_inpatient_one_with_no_stay(db, pet):
    ordinary = pet["visit"](2, "Outpatient", "Vaccination")
    orphan = pet["visit"](9, "Inpatient", "Marked inpatient, never admitted")
    admitting = pet["visit"](3, "Inpatient", "Collapsed")
    pet["case"](3, visit_id=admitting)
    ids = _visit_ids(db, pet)
    assert ordinary in ids and orphan in ids and admitting not in ids


def test_the_history_page_shows_the_stay_once(client, db, pet):
    """GUARD. As in the app, the stay carries the visit's complaint."""
    admitting = pet["visit"](3, "Inpatient", "Distinctive complaint P4")
    case = pet["case"](3, visit_id=admitting)
    db.execute("UPDATE inpatient_cases SET complaint=? WHERE id=?", ("Distinctive complaint P4", case))
    db.commit()
    page = client.get(f"/patients/{pet['id']}/history").get_data(as_text=True)
    assert page.count("Distinctive complaint P4") == 1


def test_an_admission_records_its_findings_items_and_vets_in_the_change_log(client, db, pet):
    """GUARD (audit P9). The route wrote them and logged only "created"."""
    resp = client.post("/inpatient/new", data={"patient_id": str(pet["id"]), "complaint": "P9 admit",
                                               "exam_findings": "P9 findings", "admitted_items": "P9 lead",
                                               "weight_kg": "", "bcs": "", "admission_date": ""})
    assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
    case = db.execute("SELECT id FROM inpatient_cases WHERE patient_id=? ORDER BY id DESC LIMIT 1",
                      (pet["id"],)).fetchone()["id"]
    try:
        logged = {r["field"]: r["new_value"] for r in db.execute(
            "SELECT field, new_value FROM audit_log WHERE table_name='inpatient_cases' AND record_id=? AND action='update'",
            (str(case),)).fetchall()}
        assert logged.get("exam_findings") == "P9 findings" and logged.get("admitted_items") == "P9 lead", logged
    finally:
        db.execute("DELETE FROM audit_log WHERE table_name='inpatient_cases' AND record_id=?", (str(case),))
        db.execute("DELETE FROM inpatient_cases WHERE id=?", (case,))
        db.commit()
