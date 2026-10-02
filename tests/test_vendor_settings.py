"""
What the vendor sets, and the clinic cannot
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §9-§10, owner decisions L-1-L-3).

The money setting, the palette and the monitoring ping are gated `developer`
in the settings registry: POST /settings refuses them from anyone -- the
system Admin, who holds every permission, included -- and the Developer
area saves them through the rules they always had. The GitHub token lives in
a file in the data folder, is read at every call, and never appears in a
page, a message or an audit row.
"""
import os
import stat

import pytest

from conftest import forget_stored_money_setting, needs_db
from vcs import money

pytestmark = needs_db


@pytest.fixture(autouse=True)
def _own_sign_in_limit(monkeypatch):
    from vcs.web import core
    monkeypatch.setattr(core, "_LOGIN_ATTEMPTS_BY_IP", {})


def _setting(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else None


@pytest.fixture
def left_as_found(db):
    keys = ("theme_palette", "heartbeat_url", money.SETTING_KEY, "vendor_message_text", "vendor_message_level",
            "vendor_message_expires_at", "vendor_message_enabled")
    saved = {k: _setting(db, k) for k in keys}
    yield
    for key, value in saved.items():
        if value is None:
            db.execute("DELETE FROM settings WHERE key=%s", (key,))
        else:
            db.execute("INSERT INTO settings (key, value) VALUES (%s,%s) "
                       "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()
    forget_stored_money_setting()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

# A value each vendor setting's own rules would accept, so a refusal is the
# gate's and not the value's.
ACCEPTABLE = {"theme_palette": "orchid", "heartbeat_url": "https://hc-ping.example/gate-test",
              money.SETTING_KEY: "IQ", "vendor_message_text": "Gate test", "vendor_message_level": "warning",
              "vendor_message_expires_at": "2099-01-01", "vendor_message_enabled": "1"}


def _developer_gated_keys():
    from vcs.web import vendor_settings
    from vcs.web.blueprints.settings import SETTING_FIELD_PERMISSION
    return [k for k, gate in SETTING_FIELD_PERMISSION.items() if gate == vendor_settings.DEVELOPER]


def test_the_system_admin_cannot_set_any_vendor_setting(client, db, left_as_found):
    """GUARD (§9.1; seam rule 14, licensing plan §14.2). Every key the
    registry gates `developer`, found there rather than listed here, is
    refused from the clinic's system Admin, who holds every permission.
    Removing a field from the template is not enough -- that is audit S1."""
    keys = _developer_gated_keys()
    assert len(keys) >= 7, f"only {keys} are gated -- the registry has lost the vendor's settings"
    for key in keys:
        before = _setting(db, key)
        page = client.post("/settings", data={key: ACCEPTABLE[key]}, follow_redirects=True).get_data(as_text=True)
        assert _setting(db, key) == before, key
        assert "are set by your vendor" in page, key


def test_control_the_developer_sets_the_palette(developer, db, left_as_found):
    developer.post("/developer/configuration", data={"theme_palette": "orchid"})
    assert _setting(db, "theme_palette") == "orchid"
    row = db.execute("SELECT detail FROM developer_audit WHERE action='config.palette' "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["detail"]["to"] == "orchid"


def test_the_developer_can_choose_the_money_setting_until_money_is_recorded(developer, db, left_as_found,
                                                                            monkeypatch):
    other = "IQ" if money.current().code == "JO" else "JO"
    monkeypatch.setattr(money, "is_locked", lambda db: False)
    developer.post("/developer/configuration", data={"money_setting": other})
    assert _setting(db, money.SETTING_KEY) == other


def test_the_money_setting_stays_locked_for_the_developer_too(developer, db, left_as_found, monkeypatch):
    """The lock is the rule, whoever asks (L-3: only its placement moved)."""
    current = money.current().code
    monkeypatch.setattr(money, "is_locked", lambda db: True)
    page = developer.post("/developer/configuration", data={"money_setting": "IQ" if current == "JO" else "JO"},
                          follow_redirects=True).get_data(as_text=True)
    assert _setting(db, money.SETTING_KEY) == current
    assert "be changed once money has been recorded" in page          # can&#39;t, rendered


def test_the_ping_url_is_https_and_never_written_down(developer, db, left_as_found):
    """The URL is a credential: https or nothing, and the change logs record
    that it changed, never what it is."""
    marker = "https://hc-ping.example/SECRET-MARKER-0002"
    # Only this test's rows: the vendor's audit is append-only, and a row a
    # guard-proving run wrote with the bug in stays in it.
    log_from = db.execute("SELECT COALESCE(MAX(id), 0) AS n FROM audit_log").fetchone()["n"]
    audit_from = db.execute("SELECT COALESCE(MAX(id), 0) AS n FROM developer_audit").fetchone()["n"]
    developer.post("/developer/monitoring", data={"heartbeat_url": "http://plain.example/x"})
    assert _setting(db, "heartbeat_url") != "http://plain.example/x"
    developer.post("/developer/monitoring", data={"heartbeat_url": marker})
    assert _setting(db, "heartbeat_url") == marker
    logged_rows = db.execute("SELECT old_value, new_value FROM audit_log "
                             "WHERE field='heartbeat_url' AND id > %s", (log_from,)).fetchall()
    audited_rows = db.execute("SELECT detail FROM developer_audit "
                              "WHERE action='heartbeat.changed' AND id > %s", (audit_from,)).fetchall()
    assert logged_rows and audited_rows            # the change was recorded, and looked at
    logged = " ".join(str(v) for r in logged_rows for v in r.values())
    audited = " ".join(str(r["detail"]) for r in audited_rows)
    assert marker not in logged and marker not in audited and "hc-ping.example" not in logged
    assert "SECRET-MARKER-0002" not in developer.get("/developer/monitoring").get_data(as_text=True)


def test_settings_says_who_sets_the_money_setting(client):
    """§9.3: shown, not offered."""
    page = client.get("/settings").get_data(as_text=True)
    assert 'name="money_setting"' not in page and 'name="theme_palette"' not in page
    assert 'name="heartbeat_url"' not in page


# ---------------------------------------------------------------------------
# The GitHub token (§10)
# ---------------------------------------------------------------------------

@pytest.fixture
def token_home(tmp_path, monkeypatch):
    from vcs.ops import updater
    monkeypatch.setattr(updater, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_the_token_is_read_at_every_call(token_home):
    """GUARD. It was read once, at import: a replaced token did nothing until
    a restart."""
    from vcs.ops import updater
    updater.save_token("ghp_first_token_1111")
    assert updater._api_headers()["Authorization"] == "Bearer ghp_first_token_1111"
    updater.save_token("ghp_second_token_2222")
    assert updater._api_headers()["Authorization"] == "Bearer ghp_second_token_2222"
    updater.remove_token()
    assert "Authorization" not in updater._api_headers()


def test_the_token_file_is_readable_only_by_its_owner(token_home):
    from vcs.ops import updater
    updater.save_token("ghp_private_3333")
    mode = stat.S_IMODE(os.stat(token_home / updater.TOKEN_FILE).st_mode)
    assert mode == 0o600, oct(mode)
    assert updater.masked_token() == "…3333"


@pytest.mark.parametrize("status, words", [(401, "rejected the access token"),
                                           (404, "not found or no access")])
def test_a_refusal_says_why_and_never_shows_the_token(token_home, status, words):
    import requests
    from vcs.ops import updater
    updater.save_token("ghp_never_shown_4444")
    response = requests.Response()
    response.status_code = status
    message = updater.describe_check_failure(requests.HTTPError(response=response))
    assert words in message and "ghp_never_shown_4444" not in message


def test_without_a_token_updates_say_so(developer, token_home, monkeypatch):
    from vcs.ops import updater
    monkeypatch.setattr(updater, "is_configured", lambda: True)
    monkeypatch.setattr(updater, "current_version", lambda: "1.0.0")
    data = developer.get("/developer/updates/check").get_json()
    assert "No access token is set for updates" in data["error"]


def test_the_developer_sets_and_removes_the_token_and_only_that_is_recorded(developer, db, token_home):
    from vcs.ops import updater
    developer.post("/developer/updates/token", data={"token": "ghp_audit_5555"})
    assert updater.read_token() == "ghp_audit_5555"
    assert "ghp_audit_5555" not in developer.get("/developer/updates").get_data(as_text=True)
    developer.post("/developer/updates/token", data={"remove": "1"})
    assert updater.read_token() is None
    rows = db.execute("SELECT detail FROM developer_audit WHERE action='update.token_changed' "
                      "ORDER BY id DESC LIMIT 2").fetchall()
    assert [r["detail"]["token"] for r in rows] == ["not set", "set"]
    assert "ghp_audit_5555" not in str([r["detail"] for r in rows])


def test_test_connection_reports_what_github_said(developer, token_home, monkeypatch):
    import requests
    from vcs.ops import updater
    response = requests.Response()
    response.status_code = 404

    def refuse():
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(updater, "check_latest_release", refuse)
    page = developer.post("/developer/updates/test", follow_redirects=True).get_data(as_text=True)
    assert "not found or no access" in page
    monkeypatch.setattr(updater, "check_latest_release", lambda: {"tag_name": "v1.2.3"})
    assert "Connected: the latest release is v1.2.3" in developer.post(
        "/developer/updates/test", follow_redirects=True).get_data(as_text=True)


# ---------------------------------------------------------------------------
# setup --money-setting (§9.3)
# ---------------------------------------------------------------------------

def test_setup_can_choose_the_money_setting(db, left_as_found, monkeypatch):
    import setup
    db.execute("DELETE FROM settings WHERE key=%s", (money.SETTING_KEY,))
    db.commit()
    monkeypatch.setattr("sys.argv", ["setup.py", "--money-setting", "jo"])
    assert setup.ensure_money_setting() == "JO"
    assert _setting(db, money.SETTING_KEY) == "JO"


def test_setup_will_not_move_a_locked_money_setting(db, left_as_found, monkeypatch):
    import setup
    current = _setting(db, money.SETTING_KEY)
    monkeypatch.setattr(money, "is_locked", lambda con: True)
    monkeypatch.setattr("sys.argv", ["setup.py", "--money-setting", "IQ" if current == "JO" else "JO"])
    with pytest.raises(SystemExit):
        setup.ensure_money_setting()
    assert _setting(db, money.SETTING_KEY) == current
