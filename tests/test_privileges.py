"""
Nobody hands out more access than they hold (audit S2), and a field hidden
from a role is also refused to it (audit S1).

S2: a user whose role held only `manage_users_roles` promoted themselves to
the system Admin role in one POST, and could reset the Admin's password,
create a role with every permission, or delete their own role and land in a
bigger one. S1: a role with only `manage_settings` could not see the backup
fields but could still post them — `backup_retention=1` deletes every older
backup on the next run.

Each guard is paired with a control: the same action by someone allowed to
take it succeeds, so "refused for the right reason" is distinguishable from
"refused for any reason".
"""
import uuid

import pytest

from vcs import auth
from conftest import ADMIN_ID, needs_db

pytestmark = needs_db

PASSWORD = "LimitedPass12345!"


@pytest.fixture
def as_role(flask_app, db):
    """as_role({perm, ...}) -> {"client", "user_id", "role_id"}: a user in a
    fresh role holding exactly those permissions, signed in."""
    made = []

    def make(perms):
        tag = uuid.uuid4().hex[:8]
        role_id = db.execute(
            "INSERT INTO roles (name, description, is_system, discount_cap, is_vet_role, created_at) "
            "VALUES (%s,%s,false,0,false,now()) RETURNING id", (f"Limited {tag}", "privilege test")).fetchone()["id"]
        for p in perms:
            db.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", (role_id, p))
        user_id = db.execute(
            "INSERT INTO users (username, password_hash, full_name, role_id, active, must_change_password, created_at) "
            "VALUES (%s,%s,%s,%s,true,false,now()) RETURNING id",
            (f"limited{tag}", auth.hash_password(PASSWORD), "Limited User", role_id)).fetchone()["id"]
        db.commit()
        made.append((user_id, role_id))
        client = flask_app.test_client()
        # Each sign-in from its own LAN address: the app allows 20 sign-ins
        # per address per 5 minutes, and this module signs in more often
        # than that. Asserted, because a refused sign-in makes every POST
        # below bounce off the login gate — and a guard test would pass.
        client.post("/login", data={"username": f"limited{tag}", "password": PASSWORD},
                    environ_base={"REMOTE_ADDR": f"10.77.{len(made)}.{uuid.uuid4().int % 250 + 1}"})
        with client.session_transaction() as sess:
            assert sess.get("user_id") == user_id, "the limited user could not sign in"
        return {"client": client, "user_id": user_id, "role_id": role_id}

    yield make
    db.rollback()
    for user_id, _ in made:
        for table in ("login_log", "audit_log"):
            db.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
        db.execute("DELETE FROM users WHERE id=%s", (user_id,))
    # By id — a test may have renamed a role or cleared its description —
    # plus any role a test created through the admin screens, which all carry
    # the marker description.
    role_ids = {r for _, r in made} | {r["id"] for r in db.execute(
        "SELECT id FROM roles WHERE description='privilege test' AND NOT is_system").fetchall()}
    for role_id in role_ids:
        db.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
        db.execute("DELETE FROM roles WHERE id=%s AND NOT is_system", (role_id,))
    db.commit()


@pytest.fixture(autouse=True)
def admin_restored(db, as_role):
    """Put the seeded Admin back as it was, whatever the test did. When a
    guard below is broken (or mutated to prove the test), the escalation
    SUCCEEDS — the Admin is disabled, their password replaced, or moved into
    a test role — and every later test that signs in as the Admin would fail
    for that reason instead of its own. Depends on as_role so that it is torn
    down FIRST: the Admin must be out of a test role before that role is
    deleted."""
    cols = "active, must_change_password, password_hash, password_changed_at, role_id"
    saved = db.execute(f"SELECT {cols} FROM users WHERE id=%s", (ADMIN_ID,)).fetchone()
    yield
    db.rollback()
    db.execute("UPDATE users SET active=%s, must_change_password=%s, password_hash=%s, password_changed_at=%s, role_id=%s "
               "WHERE id=%s", (saved["active"], saved["must_change_password"], saved["password_hash"],
                              saved["password_changed_at"], saved["role_id"], ADMIN_ID))
    db.commit()


