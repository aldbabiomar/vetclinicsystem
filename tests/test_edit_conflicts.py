"""
Two people editing one record: the second save never silently undoes the
first (audit B4, and the holes found fixing it).

  - B4 itself: after a conflict the form was redrawn with the FRESH record's
    token, so clicking Save a second time stored the stale values.
  - A new record had updated_at NULL, which the guard read as "nothing to
    compare against": every record's FIRST edit was unguarded.
  - The follow-up, wellness and grooming buttons, and boarding's Dismiss,
    wrote columns the edit forms also write without touching updated_at: an
    edit form opened before them undid them on save, with no conflict.

The same behaviour holds on all three edit forms — visit, boarding stay,
inpatient case — so each test runs on all three.
"""
import source_files
import ast
import html as htmllib
import pathlib
import re

import pytest

from vcs import clock
from conftest import needs_db
from test_edit_routes import _edit_case, _edit_stay, _stamp, case, patient, stay  # noqa: F401
from test_workflow_routes import _edit_visit, a_visit  # noqa: F401

ROOT = pathlib.Path(__file__).parent.parent


def _visit_save(client, db, rid, **data):
    return _edit_visit(client, rid, db, **data)


KINDS = {
    # fixture, its id key, table, the form's action, a free-text field, a second one, save()
    "visit": ("a_visit", "visit_id", "visits", "/visits/{}/edit", "complaint", "history", _visit_save),
    "stay": ("stay", "id", "boarding_sessions", "/boarding/{}/edit", "room", "admitted_items", _edit_stay),
    "case": ("case", "id", "inpatient_cases", "/inpatient/{}/edit", "complaint", "exam_findings", _edit_case),
}


@pytest.fixture(params=list(KINDS))
def record(request, client, db):
    fixture, key, table, action, field, other, save = KINDS[request.param]
    rid = request.getfixturevalue(fixture)[key]

    def value():
        return db.execute(f"SELECT {field} FROM {table} WHERE id=%s", (rid,)).fetchone()[field]

    return {"id": rid, "table": table, "action": action.format(rid), "field": field, "other": other, "value": value,
            "save": lambda **data: save(client, db, rid, **data), "kind": request.param}


def _form_inputs(page, action):
    """The hidden inputs of the one <form> posting to `action` — the
    boarding page draws an edit form for every stay."""
    start = page.index(f'action="{action}"') if f'action="{action}"' in page else page.index("<form")
    form = page[start:page.index("</form>", start)]
    return {n: htmllib.unescape(v) for n, v in
            re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form)}


@needs_db
def test_a_second_save_from_the_conflict_page_is_refused_again(db, record):
    """GUARD — B4 itself."""
    t0 = _stamp(db, record["table"], record["id"])
    assert record["save"](**{record["field"]: "Theirs"}).status_code == 302
    first = record["save"](**{record["field"]: "Mine", "expected_updated_at": t0})
    assert first.status_code == 200 and record["value"]() == "Theirs"
    hidden = _form_inputs(first.get_data(as_text=True), record["action"])
    assert clock.same_instant(hidden["expected_updated_at"], t0), (
        "the conflict page must carry the token the form was loaded with, not the fresh one")
    again = record["save"](**{record["field"]: "Mine", "expected_updated_at": hidden["expected_updated_at"]})
    assert again.status_code == 200
    assert record["value"]() == "Theirs", "the second click stored the stale values"


@needs_db
def test_the_conflict_page_lists_what_the_other_person_changed(db, record):
    t0 = _stamp(db, record["table"], record["id"])
    record["save"](**{record["field"]: "Their distinctive text"})
    page = record["save"](**{record["field"]: "Mine", "expected_updated_at": t0}).get_data(as_text=True)
    assert "Their distinctive text" in page
    assert 'name="overwrite_confirm"' in page


