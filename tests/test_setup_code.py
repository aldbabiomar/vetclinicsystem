"""
A new clinic's setup code (docs/plans/VENDOR_CONSOLE_PLAN.md V-2, V-3): made
by the Vendor Console, read by setup.py. One line carries the license --
which names the installation and the clinic -- the money setting, the
palette, and the update token and ping URL when the vendor includes them.
"""
import os
import stat
import sys

import pytest

import source_files
from conftest import needs_db

sys.path.insert(0, str(source_files.ROOT))
import setup  # noqa: E402

TOKEN = "ghp_SETUPCODE_TEST_not_a_real_token_17"
PING = "https://hc-ping.example/SETUP-CODE-PING-88"


@pytest.fixture
def code(vendor):
    license_key = vendor.license(install="5b8c1f0e-2d4a-4c6b-9e1f-7a3d5c9b2e40", clinic_name="Nour Clinic")
    return setup.make_setup_code(license_key, "IQ", "orchid", github_token=TOKEN, heartbeat_url=PING)


def test_a_setup_code_reads_back_what_went_in(code):
    got = setup.parse_setup_code(code)
    assert got["install_id"] == "5b8c1f0e-2d4a-4c6b-9e1f-7a3d5c9b2e40" and got["clinic_name"] == "Nour Clinic"
    assert (got["money_setting"], got["palette"], got["github_token"], got["heartbeat_url"]) == \
        ("IQ", "orchid", TOKEN, PING)


def test_a_setup_code_survives_a_chat_app_wrapping_it(code):
    wrapped = "\n".join(code[i:i + 60] for i in range(0, len(code), 60)) + "  \n"
    assert setup.parse_setup_code(wrapped)["install_id"] == "5b8c1f0e-2d4a-4c6b-9e1f-7a3d5c9b2e40"


@pytest.mark.parametrize("change, words", [
    (lambda c: c[:40] + ("A" if c[40] != "A" else "B") + c[41:], "changed or damaged"),
    (lambda c: c[:len(c) // 2], "not a VetClinicSystem setup code"),
    (lambda c: "VCS1." + c.split(".", 1)[1], "not a VetClinicSystem setup code"),
    (lambda c: setup.make_setup_code("not a license", "IQ"), "missing information"),
])
def test_a_damaged_setup_code_is_refused_before_anything_is_written(code, change, words):
    """GUARD. The checksum catches a changed character; nothing half-applies."""
    with pytest.raises(setup.BadSetupCode) as refused:
        setup.parse_setup_code(change(code))
    assert words in str(refused.value)


def test_setup_puts_the_codes_installation_id_in_a_new_env(code, tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.setattr(setup, "docker_claimed_ports", lambda: set())
    monkeypatch.setattr(setup, "port_in_use", lambda port: False)
    setup.ensure_env_file("docker", install_id=setup.parse_setup_code(code)["install_id"])
    assert "VETCLINICSYSTEM_INSTALL_ID=5b8c1f0e-2d4a-4c6b-9e1f-7a3d5c9b2e40\n" in (tmp_path / ".env").read_text()


def test_a_setup_code_for_another_installation_is_refused(code, capsys):
    """GUARD. An install set up before keeps its own ID; the code's license
    would never verify there, so setup stops and says why."""
    parsed = setup.parse_setup_code(code)
    with pytest.raises(SystemExit):
        setup.ensure_setup_code_matches(parsed, "00000000-0000-4000-8000-000000000000")
    assert "is for installation 5b8c1f0e" in capsys.readouterr().out
    setup.ensure_setup_code_matches(parsed, parsed["install_id"])                  # control


def test_setup_takes_the_code_from_the_command_line(code, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["setup.py", "--setup-code", code])
    assert setup.read_setup_code()["clinic_name"] == "Nour Clinic"
    monkeypatch.setattr(sys, "argv", ["setup.py", "--setup-code", code[:-3] + "zzz"])
    with pytest.raises(SystemExit):
        setup.read_setup_code()


def test_the_token_moves_into_the_data_folder_with_the_license(tmp_path):
    base, data = tmp_path / "checkout", tmp_path / "data"
    base.mkdir()
    data.mkdir()
    (base / "license").mkdir()
    (base / "license" / "license.key").write_text("VCS1.x.y\n")
    token = base / "github_token"
    token.write_text(TOKEN + "\n")
    token.chmod(0o600)
    setup.move_secrets_into(str(data), base_dir=str(base))
    assert (data / "license" / "license.key").exists() and not (base / "license").exists()
    assert (data / "github_token").read_text().strip() == TOKEN and not token.exists()
    assert stat.S_IMODE(os.stat(data / "github_token").st_mode) == 0o600


@needs_db
def test_setup_applies_what_only_the_vendor_sets(code, db, tmp_path, monkeypatch):
    """The palette, the clinic's name (when none is set), the ping URL and the
    token -- each reported as saved, a secret never printed."""
    from vcs.ops import updater
    keys = ("theme_palette", "clinic_name", "heartbeat_url")
    saved = {k: db.execute("SELECT value FROM settings WHERE key=%s", (k,)).fetchone() for k in keys}
    monkeypatch.setattr(updater, "DATA_DIR", str(tmp_path))
    db.execute("DELETE FROM settings WHERE key='clinic_name'")
    db.commit()
    try:
        setup.apply_setup_code(setup.parse_setup_code(code))
        stored = {r["key"]: r["value"] for r in db.execute(
            "SELECT key, value FROM settings WHERE key = ANY(%s)", (list(keys),)).fetchall()}
        assert stored == {"theme_palette": "orchid", "clinic_name": "Nour Clinic", "heartbeat_url": PING}
        assert updater.read_token() == TOKEN
        # A clinic that has named itself keeps its name.
        db.execute("UPDATE settings SET value='Our Own Name' WHERE key='clinic_name'")
        db.commit()
        setup.apply_setup_code(setup.parse_setup_code(code))
        assert db.execute("SELECT value FROM settings WHERE key='clinic_name'").fetchone()["value"] == "Our Own Name"
    finally:
        for key, row in saved.items():
            db.execute("DELETE FROM settings WHERE key=%s", (key,))
            if row is not None:
                db.execute("INSERT INTO settings (key, value) VALUES (%s,%s)", (key, row["value"]))
        db.commit()


@needs_db
def test_a_secret_from_the_code_is_never_printed(code, db, tmp_path, monkeypatch, capsys):
    from vcs.ops import updater
    monkeypatch.setattr(updater, "DATA_DIR", str(tmp_path))
    saved = db.execute("SELECT value FROM settings WHERE key='heartbeat_url'").fetchone()
    try:
        setup.apply_setup_code(setup.parse_setup_code(code))
        out = capsys.readouterr().out
        assert TOKEN not in out and PING not in out and "Update access token saved" in out
    finally:
        db.execute("DELETE FROM settings WHERE key='heartbeat_url'")
        if saved:
            db.execute("INSERT INTO settings (key, value) VALUES ('heartbeat_url', %s)", (saved["value"],))
        db.commit()
