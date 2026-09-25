"""
Wellness reminders: due for a while, then missed — never due forever — and
a newer entry replaces the old one (audit B19, owner decision D-16).

"Due" used to last from five days before the dose until someone ticked
"contacted", however long that took, so every uncontacted reminder since the
clinic opened stayed in the Dashboard's list and the sidebar badge. And the
Dashboard sorted oldest dose first while the Wellness page sorted newest
first. Now: most urgent first on both.
"""
from datetime import timedelta

import pytest

import clock
import logic
from conftest import needs_db
from test_money_routes import _uid

pytestmark = needs_db


@pytest.fixture
def pet(db):
    o_id, p_id = _uid("O"), _uid("P")
    db.execute("INSERT INTO owners (id, name) VALUES (?,?)", (o_id, f"Wellness Owner {o_id}"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (?,?,?)", (p_id, o_id, f"Wellness Pet {p_id}"))
    db.commit()
    made = []

    def entry(dose_in_days, wellness_type="Annual Vaccine", visit_days_ago=30, contacted="N"):
        today = clock.today()
        vid = _uid("V")
        db.execute("INSERT INTO visits (id, patient_id, date, case_status, wellness_needed, wellness_type, "
                   "wellness_next_dose_date, wellness_contacted) VALUES (?,?,?,?,?,?,?,?)",
                   (vid, p_id, today - timedelta(days=visit_days_ago), "Ongoing", "Y", wellness_type,
                    today + timedelta(days=dose_in_days), contacted))
        db.commit()
        made.append(vid)
        return vid

    yield entry
    for vid in made:
        db.execute("DELETE FROM visits WHERE id=?", (vid,))
    db.execute("DELETE FROM patients WHERE id=?", (p_id,))
    db.execute("DELETE FROM owners WHERE id=?", (o_id,))
    db.commit()


def _due_ids(db):
    return [r["visit_id"] for r in logic.wellness_reminders(db, only_due=True)]


def _missed_ids(db):
    return [m["visit_id"] for m in logic.missed_items(db) if m["kind"] == "Wellness"]


def test_a_reminder_stops_being_due_when_it_becomes_missed(db, pet):
    """GUARD. 20 days past the dose, never contacted: on the Missed Items
    list for an admin, not in the "due" list and badge any more."""
    vid = pet(-20)
    assert vid not in _due_ids(db)
    assert vid in _missed_ids(db)


@pytest.mark.parametrize("dose_in_days", [3, 0, -2, -13])
def test_control_a_reminder_is_due_from_five_days_before_until_it_is_missed(db, pet, dose_in_days):
    vid = pet(dose_in_days)
    assert vid in _due_ids(db) and vid not in _missed_ids(db)


def test_control_a_reminder_is_not_due_before_its_lead_time(db, pet):
    assert pet(10) not in _due_ids(db)


def test_a_newer_entry_for_the_same_pet_and_type_replaces_the_old_one(db, pet):
    """GUARD. The pet came back and the next dose was set again; the old
    date is no longer owed — not due, not missed, not listed."""
    old = pet(-20, visit_days_ago=400)
    new = pet(340, visit_days_ago=25)
    assert old not in _missed_ids(db) and old not in _due_ids(db)
    page_ids = [r["visit_id"] for r in logic.wellness_reminders_page(db, limit=10_000)[0]]
    assert old not in page_ids and new in page_ids


def test_control_a_newer_entry_of_another_type_replaces_nothing(db, pet):
    old = pet(-20, "Annual Vaccine", visit_days_ago=400)
    pet(340, "Deworming", visit_days_ago=25)
    assert old in _missed_ids(db)


def test_both_screens_put_the_most_urgent_first(db, pet):
    """D-16. Open reminders by the earliest dose, on the Dashboard's list
    and on the Wellness page alike; closed ones (contacted, or missed) after
    them, newest first."""
    later, sooner, missed, contacted = pet(4), pet(1, "Deworming"), pet(-30, "Rabies Vaccine"), \
        pet(2, "First Vaccine", contacted="Y")
    mine = {later, sooner, missed, contacted}
    dashboard = [i for i in _due_ids(db) if i in mine]
    assert dashboard == [sooner, later]
    page = [r["visit_id"] for r in logic.wellness_reminders_page(db, limit=10_000)[0] if r["visit_id"] in mine]
    assert page[:2] == [sooner, later], page
    assert set(page[2:]) == {missed, contacted} and page[2] == contacted, "closed ones: newest dose first"
    unpaged = [r["visit_id"] for r in logic.wellness_reminders(db) if r["visit_id"] in mine]
    assert unpaged == page, "the Dashboard's full list and the Wellness page disagree about the order"
