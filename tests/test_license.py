"""
The license's states, and read-only mode
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §5-§6, §14.1).

Read-only is one rule in one place: a before_request hook with one
allowlist. So the guard walks Flask's live url_map -- every endpoint that
writes is either on the allowlist or refused -- rather than trusting each
route to remember. It begins at a sign-in, never mid-task, and a renewal
ends it at once for everyone.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import needs_db
from test_privileges import admin_restored, as_role  # noqa: F401
from vcs import clock
from vcs.licensing import state
from vcs.web import readonly

pytestmark = needs_db
NOW = datetime.now(timezone.utc)
PASSWORD = "Admin12345!"


@pytest.fixture(autouse=True)
def _own_sign_in_limit(monkeypatch):
    """These tests sign in often; the limiter is shared with the rest of the suite."""
    from vcs.web import core
    monkeypatch.setattr(core, "_LOGIN_ATTEMPTS_BY_IP", {})


def _signed_in(flask_app):
    c = flask_app.test_client()
    assert c.post("/login", data={"username": "admin", "password": PASSWORD}).status_code == 302
    return c


def _refused(resp):
    return resp.status_code == 403 and "The system is read-only" in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("days, grace, expected", [
    (365, 14, state.ACTIVE), (5, 14, state.EXPIRING), (-3, 14, state.GRACE), (-30, 14, state.READ_ONLY),
    (-3, 0, state.READ_ONLY)])
def test_each_state_follows_from_the_key_and_the_clock(set_license, days, grace, expected):
    assert set_license(days, grace=grace).state == expected


def test_a_missing_key_is_missing(clinic_license):
    key = clinic_license / "license.key"
    saved = key.read_text()
    key.unlink()
    try:
        assert state.evaluate().state == state.MISSING
    finally:
        key.write_text(saved)


def test_an_edited_key_is_invalid(clinic_license):
    """GUARD. One changed character in the stored file."""
    key = clinic_license / "license.key"
    saved = key.read_text()
    prefix, payload, signature = saved.strip().split(".")
    key.write_text(f"{prefix}.{payload[:-2]}AA.{signature}\n" if not payload.endswith("AA")
                   else f"{prefix}.{payload[:-2]}BB.{signature}\n")
    try:
        status = state.evaluate()
        assert status.state == state.INVALID and not status.writable
    finally:
        key.write_text(saved)


def test_a_clock_wound_back_is_noticed(clinic_license):
    """GUARD (§5.3): more than a day behind the latest moment seen."""
    state.refresh()                                      # records now as seen
    assert state.evaluate(now=NOW - timedelta(days=3)).state == state.CLOCK_WRONG


def test_control_a_small_clock_correction_is_not_a_rollback(clinic_license):
    state.refresh()
    assert state.evaluate(now=NOW - timedelta(hours=2)).state == state.ACTIVE


def test_the_latest_moment_seen_is_kept_in_both_places(db, clinic_license):
    state.refresh(db)
    db.commit()
    in_file = json.loads((clinic_license / "state.json").read_text())["max_seen_at"]
    in_db = db.execute("SELECT value FROM settings WHERE key=%s", (state.MAX_SEEN_SETTING,)).fetchone()["value"]
    assert in_file and in_db


# ---------------------------------------------------------------------------
# A clock that was ahead, and has been put right (the owner's report,
# 2026-10-02)
# ---------------------------------------------------------------------------
# The app ran while the computer's clock was ahead, so the latest time it saw
# is in the future. Once the clock is corrected that reads as a clock wound
# back: read-only, with a message telling staff to correct a clock that is
# right, for as long as the clock had been ahead. A newly issued key from the
# vendor is what ends it -- and only a NEW one, or an old key replayed with
# the clock wound back would end the real thing too.

AHEAD = timedelta(days=40)


def _key(vendor, issued_at, days=365):
    payload = vendor.tool.license_payload(vendor.key, vendor.install_id, "Test Clinic",
                                          issued_at + timedelta(days=days), issued_at=issued_at)
    return vendor.tool.sign(vendor.key, payload)


@pytest.fixture
def clock_was_ahead(clinic_license, vendor, db):
    """The key held was issued 30 days ago; the app has seen a moment 40 days
    from now; the clock is right again. Everything is put back afterwards."""
    key_file, state_file = clinic_license / "license.key", clinic_license / "state.json"
    saved_key = key_file.read_text()
    saved_state = state_file.read_text() if state_file.exists() else None
    saved_row = db.execute("SELECT value FROM settings WHERE key=%s", (state.MAX_SEEN_SETTING,)).fetchone()
    key_file.write_text(_key(vendor, NOW - timedelta(days=30)) + "\n")
    assert state.refresh(db, now=NOW + AHEAD).state == state.ACTIVE          # the app, running with the clock ahead
    db.commit()
    assert state.refresh(db, now=NOW).state == state.CLOCK_WRONG, "arrangement failed: the lockout did not happen"
    yield clinic_license
    key_file.write_text(saved_key)
    if saved_state is None:
        state_file.unlink(missing_ok=True)
    else:
        state_file.write_text(saved_state)
    db.execute("DELETE FROM settings WHERE key=%s", (state.MAX_SEEN_SETTING,))
    if saved_row:
        db.execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (state.MAX_SEEN_SETTING, saved_row["value"]))
    db.commit()
    state.refresh(db)


def test_the_lockout_says_what_was_recorded_and_what_ends_it(clock_was_ahead, db):
    """Staff were told to correct a clock that was right, and nothing else."""
    status = state.evaluate(db, now=NOW)
    assert status.state == state.CLOCK_WRONG and not status.writable
    assert status.message.args["seen"] == clock.aware(NOW + AHEAD).strftime("%Y-%m-%d %H:%M")
    assert status.message.args["seen"] in status.message
    assert "If the clock is right now" in status.message and "new license key" in status.message


def test_a_new_key_ends_a_lockout_from_a_clock_that_was_ahead(clock_was_ahead, vendor, db):
    """GUARD. Before, entering a key changed nothing: the clinic stayed
    read-only until real time caught up with the mistaken time."""
    status = state.enter_key(db, _key(vendor, NOW - timedelta(hours=1)), now=NOW)
    db.commit()
    assert status.state == state.ACTIVE and status.writable
    assert abs(status.clock_accepted_from - (NOW + AHEAD)) < timedelta(seconds=1)
    in_file = json.loads((clock_was_ahead / "state.json").read_text())["max_seen_at"]
    in_db = db.execute("SELECT value FROM settings WHERE key=%s", (state.MAX_SEEN_SETTING,)).fetchone()["value"]
    assert datetime.fromisoformat(in_file) <= NOW and datetime.fromisoformat(in_db) <= NOW
    assert state.evaluate(db, now=NOW + timedelta(minutes=5)).state == state.ACTIVE      # and it stays ended
    assert state.current().clock_accepted_from is None, "the cached status is not the one-off answer"


@pytest.mark.parametrize("what, issued, entered_at", [
    # the key already held, entered again with the clock wound back to the week it was issued
    ("replayed", -timedelta(days=30), -timedelta(days=29)),
    # a newer key, but signed ten days before this computer's "now"
    ("stale", -timedelta(days=10), timedelta(0)),
    # a newer key signed three days after this computer's "now": this clock IS behind
    ("clock behind", timedelta(days=3), timedelta(0)),
])
def test_a_key_that_does_not_vouch_for_the_clock_leaves_the_lockout(clock_was_ahead, vendor, db, what, issued, entered_at):
    """GUARD. Only a key the vendor has just signed, newer than the one held,
    says the clock is right. Anything else would let an expired key be
    replayed on a wound-back clock."""
    status = state.enter_key(db, _key(vendor, NOW + issued), now=NOW + entered_at)
    assert status.state == state.CLOCK_WRONG, what
    assert status.clock_accepted_from is None


def test_the_license_page_ends_the_lockout_and_records_it(flask_app, clock_was_ahead, vendor, db):
    """Through the page the clinic uses, on the real clock."""
    c = _signed_in(flask_app)
    page = c.post("/settings/license", data={"license_key": vendor.license()}, follow_redirects=True)
    assert state.current().state == state.ACTIVE
    assert "The computer&#39;s clock was accepted" in page.get_data(as_text=True)
    newest = "SELECT id, outcome, detail FROM developer_audit WHERE action='license.clock_accepted' ORDER BY id DESC LIMIT 1"
    row = db.execute(newest).fetchone()
    assert row and row["outcome"] == "ok" and row["detail"]["recorded"][:4].isdigit()
    # CONTROL: a key entered when there is no lockout accepts no clock and records none.
    again = c.post("/settings/license", data={"license_key": vendor.license()}, follow_redirects=True)
    assert "License key saved" in again.get_data(as_text=True)
    assert "clock was accepted" not in again.get_data(as_text=True)
    assert db.execute(newest).fetchone()["id"] == row["id"]


# ---------------------------------------------------------------------------
# Read-only: one allowlist, enforced in one hook
# ---------------------------------------------------------------------------

def _writing_rules(flask_app):
    return [r for r in flask_app.url_map.iter_rules() if r.methods & readonly.WRITES and r.endpoint != "static"]


def _url(rule):
    return "".join("2000000001" if part.startswith("<") else part
                   for part in __import__("re").split(r"(<[^>]+>)", rule.rule))


# Endpoints that act on this computer rather than the database (autostart,
# a new folder): the walk asks the hook about them directly, so that a broken
# hook -- as prove_guards.py makes one -- can never run their views here.
_ACT_ON_THE_MACHINE = {"settings.settings_autostart", "settings.api_browse_folder_new"}


def _hook_refuses(flask_app, rule):
    from flask import request, session
    with flask_app.test_request_context(_url(rule), method="POST"):
        assert request.endpoint == rule.endpoint
        session[readonly.SESSION_KEY] = state.READ_ONLY
        resp = readonly.refuse_writes_when_read_only()
        return resp is not None and resp[1] == 403


def test_every_writing_endpoint_is_allowed_or_refused_when_read_only(flask_app, set_license):
    """GUARD (seam rule 1). A session that signed in read-only: every write
    not on the allowlist gets the read-only page, whatever it is."""
    set_license(-30)
    c = _signed_in(flask_app)
    refused, let_through = [], []
    for rule in _writing_rules(flask_app):
        if readonly.allowed(rule.endpoint):
            continue
        if rule.endpoint in _ACT_ON_THE_MACHINE:
            ok = _hook_refuses(flask_app, rule)
        else:
            ok = _refused(c.post(_url(rule), data={}))
        (refused if ok else let_through).append(rule.endpoint)
    assert len(refused) >= 60, f"only {len(refused)} writing endpoints checked -- did the walk see the app?"
    assert let_through == [], f"writing while read-only: {let_through}"


def test_control_the_same_write_works_when_the_license_is_active(flask_app, db):
    c = _signed_in(flask_app)
    name = f"Active-license owner {time.time_ns()}"
    assert c.post("/owners/new", data={"name": name, "phone": "", "address": ""}).status_code == 302
    try:
        assert db.execute("SELECT count(*) AS n FROM owners WHERE name=%s", (name,)).fetchone()["n"] == 1
    finally:
        db.execute("DELETE FROM owners WHERE name=%s", (name,))
        db.commit()


def test_every_allowed_endpoint_exists(flask_app):
    """An allowance for a renamed endpoint allows nothing -- and reads as if
    the action still worked while read-only."""
    endpoints = {r.endpoint for r in flask_app.url_map.iter_rules()}
    assert readonly.ALLOWED <= endpoints, readonly.ALLOWED - endpoints


def test_a_get_is_never_refused(flask_app, set_license):
    set_license(-30)
    c = _signed_in(flask_app)
    assert c.get("/owners").status_code == 200 and c.get("/patients").status_code == 200


def test_a_session_signed_in_before_expiry_keeps_writing(flask_app, set_license, db):
    """GUARD (§6.3). Read-only begins at a sign-in, never mid-task."""
    c = _signed_in(flask_app)                         # while active
    set_license(-30)
    name = f"Mid-task owner {time.time_ns()}"
    try:
        assert c.post("/owners/new", data={"name": name, "phone": "", "address": ""}).status_code == 302
        assert db.execute("SELECT count(*) AS n FROM owners WHERE name=%s", (name,)).fetchone()["n"] == 1
    finally:
        db.execute("DELETE FROM owners WHERE name=%s", (name,))
        db.commit()


def test_a_renewal_unlocks_at_once(flask_app, set_license, vendor, db):
    """§6.2: entered on the License page -- itself allowed while read-only --
    and the same session writes again without signing in."""
    set_license(-30)
    c = _signed_in(flask_app)
    assert _refused(c.post("/owners/new", data={"name": "x", "phone": "", "address": ""}))
    assert c.post("/settings/license", data={"license_key": vendor.license()}).status_code == 302
    name = f"Renewed owner {time.time_ns()}"
    try:
        assert c.post("/owners/new", data={"name": name, "phone": "", "address": ""}).status_code == 302
    finally:
        db.execute("DELETE FROM owners WHERE name=%s", (name,))
        db.commit()


def test_notes_on_an_admitted_animal_still_go_in(flask_app, set_license, db):
    """A7, for animal welfare: the one clinical write read-only keeps."""
    from test_money_routes import _uid
    o, p = _uid("O"), _uid("P")
    db.execute("INSERT INTO owners (id, name) VALUES (%s,%s)", (o, "Welfare Owner"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name) VALUES (%s,%s,%s)", (p, o, "Welfare Pet"))
    case = db.execute("INSERT INTO inpatient_cases (patient_id, admission_date, dismissed, discount_percent, "
                      "total, cleanup_amount) VALUES (%s,%s,false,0,0,0) RETURNING id",
                      (p, NOW.date())).fetchone()["id"]
    db.commit()
    try:
        set_license(-30)
        c = _signed_in(flask_app)
        c.post(f"/inpatient/{case}/update", data={"note": "Ate well"})
        assert db.execute("SELECT count(*) AS n FROM inpatient_updates WHERE case_id=%s", (case,)).fetchone()["n"] == 1
        assert _refused(c.post(f"/inpatient/{case}/payment", data={"amount": "1", "method": "Cash"}))
    finally:
        for sql, arg in (("DELETE FROM inpatient_updates WHERE case_id=%s", case),
                         ("DELETE FROM inpatient_cases WHERE id=%s", case),
                         ("DELETE FROM patients WHERE id=%s", p), ("DELETE FROM owners WHERE id=%s", o)):
            db.execute(sql, (arg,))
        db.commit()


def test_the_nightly_backup_runs_while_read_only(set_license, monkeypatch, db):
    """GUARD (§6.3). Background jobs never pass through the request hook."""
    from vcs.ops import backup, scheduler
    set_license(-30)
    ran = []
    monkeypatch.setattr(scheduler, "_backup_catchup_due", lambda *a: True)
    monkeypatch.setattr(backup, "run_backup", lambda *a, **k: ran.append(k.get("triggered_by")) or (True, ""))
    from vcs.db import pool
    assert scheduler._run_backup_if_due(pool.connect, lambda con: con.close()) is True
    assert ran == ["nightly"]


# ---------------------------------------------------------------------------
# What people see
# ---------------------------------------------------------------------------

def test_the_banners_follow_the_state_and_the_reader(flask_app, set_license, as_role):
    set_license(5)                                          # expiring
    admin, clerk = _signed_in(flask_app), as_role({"manage_patients"})["client"]
    assert "The license expires on" in admin.get("/").get_data(as_text=True)
    assert "The license expires on" not in clerk.get("/patients").get_data(as_text=True)
    set_license(-3)                                         # grace: everyone
    assert "The system becomes read-only on" in clerk.get("/patients").get_data(as_text=True)


def test_a_refused_key_is_recorded_and_changes_nothing(flask_app, vendor, db, clinic_license):
    before = (clinic_license / "license.key").read_text()
    c = _signed_in(flask_app)
    c.post("/settings/license", data={"license_key": vendor.license(install="another-install")})
    assert (clinic_license / "license.key").read_text() == before
    row = db.execute("SELECT outcome, detail FROM developer_audit WHERE action='license.entered' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["outcome"] == "refused" and row["detail"]["reason"] == "install"


# ---------------------------------------------------------------------------
# Setup (L-7)
# ---------------------------------------------------------------------------

def test_setup_does_not_finish_without_a_license(clinic_license, monkeypatch):
    """GUARD. No key, and nobody at the keyboard to paste one."""
    import setup
    key = clinic_license / "license.key"
    saved = key.read_text()
    key.unlink()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.argv", ["setup.py"])
    try:
        with pytest.raises(SystemExit):
            setup.ensure_license()
        with pytest.raises(SystemExit):
            setup.ensure_license("VCS1.not.akey")
        assert not key.exists()
    finally:
        key.write_text(saved)
        state.refresh()


def test_control_setup_finishes_with_a_valid_key(clinic_license, vendor, monkeypatch):
    import setup
    key = clinic_license / "license.key"
    saved = key.read_text()
    key.unlink()
    monkeypatch.setattr("sys.argv", ["setup.py", "--license-key", vendor.license()])
    try:
        assert setup.ensure_license().state == state.ACTIVE and key.exists()
    finally:
        key.write_text(saved)
        state.refresh()