def _admin_role(db):
    return db.execute("SELECT id FROM roles WHERE is_system").fetchone()["id"]


def _role_of(db, user_id):
    return db.execute("SELECT role_id FROM users WHERE id=%s", (user_id,)).fetchone()["role_id"]


# ---------------------------------------------------------------------------
# S2 — manage_users_roles is not a route to Admin
# ---------------------------------------------------------------------------

def test_a_users_and_roles_holder_cannot_promote_themselves_to_admin(db, as_role):
    """GUARD. The audit's own repro."""
    me = as_role({"manage_users_roles"})
    me["client"].post(f"/admin/users/{me['user_id']}/role", data={"role_id": _admin_role(db)})
    assert _role_of(db, me["user_id"]) == me["role_id"], "promoted themselves to Admin"


def test_control_an_admin_can_assign_the_admin_role(client, db, as_role):
    other = as_role({"manage_owners"})
    client.post(f"/admin/users/{other['user_id']}/role", data={"role_id": _admin_role(db)})
    assert _role_of(db, other["user_id"]) == _admin_role(db)


def test_they_cannot_reset_the_admins_password(db, as_role):
    """GUARD. Resetting a password is signing in as that person."""
    me = as_role({"manage_users_roles"})
    before = db.execute("SELECT password_hash FROM users WHERE id=%s", (ADMIN_ID,)).fetchone()["password_hash"]
    me["client"].post(f"/admin/users/{ADMIN_ID}/reset-password", data={"new_password": "Takeover12345!"})
    after = db.execute("SELECT password_hash FROM users WHERE id=%s", (ADMIN_ID,)).fetchone()["password_hash"]
    assert after == before


def test_control_they_can_reset_a_password_within_their_own_access(db, as_role):
    me = as_role({"manage_users_roles", "manage_owners"})
    other = as_role({"manage_owners"})
    me["client"].post(f"/admin/users/{other['user_id']}/reset-password", data={"new_password": "FreshStart12345!"})
    row = db.execute("SELECT password_hash FROM users WHERE id=%s", (other["user_id"],)).fetchone()
    assert auth.verify_password(row["password_hash"], "FreshStart12345!")


def test_they_cannot_create_a_role_holding_a_permission_they_lack(db, as_role):
    """GUARD."""
    me = as_role({"manage_users_roles"})
    name = f"Escalate {uuid.uuid4().hex[:6]}"
    me["client"].post("/admin/roles/new", data={"name": name, "discount_cap": "0",
                                                 "permissions": ["manage_users_roles", "manage_maintenance"],
                                                 "description": "privilege test"})
    assert db.execute("SELECT 1 FROM roles WHERE name=%s", (name,)).fetchone() is None


def test_control_they_can_create_a_role_within_their_own_access(db, as_role):
    me = as_role({"manage_users_roles", "manage_owners"})
    name = f"Within {uuid.uuid4().hex[:6]}"
    me["client"].post("/admin/roles/new", data={"name": name, "discount_cap": "0",
                                                 "permissions": ["manage_owners"], "description": "privilege test"})
    assert db.execute("SELECT 1 FROM roles WHERE name=%s", (name,)).fetchone() is not None


def test_they_cannot_create_a_user_in_the_admin_role(db, as_role):
    """GUARD. They set the new user's password, so they would be that user."""
    me = as_role({"manage_users_roles"})
    username = f"sock{uuid.uuid4().hex[:6]}"
    try:
        me["client"].post("/admin/users/new", data={"username": username, "full_name": "Sock Puppet",
                                                     "password": "SockPuppet12345!", "role_id": _admin_role(db)})
        assert db.execute("SELECT 1 FROM users WHERE username=%s", (username,)).fetchone() is None
    finally:
        db.execute("DELETE FROM audit_log WHERE table_name='users' AND record_id IN "
                   "(SELECT id::text FROM users WHERE username=%s)", (username,))
        db.execute("DELETE FROM users WHERE username=%s", (username,))
        db.commit()


