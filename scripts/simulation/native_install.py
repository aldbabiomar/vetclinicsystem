#!/usr/bin/env python3
"""
A fresh install in native PostgreSQL mode, from a setup code, for real
(licensing plan §16 phase 8; VENDOR_CONSOLE_PLAN.md; docs/NATIVE_POSTGRESQL.md):

    /tmp/vcs_test_venv_jo/bin/python scripts/simulation/native_install.py

1. On the throwaway test server (vcs_test_jo, port 55492 -- never another
   server on this machine) it makes the role and database the guide
   describes: a login role that owns its database and has CREATEDB.
2. It copies the working tree (tracked files, and new ones not ignored) into
   a temporary folder -- a clean copy, as a clinic would receive it -- makes
   a setup code as the Vendor Console does (a license for an installation ID
   chosen in advance, the money setting, a palette, a stand-in update token
   and ping URL), and runs that copy's `setup.py --setup-code … --db-mode
   native --no-enable-updates` from an environment whose PATH holds the
   PostgreSQL client tools and nothing else. There is no docker to run: a
   Docker call would stop setup with "No such file or directory".
3. It checks what setup applied: the code's installation ID in .env, the
   palette, the clinic's name, the ping URL, the token file (owner-only).
4. With the installed code, in that same environment: a backup, the restore
   check, and a restore.
5. It removes the role, the database and the folder.

The one thing not the production path: the license key is signed with the
test environment's throwaway vendor key, which the child process trusts
(tokens.trust_for_tests, as scripts/test_launcher.py does) -- no release
trusts it, and TRUSTED_KEYS is empty until the vendor makes the real key.
"""
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[2]
SERVER = "postgresql://postgres:test@127.0.0.1:55492/postgres"
TEST_VENDOR = Path("/tmp/vcs_test_data_jo/test-vendor")
PYTHON = sys.executable

CHILD = textwrap.dedent('''
    import os, sys
    sys.path.insert(0, os.getcwd())
    import setup
    sys.argv = ["setup.py", *sys.argv[1:]]
    ensure_license = setup.ensure_license

    def trusted_first(key=None):
        # By now setup has written .env and imported vcs: trust the drill's key.
        from vcs.licensing import tokens
        kid, public = open(os.environ["DRILL_TRUSTED"]).read().split()
        tokens.trust_for_tests(kid, bytes.fromhex(public))
        return ensure_license(key)
    setup.ensure_license = trusted_first
    setup.main()

    print("\\n== After setup, with the installed code")
    from vcs import config
    from vcs.db import pool
    from vcs.ops import backup, pgtools, selfverify
    assert config.DB_MODE == "native", config.DB_MODE
    print("  tools:", pgtools.describe(pgtools.server_major()))
    folder = os.path.join(os.getcwd(), "drill-backups")
    os.makedirs(folder, exist_ok=True)
    con = pool.connect()
    ok, message = backup.run_backup(con, dest_dir=folder, triggered_by="drill")
    print("  backup:", ok, message)
    assert ok, message
    result = selfverify.verify_latest_backup(con)
    print("  restore check:", result["result"], result["detail"])
    assert result["result"] == "pass", result
    dump = con.execute("SELECT filepath FROM backup_log WHERE status='success' ORDER BY id DESC LIMIT 1").fetchone()["filepath"]
    con.close()
    ok, message = backup.run_restore(pool.connect, dump, triggered_by="drill")
    print("  restore:", ok, message)
    assert ok, message
    print("DRILL OK")
''')


TOKEN = "ghp_DRILL_not_a_real_token_for_the_setup_code"
PING = "https://hc-ping.example/NATIVE-DRILL-PING"


def setup_code():
    """What the Vendor Console makes for a new clinic: an installation ID
    chosen now, its license, and the clinic's settings and secrets."""
    import uuid
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts" / "vendor"))
    import setup
    import vcs_vendor
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key((TEST_VENDOR / "private.pem").read_bytes(), password=None)
    install_id = str(uuid.uuid4())
    license_key = vcs_vendor.sign(key, vcs_vendor.license_payload(
        key, install_id, "Native Drill Clinic", datetime.now(timezone.utc) + timedelta(days=365)))
    return setup.make_setup_code(license_key, "JO", "orchid", github_token=TOKEN, heartbeat_url=PING), install_id


