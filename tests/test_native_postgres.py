"""
Native PostgreSQL (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §12, §14.3).

"Native" means the app does not manage the server, so it is tested against
the throwaway vcs_test_* container's port as if it were native -- never the
other servers on this machine. With DB_MODE=native and a PATH holding the
PostgreSQL client tools and nothing else (no docker), setup's database steps,
a backup, a restore and the restore check each run, and a recorder around
subprocess proves no docker command was started.

These need PostgreSQL client tools, at least the server's version, on this
machine. Without them the tests SKIP, loudly, saying the native tier did not
run (CLAUDE.md §5.1).
"""
import os
import stat
import subprocess
import sys

import psycopg
import pytest

from conftest import needs_db
from vcs import config
from vcs.ops import pgtools

pytestmark = needs_db


@pytest.fixture
def client_tools():
    try:
        return os.path.dirname(pgtools.find("pg_dump", pgtools.server_major()).path)
    except pgtools.ToolError as e:
        pytest.skip(f"NATIVE-MODE TIER DID NOT RUN: no usable PostgreSQL client tools ({e})")


@pytest.fixture
def native(monkeypatch, tmp_path, client_tools):
    """Native mode, a PATH of the client tools alone, and every command run
    recorded."""
    shim = tmp_path / "shim"
    shim.mkdir()
    for name in ("pg_dump", "pg_restore", "psql"):
        if os.path.exists(os.path.join(client_tools, name)):
            os.symlink(os.path.join(client_tools, name), shim / name)
    monkeypatch.setenv("PATH", str(shim))
    monkeypatch.delenv(pgtools.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(config, "DB_MODE", "native")
    monkeypatch.setattr(pgtools, "search_dirs", lambda: [])          # PATH, and only PATH
    commands = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def run(cmd, *a, **k):
        commands.append(list(cmd))
        return real_run(cmd, *a, **k)

    def popen(cmd, *a, **k):
        commands.append(list(cmd))
        return real_popen(cmd, *a, **k)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    return commands


def _no_docker(commands):
    ran = [c for c in commands if os.path.basename(str(c[0])).startswith("docker")]
    assert not ran, f"native mode ran docker: {ran}"
    assert commands, "nothing was run -- the recorder saw no tool at all"


@pytest.fixture
def throwaway_database(db):
    """A database of its own on the test server, so a real restore replaces
    nothing any other test relies on."""
    name = "native_restore_" + os.urandom(4).hex()
    url = os.environ["DATABASE_URL"]
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    yield url.rsplit("/", 1)[0] + "/" + name
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.close()


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def test_setup_in_native_mode_writes_its_env_and_never_runs_docker(native, db, tmp_path, monkeypatch):
    import setup
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["setup.py", "--db-mode", "native", "--database-url", os.environ["DATABASE_URL"]])
    monkeypatch.setattr(setup, "port_in_use", lambda port: False)
    assert setup.db_mode() == "native"
    setup.ensure_env_file("native")
    env = (tmp_path / ".env").read_text()
    assert f"DATABASE_URL={os.environ['DATABASE_URL']}\n" in env and "VETCLINICSYSTEM_DB_MODE=native" in env
    assert "POSTGRES_PASSWORD=" not in env and "VETCLINICSYSTEM_PG_CONTAINER=" not in env
    assert "VETCLINICSYSTEM_PORT=" in env and "VETCLINICSYSTEM_INSTALL_ID=" in env
    setup.wait_for_database(timeout=15)
    assert setup.check_server("native") >= 16
    assert not [c for c in native if os.path.basename(str(c[0])).startswith("docker")], native


def test_setup_will_not_change_an_installs_mode(tmp_path, monkeypatch):
    import setup
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://x@127.0.0.1:5432/x\n")        # a docker install
    monkeypatch.setattr(sys, "argv", ["setup.py", "--db-mode", "native"])
    with pytest.raises(SystemExit):
        setup.db_mode()
    monkeypatch.setattr(sys, "argv", ["setup.py"])
    assert setup.db_mode() == "docker"                                          # control


