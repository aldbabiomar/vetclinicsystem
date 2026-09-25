"""
The schema: numbered migrations, applied once each (schema.py).

What a migration run must guarantee, and what these check:
  - a fresh database ends up exactly equal to tests/schema_snapshot.json;
  - running again applies nothing and changes nothing — the updater and a
    restore both run it against databases that are usually already current;
  - a failing migration rolls back entirely, is not recorded, and stops the
    run: nothing after it applies, and the process exits non-zero (the
    updater treats that as a failed update and rolls back);
  - a file the runner would skip or mis-split is an error, not a surprise.

The database tests need a throwaway Postgres and skip cleanly without one.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid

import pytest

import schema
from conftest import needs_db, TEST_DB_URL

REPO = pathlib.Path(__file__).parent.parent
SNAPSHOT = REPO / "tests" / "schema_snapshot.json"


@pytest.fixture
def scratch_db():
    """An empty database on the test server, dropped afterwards. CREATE
    DATABASE cannot run in a transaction, hence the autocommit connection."""
    import psycopg
    admin_url = re.sub(r"/[^/]+$", "/postgres", TEST_DB_URL)
    name = f"migtest_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_url, autocommit=True) as con:
        con.execute(f'CREATE DATABASE "{name}"')
    yield re.sub(r"/[^/]+$", f"/{name}", TEST_DB_URL)
    with psycopg.connect(admin_url, autocommit=True) as con:
        con.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _connect(url):
    from psycopg.rows import dict_row
    import db as dbmod
    return dbmod.Connection.connect(url, row_factory=dict_row, autocommit=False)


def _setup_apply_schema(url):
    """Exactly what updater._run_schema_sync() runs, in a subprocess, so a
    failure surfaces the way it would during a real update."""
    env = dict(os.environ, DATABASE_URL=url, SECRET_KEY="migration-test")
    return subprocess.run([sys.executable, "-c", "import setup; setup.apply_schema()"],
                          cwd=REPO, capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------
# The real migrations
# ---------------------------------------------------------------------------

@needs_db
def test_a_fresh_database_is_built_to_the_snapshot(scratch_db):
    """The one test that says what the schema IS. If it fails after you
    added a migration, run `scripts/schema_snapshot.py`, read the diff, and
    accept it with --write only if it is what you meant."""
    run = _setup_apply_schema(scratch_db)
    assert run.returncode == 0, run.stdout[-800:] + run.stderr[-800:]
    con = _connect(scratch_db)
    try:
        built = schema.snapshot(con)
        assert schema.pending(con) == []
        applied = [r["version"] for r in con.execute(
            "SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    finally:
        con.close()
    assert applied == [v for v, _, _ in schema.migration_files()]
    expected = json.loads(SNAPSHOT.read_text())
    diff = schema.snapshot_diff(expected, built)
    assert not diff, ("the migrations build a schema different from tests/schema_snapshot.json:\n  "
                      + "\n  ".join(diff[:20]))


@needs_db
def test_running_again_applies_nothing_and_changes_nothing(scratch_db):
    assert _setup_apply_schema(scratch_db).returncode == 0
    con = _connect(scratch_db)
    before = schema.snapshot(con)
    con.close()
    for _ in range(2):
        again = _setup_apply_schema(scratch_db)
        assert again.returncode == 0, again.stderr[-800:]
        assert "Schema is up to date." in again.stdout
    con = _connect(scratch_db)
    try:
        assert schema.snapshot(con) == before
    finally:
        con.close()


@needs_db
def test_the_seed_gives_the_system_role_every_permission(scratch_db):
    """Seeding runs after the migrations on every apply, so a permission
    added in a later release reaches an existing install's Admin role."""
    import auth
    assert _setup_apply_schema(scratch_db).returncode == 0
    con = _connect(scratch_db)
    try:
        held = {r["permission_id"] for r in con.execute(
            "SELECT rp.permission_id FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id WHERE r.name = 'Admin'").fetchall()}
    finally:
        con.close()
    assert held == {key for key, *_ in auth.PERMISSIONS}


# ---------------------------------------------------------------------------
# The runner, against migrations written for the test
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_migrations(tmp_path, monkeypatch):
    """Point schema.py at a directory of test migrations; the seed step is
    stubbed because these databases have none of the app's tables."""
    import auth
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", str(tmp_path))
    monkeypatch.setattr(auth, "seed_default_roles_and_permissions", lambda con: None)

    def write(name, sql):
        (tmp_path / name).write_text(sql)
    return write


def _tables(con):
    return {r["t"] for r in con.execute(
        "SELECT tablename AS t FROM pg_tables WHERE schemaname='public'").fetchall()}


@needs_db
def test_a_failing_migration_rolls_back_whole_and_stops_the_run(scratch_db, fake_migrations):
    fake_migrations("0001_first.sql", "CREATE TABLE first_t (id INT);")
    fake_migrations("0002_broken.sql", "CREATE TABLE half_t (id INT);\nALTER TABLE no_such_table ADD COLUMN x INT;")
    fake_migrations("0003_after.sql", "CREATE TABLE after_t (id INT);")
    con = _connect(scratch_db)
    try:
        with pytest.raises(schema.MigrationFailed) as info:
            schema.apply(con, log=lambda *a: None)
        con.rollback()
        assert info.value.version == "0002"
        assert "first_t" in _tables(con)
        assert "half_t" not in _tables(con), "the failing file's first statement was kept"
        assert "after_t" not in _tables(con), "a migration after the failure still ran"
        assert schema.applied_versions(con) == {"0001"}
    finally:
        con.close()


