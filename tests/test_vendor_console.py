"""
The Vendor Console (docs/plans/VENDOR_CONSOLE_PLAN.md): the vendor's own web
app for licensing clinics.

It signs licenses, so the guards are what matter: it answers on this computer
only, wants a CSRF token on every form (any page open in the vendor's
browser can post to 127.0.0.1), signs nothing while locked, locks when idle,
and never writes down a clinic's update token, ping URL or Developer Pass.
Then the work itself: a new clinic's setup code that setup reads, a clinic
already installed, renewals, passes, and the first-run key.
"""
import re
import sqlite3
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import source_files
from vcs.licensing import tokens

sys.path.insert(0, str(source_files.ROOT / "scripts" / "vendor"))
sys.path.insert(0, str(source_files.ROOT))
import console  # noqa: E402
import setup  # noqa: E402
import vcs_vendor  # noqa: E402

PASSPHRASE = "a long passphrase for the tests"
TOKEN = "ghp_CONSOLE_TEST_not_a_real_token_91"
PING = "https://hc-ping.example/CONSOLE-SECRET-PING-42"


@pytest.fixture
def home(tmp_path):
    """A console with a signing key of its own, trusted for this process."""
    kid, public = vcs_vendor.keygen(tmp_path / "signing.pem", PASSPHRASE)
    tokens.trust_for_tests(kid, public)
    return SimpleNamespace(app=console.create_console(tmp_path), dir=tmp_path)


def _csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _unlocked(home):
    c = home.app.test_client()
    resp = c.post("/unlock", data={"csrf_token": _csrf(c, "/unlock"), "passphrase": PASSPHRASE})
    assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
    return c


def _new_clinic(c, token_from="/clinics/new", **fields):
    data = {"csrf_token": _csrf(c, token_from), "name": "Al-Rahma Vet Clinic", "money_setting": "JO",
            "palette": "sage", "length": "days", "days": "365", "warn_days": "14", "grace_days": "14",
            "time_zone": "Asia/Baghdad", "github_token": TOKEN, "heartbeat_url": PING, **fields}
    return c.post("/clinics/new", data=data)


def _shown(resp):
    return re.search(r'<pre id="code">([^<]+)</pre>', resp.get_data(as_text=True)).group(1)


def _rows(home, sql):
    con = sqlite3.connect(home.dir / "console.sqlite3")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# The guards
# ---------------------------------------------------------------------------

def test_it_answers_this_computer_only(home):
    """GUARD. A web page can reach 127.0.0.1 through a name it controls (DNS
    rebinding); the browser then sends that name as the Host."""
    c = home.app.test_client()
    assert c.get("/unlock", headers={"Host": "attacker.example"}).status_code == 400
    assert c.get("/unlock", headers={"Host": "attacker.example:5099"}).status_code == 400
    for host in ("127.0.0.1:5099", "localhost:5099", "localhost"):          # control
        assert c.get("/unlock", headers={"Host": host}).status_code == 200, host


def test_every_form_needs_its_csrf_token(home):
    """GUARD. Without it, any page open in the vendor's browser could post a
    new clinic -- and walk off with its signed license."""
    c = _unlocked(home)
    before = _rows(home, "SELECT count(*) FROM clinics")[0][0]
    data = {"name": "Forged", "money_setting": "JO", "length": "days", "days": "365"}
    assert c.post("/clinics/new", data=data).status_code == 400
    assert c.post("/lock").status_code == 400
    assert _rows(home, "SELECT count(*) FROM clinics")[0][0] == before
    assert _new_clinic(c).status_code == 200                                   # control


def test_nothing_is_signed_while_locked(home):
    """GUARD. Signing needs the key unlocked with its passphrase."""
    c = home.app.test_client()
    resp = _new_clinic(c, token_from="/unlock")            # a valid token: refused for being locked, not for that
    assert resp.status_code == 302 and "/unlock" in resp.headers["Location"]
    assert _rows(home, "SELECT count(*) FROM clinics")[0][0] == 0
    c = _unlocked(home)
    assert _new_clinic(c).status_code == 200                                   # control


def test_a_wrong_passphrase_does_not_unlock(home):
    c = home.app.test_client()
    resp = c.post("/unlock", data={"csrf_token": _csrf(c, "/unlock"), "passphrase": "not the passphrase"},
                  follow_redirects=True)
    assert "That passphrase does not open the signing key" in resp.get_data(as_text=True)
    assert home.app.key_state["key"] is None


def test_the_key_locks_when_idle_and_on_lock(home):
    c = _unlocked(home)
    home.app.config["IDLE_SECONDS"] = 0
    resp = c.get("/")
    assert resp.status_code == 302 and "/unlock" in resp.headers["Location"]
    assert home.app.key_state["key"] is None
    home.app.config["IDLE_SECONDS"] = 1800
    c = _unlocked(home)
    c.post("/lock", data={"csrf_token": _csrf(c, "/")})
    assert home.app.key_state["key"] is None


