"""
VetClinicSystem — one-command setup.
Works the same way on macOS and Windows.

    python3 setup.py --setup-code CODE     (a new clinic: the one code from the vendor's console)
    python3 setup.py [--money-setting IQ|JO] [--license-key KEY]
    python3 setup.py --db-mode native --database-url postgresql://ROLE:PASSWORD@HOST:PORT/DB ...

What it does, in order:
  1. Checks Docker is installed and running (prints install instructions if
     not) -- in Docker mode. Native mode (docs/NATIVE_POSTGRESQL.md) uses a
     PostgreSQL server installed on this computer and never runs Docker.
  2. Creates .env from .env.example if you don't have one yet (with a fresh
     random SECRET_KEY), choosing the app's port and the database's host
     port: 5050 and 5432 unless another program or container already has
     them, in which case the next free ones. In native mode DATABASE_URL is
     the one given.
  3. Starts the PostgreSQL container (docker compose up -d) and waits for it
     to be ready; in native mode, waits for the server to answer. Either way
     it must be PostgreSQL 16 or newer.
  4. Creates the database schema if it isn't there yet, AND applies any
     columns/tables added since your database was first set up — this runs
     every time, so a schema update never requires remembering to run a
     separate migration script by hand.
  5. If no one can sign in yet, creates the first administrator with a
     one-time password and prints it.
  6. The money setting (--money-setting) and the license key (--license-key,
     or asked for): setup does not finish without a valid key.
  7. Prints next steps.

Safe to re-run any time — every step skips itself if already done.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid

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
    if data_dir and os.path.isdir(data_dir):
        return data_dir
    # Run again from the folder it was downloaded to, after the first run
    # switched the install onto the release layout: its .env is in the data
    # folder beside this one. Looking only here, setup found no .env and
    # wrote a new one -- a new SECRET_KEY, and new ports, on which it then
    # republished the database while the app went on using the old port.
    sibling = os.path.join(os.path.dirname(BASE_DIR), "vetclinicsystem-data")
    if os.path.isfile(os.path.join(sibling, "active_release.txt")):
        return sibling
    return BASE_DIR


DEFAULT_APP_PORT = 5050
DEFAULT_DB_PORT = 5432
PG_CONTAINER = "vetclinicsystem_postgres"      # docker-compose.yml's container_name


def port_in_use(port):
    """Something on this machine is listening on `port` (on any address)."""
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                return True
    return False


def docker_claimed_ports(inspect_output=None):
    """Host ports published by every other container, running or stopped: a
    stopped database takes its port back the next time Docker starts it, so
    a port that is free this minute can still belong to another install.

    `inspect_output` is for the tests: the text `docker inspect` printed."""
    if inspect_output is None:
        ids = subprocess.run(["docker", "ps", "-aq"], capture_output=True, text=True).stdout.split()
        if not ids:
            return set()
        inspect_output = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}} {{json .HostConfig.PortBindings}}", *ids],
            capture_output=True, text=True).stdout
    claimed = set()
    for line in inspect_output.splitlines():
        name, _, bindings = line.strip().partition(" ")
        if not name or name.lstrip("/") == PG_CONTAINER:
            continue
        for binds in (json.loads(bindings or "null") or {}).values():
            for b in binds or []:
                if str(b.get("HostPort", "")).isdigit():
                    claimed.add(int(b["HostPort"]))
    return claimed


def first_free_port(preferred, claimed, in_use=None, span=200):
    in_use = in_use or port_in_use
    for port in range(preferred, preferred + span):
        if port not in claimed and not in_use(port):
            return port
    print(f"  No free port between {preferred} and {preferred + span - 1}. Free one, "
          "or set it in .env yourself, then run setup again.")
    sys.exit(1)


def with_ports(content, db_port, app_port):
    """.env.example's text for this install's two ports: the database's host
    port inside DATABASE_URL (docker compose publishes whatever DATABASE_URL
    says -- _compose_env), and the app's port as an active
    VETCLINICSYSTEM_PORT line, which the app and every launcher read."""
    if db_port is not None:
        content, n = re.subn(r"(DATABASE_URL=postgresql://[^@\s]+@127\.0\.0\.1:)\d+/", rf"\g<1>{db_port}/", content)
        assert n == 1, "DATABASE_URL in .env.example is not the expected local URL"
    line = f"VETCLINICSYSTEM_PORT={app_port}"
    content, n = re.subn(r"(?m)^#?VETCLINICSYSTEM_PORT=.*$", line, content)
    return content if n else content.rstrip("\n") + f"\n{line}\n"


# ---------------------------------------------------------------------------
# The setup code (docs/plans/VENDOR_CONSOLE_PLAN.md V-2, V-3): a new clinic's
# whole setup in one line, made by the vendor's console and read here. Made
# and read in this file only, so the two cannot drift; setup reads it before
# anything of vcs is imported, while .env does not exist yet.
# ---------------------------------------------------------------------------
SETUP_CODE_PREFIX = "VCSSETUP1"


class BadSetupCode(ValueError):
    """A code that cannot be used; str() is the sentence to print."""


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_setup_code(license_key, money_setting, palette=None, github_token=None, heartbeat_url=None):
    """The signed license -- which names the installation and the clinic --
    and what only the vendor sets. Not signed itself: whoever runs setup
    controls that computer anyway. The checksum catches a damaged paste."""
    body = {"v": 1, "license": license_key, "money_setting": money_setting}
    for name, value in (("palette", palette), ("github_token", github_token), ("heartbeat_url", heartbeat_url)):
        if value:
            body[name] = value
    data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"{SETUP_CODE_PREFIX}.{_b64url(data)}.{hashlib.sha256(data).hexdigest()[:12]}"


def parse_setup_code(text):
    """The code's fields, with the installation ID and the clinic's name read
    from its license. The license is verified later, by ensure_license()."""
    parts = "".join((text or "").split()).split(".")
    if len(parts) != 3 or parts[0] != SETUP_CODE_PREFIX:
        raise BadSetupCode("This is not a VetClinicSystem setup code. Check that all of it was copied.")
    try:
        data = _unb64url(parts[1])
    except ValueError:
        data = b""
    if hashlib.sha256(data).hexdigest()[:12] != parts[2]:
        raise BadSetupCode("This setup code has been changed or damaged. Copy it again from what your vendor sent.")
    try:
        body = json.loads(data)
        license_payload = json.loads(_unb64url(body["license"].split(".")[1]))
        code = dict(body, install_id=license_payload["install_id"], clinic_name=license_payload["clinic_name"])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise BadSetupCode("This setup code is missing information it needs. Ask your vendor for a new one.")
    if body.get("v") != 1 or not isinstance(code["money_setting"], str) or not isinstance(code["install_id"], str):
        raise BadSetupCode("This setup code is missing information it needs. Ask your vendor for a new one.")
    return code


def read_setup_code():
    """`--setup-code`, or asked for when a new install is set up by hand; None
    without one. A damaged code stops setup before anything is written."""
    text = _argument("--setup-code")
    new_install = not os.path.exists(os.path.join(_env_dir(), ".env"))
    if not text and new_install and sys.stdin.isatty() and not _argument("--license-key"):
        step("Setup code")
        text = input("  Paste the setup code from your vendor, or press Return to set up without one: ").strip()
    if not text:
        return None
    try:
        code = parse_setup_code(text)
    except BadSetupCode as e:
        print(f"  {e}")
        sys.exit(1)
    print(f"  Setup code for {code['clinic_name']} (installation {code['install_id']}).")
    return code


def ensure_setup_code_matches(code, install_id):
    """A setup code names the installation it was made for; an install that
    already has another ID (set up before) cannot take it."""
    if code and install_id != code["install_id"]:
        print(f"  This setup code is for installation {code['install_id']}, but this install is {install_id}. "
              "A setup code is for a new install; for this one, ask your vendor for a license key.")
        sys.exit(1)


def apply_setup_code(code):
    """What only the vendor sets, from the code: the palette, the clinic's
    name (when none is set yet), the monitoring ping URL and the update token.
    Written directly, as the money setting is -- at setup there is no request
    and no clinic user. A secret is reported as saved, never printed."""
    if not code:
        return
    step("Applying the setup code")
    from vcs.db import pool as dbmod
    from vcs.ops import updater
    from vcs.web import palettes

    def put(con, key, value):
        con.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
    con = dbmod.connect()
    try:
        palette = code.get("palette")
        if palette and palettes.is_palette(palette):
            put(con, "theme_palette", palette)
            print(f"  Color palette: {palette}.")
        elif palette:
            print(f"  Not a color palette: {palette!r}; the default stays.")
        if not con.execute("SELECT 1 FROM settings WHERE key='clinic_name'").fetchone():
            put(con, "clinic_name", code["clinic_name"])
            print(f"  Clinic name: {code['clinic_name']}.")
        url = code.get("heartbeat_url")
        if url and url.lower().startswith("https://"):
            put(con, "heartbeat_url", url)
            print("  Monitoring ping URL saved.")
        elif url:
            print("  The monitoring ping URL does not start with https://, so it was not saved.")
        con.commit()
    finally:
        con.close()
    if code.get("github_token"):
        updater.save_token(code["github_token"])
        print("  Update access token saved.")


DB_MODES = ("docker", "native")
MIN_SERVER_VERSION = 160000          # PostgreSQL 16 (server_version_num)


def db_mode():
    """How this install's PostgreSQL runs (licensing plan A11): `--db-mode`,
    else VETCLINICSYSTEM_DB_MODE from the environment or this install's .env,
    else docker. Explicit, never detected: on a machine with two servers,
    "whatever answers on the port" could be the wrong one."""
    value = _argument("--db-mode") or os.environ.get("VETCLINICSYSTEM_DB_MODE")
    env_path = os.path.join(_env_dir(), ".env")
    stored = None
    if os.path.exists(env_path):
        from dotenv import dotenv_values
        stored = dotenv_values(env_path).get("VETCLINICSYSTEM_DB_MODE") or "docker"
    value = (value or stored or "docker").strip().lower()
    if value not in DB_MODES:
        print(f"  The database mode must be one of {', '.join(DB_MODES)}, not {value!r}.")
        sys.exit(1)
    if stored and value != stored.strip().lower():
        print(f"  This install's database mode is {stored} (its .env); setup does not move an install "
              f"from one mode to another. Leave --db-mode out, or set up a new install.")
        sys.exit(1)
    return value


def choose_ports(mode="docker"):
    """(database host port, app port) for a new install. An explicit
    POSTGRES_HOST_PORT / VETCLINICSYSTEM_PORT in the environment wins. In
    native mode there is no container to ask about its ports -- and no
    docker command to ask with."""
    claimed = docker_claimed_ports() if mode == "docker" else set()
    chosen = []
    for var, preferred, what in (("POSTGRES_HOST_PORT", DEFAULT_DB_PORT, "database"),
                                 ("VETCLINICSYSTEM_PORT", DEFAULT_APP_PORT, "app")):
        if os.environ.get(var, "").isdigit():
            port = int(os.environ[var])
        else:
            port = first_free_port(preferred, claimed)
            if port != preferred:
                print(f"  Port {preferred} is already taken on this computer — the {what} "
                      f"will use {port} instead.")
        claimed.add(port)
        chosen.append(port)
    return tuple(chosen)


def native_env(content, database_url, app_port):
    """.env.example's text for a native-mode install: the clinic's own
    DATABASE_URL, the mode, and none of the container's settings."""
    content, n = re.subn(r"(?m)^DATABASE_URL=.*$", lambda m: f"DATABASE_URL={database_url}", content)
    assert n == 1, "no DATABASE_URL line in .env.example"
    content = re.sub(r"(?m)^(POSTGRES_PASSWORD|VETCLINICSYSTEM_PG_CONTAINER)=.*\n", "", content)
    content = with_ports(content, None, app_port)
    return content.rstrip("\n") + "\nVETCLINICSYSTEM_DB_MODE=native\n"