@needs_db
def test_control_after_the_cause_is_fixed_the_run_resumes(scratch_db, fake_migrations):
    fake_migrations("0001_first.sql", "CREATE TABLE first_t (id INT);")
    fake_migrations("0002_broken.sql", "ALTER TABLE no_such_table ADD COLUMN x INT;")
    con = _connect(scratch_db)
    try:
        with pytest.raises(schema.MigrationFailed):
            schema.apply(con, log=lambda *a: None)
        con.rollback()
        fake_migrations("0002_broken.sql", "CREATE TABLE fixed_t (id INT);")
        assert schema.apply(con, log=lambda *a: None) == ["0002_broken.sql"]
        assert {"first_t", "fixed_t"} <= _tables(con)
        assert schema.pending(con) == []
    finally:
        con.close()


def test_a_misnamed_migration_file_is_an_error_not_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", str(tmp_path))
    (tmp_path / "0001_ok.sql").write_text("")
    (tmp_path / "2_forgot_the_zeros.sql").write_text("")
    with pytest.raises(ValueError, match="2_forgot_the_zeros"):
        schema.migration_files()


def test_two_migrations_with_one_number_are_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", str(tmp_path))
    (tmp_path / "0001_a.sql").write_text("")
    (tmp_path / "0001_b.sql").write_text("")
    with pytest.raises(ValueError, match="share a number"):
        schema.migration_files()


# ---------------------------------------------------------------------------
# The files themselves (no database)
# ---------------------------------------------------------------------------

def _statements(sql_text):
    """Split the way db.run_script() does."""
    lines = []
    for line in sql_text.splitlines():
        i = line.find("--")
        lines.append(line[:i] if i != -1 else line)
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def test_control_the_splitter_check_catches_a_semicolon_in_a_string():
    stmts = _statements("INSERT INTO t VALUES ('a;b');")
    assert any(s.count("'") % 2 for s in stmts)


def test_every_migration_survives_run_scripts_splitting():
    """db.run_script() strips '--' comments and splits on ';' without
    knowing about quotes. A ';' or '--' inside a string literal, or a DO /
    function body, would be cut in half — and the half-statement error
    would read like a bug in the SQL, not in the splitter."""
    for version, name, path in schema.migration_files():
        text = pathlib.Path(path).read_text(encoding="utf-8")
        assert "$$" not in text, f"{name}: dollar-quoted bodies cannot be split safely"
        for stmt in _statements(text):
            assert stmt.count("'") % 2 == 0, f"{name}: unbalanced quote in: {stmt[:120]}"


def test_the_baseline_does_not_use_if_not_exists():
    """A migration runs once. IF NOT EXISTS would let the baseline 'succeed'
    against a database that already has a different table of the same name."""
    text = (REPO / "migrations" / "0001_baseline.sql").read_text(encoding="utf-8")
    code = "\n".join(l.split("--")[0] for l in text.splitlines())
    assert "IF NOT EXISTS" not in code.upper()


# ---------------------------------------------------------------------------
# The first administrator (setup.ensure_first_admin)
# ---------------------------------------------------------------------------

def _first_admin(url):
    env = dict(os.environ, DATABASE_URL=url, SECRET_KEY="migration-test")
    return subprocess.run([sys.executable, "-c", "import setup; setup.ensure_first_admin()"],
                          cwd=REPO, capture_output=True, text=True, env=env)


def _printed_password(out):
    m = re.search(r"password\s+(\S+)", out)
    return m.group(1) if m else None


@needs_db
def test_setup_creates_one_admin_with_a_printed_one_time_password(scratch_db):
    """GUARD. No well-known default password: the repository is public and
    the app listens on the clinic network."""
    import auth
    assert _setup_apply_schema(scratch_db).returncode == 0
    run = _first_admin(scratch_db)
    assert run.returncode == 0, run.stderr[-600:]
    password = _printed_password(run.stdout)
    assert password and password != "admin123" and len(password) >= 12
    con = _connect(scratch_db)
    try:
        users = con.execute("SELECT username, password_hash, must_change_password FROM users").fetchall()
    finally:
        con.close()
    assert [u["username"] for u in users] == ["admin"]
    assert users[0]["must_change_password"] is True
    assert auth.verify_password(users[0]["password_hash"], password)


@needs_db
def test_until_first_sign_in_setup_issues_a_new_password_then_never_again(scratch_db):
    import auth
    assert _setup_apply_schema(scratch_db).returncode == 0
    first = _printed_password(_first_admin(scratch_db).stdout)
    second = _printed_password(_first_admin(scratch_db).stdout)
    assert first and second and first != second
    con = _connect(scratch_db)
    try:
        row = con.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
        assert auth.verify_password(row["password_hash"], second), "the reprinted password does not work"
        # The admin signs in and chooses their own password.
        con.execute("UPDATE users SET must_change_password=false")
        con.commit()
        before = con.execute("SELECT password_hash FROM users").fetchone()["password_hash"]
    finally:
        con.close()
    third = _first_admin(scratch_db)
    assert _printed_password(third.stdout) is None, "setup reset a password someone had already chosen"
    con = _connect(scratch_db)
    try:
        assert con.execute("SELECT password_hash FROM users").fetchone()["password_hash"] == before
    finally:
        con.close()
