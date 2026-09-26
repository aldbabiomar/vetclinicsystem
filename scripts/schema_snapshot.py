#!/usr/bin/env python3
"""
Build the schema from migrations/ in a scratch database and compare it with
tests/schema_snapshot.json — or, with --write, replace that file.

    TEST_DATABASE_URL=postgresql://postgres:test@localhost:55492/vetclinicsystem \\
        /tmp/vcs_test_venv_jo/bin/python scripts/schema_snapshot.py [--write]

Uses the SERVER named by TEST_DATABASE_URL (a throwaway test container, never
a real install) to create and drop a scratch database; the database named in
the URL is not touched.

Writing the snapshot is a deliberate act: run it after adding a migration,
read the diff it prints, and commit the new file with the migration. The test
that compares against it (tests/test_migrations.py) is what notices a
migration that does something other than what its author meant.
"""
import json
import os
import re
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SNAPSHOT = os.path.join(ROOT, "tests", "schema_snapshot.json")


def build_snapshot(server_url):
    import psycopg
    from psycopg.rows import dict_row
    from vcs.db import migrate as schema
    admin_url = re.sub(r"/[^/]+$", "/postgres", server_url)
    name = f"snapshot_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_url, autocommit=True) as con:
        con.execute(f'CREATE DATABASE "{name}"')
    try:
        con = psycopg.connect(re.sub(r"/[^/]+$", f"/{name}", server_url),
                              row_factory=dict_row, autocommit=False)
        try:
            schema.apply(con, log=lambda *a: None)
            return schema.snapshot(con)
        finally:
            con.close()
    finally:
        with psycopg.connect(admin_url, autocommit=True) as con:
            con.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def main():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        sys.exit("TEST_DATABASE_URL is not set — point it at a throwaway test server.")
    from vcs.db import migrate as schema
    built = build_snapshot(url)
    current = json.load(open(SNAPSHOT)) if os.path.exists(SNAPSHOT) else {}
    diff = schema.snapshot_diff(current, built)
    for line in diff:
        print(" ", line)
    if "--write" in sys.argv:
        with open(SNAPSHOT, "w") as f:
            json.dump(built, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"wrote {os.path.relpath(SNAPSHOT, ROOT)} ({len(diff)} change(s))")
    else:
        print("matches" if not diff else f"{len(diff)} difference(s) — rerun with --write to accept")
        sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