def ensure_env_file(mode="docker", install_id=None):
    step("Checking configuration (.env)")
    env_path = os.path.join(_env_dir(), ".env")
    example_path = os.path.join(BASE_DIR, ".env.example")
    if os.path.exists(env_path):
        print("  .env already exists — leaving it as-is.")
        return
    with open(example_path) as f:
        content = f.read()
    content = content.replace("change-me", secrets.token_hex(32))
    if mode == "native":
        database_url = _argument("--database-url") or os.environ.get("DATABASE_URL")
        if not database_url:
            print("  Native mode connects to a PostgreSQL server you run, so setup needs its address:\n"
                  "    python3 setup.py --db-mode native --database-url "
                  "postgresql://ROLE:PASSWORD@HOST:PORT/DATABASE\n"
                  "  The role must own the database and have CREATEDB (docs/NATIVE_POSTGRESQL.md).")
            sys.exit(1)
        _db_port, app_port = choose_ports("native")
        content = native_env(content, database_url, app_port)
        with open(env_path, "w") as f:
            f.write(content.rstrip("\n") + f"\nVETCLINICSYSTEM_INSTALL_ID={install_id or uuid.uuid4()}\n")
        print(f"  Created .env for native PostgreSQL with a fresh secret key. The app will be at "
              f"http://127.0.0.1:{app_port}.")
        return
    db_port, app_port = choose_ports()
    content = with_ports(content, db_port, app_port)
    content = content.rstrip("\n") + f"\nVETCLINICSYSTEM_INSTALL_ID={install_id or uuid.uuid4()}\n"
    with open(env_path, "w") as f:
        f.write(content)
    print(f"  Created .env with a fresh secret key. The app will be at http://127.0.0.1:{app_port}; "
          f"its database on port {db_port}.")


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

    DATABASE_URL is read from .env when the environment does not carry it:
    setup loads .env only after the database is up, so on a first install
    the port setup had just written there never reached docker compose,
    which published 5432 regardless ("port is already allocated").
    """
    env = dict(os.environ)
    if env.get("POSTGRES_HOST_PORT"):
        return env
    url = env.get("DATABASE_URL")
    if not url:
        from dotenv import dotenv_values
        url = dotenv_values(os.path.join(_env_dir(), ".env")).get("DATABASE_URL")
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


def _where(url):
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(url)
        return f"{parts.hostname or '127.0.0.1'}:{parts.port or 5432}"
    except ValueError:
        return "the address in DATABASE_URL"


def wait_for_database(timeout=60):
    """Native mode: the server is the clinic's own, already running (or
    starting at boot). Wait for DATABASE_URL to answer; never start or ask
    Docker."""
    step("Waiting for PostgreSQL")
    import psycopg
    url = os.environ.get("DATABASE_URL", "")
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=5) as con:
                con.execute("SELECT 1")
            print(f"  PostgreSQL at {_where(url)} is accepting connections.")
            return
        except psycopg.OperationalError as e:
            error = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            time.sleep(2)
    print(f"  PostgreSQL at {_where(url)} did not accept a connection within {timeout} seconds "
          f"({error}).\n  Start its service, check DATABASE_URL in .env, then run setup again.")
    sys.exit(1)


def check_server(mode):
    """PostgreSQL 16 or newer, in either mode; in native mode, a role that
    can create databases, which the monthly restore check needs
    (licensing plan §12.1, §12.3)."""
    step("Checking the PostgreSQL server")
    import psycopg
    url = os.environ.get("DATABASE_URL", "")
    with psycopg.connect(url, connect_timeout=10) as con:
        version = int(con.execute("SHOW server_version_num").fetchone()[0])
        can_create = con.execute("SELECT rolcreatedb OR rolsuper FROM pg_roles "
                                 "WHERE rolname = current_user").fetchone()[0]
    major = version // 10000
    if version < MIN_SERVER_VERSION:
        print(f"  The PostgreSQL server at {_where(url)} is version {major}; VetClinicSystem needs 16 or "
              "newer. Upgrade the server, then run setup again.")
        sys.exit(1)
    print(f"  PostgreSQL {major} ({mode} mode).")
    if mode == "native" and not can_create:
        print("  !! The database role cannot create databases (CREATEDB). The app works, but the monthly\n"
              "     check that a backup really restores needs to create a throwaway database, so it will\n"
              "     report this until the role is given CREATEDB (docs/NATIVE_POSTGRESQL.md).")
    return major


def ensure_install_id():
    """This install's identity for licensing (vcs/config.py INSTALL_ID): a
    UUID written into .env once, and never changed after -- a license is
    signed for it. An .env made before it existed gets one added."""
    env_path = os.path.join(_env_dir(), ".env")
    with open(env_path) as f:
        content = f.read()
    found = re.search(r"(?m)^VETCLINICSYSTEM_INSTALL_ID=(\S+)", content)
    if found:
        install_id = found.group(1)
    else:
        install_id = str(uuid.uuid4())
        with open(env_path, "a") as f:
            f.write(("" if content.endswith("\n") else "\n") + f"VETCLINICSYSTEM_INSTALL_ID={install_id}\n")
    print(f"  This installation's ID: {install_id} (your vendor needs it for the license key).")
    return install_id


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
            con.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                        (auth.hash_password(password), users[0]["id"]))
        else:
            username = "admin"
            role = con.execute("SELECT id FROM roles WHERE is_system = true").fetchone()
            con.execute(
                "INSERT INTO users (username, password_hash, full_name, role_id, active, "
                "must_change_password, created_at) VALUES (%s,%s,%s,%s,true,true,now())",
                (username, auth.hash_password(password), "Clinic Admin", role["id"]))
        con.commit()
    finally:
        con.close()
    print(f"\n  First sign-in:   username  {username}\n"
          f"                   password  {password}\n"
          "  You will choose your own password straight away. Until you do, running\n"
          "  setup again prints a new temporary password.\n")


def _argument(name):
    """The value after `--name` on the command line, or None."""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def ensure_money_setting(from_setup_code=None):
    """`--money-setting IQ|JO`, or the setup code's: the vendor chooses it at
    setup, so the clinic can record money from the first day (licensing plan
    §9.3). The same rule as the Developer area's: it can change until money
    has been recorded. Without either, nothing is done; Developer ->
    Configuration sets it."""
    code = _argument("--money-setting") or from_setup_code
    if not code:
        return None
    step("Setting the money setting")
    from vcs import money
    from vcs.db import pool as dbmod
    code = code.strip().upper()
    if code not in money.SETTINGS:
        print(f"  Not a money setting: {code!r}. Use one of {', '.join(money.SETTINGS)}.")
        sys.exit(1)
    con = dbmod.connect()
    try:
        current = money.load(con)
        if current and current.code == code:
            print(f"  Already {code}.")
            return code
        if current and money.is_locked(con):
            print(f"  The money setting is {current.code} and money has been recorded in it, so it cannot change.")
            sys.exit(1)
        con.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (money.SETTING_KEY, code))
        con.commit()
    finally:
        con.close()
    print(f"  Money setting: {code}.")
    return code


def ensure_license(key=None):
    """Setup does not finish without a license key that verifies for this
    installation (licensing plan L-7). There is no trial. A key already stored
    is kept; otherwise `--license-key KEY`, or it is asked for."""
    step("Checking the license")
    from vcs import config
    from vcs.licensing import state, tokens
    status = state.evaluate()
    if status.state not in (state.MISSING, state.INVALID):
        print(f"  License: {state.LABELS[status.state]}.")
        return status
    key = key or _argument("--license-key")
    if not key and sys.stdin.isatty():
        print(f"  This installation's ID is {config.INSTALL_ID}. Your vendor signs the license for it.")
        key = input("  Paste the license key: ")
    if not key:
        print(f"  No license key. Ask your vendor for one for installation {config.INSTALL_ID}, "
              "then run setup again with --license-key.")
        sys.exit(1)
    try:
        status = state.enter_key(None, key)
    except tokens.TokenError as e:
        print(f"  That license key was refused: {e.message}")
        sys.exit(1)
    print(f"  License saved: {state.LABELS[status.state]}, until {status.payload['expires_at']}.")
    return status


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
    code = read_setup_code()
    mode = db_mode()
    if mode == "docker":
        check_docker()
    ensure_env_file(mode, install_id=code and code["install_id"])
    ensure_setup_code_matches(code, ensure_install_id())
    if mode == "docker":
        start_postgres()
    load_dotenv_now()
    if mode == "native":
        wait_for_database()
    check_server(mode)
    apply_schema()
    ensure_first_admin()
    ensure_money_setting(code and code["money_setting"])
    ensure_license(code and code["license"])
    apply_setup_code(code)

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
# The port this install was given (setup.py moves off 5050 when it is taken
# and writes the choice into .env); the environment still wins.
PORT="${VETCLINICSYSTEM_PORT:-}"
if [ -z "$PORT" ] && [ -f "$DATA_DIR/.env" ]; then
  PORT="$(sed -n 's/^VETCLINICSYSTEM_PORT=//p' "$DATA_DIR/.env" | tail -n 1 | tr -d '[:space:]')"
fi
PORT="${PORT:-5050}"
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
REM The port this install was given (setup.py writes it into .env).
if not defined VETCLINICSYSTEM_PORT if exist "%DATA_DIR%.env" for /f "usebackq tokens=1,* delims==" %%A in ("%DATA_DIR%.env") do if "%%A"=="VETCLINICSYSTEM_PORT" set "VETCLINICSYSTEM_PORT=%%B"
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
    exclude = {"venv", ".git", "__pycache__", "logs", ".env", "license", "github_token", "vetclinicsystem-data",
               "vetclinicsystem-releases"}

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


def move_secrets_into(data_dir, base_dir=None):
    """The license key and the update token stay with the install, in the data
    folder: the app reads them there (vcs/licensing/state.py, updater
    TOKEN_FILE), and a release copy must never carry them. A move keeps the
    token's owner-only permissions."""
    base_dir = base_dir or BASE_DIR
    for name, is_there in (("license", os.path.isdir), ("github_token", os.path.isfile)):
        src, dst = os.path.join(base_dir, name), os.path.join(data_dir, name)
        if is_there(src) and not os.path.exists(dst):
            shutil.move(src, dst)
            print(f"  Moved {name} -> {dst}")


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

    move_secrets_into(data_dir)

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
