"""
VetClinicSystem — one-command setup.
Works the same way on macOS and Windows.

    python3 setup.py

What it does, in order:
  1. Checks Docker is installed and running (prints install instructions if not).
  2. Creates .env from .env.example if you don't have one yet (with a fresh
     random SECRET_KEY).
  3. Starts the PostgreSQL container (docker compose up -d) and waits for it
     to be ready.
  4. Creates the database schema if it isn't there yet, AND applies any
     columns/tables added since your database was first set up — this runs
     every time, so a schema update never requires remembering to run a
     separate migration script by hand.
  5. If no one can sign in yet, creates the first administrator with a
     one-time password and prints it.
  6. Prints next steps.

Safe to re-run any time — every step skips itself if already done.
"""
import os
import secrets
import shutil
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def step(msg):
    print(f"\n== {msg}")


def run(cmd, **kwargs):
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=BASE_DIR, **kwargs)


def check_docker():
    step("Checking Docker")
    if not shutil.which("docker"):
        print(
            "Docker was not found on this computer.\n\n"
            "Install Docker Desktop (free) from:\n"
            "  https://www.docker.com/products/docker-desktop/\n"
            "then run this script again. Docker Desktop works the same way "
            "on macOS and Windows."
        )
        sys.exit(1)
    result = run(["docker", "info"], capture_output=True, text=True)
    if result.returncode != 0:
        print(
            "Docker is installed but doesn't seem to be running.\n"
            "Start Docker Desktop, wait for it to finish launching, then "
            "run this script again."
        )
        sys.exit(1)
    print("  Docker is installed and running.")


def _env_dir():
    """Where this install's real .env lives.

    On the versioned-release layout that is the data directory, NOT the release
    folder — vcs/config.py resolves it the same way. setup.py used to look only
    in BASE_DIR, with two consequences on a managed install: load_dotenv_now()
    loaded nothing, so DATABASE_URL was absent and the database work ran
    against defaults; and ensure_env_file() found no .env and helpfully created
    one, inventing a fresh SECRET_KEY and a DATABASE_URL on the default port.
    That second file sat in the release folder shadowing nothing in normal
    operation (the launcher exports the data dir) but ready to be picked up by
    anyone running `python3 run.py` from that folder — pointing at the wrong
    port, with a secret key that would sign everybody out.
    """
    data_dir = os.environ.get("VETCLINICSYSTEM_DATA_DIR")
    return data_dir if data_dir and os.path.isdir(data_dir) else BASE_DIR


def ensure_env_file():
    step("Checking configuration (.env)")
    env_path = os.path.join(_env_dir(), ".env")
    example_path = os.path.join(BASE_DIR, ".env.example")
    if os.path.exists(env_path):
        print("  .env already exists — leaving it as-is.")
        return
    with open(example_path) as f:
        content = f.read()
    content = content.replace("change-me", secrets.token_hex(32))
    with open(env_path, "w") as f:
        f.write(content)
    print("  Created .env with a fresh secret key.")


def _compose_env():
    """Environment for `docker compose`, with the host port taken from
    DATABASE_URL.

    docker-compose.yml publishes the database on ${POSTGRES_HOST_PORT:-5432}.
    DATABASE_URL is what the app actually connects to. If those two disagree
    the container comes up on one port and every connection goes to another,
    which looks exactly like "Postgres didn't become ready in time" and sends
    you reading Docker logs that show a perfectly healthy database.

    Deriving one from the other means they cannot drift. An explicit
    POSTGRES_HOST_PORT already in the environment still wins, so an admin can
    override deliberately.
    """
    env = dict(os.environ)
    if env.get("POSTGRES_HOST_PORT"):
        return env
    url = env.get("DATABASE_URL")
    if url:
        try:
            from urllib.parse import urlparse
            port = urlparse(url).port
            if port:
                env["POSTGRES_HOST_PORT"] = str(port)
        except ValueError:
            # A malformed DATABASE_URL is the app's problem to report, not
            # this helper's — fall through to the compose default.
            pass
    return env


