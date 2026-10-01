"""
A new clinic's setup code (docs/plans/VENDOR_CONSOLE_PLAN.md V-2, V-3): made
by the Vendor Console, read by setup.py. One line carries the license --
which names the installation and the clinic -- the money setting, the
palette, and the update token and ping URL when the vendor includes them.
"""
import os
import select
import stat
import sys
import time

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


# --- pasted at setup's prompt, on a real terminal -----------------------------

at_a_terminal = pytest.mark.skipif(sys.platform == "win32", reason="the test types through a pty, which Windows lacks")
PROMPT = b"Paste the setup code"
PASTER = ("import sys; sys.path.insert(0, {root!r}); import setup\n"
          "text = setup.paste_setup_code()\n"
          "print('ARRIVED', len(''.join(text.split())), flush=True)\n")


def _pasted_at_the_prompt(typed, wait=20):
    """Run setup's prompt on a terminal of its own, type `typed` at it, and
    return how many characters of a setup code it got -- None if it never
    answered, which is what a terminal that stopped taking input looks like.

    The typing and the reading take turns: the terminal echoes every key, and
    a writer that does not read its echo fills the pipe and waits for ever on
    a reader that is waiting on it."""
    import pty
    import subprocess
    fd, terminal = pty.openpty()
    # Popen, not pty.fork(): forking a test process that has threads can deadlock the child.
    child = subprocess.Popen([sys.executable, "-c", PASTER.format(root=str(source_files.ROOT))],
                             stdin=terminal, stdout=terminal, stderr=terminal, start_new_session=True)
    os.close(terminal)
    os.set_blocking(fd, False)
    out, pending = b"", b""

    def run_until(marker, seconds):
        nonlocal out, pending
        end = time.monotonic() + seconds
        while marker not in out and time.monotonic() < end:
            readable, writable, _ = select.select([fd], [fd] if pending else [], [], 0.2)
            if readable:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    chunk = None
                except OSError:
                    break
                if chunk == b"":
                    break
                out += chunk or b""
            if writable and pending:
                try:
                    pending = pending[os.write(fd, pending[:128]):]
                except BlockingIOError:
                    pass
        return marker in out
    try:
        assert run_until(PROMPT, 20), f"setup never showed its prompt: {out[-300:]!r}"
        pending = typed.encode()
        if not run_until(b"ARRIVED ", wait):
            return None
        run_until(b"ARRIVED never-a-match", 0.5)          # the rest of that line
        return int(out.rsplit(b"ARRIVED ", 1)[1].split()[0])
    finally:
        child.kill()
        child.wait()
        os.close(fd)


@at_a_terminal
def test_a_setup_code_longer_than_a_terminal_line_can_be_pasted(vendor):
    """GUARD. A terminal's own line editing stops at 1,024 characters on macOS
    and 4,096 on Linux, and drops the rest with the Return: a code carrying an
    update token and a ping URL passed the first, and setup never got it."""
    license_key = vendor.license(install="5b8c1f0e-2d4a-4c6b-9e1f-7a3d5c9b2e40", clinic_name="Nour Clinic")
    long_code = setup.make_setup_code(license_key, "IQ", "orchid", github_token="not_a_real_token_" + "x" * 3200,
                                      heartbeat_url=PING)
    assert len(long_code) > 4096, "the code must be longer than either terminal's line"
    assert _pasted_at_the_prompt(long_code + "\n", wait=8) == len(long_code)


@at_a_terminal
def test_a_setup_code_pasted_at_the_prompt_arrives(code):
    """CONTROL for the two beside it: an ordinary code, on one line."""
    assert len(code) < 1024
    assert _pasted_at_the_prompt(code + "\n") == len(code)


@at_a_terminal
def test_a_setup_code_pasted_in_pieces_is_put_back_together(code):
    """GUARD. A mail or chat app breaks the long line; a terminal hands the
    pieces over one at a time, and the first alone is not a setup code."""
    pieces = [code[i:i + 60] for i in range(0, len(code), 60)]
    assert len(pieces) > 5
    assert _pasted_at_the_prompt("\n".join(pieces) + "\n") == len(code)


@at_a_terminal
def test_a_paste_that_is_not_a_setup_code_stops_at_an_empty_line():
    """CONTROL: the prompt does not wait for ever for a code that never
    becomes whole; Return ends it, and setup then refuses what it was given."""
    assert _pasted_at_the_prompt("not a setup code\n\n") == len("notasetupcode")
