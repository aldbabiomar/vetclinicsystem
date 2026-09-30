"""
Who reaches the Developer area, and what it leaves behind
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §7, §14.1).

Only a Developer Pass signed for this install opens it -- not a password,
not a role, not a permission: the system Admin, who holds every permission,
is refused on every page. It works with or without a clinic sign-in, and
every sign-in, refused or not, is written to developer_audit, which nothing
prunes and nothing deletes.
"""
import pytest

import source_files
from conftest import needs_db

pytestmark = needs_db


@pytest.fixture(autouse=True)
def _own_sign_in_limit(monkeypatch):
    """These tests sign in often from one address. The limiter is shared with
    the clinic's sign-in, so each test counts against a limiter of its own,
    or the rest of the suite's sign-ins would be refused after them."""
    from vcs.web import core
    monkeypatch.setattr(core, "_LOGIN_ATTEMPTS_BY_IP", {})


def _developer_pages(flask_app):
    """Every GET page of the Developer area behind the pass: all but sign-in."""
    return sorted(r.rule for r in flask_app.url_map.iter_rules()
                  if r.endpoint.startswith("developer.") and "GET" in r.methods
                  and r.endpoint != "developer.login" and "<" not in r.rule)


def _sign_in(c, token):
    return c.post("/developer/login", data={"dev_pass": token})


def _audit(db, action):
    return db.execute("SELECT actor, pass_id, outcome, detail FROM developer_audit WHERE action=%s "
                      "ORDER BY id DESC LIMIT 1", (action,)).fetchone()


def _count(db, action):
    return db.execute("SELECT count(*) AS n FROM developer_audit WHERE action=%s", (action,)).fetchone()["n"]


# ---------------------------------------------------------------------------
# No role, no permission, no clinic sign-in reaches it
# ---------------------------------------------------------------------------

def test_the_system_admin_is_refused_on_every_developer_page(client, flask_app):
    """GUARD. Every permission there is, and none of it opens the area."""
    pages = _developer_pages(flask_app)
    assert len(pages) >= 2, f"only {pages} found -- did the blueprint move?"
    for page in pages:
        r = client.get(page)
        assert r.status_code == 302 and "/developer/login" in r.headers["Location"], (page, r.status_code)


def test_control_a_valid_pass_opens_every_developer_page(flask_app, vendor):
    """Without a clinic sign-in at all (plan A12)."""
    c = flask_app.test_client()
    assert _sign_in(c, vendor.dev_pass()).status_code == 302
    for page in _developer_pages(flask_app):
        # In: not sent to sign in. (/developer/job-status answers 404 JSON
        # without a job id; every page answers 200.)
        r = c.get(page)
        assert r.status_code != 302 and r.status_code < 500, (page, r.status_code)


def test_a_signed_in_admin_with_a_pass_gets_in_too(client, vendor):
    assert _sign_in(client, vendor.dev_pass()).status_code == 302
    assert client.get("/developer/").status_code == 200
    client.post("/developer/logout")


def test_there_is_no_developer_permission():
    """GUARD. Not in the registry, so the role editor cannot grant it and
    the system Admin -- re-granted every permission at seed -- never has it."""
    from vcs import auth
    assert not any("developer" in key for key in auth.PERMISSION_KEY_SET)


def test_a_role_naming_developer_gets_nothing_from_it(client, db):
    import uuid
    name = f"Would-be developer {uuid.uuid4().hex[:6]}"
    client.post("/admin/roles/new", data={"name": name, "description": "", "discount_cap": "0",
                                          "is_vet_role": "N", "permissions": ["developer", "manage_patients"]})
    role = db.execute("SELECT id FROM roles WHERE name=%s", (name,)).fetchone()
    try:
        perms = {r["permission_id"] for r in db.execute(
            "SELECT permission_id FROM role_permissions WHERE role_id=%s", (role["id"],)).fetchall()}
        assert perms == {"manage_patients"}, perms          # the real one kept: the control
    finally:
        db.execute("DELETE FROM role_permissions WHERE role_id=%s", (role["id"],))
        db.execute("DELETE FROM roles WHERE id=%s", (role["id"],))
        db.commit()