def test_the_console_never_writes_down_a_secret(home):
    """GUARD (V-3). The update token and the ping URL live only in the setup
    code; a Developer Pass only on its page. The ledger is read as bytes."""
    c = _unlocked(home)
    code = _shown(_new_clinic(c))
    clinic_id = _rows(home, "SELECT id FROM clinics")[0][0]
    resp = c.post(f"/clinics/{clinic_id}/pass",
                  data={"csrf_token": _csrf(c, f"/clinics/{clinic_id}"), "developer": "Omar", "hours": "8"})
    dev_pass = _shown(resp)
    ledger = (home.dir / "console.sqlite3").read_bytes()
    for secret in (TOKEN, PING, dev_pass, code):
        assert secret.encode() not in ledger, secret[:30]
    license_key = setup.parse_setup_code(code)["license"]
    assert license_key.encode() in ledger          # control: the scan reads what the ledger does keep
    assert resp.headers["Cache-Control"] == "no-store"


def test_it_listens_on_the_loopback_address_only(home, monkeypatch):
    import waitress
    seen = {}
    monkeypatch.setattr(waitress, "serve", lambda app, **kw: seen.update(kw))
    console.serve(home.app, port=5099, open_browser=False)
    assert seen["host"] == "127.0.0.1"


def test_a_stale_form_is_refused_with_a_page_that_says_so(home):
    """A tab left open across a restart posts a token the new console never
    issued: refused (400), in words, not a bare "Bad Request"."""
    c = home.app.test_client()
    resp = c.post("/unlock", data={"passphrase": PASSPHRASE})
    assert resp.status_code == 400 and "nothing changed" in resp.get_data(as_text=True)
    assert home.app.key_state["key"] is None


def test_a_port_in_use_is_a_plain_message(home, monkeypatch):
    import errno
    import waitress

    def taken(app, **kw):
        raise OSError(errno.EADDRINUSE, "Address already in use")
    monkeypatch.setattr(waitress, "serve", taken)
    with pytest.raises(SystemExit) as stopped:
        console.serve(home.app, port=5099, open_browser=False)
    assert "Port 5099 is already in use" in str(stopped.value) and "--port 5100" in str(stopped.value)


def test_a_hidden_field_is_really_hidden():
    """The script shows either Days or Last day by setting `hidden`. A field's
    own `display: grid` beat the browser's rule for [hidden], so both showed."""
    static = source_files.ROOT / "scripts" / "vendor" / "console_static"
    assert ".hidden = " in (static / "console.js").read_text()
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important", (static / "console.css").read_text())


def test_its_records_live_outside_the_code():
    with pytest.raises(SystemExit):
        console.create_console(source_files.ROOT / "console-data")
    assert not (source_files.ROOT / "console-data").exists()


# ---------------------------------------------------------------------------
# The work
# ---------------------------------------------------------------------------

def test_a_new_clinic_gets_one_setup_code_that_setup_reads(home):
    c = _unlocked(home)
    resp = _new_clinic(c)
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
    code = setup.parse_setup_code(_shown(resp))
    stored = _rows(home, "SELECT install_id, money_setting, palette, made_with FROM clinics")[0]
    assert (code["install_id"], code["money_setting"], code["palette"]) == stored[:3] == (stored[0], "JO", "sage")
    assert stored[3] == "setup code"
    assert code["github_token"] == TOKEN and code["heartbeat_url"] == PING
    payload = tokens.verify(code["license"], tokens.LICENSE, code["install_id"], datetime.now(timezone.utc))
    assert payload["clinic_name"] == code["clinic_name"] == "Al-Rahma Vet Clinic"


def test_a_setup_code_without_secrets_says_it_is_safe_to_send(home):
    c = _unlocked(home)
    resp = _new_clinic(c, github_token="", heartbeat_url="")
    code = setup.parse_setup_code(_shown(resp))
    assert "github_token" not in code and "heartbeat_url" not in code
    assert "No secrets in this code" in resp.get_data(as_text=True)


@pytest.mark.parametrize("fields, words", [
    ({"name": ""}, "Give the clinic&#39;s name"),
    ({"money_setting": "XX"}, "Choose IQ or JO"),
    ({"palette": "neon"}, "Choose a palette"),
    ({"heartbeat_url": "http://plain.example"}, "must start with https://"),
    ({"days": "0"}, "at least 1 day"),
    ({"length": "date", "expires": "2020-01-01"}, "has already ended"),
    ({"warn_days": "-1"}, "0 days or more"),
])
def test_a_new_clinic_the_rules_refuse_is_not_made(home, fields, words):
    c = _unlocked(home)
    resp = _new_clinic(c, **fields)
    assert resp.status_code == 400 and words in resp.get_data(as_text=True)
    assert _rows(home, "SELECT count(*) FROM clinics")[0][0] == 0


