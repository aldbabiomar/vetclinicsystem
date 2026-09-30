"""
The vendor's tools (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11, §14.1):
Developer -> System, the support bundle, restoring administrator access, the
full data export and the vendor's message.

The support bundle and the export are where clinic data and secrets could
leave the building, so their tests plant both -- a patient's name, a phone
number, an e-mail address, the update token, the ping URL, the license key,
the database password, the app's secret key -- in the database and in the
logs, and look for every one in every file of the ZIP.
"""
import csv
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import timedelta

import pytest

from conftest import needs_db, new_id
from vcs import auth, clock

pytestmark = needs_db
PASSWORD = "Admin12345!"

PATIENT = "Zanzibarella"
PHONE = "+964 770 123 4567"
PHONE_DIGITS = "7701234567"
EMAIL = "owner.person@example.com"
TOKEN = "ghp_PLANTED_TEST_ONLY_not_a_real_token_77"   # underscores: no real token has them
PING = "https://hc-ping.example/SECRET-BUNDLE-MARKER-77"
DB_PASSWORD = "Db-Password-Planted-9931"
SECRET_KEY = "secret-key-planted-for-the-bundle-test-000000"


@pytest.fixture(autouse=True)
def _own_sign_in_limit(monkeypatch):
    from vcs.web import core
    monkeypatch.setattr(core, "_LOGIN_ATTEMPTS_BY_IP", {})