# ---------------------------------------------------------------------------
# Passes that must not open it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("which", ["another_install", "expired", "license", "garbage"])
def test_a_pass_that_is_not_for_now_and_here_is_refused_and_recorded(flask_app, vendor, db, which):
    from datetime import datetime, timedelta, timezone
    token = {"another_install": lambda: vendor.dev_pass(install="another-install"),
             "expired": lambda: vendor.tool.sign(vendor.key, vendor.tool.pass_payload(
                 vendor.key, vendor.install_id, "Dev", hours=1,
                 issued_at=datetime.now(timezone.utc) - timedelta(hours=2))),
             "license": vendor.license,
             "garbage": lambda: "not a pass"}[which]()
    c = flask_app.test_client()
    before = _count(db, "developer.login_failed")
    r = _sign_in(c, token)
    assert r.status_code == 400
    assert c.get("/developer/").status_code == 302
    assert _count(db, "developer.login_failed") == before + 1, "the refusal was not recorded"
    row = _audit(db, "developer.login_failed")
    assert row["outcome"] == "refused" and row["detail"]["reason"]
    assert token not in str(row["detail"]), "a pasted pass must never be written down"


def test_a_session_ends_when_its_pass_does(flask_app, vendor):
    c = flask_app.test_client()
    _sign_in(c, vendor.dev_pass())
    with c.session_transaction() as sess:
        sess["developer"]["expires_at"] = "2000-01-01T00:00:00+00:00"
        sess.modified = True
    assert c.get("/developer/").status_code == 302


def test_developer_sign_in_shares_the_clinic_sign_in_limit(flask_app, vendor, monkeypatch):
    """GUARD. The same limiter, so a script cannot try passes where it could
    not try passwords."""
    import time
    from vcs.web import core
    monkeypatch.setitem(core._LOGIN_ATTEMPTS_BY_IP, "127.0.0.1",
                        [time.monotonic()] * core._LOGIN_RATE_LIMIT_MAX)
    assert _sign_in(flask_app.test_client(), vendor.dev_pass()).status_code == 429


# ---------------------------------------------------------------------------
# What it leaves behind
# ---------------------------------------------------------------------------

def test_a_sign_in_is_recorded_with_the_developers_name(flask_app, vendor, db):
    c = flask_app.test_client()
    before = _count(db, "developer.login")
    _sign_in(c, vendor.dev_pass())
    assert _count(db, "developer.login") == before + 1, "the sign-in was not recorded"
    row = _audit(db, "developer.login")
    assert row["actor"] == "dev:Test Developer" and row["pass_id"].startswith("P-") and row["outcome"] == "ok"


def test_nothing_prunes_or_deletes_the_developer_audit():
    """GUARD (A10). The clinic's log retention setting prunes audit_log; it
    must not reach what the vendor did."""
    from vcs.domain import logs
    assert "developer_audit" not in {t for t, _ in logs.RETENTION_TABLES}
    files = source_files.all_python()
    assert len(files) >= 60
    deleting = [p.name for p in files
                if "DELETE FROM developer_audit" in p.read_text(encoding="utf-8").replace("\n", " ")]
    assert deleting == []


def test_the_clinic_can_read_what_its_vendor_did(client, flask_app, vendor):
    """A10: holders of view_logins_changes, from the audit-log page."""
    _sign_in(flask_app.test_client(), vendor.dev_pass())
    page = client.get("/admin/developer-audit").get_data(as_text=True)
    assert "Signed in to the Developer area" in page and "dev:Test Developer" in page


def test_the_developer_group_is_drawn_only_in_a_developer_session(client, vendor):
    assert "/developer/audit" not in client.get("/").get_data(as_text=True)
    _sign_in(client, vendor.dev_pass())
    assert "/developer/audit" in client.get("/").get_data(as_text=True)
    client.post("/developer/logout")
    assert "/developer/audit" not in client.get("/").get_data(as_text=True)