def test_a_clinic_already_installed_is_licensed_by_its_own_id(home):
    c = _unlocked(home)
    install_id = "3f2a9c1e-7b4d-4e8a-9c21-5d6f0a8b7e13"
    data = {"csrf_token": _csrf(c, "/clinics/installed"), "name": "Nour Clinic", "install_id": "not-an-id",
            "length": "date", "expires": "2099-09-30", "warn_days": "14", "grace_days": "14",
            "time_zone": "Asia/Baghdad"}
    assert c.post("/clinics/installed", data=data).status_code == 400
    resp = c.post("/clinics/installed", data={**data, "install_id": install_id.upper()})
    key = _shown(resp)
    payload = tokens.verify(key, tokens.LICENSE, install_id, datetime.now(timezone.utc))
    assert datetime.fromisoformat(payload["expires_at"]).astimezone(ZoneInfo("Asia/Baghdad")).date().isoformat() \
        == "2099-09-30"
    assert c.post("/clinics/installed", data={**data, "install_id": install_id}).status_code == 400   # already listed


def test_a_renewal_runs_a_year_past_the_current_end(home):
    c = _unlocked(home)
    code = setup.parse_setup_code(_shown(_new_clinic(c, length="date", expires="2099-03-15")))
    clinic_id = _rows(home, "SELECT id FROM clinics")[0][0]
    page = c.get(f"/clinics/{clinic_id}").get_data(as_text=True)
    assert 'value="2100-03-15"' in page
    resp = c.post(f"/clinics/{clinic_id}/license", data={"csrf_token": _csrf(c, f"/clinics/{clinic_id}"),
                                                        "expires": "2100-03-15", "warn_days": "7", "grace_days": "30"})
    payload = tokens.verify(_shown(resp), tokens.LICENSE, code["install_id"], datetime.now(timezone.utc))
    assert (payload["warn_days"], payload["grace_days"]) == (7, 30)
    assert len(_rows(home, "SELECT id FROM licenses")) == 2


def test_a_developer_pass_opens_that_clinic_for_its_hours(home):
    c = _unlocked(home)
    code = setup.parse_setup_code(_shown(_new_clinic(c)))
    clinic_id = _rows(home, "SELECT id FROM clinics")[0][0]
    token = _csrf(c, f"/clinics/{clinic_id}")
    refused = c.post(f"/clinics/{clinic_id}/pass", data={"csrf_token": token, "developer": "Omar", "hours": "13"},
                     follow_redirects=True)
    assert "between 1 and 12 hours" in refused.get_data(as_text=True)
    resp = c.post(f"/clinics/{clinic_id}/pass", data={"csrf_token": token, "developer": "Omar", "hours": "4"})
    payload = tokens.verify(_shown(resp), tokens.DEV_PASS, code["install_id"], datetime.now(timezone.utc))
    assert payload["developer"] == "Omar"
    assert _rows(home, "SELECT developer FROM passes")[0][0] == "Omar"


def test_first_run_makes_the_key_and_shows_its_line_for_the_code(tmp_path):
    app = console.create_console(tmp_path)
    c = app.test_client()
    assert c.get("/").headers["Location"].endswith("/start")
    token = _csrf(c, "/start")
    differ = c.post("/start", data={"csrf_token": token, "action": "new", "path": str(tmp_path / "signing.pem"),
                                    "passphrase": PASSPHRASE, "again": PASSPHRASE + "x"}, follow_redirects=True)
    assert "The two passphrases differ" in differ.get_data(as_text=True)
    resp = c.post("/start", data={"csrf_token": token, "action": "new", "path": str(tmp_path / "signing.pem"),
                                  "passphrase": PASSPHRASE, "again": PASSPHRASE})
    line = re.search(r'"(k[0-9a-f]{12})": bytes\.fromhex\("([0-9a-f]{64})"\)', resp.get_data(as_text=True))
    assert line, "the page does not show the line for trusted_keys.py"
    key = vcs_vendor.load_key(tmp_path / "signing.pem", PASSPHRASE)
    assert vcs_vendor.kid_for(vcs_vendor.public_bytes(key)) == line.group(1)
    assert "ENCRYPTED" in (tmp_path / "signing.pem").read_text()


def test_a_key_not_yet_in_the_code_is_flagged(home):
    """Until a release trusts it, clinics refuse its licenses; the console says
    so on every page. (Here the key is trusted in-process only, which is not
    TRUSTED_KEYS.)"""
    c = _unlocked(home)
    assert "This key is not in the app's code yet" in c.get("/").get_data(as_text=True)
