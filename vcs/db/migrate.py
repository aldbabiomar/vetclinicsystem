"""
The database schema: numbered migrations, each applied exactly once.

    migrations/0001_baseline.sql     the whole schema of the first release
    migrations/0002_<what>.sql       every later change, one file each

`apply(con)` runs every file not yet recorded in `schema_migrations`, in
order, each in its own transaction, then runs the seed step (roles and
permissions, which is idempotent and runs every time). A migration that fails
rolls back on its own and raises `MigrationFailed` — the install or update
stops there, loudly. Nothing is skipped and carried on from: the predecessor
apps re-ran ~100 "idempotent" statements on every launch, recorded the ones
that failed in a settings row and started anyway, and one index over a
migration-added column once left 16 of 38 releases unable to update
(docs/archive/COMPARISON.md §53).

Rules for a migration file, enforced by tests/test_migrations.py:
  - never edit a file once a release containing it is published (installs
    have already recorded it as applied); before 1.0.0 the baseline may be
    edited in place, because no install exists yet;
  - one file, one change; it runs inside a transaction, so no
    CREATE INDEX CONCURRENTLY and no VACUUM;
  - db.run_script() splits the file on ';' after stripping '--' comments, so
    neither may appear inside a string literal, and there are no DO blocks
    or function bodies;
  - it must leave the database equal to tests/schema_snapshot.json once all
    files have run — regenerate that file deliberately with
    `python scripts/schema_snapshot.py --write`, and read the diff.
"""
import os
import re

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
_FILE_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

# pg_advisory_xact_lock key: two processes applying the schema at once (an
# update racing a manual setup.py run) must not both apply the same file.
_LOCK_KEY = 7_302_025


class MigrationFailed(Exception):
    def __init__(self, version, filename, error):
        super().__init__(f"migration {filename} failed: {error}")
        self.version, self.filename, self.error = version, filename, error


def migration_files():
    """[(version, filename, path)] in order. A file in migrations/ that does
    not match NNNN_name.sql is an error, not something to skip: a typo in a
    name would otherwise silently never run."""
    out = []
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if name.startswith(".") or name == "README.md":
            continue
        m = _FILE_RE.match(name)
        if not m:
            raise ValueError(f"migrations/{name}: not a NNNN_name.sql file")
        out.append((m.group(1), name, os.path.join(MIGRATIONS_DIR, name)))
    versions = [v for v, _, _ in out]
    if len(set(versions)) != len(versions):
        raise ValueError(f"two migrations share a number: {versions}")
    return out


def _ensure_table(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version TEXT PRIMARY KEY,"
        "  filename TEXT NOT NULL,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def applied_versions(con):
    """Versions recorded as applied; empty for a database that has never been
    migrated (including one with no schema_migrations table at all)."""
    exists = con.execute("SELECT to_regclass('public.schema_migrations') AS t").fetchone()["t"]
    if not exists:
        return set()
    return {r["version"] for r in con.execute("SELECT version FROM schema_migrations").fetchall()}


def pending(con):
    """Migration files this database has not applied — non-empty means the
    code is newer than the schema (a release started without its schema
    step)."""
    done = applied_versions(con)
    return [(v, name) for v, name, _ in migration_files() if v not in done]


def apply(con, log=print):
    """Bring the database up to date, then seed. Returns the filenames
    applied. Raises MigrationFailed on the first failing file; the files
    before it stay applied (each committed on its own)."""
    from vcs.db import pool as dbmod
    from vcs import auth
    with con.transaction():
        con.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        _ensure_table(con)
    applied = []
    for version, name, path in migration_files():
        with con.transaction():
            con.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            if con.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,)).fetchone():
                continue
            with open(path, encoding="utf-8") as f:
                sql_text = f.read()
            try:
                with con.transaction():
                    dbmod.run_script(con, sql_text)
            except Exception as e:
                raise MigrationFailed(version, name, e) from e
            con.execute("INSERT INTO schema_migrations (version, filename) VALUES (%s, %s)",
                        (version, name))
        applied.append(name)
        log(f"  applied {name}")
    con.commit()
    auth.seed_default_roles_and_permissions(con)
    con.commit()
    return applied


# ---------------------------------------------------------------------------
# Snapshot — the schema as data, for comparing two databases or pinning one
# ---------------------------------------------------------------------------

def snapshot(con):
    """Every table, column, constraint and index in the public schema, as a
    plain dict that compares equal for two databases with the same schema.
    Constraint and index definitions come from Postgres itself
    (pg_get_constraintdef / pg_get_indexdef), so a difference in how a file
    spells something that means the same thing does not show up — and a
    difference in what it means does."""
    tables = {}
    for r in con.execute(
            "SELECT c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' ORDER BY 1").fetchall():
        tables[r["t"]] = {"columns": {}, "constraints": {}, "indexes": {}}
    for r in con.execute(
            "SELECT table_name AS t, column_name AS c, data_type, character_maximum_length AS len, "
            "numeric_precision AS p, numeric_scale AS s, is_nullable, column_default, is_identity, "
            "identity_generation "
            "FROM information_schema.columns WHERE table_schema='public' ORDER BY 1, 2").fetchall():
        if r["t"] not in tables:
            continue
        typ = r["data_type"]
        if typ == "numeric" and r["p"] is not None:
            typ = f"numeric({r['p']},{r['s']})"
        tables[r["t"]]["columns"][r["c"]] = {
            "type": typ,
            "null": r["is_nullable"] == "YES",
            "default": r["column_default"],
            "identity": r["identity_generation"] if r["is_identity"] == "YES" else None,
        }
    for r in con.execute(
            "SELECT cl.relname AS t, co.conname AS name, pg_get_constraintdef(co.oid) AS def "
            "FROM pg_constraint co JOIN pg_class cl ON cl.oid=co.conrelid "
            "JOIN pg_namespace n ON n.oid=cl.relnamespace WHERE n.nspname='public' "
            "ORDER BY 1, 2").fetchall():
        if r["t"] in tables:
            tables[r["t"]]["constraints"][r["name"]] = r["def"]
    for r in con.execute(
            "SELECT tablename AS t, indexname AS name, indexdef AS def FROM pg_indexes "
            "WHERE schemaname='public' ORDER BY 1, 2").fetchall():
        if r["t"] in tables:
            tables[r["t"]]["indexes"][r["name"]] = r["def"]
    return tables


def snapshot_diff(a, b):
    """Human-readable differences between two snapshots (a = expected)."""
    out = []
    for t in sorted(set(a) | set(b)):
        if t not in b:
            out.append(f"table {t}: missing")
            continue
        if t not in a:
            out.append(f"table {t}: unexpected")
            continue
        for part in ("columns", "constraints", "indexes"):
            ea, eb = a[t][part], b[t][part]
            for k in sorted(set(ea) | set(eb)):
                if ea.get(k) != eb.get(k):
                    out.append(f"{t}.{part}.{k}: expected {ea.get(k)!r}, got {eb.get(k)!r}")
    return out