def main():
    role = "vcs_native_drill_" + secrets.token_hex(3)
    password = "Drill-" + secrets.token_hex(12)
    work = Path(tempfile.mkdtemp(prefix="vcs-native-drill-"))
    admin = psycopg.connect(SERVER, autocommit=True)
    try:
        admin.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' CREATEDB")
        admin.execute(f'CREATE DATABASE "{role}" OWNER {role}')
        install = work / "vetclinicsystem"
        install.mkdir()
        listed = subprocess.run(["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"], cwd=REPO,
                                check=True, capture_output=True).stdout.decode().split("\0")
        for name in filter(None, listed):
            source = REPO / name
            if source.is_file():
                (install / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, install / name)
        code, install_id = setup_code()
        shim = work / "bin"
        shim.mkdir()
        tools = subprocess.run([PYTHON, "-c", "import sys; sys.path.insert(0, '.'); from vcs.ops import pgtools; "
                                "print(pgtools.find('pg_dump').path)"], cwd=REPO, capture_output=True, text=True,
                               check=True).stdout.strip()
        for name in ("pg_dump", "pg_restore", "psql"):
            source = Path(tools).with_name(name)
            if source.exists():
                (shim / name).symlink_to(source)
        env = {"PATH": str(shim), "HOME": str(work), "LANG": "C.UTF-8",
               "DRILL_TRUSTED": str(TEST_VENDOR / "trusted.key")}
        url = f"postgresql://{role}:{password}@127.0.0.1:55492/{role}"
        print(f"== setup.py --db-mode native in {install} (PATH={shim}: {sorted(os.listdir(shim))})", flush=True)
        run = subprocess.run([PYTHON, "-c", CHILD, "--setup-code", code, "--db-mode", "native",
                              "--database-url", url, "--no-enable-updates"],
                             cwd=install, env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True)
        out = run.stdout + run.stderr
        print(textwrap.indent(out.replace(password, "[password]"), "  | "))
        env_file = (install / ".env").read_text() if (install / ".env").exists() else ""
        with psycopg.connect(url) as con:
            stored = dict(con.execute("SELECT key, value FROM settings WHERE key IN "
                                      "('theme_palette', 'clinic_name', 'heartbeat_url', 'money_setting')").fetchall())
        token_file = install / "github_token"
        checks = {
            "the setup code's installation ID is in .env": f"VETCLINICSYSTEM_INSTALL_ID={install_id}" in env_file,
            "the code's settings were applied": stored == {"theme_palette": "orchid", "clinic_name": "Native Drill Clinic",
                                                           "heartbeat_url": PING, "money_setting": "JO"},
            "the token is saved, owner-only": token_file.exists() and token_file.read_text().strip() == TOKEN
            and (token_file.stat().st_mode & 0o777) == 0o600,
            "no secret was printed": TOKEN not in out and PING not in out,
            "setup and the drill finished": run.returncode == 0 and "DRILL OK" in out,
            "no docker was needed": "docker" not in out.lower().replace("docker mode", ""),
            ".env says native": "VETCLINICSYSTEM_DB_MODE=native" in env_file,
            ".env has no container settings": "VETCLINICSYSTEM_PG_CONTAINER" not in env_file,
            "the server was checked": "PostgreSQL 16 (native mode)" in out,
            "the license was saved": "License saved" in out,
        }
        for what, ok in checks.items():
            print(f"  [{'ok' if ok else 'FAIL'}] {what}")
        return 0 if all(checks.values()) else 1
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{role}" WITH (FORCE)')
        # A restore check that failed half-way leaves its throwaway, owned by
        # this role -- only this role's databases are touched.
        for (name,) in admin.execute("SELECT datname FROM pg_database WHERE pg_get_userbyid(datdba) = %s",
                                     (role,)).fetchall():
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