def test_control_they_can_create_a_user_within_their_own_access(db, as_role):
    me = as_role({"manage_users_roles", "manage_owners"})
    peer = as_role({"manage_owners"})
    username = f"peer{uuid.uuid4().hex[:6]}"
    try:
        me["client"].post("/admin/users/new", data={"username": username, "full_name": "Peer",
                                                     "password": "PeerUser12345!", "role_id": peer["role_id"]})
        assert db.execute("SELECT 1 FROM users WHERE username=%s", (username,)).fetchone() is not None
    finally:
        db.execute("DELETE FROM audit_log WHERE table_name='users' AND record_id IN "
                   "(SELECT id::text FROM users WHERE username=%s)", (username,))
        db.execute("DELETE FROM users WHERE username=%s", (username,))
        db.commit()


def test_they_cannot_disable_an_admin(db, as_role):
    """GUARD. With a second active Admin present, so the "last active Admin"
    rule cannot be what refuses it — only the privilege rule can."""
    me = as_role({"manage_users_roles"})
    second = db.execute(
        "INSERT INTO users (username, password_hash, full_name, role_id, active, must_change_password, created_at) "
        "VALUES (%s,%s,%s,%s,true,false,now()) RETURNING id",
        (f"admin2{uuid.uuid4().hex[:6]}", auth.hash_password(PASSWORD), "Second Admin", _admin_role(db))).fetchone()["id"]
    db.commit()
    try:
        me["client"].post(f"/admin/users/{ADMIN_ID}/toggle-active")
        assert db.execute("SELECT active FROM users WHERE id=%s", (ADMIN_ID,)).fetchone()["active"] is True
    finally:
        db.execute("DELETE FROM users WHERE id=%s", (second,))
        db.commit()


def test_they_cannot_delete_their_own_role_into_the_admin_role(db, as_role):
    """GUARD. The same escalation by a longer road: delete the role you are
    in, and have its staff — you — reassigned to Admin."""
    me = as_role({"manage_users_roles"})
    me["client"].post(f"/admin/roles/{me['role_id']}/delete", data={"reassign_to": _admin_role(db)})
    assert _role_of(db, me["user_id"]) != _admin_role(db)


# ---------------------------------------------------------------------------
# S1 — a field the template hides is refused by the POST
# ---------------------------------------------------------------------------

