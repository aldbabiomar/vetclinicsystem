"""
The Dashboard snapshot reads only what it shows (audit D3), and shows what it
always showed.

It runs on every page, for the sidebar badge, and it used to read every visit
ever recorded, every pending follow-up and every wellness reminder ever set.
Now the database narrows each list first: a COUNT for the active cases,
today's and tomorrow's follow-ups, the wellness doses that can be due. The
Python that decides "due" is unchanged, so the snapshot must equal what the
unbounded reads produce -- built here on both sides of every boundary.
"""
from datetime import timedelta

import pytest

from vcs import clock
from vcs.domain import alerts, clinical, dates
from conftest import needs_db, new_id

pytestmark = needs_db


@pytest.fixture
def clinic(db):
    today = clock.today()
    o_id, p_id = new_id(), new_id()
    db.execute("INSERT INTO owners (id, name) VALUES (%s,%s)", (o_id, f"Bounds Owner {o_id}"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (%s,%s,%s)", (p_id, o_id, f"Bounds Pet {p_id}"))
    made = []

    def visit(**cols):
        vid = new_id()
        cols = {"date": today - timedelta(days=30), "case_status": "Ongoing", **cols}
        db.execute(f"INSERT INTO visits (id, patient_id, {', '.join(cols)}) "
                   f"VALUES (%s,%s,{', '.join(['%s'] * len(cols))})", (vid, p_id, *cols.values()))
        made.append(vid)
        return vid

    # follow-ups: yesterday, today, tomorrow (by visit and by phone), done today
    for offset, method, status in [(-1, "Physical Visit", "Pending"), (0, "Physical Visit", "Pending"),
                                   (0, "Phone Call", "Pending"), (1, "Physical Visit", "Pending"),
                                   (1, "Phone Call", "Pending"), (0, "Physical Visit", "Completed"), (2, "Physical Visit", "Pending")]:
        visit(followup_needed="Y", followup_method=method, followup_status=status,
              followup_date=today + timedelta(days=offset), case_status="Resolved")
    # wellness: every edge of "due" -- one per type so none replaces another
    for i, (offset, contacted) in enumerate([(-14, "N"), (-13, "N"), (0, "N"), (5, "N"), (6, "N"), (2, "Y"), (-30, "N")]):
        visit(wellness_needed="Y", wellness_type=f"Bounds Type {i}", wellness_contacted=contacted,
              wellness_next_dose_date=today + timedelta(days=offset))
    db.commit()
    yield
    for vid in made:
        db.execute("DELETE FROM visits WHERE id=%s", (vid,))
    db.execute("DELETE FROM patients WHERE id=%s", (p_id,))
    db.execute("DELETE FROM owners WHERE id=%s", (o_id,))
    db.commit()


def _ids(rows):
    return [r["visit_id"] for r in rows]


def test_the_snapshot_equals_the_unbounded_reads(db, clinic):
    """GUARD. The old way of reading each list, beside the new one."""
    today = clock.today()
    snap = alerts.dashboard_snapshot(db)

    active = sum(1 for v in db.execute("SELECT case_status FROM visits").fetchall()
                 if v["case_status"] in {"Ongoing", "Admitted to Inpatient", "Needs Filling"})
    assert snap["active_cases"] == active

    pending = clinical.followups(db, only_pending=True)
    assert _ids(snap["due_today"]) == _ids(f for f in pending if dates.as_date(f["followup_date"]) == today)
    assert _ids(snap["reminders_tomorrow"]) == _ids(
        f for f in pending if dates.as_date(f["followup_date"]) == today + timedelta(days=1)
        and f["followup_method"] == "Physical Visit")

    assert _ids(snap["wellness_due"]) == _ids(r for r in clinical.wellness_reminders(db) if r["due"])


def test_control_the_edges_are_where_they_should_be(db, clinic):
    """CONTROL: the fixture really straddles each boundary, so the guard is
    comparing lists that could differ."""
    today = clock.today()
    snap = alerts.dashboard_snapshot(db)
    mine = {r["visit_id"]: r for r in clinical.wellness_reminders(db) if r["wellness_type"].startswith("Bounds Type")}
    due_offsets = sorted((dates.as_date(r["wellness_next_dose_date"]) - today).days
                         for r in snap["wellness_due"] if r["visit_id"] in mine)
    assert due_offsets == [-13, 0, 5], "due runs from 13 days past the dose to 5 days before it"
    assert len([f for f in snap["due_today"] if "Bounds" in f["animal_name"]]) == 2
    assert len([f for f in snap["reminders_tomorrow"] if "Bounds" in f["animal_name"]]) == 1
