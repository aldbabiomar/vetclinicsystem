#!/usr/bin/env python3
"""
A fresh install in native PostgreSQL mode, for real (licensing plan §16,
phase 8; docs/NATIVE_POSTGRESQL.md):

    /tmp/vcs_test_venv_jo/bin/python scripts/simulation/native_install.py

1. On the throwaway test server (vcs_test_jo, port 55492 -- never another
   server on this machine) it makes the role and database the guide
   describes: a login role that owns its database and has CREATEDB.
2. It exports HEAD into a temporary folder -- a clean copy, as a clinic would
   receive it -- and runs that copy's setup.py with --db-mode native and
   --no-enable-updates, from an environment whose PATH holds the PostgreSQL
   client tools and nothing else. There is no docker to run: a Docker call
   would stop setup with "No such file or directory".
3. With the installed code, in that same environment: a backup, the restore
   check, and a restore.
4. It removes the role, the database and the folder.

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
    from datetime import datetime, timedelta, timezone
    sys.path.insert(0, os.getcwd())
    import setup
    args = sys.argv[1:]
    sys.argv = ["setup.py", *args]
    mode = setup.db_mode()
    setup.ensure_env_file(mode)
    install_id = setup.ensure_install_id()
    setup.load_dotenv_now()
    from vcs.licensing import tokens                    # the first vcs import: config reads the new .env
    kid, public = open(os.environ["DRILL_TRUSTED"]).read().split()
    tokens.trust_for_tests(kid, bytes.fromhex(public))
    sys.path.insert(0, os.path.join(os.getcwd(), "scripts", "vendor"))
    import vcs_vendor
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(open(os.environ["DRILL_PRIVATE"], "rb").read(), password=None)
    license_key = vcs_vendor.sign(key, vcs_vendor.license_payload(
        key, install_id, "Native Drill Clinic", datetime.now(timezone.utc) + timedelta(days=365)))
    sys.argv += ["--license-key", license_key]
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
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=REPO, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(install)], input=archive, check=True)
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
               "DRILL_TRUSTED": str(TEST_VENDOR / "trusted.key"), "DRILL_PRIVATE": str(TEST_VENDOR / "private.pem")}
        url = f"postgresql://{role}:{password}@127.0.0.1:55492/{role}"
        print(f"== setup.py --db-mode native in {install} (PATH={shim}: {sorted(os.listdir(shim))})", flush=True)
        run = subprocess.run([PYTHON, "-c", CHILD, "--db-mode", "native", "--database-url", url,
                              "--money-setting", "JO", "--no-enable-updates"],
                             cwd=install, env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True)
        out = run.stdout + run.stderr
        print(textwrap.indent(out.replace(password, "[password]"), "  | "))
        env_file = (install / ".env").read_text() if (install / ".env").exists() else ""
        checks = {
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