def _setting(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else None


@pytest.mark.parametrize("key,value", [("backup_retention", "1"), ("log_retention_days", "90"),
                                       ("backup_dir", "/tmp/elsewhere"), ("backup_time", "03:33")])
def test_a_settings_only_role_cannot_post_the_backup_fields(db, as_role, key, value):
    """GUARD. The audit's repro, one field at a time: backup_retention=1
    would delete every older backup on the next run."""
    me = as_role({"manage_settings"})
    before = _setting(db, key)
    resp = me["client"].post("/settings", data={key: value}, follow_redirects=True)
    assert _setting(db, key) == before
    assert "Nothing was saved" in resp.get_data(as_text=True)


def test_control_the_same_role_can_save_the_fields_it_holds(db, as_role):
    me = as_role({"manage_settings"})
    before = _setting(db, "clinic_location")
    try:
        me["client"].post("/settings", data={"clinic_location": "Privilege Test"})
        assert _setting(db, "clinic_location") == "Privilege Test"
    finally:
        db.execute("DELETE FROM settings WHERE key='clinic_location'") if before is None else \
            db.execute("UPDATE settings SET value=%s WHERE key='clinic_location'", (before,))
        db.commit()


def test_the_backup_fields_are_drawn_only_for_those_who_may_save_them(client, as_role):
    me = as_role({"manage_settings"})
    assert 'name="backup_retention"' not in me["client"].get("/settings").get_data(as_text=True)
    assert 'name="backup_retention"' in client.get("/settings").get_data(as_text=True)


def test_control_they_can_disable_a_user_within_their_own_access(db, as_role):
    me = as_role({"manage_users_roles", "manage_owners"})
    peer = as_role({"manage_owners"})
    me["client"].post(f"/admin/users/{peer['user_id']}/toggle-active")
    assert db.execute("SELECT active FROM users WHERE id=%s", (peer["user_id"],)).fetchone()["active"] is False


def test_they_cannot_move_an_admin_into_a_smaller_role(db, as_role):
    """GUARD. Taking access away is reaching it too: a manage_users_roles
    holder could otherwise demote every Admin into their own role. A second
    active Admin is present so the "last active Admin" rule is not what
    refuses it."""
    me = as_role({"manage_users_roles"})
    second = db.execute(
        "INSERT INTO users (username, password_hash, full_name, role_id, active, must_change_password, created_at) "
        "VALUES (%s,%s,%s,%s,true,false,now()) RETURNING id",
        (f"admin2{uuid.uuid4().hex[:6]}", auth.hash_password(PASSWORD), "Second Admin", _admin_role(db))).fetchone()["id"]
    db.commit()
    try:
        me["client"].post(f"/admin/users/{ADMIN_ID}/role", data={"role_id": me["role_id"]})
        assert _role_of(db, ADMIN_ID) == _admin_role(db)
    finally:
        db.execute("DELETE FROM users WHERE id=%s", (second,))
        db.commit()


def test_they_cannot_edit_a_role_that_holds_more_than_they_do(db, as_role):
    """GUARD. Editing a stronger role — even only to strip it — is refused."""
    me = as_role({"manage_users_roles"})
    stronger = as_role({"manage_users_roles", "manage_maintenance"})
    me["client"].post(f"/admin/roles/{stronger['role_id']}/edit",
                      data={"name": f"Stripped {uuid.uuid4().hex[:6]}", "discount_cap": "0",
                            "permissions": ["manage_users_roles"], "description": "privilege test"})
    perms = {r["permission_id"] for r in db.execute(
        "SELECT permission_id FROM role_permissions WHERE role_id=%s", (stronger["role_id"],)).fetchall()}
    assert perms == {"manage_users_roles", "manage_maintenance"}


def test_control_they_can_edit_a_role_within_their_own_access(db, as_role):
    me = as_role({"manage_users_roles", "manage_owners"})
    peer = as_role({"manage_owners"})
    me["client"].post(f"/admin/roles/{peer['role_id']}/edit",
                      data={"name": f"Edited {uuid.uuid4().hex[:6]}", "discount_cap": "0", "permissions": [],
                            "description": "privilege test"})
    assert db.execute("SELECT COUNT(*) c FROM role_permissions WHERE role_id=%s", (peer["role_id"],)).fetchone()["c"] == 0


def test_they_cannot_delete_a_role_that_holds_more_than_they_do(db, as_role):
    """GUARD."""
    me = as_role({"manage_users_roles"})
    stronger = as_role({"manage_users_roles", "manage_maintenance"})
    me["client"].post(f"/admin/roles/{stronger['role_id']}/delete", data={"reassign_to": me["role_id"]})
    assert db.execute("SELECT 1 FROM roles WHERE id=%s", (stronger["role_id"],)).fetchone() is not None
    assert _role_of(db, stronger["user_id"]) == stronger["role_id"]


def test_signed_out_by_a_password_change_is_told_why_and_brought_back(db, as_role):
    """GUARD (audit P14). One predecessor app said why and lost the page; the
    other kept the page and said nothing."""
    me = as_role({"manage_owners"})
    db.execute("UPDATE users SET password_changed_at = now() WHERE id=%s", (me["user_id"],))
    db.commit()
    resp = me["client"].get("/owners")
    location = resp.headers["Location"]
    assert resp.status_code == 302 and ("next=/owners" in location or "next=%2Fowners" in location), location
    login_page = me["client"].get(resp.headers["Location"]).get_data(as_text=True)
    assert "Your password was changed" in login_page
    username = db.execute("SELECT username FROM users WHERE id=%s", (me["user_id"],)).fetchone()["username"]
    back = me["client"].post(resp.headers["Location"], data={"username": username, "password": PASSWORD},
                             environ_base={"REMOTE_ADDR": "10.78.1.1"})
    assert back.status_code == 302 and back.headers["Location"].endswith("/owners"), back.headers.get("Location")