@needs_db
def test_the_conflict_page_does_not_list_what_was_there_when_the_form_opened(db, record):
    """GUARD. Only changes AFTER the loaded version: the audit rows carry the
    very instant written to updated_at (log_change(at=...)). Written a few
    microseconds later, the loaded version's own changes would be listed as
    if someone else had just made them."""
    other = record["other"]
    record["save"](**{record["field"]: "Before", other: "Earlier text"})
    t0 = _stamp(db, record["table"], record["id"])
    record["save"](**{record["field"]: "Theirs", other: "Earlier text"})
    page = record["save"](**{record["field"]: "Mine", other: "", "expected_updated_at": t0}).get_data(as_text=True)
    assert "Theirs" in page, "the conflict was not detected — the test would prove nothing"
    assert "Earlier text" not in page


@needs_db
def test_control_saving_over_their_changes_after_seeing_them(db, record):
    """CONTROL. The way forward from a conflict, without retyping."""
    t0 = _stamp(db, record["table"], record["id"])
    record["save"](**{record["field"]: "Theirs"})
    page = record["save"](**{record["field"]: "Mine", "expected_updated_at": t0}).get_data(as_text=True)
    hidden = _form_inputs(page, record["action"])
    resp = record["save"](**{record["field"]: "Mine", "expected_updated_at": hidden["expected_updated_at"],
                             "overwrite_confirm": "1", "overwrite_updated_at": hidden["overwrite_updated_at"]})
    assert resp.status_code == 302
    assert record["value"]() == "Mine"


@needs_db
def test_saving_over_is_only_over_the_version_that_was_shown(db, record):
    """GUARD. A third save after the conflict page was drawn: ticking
    "save mine over theirs" must not silently undo a change it never showed."""
    t0 = _stamp(db, record["table"], record["id"])
    record["save"](**{record["field"]: "Theirs"})
    page = record["save"](**{record["field"]: "Mine", "expected_updated_at": t0}).get_data(as_text=True)
    hidden = _form_inputs(page, record["action"])
    record["save"](**{record["field"]: "Third"})
    resp = record["save"](**{record["field"]: "Mine", "expected_updated_at": hidden["expected_updated_at"],
                             "overwrite_confirm": "1", "overwrite_updated_at": hidden["overwrite_updated_at"]})
    assert resp.status_code == 200
    assert record["value"]() == "Third"


@needs_db
def test_the_overwrite_box_alone_is_not_enough(db, record):
    """GUARD. Ticked, but without the token of a version shown: refused."""
    t0 = _stamp(db, record["table"], record["id"])
    record["save"](**{record["field"]: "Theirs"})
    resp = record["save"](**{record["field"]: "Mine", "expected_updated_at": t0, "overwrite_confirm": "1"})
    assert resp.status_code == 200 and record["value"]() == "Theirs"


@needs_db
def test_the_first_edit_of_a_new_record_is_guarded_too(db, record):
    """GUARD. updated_at was NULL until the first edit, and NULL meant "no
    check": two people opening a brand-new record both saved, last one wins."""
    t0 = _stamp(db, record["table"], record["id"])
    assert t0, "a new record must carry an edit stamp from the moment it exists"
    assert record["save"](**{record["field"]: "First", "expected_updated_at": t0}).status_code == 302
    assert record["save"](**{record["field"]: "Second", "expected_updated_at": t0}).status_code == 200
    assert record["value"]() == "First"


@needs_db
def test_a_form_without_a_token_is_refused(db, record):
    """GUARD. A missing token is not a match."""
    resp = record["save"](**{record["field"]: "Tokenless", "expected_updated_at": ""})
    assert resp.status_code == 200 and record["value"]() != "Tokenless"


# ---------------------------------------------------------------------------
# The sibling writes: each must make an open edit form stale
# ---------------------------------------------------------------------------