def start_postgres():
    step("Starting PostgreSQL (Docker)")
    compose = ["docker", "compose"]
    result = run(compose + ["version"], capture_output=True, text=True)
    if result.returncode != 0:
        compose = ["docker-compose"]  # older standalone binary
    env = _compose_env()
    host_port = env.get("POSTGRES_HOST_PORT", "5432")
    if host_port != "5432":
        print(f"  Publishing Postgres on host port {host_port} (from DATABASE_URL).")
    run(compose + ["up", "-d"], check=True, env=env)

    print("  Waiting for the database to be ready...")
    for _ in range(60):
        r = run(
            compose + ["exec", "-T", "db", "pg_isready", "-U", "vetclinicsystem", "-d", "vetclinicsystem"],
            capture_output=True, text=True, env=env,
        )
        if r.returncode == 0:
            print("  PostgreSQL is ready.")
            return
        time.sleep(2)
    print("  PostgreSQL didn't become ready in time — check `docker compose logs db`.")
    sys.exit(1)


def load_dotenv_now():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_env_dir(), ".env"))


def apply_schema():
    """Apply every pending migration, then seed roles and permissions
    (schema.py). Run by setup, by the in-app updater for a new release
    before it is switched to, and after a restore. A failing migration stops
    here with a non-zero exit — which fails the update and rolls it back —
    rather than being recorded and started past."""
    step("Setting up the database schema")
    from vcs.db import pool as dbmod
    from vcs.db import migrate as schema
    con = dbmod.connect()
    try:
        applied = schema.apply(con)
    except schema.MigrationFailed as e:
        con.rollback()
        print(f"\n  !! {e.filename} could not be applied:\n     {e.error}")
        print("     Nothing in that migration was kept. Fix the cause and run setup again.")
        sys.exit(1)
    finally:
        con.close()
    print("  Schema is up to date." if not applied else f"  Applied {len(applied)} migration(s).")


def ensure_first_admin():
    """The first administrator, with a one-time password printed here.

    A random password, not a well-known default: the repository is public
    and the app listens on the clinic network, so "admin / admin123" would be
    a working sign-in for anyone on the Wi-Fi until someone changed it. The
    account must choose its own password at first sign-in. Until it has, a
    re-run of setup issues a new temporary password, so a lost printout is
    never a locked-out clinic. Once anyone has signed in and changed it, this
    does nothing."""
    step("Checking the first administrator account")
    from vcs import auth
    from vcs.db import pool as dbmod
    con = dbmod.connect()
    try:
        users = con.execute("SELECT id, username, must_change_password FROM users ORDER BY id").fetchall()
        if len(users) > 1 or (users and not users[0]["must_change_password"]):
            print("  Accounts already exist — nothing to do.")
            return
        password = secrets.token_urlsafe(12)
        if users:
            username = users[0]["username"]
            con.execute("UPDATE users SET password_hash=? WHERE id=?",
                        (auth.hash_password(password), users[0]["id"]))
        else:
            username = "admin"
            role = con.execute("SELECT id FROM roles WHERE is_system = true").fetchone()
            con.execute(
                "INSERT INTO users (username, password_hash, full_name, role_id, active, "
                "must_change_password, created_at) VALUES (?,?,?,?,true,true,now())",
                (username, auth.hash_password(password), "Clinic Admin", role["id"]))
        con.commit()
    finally:
        con.close()
    print(f"\n  First sign-in:   username  {username}\n"
          f"                   password  {password}\n"
          "  You will choose your own password straight away. Until you do, running\n"
          "  setup again prints a new temporary password.\n")


def ensure_dependencies():
    step("Checking Python dependencies")
    req = os.path.join(BASE_DIR, "requirements.txt")
    # Plain install first; if the system Python refuses (macOS's
    # "externally-managed-environment" restriction on Homebrew/python.org
    # installs is the common case), retry with --user before giving up.
    attempts = [
        [sys.executable, "-m", "pip", "install", "-q", "-r", req],
        [sys.executable, "-m", "pip", "install", "-q", "--user", "-r", req],
    ]
    for cmd in attempts:
        if subprocess.run(cmd).returncode == 0:
            print("  Dependencies are installed.")
            return
    print(
        "\nCouldn't install the required Python packages automatically.\n"
        "Try running this by hand and then re-run setup.py:\n\n"
        f"  {sys.executable} -m pip install -r requirements.txt\n\n"
        "If that reports an 'externally-managed-environment' error, add\n"
        "--break-system-packages to the command above, or use a virtual\n"
        "environment (python3 -m venv .venv && source .venv/bin/activate).\n"
    )
    sys.exit(1)


