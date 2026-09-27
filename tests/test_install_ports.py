"""
A fresh install never takes a port something else holds (plan §12, item 5).

setup.py gave every install the app port 5050 and the database port 5432.
On a computer that already runs another install -- this one runs the
predecessor IQ app, on exactly those two -- the second `docker compose up`
failed with "port is already allocated". Now a new install takes the next
free port, counting the ports other containers publish even while they are
stopped, and writes both into .env; the app, both launchers and the Desktop
shortcut read the app's port from there. Only a new .env is given ports: an
install that already has one keeps them.

Pure tier: nothing here binds a real port or starts Docker; the machine's
state is passed in.
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import setup  # noqa: E402
from vcs.ops import desktop_shortcut  # noqa: E402

EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
INSPECT = """/vetclinicsystemiq_postgres {"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"5432"}]}
/vetclinicsystemjo_postgres {"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"5433"}]}
/stopped_thing {"80/tcp":[{"HostIp":"","HostPort":"5050"}]}
/vetclinicsystem_postgres {"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"5434"}]}
/no_ports null
"""


def _env_line(text, key):
    return next(l for l in text.splitlines() if l.startswith(f"{key}="))


# ---------------------------------------------------------------------------
# Which ports are taken
# ---------------------------------------------------------------------------

def test_every_other_containers_ports_count_as_taken_running_or_not():
    """A stopped database takes its port back when Docker restarts it; this
    install's own container is not "another" one."""
    assert setup.docker_claimed_ports(INSPECT) == {5432, 5433, 5050}


def test_the_first_free_port_skips_claimed_and_listening_ones():
    assert setup.first_free_port(5432, {5432, 5433}, in_use=lambda p: p == 5434) == 5435


def test_control_the_preferred_port_is_kept_when_it_is_free():
    assert setup.first_free_port(5050, set(), in_use=lambda p: False) == 5050


def test_ports_are_chosen_around_what_the_machine_holds(monkeypatch):
    """GUARD. This computer's case: the predecessors' databases publish 5432
    and 5433, and an app listens on 5050."""
    monkeypatch.delenv("POSTGRES_HOST_PORT", raising=False)
    monkeypatch.delenv("VETCLINICSYSTEM_PORT", raising=False)
    monkeypatch.setattr(setup, "docker_claimed_ports", lambda: {5432, 5433})
    monkeypatch.setattr(setup, "port_in_use", lambda p: p == 5050)
    assert setup.choose_ports() == (5434, 5051)


def test_an_explicit_port_in_the_environment_wins(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST_PORT", "6543")
    monkeypatch.setenv("VETCLINICSYSTEM_PORT", "6050")
    monkeypatch.setattr(setup, "docker_claimed_ports", lambda: {6543, 6050})
    assert setup.choose_ports() == (6543, 6050)


# ---------------------------------------------------------------------------
# The choice reaches .env, and everything that starts the app reads it there
# ---------------------------------------------------------------------------

def test_the_chosen_ports_are_written_into_the_new_env():
    env = setup.with_ports(EXAMPLE, 5434, 5051)
    assert _env_line(env, "DATABASE_URL").endswith("@127.0.0.1:5434/vetclinicsystem")
    assert _env_line(env, "VETCLINICSYSTEM_PORT") == "VETCLINICSYSTEM_PORT=5051"
    assert env.count("VETCLINICSYSTEM_PORT=") == 1


def test_control_the_default_ports_leave_the_database_url_as_it_was():
    env = setup.with_ports(EXAMPLE, 5432, 5050)
    assert _env_line(env, "DATABASE_URL") == _env_line(EXAMPLE, "DATABASE_URL")


def _launcher_port(tmp_path, env_text, environ_port=None):
    """Runs the real macOS supervisor launcher in an empty data folder. It
    prints the URL it will serve, then stops at "no valid release"."""
    data = tmp_path / "vetclinicsystem-data"
    data.mkdir(parents=True)
    (data / ".env").write_text(env_text)
    launcher = data / "Start VetClinicSystem.command"
    launcher.write_text(setup._MACOS_LAUNCHER)
    env = {k: v for k, v in os.environ.items() if k != "VETCLINICSYSTEM_PORT"}
    if environ_port:
        env["VETCLINICSYSTEM_PORT"] = environ_port
    r = subprocess.run(["bash", str(launcher)], capture_output=True, text=True, timeout=30,
                       stdin=subprocess.DEVNULL, env=env)
    line = next(l for l in r.stdout.splitlines() if "is running at" in l)
    return line.rsplit(":", 1)[1]


@pytest.mark.skipif(sys.platform == "win32", reason="the macOS launcher is a bash script")
def test_the_launcher_serves_on_the_port_in_env(tmp_path):
    """GUARD. The launcher defaulted to 5050 and passed it to the app
    explicitly, so a port in .env was overridden on every start."""
    assert _launcher_port(tmp_path, "VETCLINICSYSTEM_PORT=5051\n") == "5051"


@pytest.mark.skipif(sys.platform == "win32", reason="the macOS launcher is a bash script")
def test_control_the_launcher_falls_back_to_5050_and_the_environment_wins(tmp_path):
    assert _launcher_port(tmp_path / "a", "SECRET_KEY=x\n") == "5050"
    assert _launcher_port(tmp_path / "b", "VETCLINICSYSTEM_PORT=5051\n", environ_port="6060") == "6060"


def test_the_windows_launcher_reads_the_port_from_env():
    """The .bat cannot run here; this holds that it reads .env before it
    falls back to 5050."""
    t = setup._WINDOWS_LAUNCHER
    reads = t.index('for /f "usebackq tokens=1,* delims==" %%A in ("%DATA_DIR%.env")')
    default = t.index('if not defined VETCLINICSYSTEM_PORT set "VETCLINICSYSTEM_PORT=5050"')
    assert reads < default


def test_the_desktop_shortcut_opens_the_installs_port(tmp_path):
    (tmp_path / ".env").write_text("SECRET_KEY=x\nVETCLINICSYSTEM_PORT=5051\n")
    assert desktop_shortcut.install_port(str(tmp_path)) == "5051"
    (tmp_path / ".env").write_text("SECRET_KEY=x\n")
    assert desktop_shortcut.install_port(str(tmp_path)) == "5050"


def test_docker_publishes_the_port_setup_wrote_into_env(tmp_path, monkeypatch):
    """GUARD, found by a real first install: setup loads .env only after the
    database is up, so compose never saw the port it had just chosen and
    published 5432 -- "port is already allocated"."""
    (tmp_path / ".env").write_text(setup.with_ports(EXAMPLE, 5434, 5051))
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_HOST_PORT", raising=False)
    assert setup._compose_env()["POSTGRES_HOST_PORT"] == "5434"


def test_control_an_explicit_host_port_still_wins(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(setup.with_ports(EXAMPLE, 5434, 5051))
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.setenv("POSTGRES_HOST_PORT", "6543")
    assert setup._compose_env()["POSTGRES_HOST_PORT"] == "6543"


# ---------------------------------------------------------------------------
# The first double-click, and the ones after it (found by a real install)
# ---------------------------------------------------------------------------

def _layout(tmp_path, managed):
    """The folder a clinic downloads, and -- once setup has run -- the data
    folder beside it holding .env and the managed launcher."""
    checkout = tmp_path / "VetClinicSystem"
    checkout.mkdir()
    data = tmp_path / "vetclinicsystem-data"
    if managed:
        data.mkdir()
        (data / "active_release.txt").write_text("app_v1.0.0")
        (data / ".env").write_text("SECRET_KEY=x\nVETCLINICSYSTEM_PORT=5093\n")
    return checkout, data


def test_setup_run_again_from_the_download_folder_uses_the_installs_env(tmp_path, monkeypatch):
    """GUARD. It looked for .env only beside itself, found none (the first run
    had moved it), and wrote a new one: a new SECRET_KEY and new ports."""
    checkout, data = _layout(tmp_path, managed=True)
    monkeypatch.setattr(setup, "BASE_DIR", str(checkout))
    monkeypatch.delenv("VETCLINICSYSTEM_DATA_DIR", raising=False)
    assert setup._env_dir() == str(data)


def test_control_a_plain_checkout_keeps_its_env_beside_it(tmp_path, monkeypatch):
    checkout, _ = _layout(tmp_path, managed=False)
    monkeypatch.setattr(setup, "BASE_DIR", str(checkout))
    monkeypatch.delenv("VETCLINICSYSTEM_DATA_DIR", raising=False)
    assert setup._env_dir() == str(checkout)


def _double_click(tmp_path, managed):
    """Runs the real 'Start VetClinicSystem.command' of the download folder,
    with python3 and the venv stubbed: what it starts, and what it says."""
    checkout, data = _layout(tmp_path, managed)
    (checkout / "Start VetClinicSystem.command").write_text(
        (ROOT / "Start VetClinicSystem.command").read_text(encoding="utf-8"))
    (checkout / "venv" / "bin").mkdir(parents=True)
    (checkout / "venv" / "bin" / "activate").write_text("deactivate() { :; }\n")
    (checkout / ".env").write_text("SECRET_KEY=x\nVETCLINICSYSTEM_PORT=5094\n")
    if managed:
        (data / "Start VetClinicSystem.command").write_text('#!/bin/bash\necho "MANAGED LAUNCHER STARTED"\n')
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "python3").write_text(f'#!/bin/bash\necho "python3 $*" >> "{tmp_path}/python3.log"\n')
    (stubs / "open").write_text("#!/bin/bash\n")
    for f in stubs.iterdir():
        f.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "VETCLINICSYSTEM_PORT"}
    env["PATH"] = f"{stubs}:{env['PATH']}"
    r = subprocess.run(["bash", str(checkout / "Start VetClinicSystem.command")], capture_output=True,
                       text=True, timeout=30, stdin=subprocess.DEVNULL, env=env)
    return r.stdout, (tmp_path / "python3.log").read_text()


@pytest.mark.skipif(sys.platform == "win32", reason="the macOS launcher is a bash script")
def test_the_first_double_click_hands_over_to_the_installs_launcher(tmp_path):
    """GUARD. After setup, it ran run.py from the download folder, where the
    .env setup had just moved away no longer was: "SECRET_KEY is not set",
    and the app did not start on a clinic's first double-click."""
    out, ran = _double_click(tmp_path, managed=True)
    assert "python3 setup.py" in ran
    assert "MANAGED LAUNCHER STARTED" in out
    assert "run.py" not in ran


@pytest.mark.skipif(sys.platform == "win32", reason="the macOS launcher is a bash script")
def test_control_a_checkout_without_the_release_layout_runs_in_place_on_its_port(tmp_path):
    out, ran = _double_click(tmp_path, managed=False)
    assert "python3 run.py" in ran
    assert "http://127.0.0.1:5094" in out


def test_the_windows_double_click_hands_over_before_running_in_place():
    bat = (ROOT / "Start VetClinicSystem.bat").read_text(encoding="utf-8")
    handover = bat.index('call "..\\vetclinicsystem-data\\Start VetClinicSystem.bat"')
    assert handover < bat.index("python run.py")
    assert "127.0.0.1:5050" not in bat, "the in-place launcher still announces a fixed port"


# ---------------------------------------------------------------------------
# The install's identity for licensing (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §5.1)
# ---------------------------------------------------------------------------

def test_an_env_without_an_install_id_gets_one(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SECRET_KEY=x")
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    install_id = setup.ensure_install_id()
    assert f"\nVETCLINICSYSTEM_INSTALL_ID={install_id}\n" in (tmp_path / ".env").read_text()


def test_control_an_install_id_is_never_replaced(tmp_path, monkeypatch):
    """GUARD. A license is signed for it: a new ID on a re-run would
    invalidate the clinic's license."""
    (tmp_path / ".env").write_text("SECRET_KEY=x\nVETCLINICSYSTEM_INSTALL_ID=kept-1234\n")
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    assert setup.ensure_install_id() == "kept-1234"
    assert (tmp_path / ".env").read_text().count("VETCLINICSYSTEM_INSTALL_ID=") == 1


def test_a_new_env_is_created_with_an_install_id(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "BASE_DIR", str(ROOT))
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.setattr(setup, "choose_ports", lambda: (5432, 5050))
    setup.ensure_env_file()
    assert _env_line((tmp_path / ".env").read_text(), "VETCLINICSYSTEM_INSTALL_ID").count("-") == 4