def _setting(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else None


@pytest.fixture
def settings_left_as_found(db):
    from vcs.domain import vendor_message
    keys = ("heartbeat_url", *vendor_message.KEYS)
    saved = {k: _setting(db, k) for k in keys}
    yield
    for key, value in saved.items():
        if value is None:
            db.execute("DELETE FROM settings WHERE key=%s", (key,))
        else:
            db.execute("INSERT INTO settings (key, value) VALUES (%s,%s) "
                       "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """The error and update logs the System page and the bundle read, in a
    folder of this test's own."""
    from vcs.ops import system_info
    errors, updates = tmp_path / "errors.log", tmp_path / "updates.log"
    monkeypatch.setattr(system_info, "error_log_path", lambda: str(errors))
    monkeypatch.setattr(system_info, "updates_log_path", lambda: str(updates))
    return errors, updates


@pytest.fixture
def token_home(tmp_path, monkeypatch):
    from vcs.ops import updater
    monkeypatch.setattr(updater, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def planted(db, logs, token_home, clinic_license, monkeypatch, settings_left_as_found):
    """Every secret set to a known value, and clinic data with a patient's
    name, a phone number and an e-mail address, in the database and in the
    logs, the way a real failure would write them."""
    from vcs.ops import updater
    updater.save_token(TOKEN)
    db.execute("INSERT INTO settings (key, value) VALUES ('heartbeat_url', %s) "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (PING,))
    monkeypatch.setenv("DATABASE_URL", f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/vetclinicsystem")
    monkeypatch.setenv("SECRET_KEY", SECRET_KEY)
    license_key = (clinic_license / "license.key").read_text().strip()
    o, p = new_id(), new_id()
    db.execute("INSERT INTO owners (id, name, phone) VALUES (%s,%s,%s)", (o, "Planted Owner", PHONE.replace(" ", "")))
    db.execute("INSERT INTO patients (id, owner_id, animal_name, species, sex) VALUES (%s,%s,%s,'Dog','Male')",
               (p, o, PATIENT))
    db.commit()
    errors, updates = logs
    errors.write_text(
        "[ref A1B2C3] 2026-09-30 10:00:00 POST /owners/new\n"
        "Traceback (most recent call last):\n"
        '  File "/app/vcs/web/blueprints/clinical.py", line 12, in owner_new\n'
        "    db.execute(sql, params)\n"
        'psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "owners_phone_key"\n'
        f"DETAIL:  Key (phone)=({PHONE}) already exists.\n"
        f"DETAIL:  Failing row contains ({p}, {PATIENT}, Dog, 0770 123 4567).\n"
        f"ValueError: the owner of '{PATIENT}' could not be saved; write to {EMAIL}\n"
        f"GitHub refused the token {TOKEN}\n"
        f"The ping to {PING} failed\n"
        f"connection failed: postgresql://postgres:{DB_PASSWORD}@localhost:5432/vetclinicsystem\n"
        f"session signing with {SECRET_KEY}\n"
        f"license {license_key}\n", encoding="utf-8")
    updates.write_text(f"2026-09-30 10:00:00  Downloading with {TOKEN}\n", encoding="utf-8")
    yield {"license_key": license_key}
    db.execute("DELETE FROM patients WHERE id=%s", (p,))
    db.execute("DELETE FROM owners WHERE id=%s", (o,))
    db.commit()


def _secrets_and_pii(planted):
    return [PATIENT, PHONE, PHONE_DIGITS, EMAIL, TOKEN, PING, DB_PASSWORD, SECRET_KEY, planted["license_key"],
            "SECRET-BUNDLE-MARKER", "owner.person"]


def _all_text(z):
    return {name: z.read(name).decode("utf-8", "replace") for name in z.namelist()}


# ---------------------------------------------------------------------------
# System (§11.1)
# ---------------------------------------------------------------------------

def test_the_system_page_shows_what_the_app_knows(developer, db):
    """CONTROL: the facts are there -- the version, the database's version,
    the tools, the self-check."""
    from vcs.web.core import VERSION
    server = db.execute("SHOW server_version").fetchone()["server_version"]
    page = developer.get("/developer/system").get_data(as_text=True)
    assert VERSION in page and server in page and "pg_dump" in page


def test_the_error_log_on_the_system_page_is_redacted(developer, planted):
    page = developer.get("/developer/system").get_data(as_text=True)
    assert "clinical.py" in page and "UniqueViolation" in page          # the log is there
    for value in _secrets_and_pii(planted):
        assert value not in page, value


def test_running_the_self_check_records_it_with_the_disk_it_read(developer, db):
    before = db.execute("SELECT COALESCE(MAX(id), 0) AS n FROM self_check_log").fetchone()["n"]
    developer.post("/developer/system/self-check")
    row = db.execute("SELECT * FROM self_check_log WHERE id > %s ORDER BY id DESC LIMIT 1", (before,)).fetchone()
    assert row is not None and row["disk_free_bytes"] and row["disk_free_bytes"] > 0
    assert db.execute("SELECT 1 FROM developer_audit WHERE action='selfcheck.run' ORDER BY id DESC LIMIT 1"
                      ).fetchone()


# ---------------------------------------------------------------------------
# The support bundle (§11.2)
# ---------------------------------------------------------------------------

def test_the_support_bundle_carries_no_secret_and_no_clinic_data(developer, db, planted):
    """GUARD (§11.2, seam rule 4). Planted in the database and in both logs;
    looked for in every file."""
    resp = developer.post("/developer/support/bundle")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
    files = _all_text(zipfile.ZipFile(io.BytesIO(resp.data)))
    assert len(files) >= 9
    for name, text in files.items():
        for value in _secrets_and_pii(planted):
            assert value not in text, f"{value!r} is in {name}"


def test_control_the_bundle_says_what_it_should(developer, db, planted):
    """CONTROL: the redaction left the useful parts -- the version, the
    self-check result, the log's own lines and file names."""
    from vcs.ops import selfcheck
    from vcs.web.core import VERSION
    selfcheck.record(db, selfcheck.run_self_check(db))
    files = _all_text(zipfile.ZipFile(io.BytesIO(developer.post("/developer/support/bundle").data)))
    assert VERSION in files["system.json"]
    check = json.loads(files["self_check.json"])
    assert check["status"] in ("ok", "warn", "fail")
    assert 'File "/app/vcs/web/blueprints/clinical.py", line 12' in files["errors.log"]
    assert "UniqueViolation" in files["errors.log"] and "[redacted]" in files["errors.log"]
    sent = json.loads(files["settings.json"])
    assert sent["money_setting"] in ("IQ", "JO") and "heartbeat_url" not in sent
    assert json.loads(files["license.json"])["state"] == "active"
    row = db.execute("SELECT target FROM developer_audit WHERE action='support_bundle.generated' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["target"].startswith("vcs-support-")


def test_the_bundle_takes_settings_by_allowlist_not_by_exclusion(developer, db):
    """A setting added later -- a secret, say -- stays out without anyone
    remembering to exclude it."""
    db.execute("INSERT INTO settings (key, value) VALUES ('some_future_secret', 'FUTURE-SECRET-4411') "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value")
    db.commit()
    try:
        files = _all_text(zipfile.ZipFile(io.BytesIO(developer.post("/developer/support/bundle").data)))
        assert "FUTURE-SECRET-4411" not in "".join(files.values())
    finally:
        db.execute("DELETE FROM settings WHERE key='some_future_secret'")
        db.commit()


# ---------------------------------------------------------------------------
# Restore administrator access (§11.3)
# ---------------------------------------------------------------------------

@pytest.fixture
def spare_admin(db, flask_app):
    """A system administrator with a session open, then locked out by
    failed sign-ins."""
    role = db.execute("SELECT id FROM roles WHERE is_system ORDER BY id LIMIT 1").fetchone()["id"]
    uid = new_id()
    username = f"spare{uid % 1_000_000}"
    db.execute("INSERT INTO users (id, username, password_hash, full_name, role_id, created_at) "
               "VALUES (%s,%s,%s,%s,%s,%s)",
               (uid, username, auth.hash_password("Old-Password-123"), "Spare Admin", role, clock.now()))
    db.commit()
    session = flask_app.test_client()
    assert session.post("/login", data={"username": username, "password": "Old-Password-123"}).status_code == 302
    time.sleep(0.05)
    for _ in range(6):                     # after that sign-in (or they would not count), before the reset
        db.execute("INSERT INTO login_log (username, success, timestamp, ip) VALUES (%s, 0, %s, '127.0.0.1')",
                   (username, clock.now()))
    db.commit()
    yield {"id": uid, "username": username, "session": session}
    db.execute("DELETE FROM login_log WHERE username=%s", (username,))
    db.execute("DELETE FROM users WHERE id=%s", (uid,))
    db.commit()


def test_restoring_admin_access(developer, db, flask_app, spare_admin):
    """The whole path (§11.3): a temporary password shown once; the lockout
    cleared; the open session ended; forced to change it at sign-in; and
    both logs say so -- without the password."""
    uid, username = spare_admin["id"], spare_admin["username"]
    assert auth.login_lock_status(db, username)[0], "the fixture must lock the account"
    audit_from = db.execute("SELECT COALESCE(MAX(id), 0) AS n FROM audit_log").fetchone()["n"]
    resp = developer.post("/developer/support/recover", data={"user_id": uid})
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
    password = re.search(r'<div class="code-box u-mono">([^<]+)</div>', resp.get_data(as_text=True)).group(1)
    assert auth.password_error(password, username) is None

    assert not auth.login_lock_status(db, username)[0], "the lockout outlived the reset"
    assert spare_admin["session"].get("/").status_code == 302, "their open session survived"
    fresh = flask_app.test_client()
    signed_in = fresh.post("/login", data={"username": username, "password": password})
    assert signed_in.status_code == 302
    assert fresh.get("/").headers["Location"].endswith("/change-password")

    change = db.execute("SELECT username, new_value FROM audit_log WHERE table_name='users' AND record_id=%s "
                        "AND id > %s", (str(uid), audit_from)).fetchone()
    assert change["new_value"] == "(reset by vendor)" and change["username"] == "dev:Test Developer"
    recovered = db.execute("SELECT detail FROM developer_audit WHERE action='admin.recovered' AND target=%s",
                           (str(uid),)).fetchone()
    assert recovered["detail"] == {"username": username}
    written = " ".join(str(v) for table in ("audit_log", "developer_audit", "login_log")
                       for r in db.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 50").fetchall()
                       for v in r.values())
    assert password not in written
    with developer.session_transaction() as s:
        assert password not in json.dumps(dict(s), default=str), "the password went into the session cookie"


def test_only_a_system_administrator_can_be_restored(developer, db):
    """GUARD: this is for getting the clinic's administration back, not a
    way into any account."""
    role = db.execute("SELECT id FROM roles WHERE NOT is_system ORDER BY id LIMIT 1").fetchone()["id"]
    uid = new_id()
    db.execute("INSERT INTO users (id, username, password_hash, full_name, role_id, created_at) "
               "VALUES (%s,%s,%s,'Staff',%s,%s)",
               (uid, f"staff{uid % 1_000_000}", auth.hash_password("Staff-Password-1"), role, clock.now()))
    db.commit()
    before = db.execute("SELECT password_hash FROM users WHERE id=%s", (uid,)).fetchone()["password_hash"]
    try:
        page = developer.post("/developer/support/recover", data={"user_id": uid},
                              follow_redirects=True).get_data(as_text=True)
        assert "Only an active system administrator" in page
        assert db.execute("SELECT password_hash FROM users WHERE id=%s", (uid,)).fetchone()["password_hash"] == before
    finally:
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        db.commit()


# ---------------------------------------------------------------------------
# The data export (§11.4)
# ---------------------------------------------------------------------------

@pytest.fixture
def export_home(tmp_path, monkeypatch):
    from vcs.ops import data_export
    monkeypatch.setattr(data_export, "export_dir", lambda: str(tmp_path / "exports"))
    return tmp_path / "exports"


@pytest.fixture
def attachment(db, tmp_path, monkeypatch):
    """One uploaded file, on disk and in the attachments table."""
    from vcs.domain import attachments
    root = tmp_path / "uploads"
    monkeypatch.setattr(attachments, "UPLOAD_ROOT", str(root))
    o, p, v = new_id(), new_id(), new_id()
    db.execute("INSERT INTO owners (id, name) VALUES (%s,%s)", (o, "Export Owner"))
    db.execute("INSERT INTO patients (id, owner_id, animal_name, species, sex) VALUES (%s,%s,'Export Pet','Cat','Female')",
               (p, o))
    db.execute("INSERT INTO visits (id, patient_id, date, case_status) VALUES (%s,%s,%s,'Ongoing')",
               (v, p, clock.today().isoformat()))
    relative = f"{p}/visit_{v}/xray.txt"
    (root / f"{p}" / f"visit_{v}").mkdir(parents=True)
    (root / relative).write_bytes(b"X-RAY BYTES")
    a = db.execute("INSERT INTO attachments (patient_id, visit_id, relative_path, original_name, uploaded_at) "
                   "VALUES (%s,%s,%s,'xray.txt',%s) RETURNING id", (p, v, relative, clock.now())).fetchone()["id"]
    db.commit()
    yield relative
    db.execute("DELETE FROM attachments WHERE id=%s", (a,))
    db.execute("DELETE FROM visits WHERE id=%s", (v,))
    db.execute("DELETE FROM patients WHERE id=%s", (p,))
    db.execute("DELETE FROM owners WHERE id=%s", (o,))
    db.commit()


def _export(export_home):
    from vcs.db import pool
    from vcs.ops import data_export
    conn = pool.connect()
    try:
        name = data_export.run(conn)
    finally:
        conn.close()
    return zipfile.ZipFile(export_home / name)


def test_every_table_is_exported_or_excluded(db, export_home):
    """GUARD (§14.2): the tables come from the live schema, so a table added
    later is exported -- or someone decided, in the registry, why not."""
    from vcs.ops import data_export
    z = _export(export_home)
    manifest = json.loads(z.read("manifest.json"))
    live = set(data_export.live_tables(db))
    assert len(live) >= 40, f"only {len(live)} tables found -- the scan is looking at the wrong schema"
    assert set(manifest["tables"]) | set(data_export.EXCLUDED_TABLES) == live
    for table, entry in manifest["tables"].items():
        data = z.read(f"data/{table}.csv")
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_the_row_counts_match_the_database(db, export_home, settings_left_as_found):
    from vcs.domain import settings
    db.execute("INSERT INTO settings (key, value) VALUES ('heartbeat_url', %s) "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (PING,))
    db.commit()
    z = _export(export_home)
    manifest = json.loads(z.read("manifest.json"))
    checked = 0
    for table, entry in manifest["tables"].items():
        expected = db.execute(f'SELECT count(*) AS n FROM "{table}"').fetchone()["n"]
        if table == "settings":
            expected -= db.execute("SELECT count(*) AS n FROM settings WHERE key = ANY(%s)",
                                   (list(settings.SECRET_KEYS),)).fetchone()["n"]
        rows = list(csv.reader(io.StringIO(z.read(f"data/{table}.csv").decode("utf-8-sig"))))
        assert entry["rows"] == expected == len(rows) - 1, table
        checked += 1
    assert checked >= 40


def test_the_export_holds_no_password_hash_and_no_ping_url(db, export_home, settings_left_as_found):
    db.execute("INSERT INTO settings (key, value) VALUES ('heartbeat_url', %s) "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (PING,))
    db.commit()
    z = _export(export_home)
    users = z.read("data/users.csv").decode("utf-8-sig")
    assert "password_hash" not in users.splitlines()[0] and "username" in users.splitlines()[0]
    everything = b"".join(z.read(n) for n in z.namelist())
    assert b"pbkdf2:" not in everything and b"scrypt:" not in everything
    assert PING.encode() not in everything and b"SECRET-BUNDLE-MARKER" not in everything


def test_the_export_is_readable_by_a_spreadsheet(db, export_home, attachment):
    """CONTROL: a BOM (Excel then reads Arabic right), ISO moments, the
    attachment itself, the schema and the README."""
    z = _export(export_home)
    users = z.read("data/users.csv")
    assert users.startswith(b"\xef\xbb\xbf")
    created = list(csv.DictReader(io.StringIO(users.decode("utf-8-sig"))))[0]["created_at"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", created), created
    assert z.read(f"attachments/{attachment}") == b"X-RAY BYTES"
    assert b"CREATE TABLE users" in z.read("schema.sql")
    assert b"This is not a backup" in z.read("README.md")
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["attachments"]["files"] >= 1
    assert {"table": "users", "column": "password_hash"}.items() <= manifest["excluded"][0].items()


def _poll(client, url):
    for _ in range(300):
        data = client.get(url).get_json()
        if data["status"] != "running":
            return data
        time.sleep(0.1)
    raise AssertionError("the export job did not finish")


def test_the_export_runs_while_read_only(flask_app, db, export_home, set_license):
    """A7: an expired clinic can still take its own data -- and the same
    session is refused an ordinary write (the control)."""
    set_license(-30)
    c = flask_app.test_client()
    assert c.post("/login", data={"username": "admin", "password": PASSWORD}).status_code == 302
    assert c.post("/settings", data={"clinic_name": "x"}).status_code == 403
    started = c.post("/settings/data-export/start")
    assert started.status_code == 200, started.get_data(as_text=True)[:300]
    done = _poll(c, f"/settings/job-status?job_id={started.get_json()['job_id']}")
    assert done["ok"], done
    name = next(p.name for p in export_home.iterdir() if p.suffix == ".zip")
    download = c.get(f"/settings/data-export/{name}")
    assert download.status_code == 200 and download.data[:2] == b"PK"
    row = db.execute("SELECT actor, target FROM developer_audit WHERE action='export.generated' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["actor"] == "user:admin" and row["target"] == name


@pytest.mark.parametrize("name", ["notes.zip", "vcs-export-20260930-000000.zip.bak", "..%2F..%2F.env",
                                  "vcs-export-20260930-000001.zip"])
def test_a_download_is_only_an_export_this_install_made(client, export_home, name):
    """GUARD: files that are there, but are not an export by name, are
    refused -- as are paths and exports that do not exist."""
    export_home.mkdir(parents=True, exist_ok=True)
    for present in ("notes.zip", "vcs-export-20260930-000000.zip.bak", "vcs-export-20260930-000000.zip"):
        (export_home / present).write_bytes(b"PK not an export")
    assert client.get(f"/settings/data-export/{name}").status_code == 404
    assert client.get("/settings/data-export/vcs-export-20260930-000000.zip").status_code == 200   # control


def test_the_developer_can_export_too(developer, db, export_home):
    started = developer.post("/developer/data-export/start")
    done = _poll(developer, f"/developer/job-status?job_id={started.get_json()['job_id']}")
    assert done["ok"], done
    row = db.execute("SELECT actor, pass_id FROM developer_audit WHERE action='export.generated' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["actor"] == "dev:Test Developer" and row["pass_id"]
    page = developer.get("/developer/data-export").get_data(as_text=True)
    assert "vcs-export-" in page


# ---------------------------------------------------------------------------
# The vendor's message (§11.5)
# ---------------------------------------------------------------------------

def _post_message(developer, **fields):
    data = {"text": "", "level": "info", "expires_at": "", **fields}
    return developer.post("/developer/vendor-message", data=data, follow_redirects=True)


def test_the_message_is_shown_escaped_and_labelled(developer, client, db, settings_left_as_found):
    _post_message(developer, text="<b>Renewal</b> is due & soon", level="warning", enabled="1")
    page = client.get("/").get_data(as_text=True)
    assert "Message from your vendor" in page and "vendor-message warning" in page
    assert "&lt;b&gt;Renewal&lt;/b&gt; is due &amp; soon" in page and "<b>Renewal</b>" not in page
    row = db.execute("SELECT detail FROM developer_audit WHERE action='vendor_message.changed' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["detail"]["text"] == "<b>Renewal</b> is due & soon"


@pytest.mark.parametrize("fields, shown", [
    ({"enabled": "1"}, True),
    ({}, False),                                                             # turned off
    ({"enabled": "1", "expires_at": "__today__"}, True),                     # its last day
    ({"enabled": "1", "expires_at": "__yesterday__"}, False),                # past it
])
def test_the_message_shows_while_on_and_until_its_last_day(developer, client, settings_left_as_found, fields, shown):
    dates = {"__today__": clock.today().isoformat(),
             "__yesterday__": (clock.today() - timedelta(days=1)).isoformat()}
    fields = {k: dates.get(v, v) for k, v in fields.items()}
    _post_message(developer, text="Maintenance on Friday evening", **fields)
    assert ("Maintenance on Friday evening" in client.get("/").get_data(as_text=True)) is shown


def test_clearing_the_message_removes_it(developer, client, db, settings_left_as_found):
    _post_message(developer, text="Temporary note", enabled="1")
    developer.post("/developer/vendor-message", data={"clear": "1"})
    assert "Temporary note" not in client.get("/").get_data(as_text=True)
    assert _setting(db, "vendor_message_text") is None
    assert db.execute("SELECT 1 FROM developer_audit WHERE action='vendor_message.cleared'").fetchone()


@pytest.mark.parametrize("fields, words", [
    ({"level": "shouting", "text": "x"}, "Not a valid message level"),
    ({"text": "x" * 1001}, "longer than"),
    ({"enabled": "1"}, "Write the message"),
    ({"text": "x", "expires_at": "next week"}, "Not a valid date"),
])
def test_a_message_the_rules_refuse_is_not_saved(developer, db, settings_left_as_found, fields, words):
    before = _setting(db, "vendor_message_text")
    page = _post_message(developer, **fields).get_data(as_text=True)
    assert words in page and _setting(db, "vendor_message_text") == before