def test_native_setup_needs_the_database_address(tmp_path, monkeypatch, capsys):
    import setup
    monkeypatch.setattr(setup, "_env_dir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["setup.py", "--db-mode", "native"])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        setup.ensure_env_file("native")
    assert "--database-url" in capsys.readouterr().out and not (tmp_path / ".env").exists()


def test_setup_refuses_a_server_older_than_16(monkeypatch, capsys):
    import setup

    class Old:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            class R:
                def fetchone(self_inner):
                    return ["150008"] if "server_version_num" in sql else [True]
            return R()
    monkeypatch.setattr(psycopg, "connect", Old)
    with pytest.raises(SystemExit):
        setup.check_server("docker")
    assert "version 15" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# backup, restore and the restore check
# ---------------------------------------------------------------------------

def test_backup_restore_and_the_restore_check_run_without_docker(native, db, tmp_path, monkeypatch,
                                                                  throwaway_database):
    """The whole round in native mode: a backup through the local pg_dump,
    the restore check through the local pg_restore, and a restore -- into a
    throwaway database, so nothing the suite relies on is replaced."""
    from vcs.db import pool
    from vcs.ops import backup, selfverify
    folder = tmp_path / "backups"
    folder.mkdir()
    before = db.execute("SELECT COALESCE(MAX(id), 0) AS n FROM backup_log").fetchone()["n"]
    db.commit()
    try:
        ok, message = backup.run_backup(db, dest_dir=str(folder), triggered_by="native-test")
        assert ok, message
        dump = db.execute("SELECT filepath FROM backup_log WHERE id > %s AND status='success' ORDER BY id DESC "
                          "LIMIT 1", (before,)).fetchone()["filepath"]
        result = selfverify.verify_latest_backup(db)
        assert result["result"] == "pass", result
        db.commit()

        monkeypatch.setattr(backup, "_RESTORE_MARKER_PATH", str(tmp_path / "last_restore.json"))
        monkeypatch.setenv("DATABASE_URL", throwaway_database)
        ok, message = backup.run_restore(pool.connect, dump, triggered_by="native-test")
        assert ok, message
        with psycopg.connect(throwaway_database) as restored:
            assert restored.execute("SELECT count(*) FROM users").fetchone()[0] >= 1
    finally:
        db.execute("DELETE FROM backup_log WHERE id > %s", (before,))
        db.commit()
    _no_docker(native)
    assert any(os.path.basename(str(c[0])) == "pg_dump" for c in native)
    assert any(os.path.basename(str(c[0])) == "pg_restore" for c in native)


# ---------------------------------------------------------------------------
# the finder
# ---------------------------------------------------------------------------

def test_an_empty_bin_dir_names_the_tool_and_not_docker(tmp_path, monkeypatch):
    monkeypatch.setenv(pgtools.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(config, "DB_MODE", "native")
    with pytest.raises(pgtools.ToolError) as e:
        pgtools.choose("pg_dump", 16)
    assert "pg_dump" in str(e.value) and str(tmp_path) in str(e.value)
    assert "docker" not in str(e.value).lower()


def test_a_bin_dir_is_the_only_place_looked(tmp_path, monkeypatch, client_tools):
    """GUARD: set, it is used alone -- a copy on PATH does not stand in."""
    monkeypatch.setenv(pgtools.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("PATH", client_tools)
    assert pgtools.candidates("pg_dump") == []


def _fake_tool(folder, name, version):
    path = folder / name
    path.write_text(f"#!/bin/sh\necho '{name} (PostgreSQL) {version}.4'\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_a_tool_older_than_the_server_is_refused(tmp_path, monkeypatch, db):
    server = pgtools.server_major(db)
    _fake_tool(tmp_path, "pg_dump", server - 1)
    monkeypatch.setenv(pgtools.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(config, "DB_MODE", "native")
    with pytest.raises(pgtools.ToolError) as e:
        pgtools.choose("pg_dump", server)
    assert f"version {server} or newer" in str(e.value) and f"version {server - 1}" in str(e.value)


def test_control_a_tool_at_the_servers_version_is_used(tmp_path, monkeypatch, db):
    server = pgtools.server_major(db)
    path = _fake_tool(tmp_path, "pg_dump", server)
    monkeypatch.setenv(pgtools.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(config, "DB_MODE", "native")
    tool = pgtools.choose("pg_dump", server)
    assert tool.kind == "local" and tool.path == str(path) and tool.version == server


def test_docker_mode_falls_back_to_the_container_but_native_never_does(tmp_path, monkeypatch):
    monkeypatch.setenv(pgtools.BIN_DIR_ENV, str(tmp_path))                  # nothing local
    monkeypatch.setattr(pgtools, "docker", lambda: "/usr/local/bin/docker")
    monkeypatch.setattr(config, "DB_MODE", "docker")
    assert pgtools.choose("pg_restore", 16).kind == "docker"
    monkeypatch.setattr(config, "DB_MODE", "native")
    with pytest.raises(pgtools.ToolError):
        pgtools.choose("pg_restore", 16)


# ---------------------------------------------------------------------------
# a role without CREATEDB
# ---------------------------------------------------------------------------

@pytest.fixture
def role_without_createdb(db):
    """A login role that can read the app's tables but not create a
    database, on the throwaway server."""
    name = "vcs_nocreate_" + os.urandom(3).hex()
    password = "No-Createdb-" + os.urandom(6).hex()
    admin = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    admin.execute(f"CREATE ROLE {name} LOGIN PASSWORD '{password}' NOCREATEDB")
    admin.execute(f"GRANT pg_read_all_data TO {name}")
    url = os.environ["DATABASE_URL"].replace("postgres:test@", f"{name}:{password}@", 1)
    assert name in url, "the test database URL is not the expected postgres:test one"
    yield url
    admin.execute(f"REASSIGN OWNED BY {name} TO CURRENT_USER")
    admin.execute(f"DROP OWNED BY {name}")
    admin.execute(f"DROP ROLE {name}")
    admin.close()


def test_the_self_check_says_the_role_cannot_create_databases(role_without_createdb, db):
    from psycopg.rows import dict_row
    from vcs.ops import selfcheck, selfverify
    with psycopg.connect(role_without_createdb, row_factory=dict_row) as con:
        assert selfverify.can_create_databases(con) is False
        codes = {f["code"] for f in selfcheck.run_self_check(con)["findings"]}
        assert "restore_no_privilege" in codes, codes
        assert "restore_unverified" not in codes, "the specific cause, not a generic failure"
    assert selfverify.can_create_databases(db) is True                           # control: the test role can
    assert "restore_no_privilege" not in {f["code"] for f in selfcheck.run_self_check(db)["findings"]}