SIBLINGS = [
    ("/followups/{}/status", {"status": "Done"}, "followup_status", "Done"),
    ("/wellness/{}/update", {"wellness_contacted": "Y", "wellness_contact_method": "Call"}, "wellness_contacted", "Y"),
    ("/grooming/{}/update", {"grooming_status": "Finished", "grooming_contacted": "Y"}, "grooming_status", "Finished"),
]


@needs_db
@pytest.mark.parametrize("url,data,column,value", SIBLINGS)
def test_a_status_button_makes_an_open_visit_form_stale(client, db, a_visit, url, data, column, value):
    """GUARD. The visit form also writes these columns; saved from a form
    opened before the button was pressed, it put the old value back."""
    vid = a_visit["visit_id"]
    t0 = _stamp(db, "visits", vid)
    client.post(url.format(vid), data=data)
    assert db.execute(f"SELECT {column} FROM visits WHERE id=%s", (vid,)).fetchone()[column] == value, (
        "the button's own write failed — the test would prove nothing")
    resp = _edit_visit(client, vid, db, complaint="Stale form", expected_updated_at=t0)
    assert resp.status_code == 200
    assert db.execute(f"SELECT {column} FROM visits WHERE id=%s", (vid,)).fetchone()[column] == value


@needs_db
def test_dismissing_a_stay_makes_an_open_stay_form_stale(client, db, stay):
    """GUARD. The stay form writes dismissal_date and total, which Dismiss sets."""
    t0 = _stamp(db, "boarding_sessions", stay["id"])
    client.post(f"/boarding/{stay['id']}/dismiss")
    dismissed = db.execute("SELECT dismissed, dismissal_date FROM boarding_sessions WHERE id=%s",
                           (stay["id"],)).fetchone()
    assert dismissed["dismissed"] and dismissed["dismissal_date"], "Dismiss did not land"
    resp = _edit_stay(client, db, stay["id"], dismissal_date="", room="Stale", expected_updated_at=t0)
    assert resp.status_code == 200
    after = db.execute("SELECT dismissal_date, room FROM boarding_sessions WHERE id=%s", (stay["id"],)).fetchone()
    assert after["dismissal_date"] == dismissed["dismissal_date"] and after["room"] != "Stale"


# ---------------------------------------------------------------------------
# The rule behind those, for every write to come
# ---------------------------------------------------------------------------

TABLES = ("visits", "boarding_sessions", "inpatient_cases")
UPDATE_SQL = re.compile(r"UPDATE\s+(visits|boarding_sessions|inpatient_cases)\s+SET\s+(.*?)\s+WHERE", re.S | re.I)


def _updates():
    """(module, table, {columns set}) for every UPDATE of the three tables
    in the application's Python — string constants from the AST, so implicit
    concatenation across lines is already joined."""
    out = []
    for path in [*source_files.web_modules(), *source_files.domain_modules()]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in UPDATE_SQL.finditer(node.value):
                    cols = {c.split("=")[0].strip().lower() for c in m.group(2).split(",") if "=" in c}
                    out.append((path.name, m.group(1).lower(), cols))
    return out


def test_every_write_to_a_column_an_edit_form_writes_bumps_updated_at():
    """GUARD. The edit form's own UPDATE (the one setting updated_at) names
    the columns it writes; any other UPDATE touching one of them must set
    updated_at too, or an open edit form will undo it without a conflict."""
    updates = _updates()
    edited = {t: set().union(*[c for _, tt, c in updates if tt == t and "updated_at" in c] or [set()])
              for t in TABLES}
    assert len(updates) >= 12 and all(len(edited[t]) >= 8 for t in TABLES), (
        "the scan found too little — the pattern has drifted", len(updates), {t: len(c) for t, c in edited.items()})
    offenders = [f"{mod}: UPDATE {t} SET {', '.join(sorted(cols))}"
                 for mod, t, cols in updates
                 if "updated_at" not in cols and cols & (edited[t] - {"updated_at"})]
    assert not offenders, ("these write a column an edit form also writes, without bumping updated_at:\n  "
                           + "\n  ".join(offenders))