def main():
    ensure_dependencies()
    check_docker()
    ensure_env_file()
    start_postgres()
    load_dotenv_now()
    apply_schema()
    ensure_first_admin()

    # In-app updates (Settings -> Updates) are on by default for every new
    # install — this switches onto the versioned-release layout
    # automatically, the same as running setup.py --enable-updates by hand
    # used to require. Skipped when already running from inside a managed
    # release, or when --no-enable-updates is passed (e.g. a plain local
    # dev checkout that deliberately wants to keep running in place).
    # "Already inside a managed release" is checked two ways: VETCLINICSYSTEM_DATA_DIR
    # is set when launched through the real launcher, but someone can also
    # cd into a release folder and run setup.py by hand with no env vars
    # set at all — the structural check (this folder is literally named
    # app_v* directly under a vetclinicsystem-releases/ folder) catches that case
    # too, since re-running enable_updates() from in there would resolve
    # data_dir/releases_dir relative to the WRONG parent and nest a second,
    # broken layout inside the first.
    in_release_folder = (
        os.path.basename(BASE_DIR).startswith("app_v")
        and os.path.basename(os.path.dirname(BASE_DIR)) == "vetclinicsystem-releases"
    )
    already_managed = bool(os.environ.get("VETCLINICSYSTEM_DATA_DIR")) or in_release_folder
    if already_managed or "--no-enable-updates" in sys.argv:
        # Managed installs still want their Desktop shortcut kept current;
        # only the layout switch below is a one-time thing.
        if already_managed:
            ensure_desktop_shortcut()
        print(
            "\nAll set. Start the app with:\n"
            "  python3 run.py\n"
            "\n(macOS: double-click 'Start VetClinicSystem.command'."
            "  Windows: double-click 'Start VetClinicSystem.bat'.)\n"
        )
        return

    enable_updates()


def ensure_desktop_shortcut(data_dir=None):
    """Creates (or refreshes) the Desktop shortcut — the fail-safe way to start
    the app when autostart didn't fire or was never turned on. Re-run on every
    setup.py pass, not just the first, so a shortcut someone deleted comes
    back and one left pointing at an old path gets corrected.

    Never fatal: an install that can't get a Desktop icon is still a perfectly
    working install, so this only ever reports what happened."""
    step("Desktop shortcut")
    try:
        from vcs.ops import desktop_shortcut
    except ImportError as e:
        print(f"  Skipped — could not load desktop_shortcut.py ({e}).")
        return
    if not desktop_shortcut.is_supported():
        print("  Skipped — not supported on this operating system.")
        return
    ok, message = desktop_shortcut.create(data_dir)
    print(f"  {message}")


