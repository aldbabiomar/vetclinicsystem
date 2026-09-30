"""
No secret appears in any output (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md
§13; seam rule 15, §14.2).

One test: every secret the plan lists is set to a value of its own, the
actions that touch it are driven through the app -- a Developer Pass sign-in,
the license entered, the update token saved and refused by GitHub, the ping
URL saved, an administrator recovered, a data export, a support bundle --
and every output the plan names is searched for every value: the logs, both
audit tables, the sign-in log, the job results, the bundle, the export, the
pages and the session.
"""
import io
import json
import re
import zipfile

import pytest
import requests

from conftest import needs_db
from test_developer_tools import (_poll, export_home, logs, settings_left_as_found,  # noqa: F401
                                  spare_admin, token_home)

pytestmark = needs_db

TOKEN = "github_pat_TEST_ONLY_not_a_real_token_SECRETSCAN_5150"
PING = "https://hc-ping.example/SECRET-SCAN-PING-5150"
DB_PASSWORD = "Db-Password-Secret-Scan-2718"
SECRET_KEY = "secret-key-for-the-secret-scan-000000000000"


@pytest.fixture(autouse=True)
def _own_sign_in_limit(monkeypatch):
    from vcs.web import core
    monkeypatch.setattr(core, "_LOGIN_ATTEMPTS_BY_IP", {})


def _rows(db, table):
    return json.dumps([dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 200").fetchall()],
                      default=str)


def _zip_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def test_no_secret_reaches_any_output(flask_app, db, vendor, clinic_license, spare_admin, export_home, logs,
                                      token_home, settings_left_as_found, monkeypatch):
    from vcs.errorlog import ERROR_LOG_PATH
    from vcs.ops import updater
    monkeypatch.setenv("SECRET_KEY", SECRET_KEY)
    license_key = (clinic_license / "license.key").read_text().strip()
    dev_pass = vendor.dev_pass()
    outputs = {}

    # The actions, each through the app.
    dev = flask_app.test_client()
    outputs["developer sign-in"] = dev.post("/developer/login", data={"dev_pass": dev_pass},
                                            follow_redirects=True).get_data(as_text=True)
    outputs["license entered"] = dev.post("/developer/license", data={"license_key": license_key},
                                          follow_redirects=True).get_data(as_text=True)
    outputs["token saved"] = dev.post("/developer/updates/token", data={"token": TOKEN},
                                      follow_redirects=True).get_data(as_text=True)
    outputs["ping saved"] = dev.post("/developer/monitoring", data={"heartbeat_url": PING},
                                     follow_redirects=True).get_data(as_text=True)

    def refused(*args, **kwargs):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(updater, "check_latest_release", refused)
    monkeypatch.setattr(updater, "is_configured", lambda: True)
    monkeypatch.setattr(updater, "current_version", lambda: "1.0.0")
    outputs["update check refused"] = json.dumps(dev.get("/developer/updates/check").get_json())
    outputs["test connection refused"] = dev.post("/developer/updates/test",
                                                  follow_redirects=True).get_data(as_text=True)

    recovered = dev.post("/developer/support/recover", data={"user_id": spare_admin["id"]}).get_data(as_text=True)
    temporary = re.search(r'<div class="code-box u-mono">([^<]+)</div>', recovered).group(1)

    started = dev.post("/developer/data-export/start").get_json()
    outputs["export job result"] = json.dumps(_poll(dev, f"/developer/job-status?job_id={started['job_id']}"))
    outputs["data export"] = _zip_text(next(p for p in export_home.iterdir() if p.suffix == ".zip").read_bytes())
    # The configured database password, as the bundle's redactor finds it. Set
    # only now: the export's job opens a connection of its own with it.
    monkeypatch.setenv("DATABASE_URL", f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/vetclinicsystem")
    outputs["support bundle"] = _zip_text(dev.post("/developer/support/bundle").data)

    # The pages that show a secret's state, and what the browser keeps.
    for page in ("/developer/updates", "/developer/monitoring", "/developer/license", "/developer/audit",
                 "/developer/system"):
        outputs[page] = dev.get(page).get_data(as_text=True)
    with dev.session_transaction() as s:
        outputs["session"] = json.dumps(dict(s), default=str)

    # The stores.
    for table in ("developer_audit", "audit_log", "login_log"):
        outputs[table] = _rows(db, table)
    for name, path in (("errors.log", ERROR_LOG_PATH), ("updates.log", token_home / "logs" / "updates.log")):
        try:
            outputs[name] = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            outputs[name] = ""

    # CONTROL: each action left its trace where the scan reads -- a scan of
    # the wrong table or page would pass as well as a clean one.
    assert "…" + TOKEN[-4:] in outputs["/developer/updates"]
    for trace in ('"license.entered"', '"update.token_changed"', '"heartbeat.changed"', '"admin.recovered"',
                  '"export.generated"', '"support_bundle.generated"', '"developer.login"'):
        assert trace in outputs["developer_audit"], trace
    assert "(reset by vendor)" in outputs["audit_log"] and "rejected the access token" in outputs["update check refused"]
    assert "data/users.csv" in outputs["data export"] and spare_admin["username"] in outputs["data export"]

    secrets = {"license key": license_key, "Developer Pass": dev_pass, "update token": TOKEN, "ping URL": PING,
               "temporary password": temporary, "database password": DB_PASSWORD, "SECRET_KEY": SECRET_KEY}
    assert len(outputs) >= 17 and all(len(v) >= 6 for v in secrets.values()), sorted(outputs)
    # Where a secret legitimately is: the ping URL in `settings` (A6) and the
    # temporary password on the one page that shows it -- neither is scanned.
    leaks = [f"{what} in {where}" for where, text in outputs.items()
             for what, value in secrets.items() if value in text]
    assert not leaks, "\n  ".join(["secrets found in outputs:"] + leaks)


def test_control_the_scan_finds_a_secret_where_one_is(db, vendor):
    """CONTROL: the values the scan looks for are really there to be found
    when they are written -- the scan is not passing because it reads the
    wrong column or table."""
    marker = "SECRET-SCAN-CONTROL-8080"
    db.execute("INSERT INTO audit_log (username, timestamp, action, table_name, record_id, new_value) "
               "VALUES ('control', now(), 'update', 'control', '0', %s)", (marker,))
    db.commit()
    try:
        assert marker in _rows(db, "audit_log")
    finally:
        db.execute("DELETE FROM audit_log WHERE new_value=%s", (marker,))
        db.commit()