# ---------------------------------------------------------------------------
# One-time opt-in: switch this install onto the versioned-release layout
# the in-app updater (Settings -> Updates, updater.py) needs. Not run by
# default main() — an admin runs `python3 setup.py --enable-updates`
# deliberately, since it moves .env/logs/attachments out of this folder.
# See RELEASE_WORKFLOW.md §3 for the target layout.
# ---------------------------------------------------------------------------
_MACOS_LAUNCHER = """#!/bin/bash
# VetClinicSystem — supervisor launcher (macOS). Lives in vetclinicsystem-data/,
# OUTSIDE any versioned release folder, so it survives every update.
# Reads active_release.txt fresh on every loop iteration to know which
# vetclinicsystem-releases/app_vX.Y.Z/ to run, and restarts automatically if the
# app process exits for any reason — a crash, or the deliberate exit
# updater.py triggers after promoting a new release (see
# updater.py's _request_restart()). updater.py has already proven the new
# release boots and passes /health, on a throwaway port, before ever
# flipping the pointer that controls what this loop runs next — this
# script's only job is to keep something running and pick up that change.
set -u
DATA_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASES_DIR="$(cd "$DATA_DIR/../vetclinicsystem-releases" && pwd)"
POINTER="$DATA_DIR/active_release.txt"
PORT="${VETCLINICSYSTEM_PORT:-5050}"
opened_browser=false

echo "VetClinicSystem is running at http://127.0.0.1:$PORT"
echo "Leave this window open while you use the app."
echo "Close this window (or press Control-C) to stop it."
echo ""

while true; do
  ACTIVE=$(cat "$POINTER" 2>/dev/null || true)
  if [ -z "$ACTIVE" ] || [ ! -d "$RELEASES_DIR/$ACTIVE" ]; then
    echo "No valid release at $POINTER — can't start. Run setup.py --enable-updates again?"
    read -p "Press Return to close this window..."
    exit 1
  fi
  RELEASE_DIR="$RELEASES_DIR/$ACTIVE"

  # Is this release's Python still usable? A Python upgrade (on macOS,
  # `brew upgrade` deleting the versioned Cellar directory this venv was
  # built against) leaves venv/bin/python3 dangling. Without this check the
  # app never starts and the loop below respawns a missing interpreter every
  # two seconds, forever, with nothing on screen explaining why.
  #
  # Rebuilding is safe: a venv holds only dependencies. All data lives in
  # Postgres and the data folder.
  if ! "$RELEASE_DIR/venv/bin/python3" -c "" >/dev/null 2>&1; then
    echo "The Python environment for this release is not working."
    echo "This usually means Python was upgraded or reinstalled."
    echo "Rebuilding it now — this takes about a minute..."
    rm -rf "$RELEASE_DIR/venv"
    if python3 -m venv "$RELEASE_DIR/venv" >/dev/null 2>&1 && \
       "$RELEASE_DIR/venv/bin/python3" -m pip install -q -r "$RELEASE_DIR/requirements.txt"; then
      echo "Rebuilt successfully."
    else
      echo ""
      echo "Could not rebuild it. Check that Python 3 is installed:"
      echo "  python3 --version"
      read -p "Press Return to close this window..."
      exit 1
    fi
  fi

  echo "Starting $ACTIVE..."
  VETCLINICSYSTEM_DATA_DIR="$DATA_DIR" VETCLINICSYSTEM_RELEASES_DIR="$RELEASES_DIR" VETCLINICSYSTEM_PORT="$PORT" \\
    "$RELEASE_DIR/venv/bin/python3" "$RELEASE_DIR/run.py" &
  APP_PID=$!

  if [ "$opened_browser" = false ]; then
    ( sleep 1.5 && open "http://127.0.0.1:$PORT" ) &
    opened_browser=true
  fi

  wait "$APP_PID"
  echo "VetClinicSystem exited (code $?) — restarting in 2 seconds..."
  sleep 2
done
"""

_WINDOWS_LAUNCHER = """@echo off
REM VetClinicSystem — supervisor launcher (Windows). Lives in vetclinicsystem-data\\,
REM OUTSIDE any versioned release folder, so it survives every update.
REM Reads active_release.txt fresh on every loop iteration — see the
REM matching comment in the macOS launcher (Start VetClinicSystem.command) for
REM why this loop doesn't need its own health-check/rollback logic.
setlocal
set "DATA_DIR=%~dp0"
set "RELEASES_DIR=%DATA_DIR%..\\vetclinicsystem-releases"
set "POINTER=%DATA_DIR%active_release.txt"
if not defined VETCLINICSYSTEM_PORT set "VETCLINICSYSTEM_PORT=5050"
set "OPENED_BROWSER=0"

:loop
set /p ACTIVE=<"%POINTER%"
if not exist "%RELEASES_DIR%\\%ACTIVE%" (
  echo No valid release at %POINTER% — can't start. Run setup.py --enable-updates again?
  pause
  exit /b 1
)
set "RELEASE_DIR=%RELEASES_DIR%\\%ACTIVE%"

REM Is this release's Python still usable? If Python was uninstalled, moved
REM or replaced, the venv's python.exe stops working and the app never
REM starts -- the loop below would otherwise respawn it every two seconds
REM forever with nothing explaining why. Rebuilding is safe: a venv holds
REM only dependencies; all data lives in Postgres and the data folder.
"%RELEASE_DIR%\\venv\\Scripts\\python.exe" -c "" >nul 2>&1
if errorlevel 1 (
  echo The Python environment for this release is not working.
  echo This usually means Python was upgraded, moved or reinstalled.
  echo Rebuilding it now - this takes about a minute...
  rmdir /s /q "%RELEASE_DIR%\\venv" 2>nul
  python -m venv "%RELEASE_DIR%\\venv" >nul 2>&1
  if errorlevel 1 goto rebuildfailed
  "%RELEASE_DIR%\\venv\\Scripts\\python.exe" -m pip install -q -r "%RELEASE_DIR%\\requirements.txt"
  if errorlevel 1 goto rebuildfailed
  echo Rebuilt successfully.
)
echo Starting %ACTIVE%...
set "VETCLINICSYSTEM_DATA_DIR=%DATA_DIR%"
set "VETCLINICSYSTEM_RELEASES_DIR=%RELEASES_DIR%"
if "%OPENED_BROWSER%"=="0" (
  start "" http://127.0.0.1:%VETCLINICSYSTEM_PORT%
  set "OPENED_BROWSER=1"
)
"%RELEASE_DIR%\\venv\\Scripts\\python.exe" "%RELEASE_DIR%\\run.py"
echo VetClinicSystem exited — restarting in 2 seconds...
timeout /t 2 /nobreak >nul
goto loop

:rebuildfailed
echo.
echo Could not rebuild the Python environment. Check that Python 3 is
echo installed and on PATH:  python --version
pause
exit /b 1
"""


def _base_interpreter():
    """The interpreter to build a release venv from.

    NOT sys.executable. When setup.py itself runs inside a venv, that is the
    venv's own python, and the new venv inherits whatever path the parent
    resolved to. On Homebrew that path is often a VERSIONED one
    (/opt/homebrew/Cellar/python@3.14/3.14.6/...), which `brew upgrade`
    deletes -- so every release built from it is one upgrade away from a
    dangling symlink and an app that cannot start at all. Observed on a real
    install 2026-09-02: two releases, both unstartable, with the supervisor
    loop respawning a missing interpreter every two seconds forever.

    sys._base_executable is the underlying interpreter, which on Homebrew
    resolves through the stable /opt/homebrew/opt/... symlink that brew
    repoints on upgrade. Falls back to sys.executable where it is missing or
    not a real file, so this can never make venv creation fail.

    This narrows the window; it does not close it. A Python that is
    uninstalled or moved breaks the venv regardless, which is why the
    launcher also rebuilds a broken venv on startup.
    """
    base = getattr(sys, "_base_executable", None)
    if base and os.path.isfile(base):
        return base
    return sys.executable


def _copy_release_snapshot(dest):
    """Copies the current codebase into dest, excluding everything that
    belongs to a specific machine/install rather than the versioned app
    itself (venv, .git, __pycache__, and anything already destined for
    vetclinicsystem-data/)."""
    exclude = {"venv", ".git", "__pycache__", "logs", ".env", "vetclinicsystem-data", "vetclinicsystem-releases"}

    def _skip(src, names):
        # `.env*` is excluded to keep this machine's real .env out of a
        # versioned release — but NOT .env.example, which is part of the app
        # and which ensure_env_file() reads. Excluding it left every release
        # built by this function without it, so running setup.py inside that
        # release died with FileNotFoundError on .env.example. Releases
        # unpacked by updater.py were unaffected, which is why this survived:
        # the only way to see it is a fresh --enable-updates install.
        return [n for n in names
                if n in exclude or (n.startswith(".env") and n != ".env.example")]

    shutil.copytree(BASE_DIR, dest, ignore=_skip)


def enable_updates(data_dir=None, releases_dir=None):
    step("Switching to the versioned-release layout")
    parent = os.path.dirname(BASE_DIR)
    data_dir = os.path.abspath(data_dir or os.path.join(parent, "vetclinicsystem-data"))
    releases_dir = os.path.abspath(releases_dir or os.path.join(parent, "vetclinicsystem-releases"))
    pointer = os.path.join(data_dir, "active_release.txt")

    if os.path.isfile(pointer):
        print(f"  Already enabled — {pointer} exists.")
        ensure_desktop_shortcut(data_dir)
        print(f"  VETCLINICSYSTEM_DATA_DIR={data_dir}\n  VETCLINICSYSTEM_RELEASES_DIR={releases_dir}")
        return

    version_path = os.path.join(BASE_DIR, "VERSION")
    if not os.path.isfile(version_path):
        print("  No VERSION file in this codebase — can't determine the release name. Aborting.")
        sys.exit(1)
    version = open(version_path).read().strip()
    release_name = f"app_v{version}"
    release_path = os.path.join(releases_dir, release_name)

    print(f"  This will:\n"
          f"    - create {data_dir}/ (persistent: .env, logs, attachments, backups)\n"
          f"    - create {releases_dir}/{release_name}/ (a copy of this codebase)\n"
          f"    - move .env, logs/, attachments/uploads/ into {data_dir}/\n"
          f"    - write new launcher scripts into {data_dir}/\n"
          f"  This folder ({BASE_DIR}) is left as-is otherwise — nothing here is deleted.\n")

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(releases_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "backups"), exist_ok=True)

    print(f"  Copying codebase into {release_path} ...")
    if os.path.isdir(release_path):
        shutil.rmtree(release_path)
    _copy_release_snapshot(release_path)

    print("  Creating this release's own virtual environment...")
    subprocess.run([_base_interpreter(), "-m", "venv", os.path.join(release_path, "venv")],
                   check=True)
    venv_py = os.path.join(release_path, "venv", "Scripts" if sys.platform == "win32" else "bin",
                            "python.exe" if sys.platform == "win32" else "python3")
    subprocess.run([venv_py, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                    check=True, cwd=release_path)

    env_src = os.path.join(BASE_DIR, ".env")
    env_dst = os.path.join(data_dir, ".env")
    if os.path.isfile(env_src) and not os.path.isfile(env_dst):
        shutil.move(env_src, env_dst)
        print(f"  Moved .env -> {env_dst}")

    logs_src = os.path.join(BASE_DIR, "logs")
    logs_dst = os.path.join(data_dir, "logs")
    os.makedirs(logs_dst, exist_ok=True)
    if os.path.isdir(logs_src):
        for name in os.listdir(logs_src):
            shutil.move(os.path.join(logs_src, name), os.path.join(logs_dst, name))

    uploads_src = os.path.join(BASE_DIR, "uploads")
    uploads_dst = os.path.join(data_dir, "attachments", "uploads")
    if os.path.isdir(uploads_src):
        os.makedirs(os.path.dirname(uploads_dst), exist_ok=True)
        shutil.move(uploads_src, uploads_dst)
        print(f"  Moved uploads/ -> {uploads_dst}")

    with open(pointer, "w") as f:
        f.write(release_name)

    mac_launcher = os.path.join(data_dir, "Start VetClinicSystem.command")
    win_launcher = os.path.join(data_dir, "Start VetClinicSystem.bat")
    with open(mac_launcher, "w", newline="\n") as f:
        f.write(_MACOS_LAUNCHER)
    os.chmod(mac_launcher, 0o755)
    with open(win_launcher, "w", newline="\r\n") as f:
        f.write(_WINDOWS_LAUNCHER)

    ensure_desktop_shortcut(data_dir)

    print(
        f"\nDone. Add these two lines to {env_dst}:\n\n"
        f"  VETCLINICSYSTEM_DATA_DIR={data_dir}\n"
        f"  VETCLINICSYSTEM_RELEASES_DIR={releases_dir}\n\n"
        f"Then start the app from now on with:\n"
        f"  {mac_launcher}   (macOS)\n"
        f"  {win_launcher}   (Windows)\n\n"
        f"Not from {os.path.join(BASE_DIR, 'Start VetClinicSystem.command')} anymore — that copy has no "
        f"way to pick up future updates. This original folder is untouched and safe to keep "
        f"around, but the copy under {releases_dir}/ is what actually runs from now on.\n"
    )


if __name__ == "__main__":
    if "--desktop-shortcut" in sys.argv:
        ensure_desktop_shortcut()
    elif "--enable-updates" in sys.argv:
        enable_updates()
    else:
        main()
