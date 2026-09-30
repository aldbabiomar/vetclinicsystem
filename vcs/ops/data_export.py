"""
The full data export: every table as CSV, every attachment, the schema, and
a manifest (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11.4, owner decision
L-5). It is the clinic's own data in a form any spreadsheet opens -- also
after its license has run out, which is why it is allowed in read-only mode
(A7). A backup (.dump) remains the exact copy to restore from; this is for
reading, and for taking elsewhere.

Tables are discovered from the live database, not listed here, so a table
added later is exported without anyone remembering to. What is left out is
recorded below with its reason, and a test fails for any table that is
neither exported nor excluded.
"""
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from base64 import b64encode
from datetime import date, datetime, time
from decimal import Decimal

from psycopg import sql
from psycopg.rows import tuple_row

from vcs import clock, config, money
from vcs.domain import settings
from vcs.messages import N_
from vcs.paths import ROOT

# Whole tables left out, and why. None: everything the clinic recorded is
# the clinic's to take.
EXCLUDED_TABLES = {}
# Columns left out of an exported table, and why.
EXCLUDED_COLUMNS = {
    ("users", "password_hash"): N_("a credential: with the hash, a password can be guessed offline"),
}
# Rows left out of an exported table: (column, values, reason).
EXCLUDED_ROWS = {
    "settings": ("key", sorted(settings.SECRET_KEYS),
                 N_("a credential: the monitoring ping address can be used to silence the alert")),
}

KEEP = 3                                   # older exports are removed when a new one is made
NAME = re.compile(r"^vcs-export-\d{8}-\d{6}\.zip$")

STEPS = (N_("Reading the tables"), N_("Adding the attachments"), N_("Writing the manifest"))

README = """\
# VetClinicSystem data export

Made {made} for installation `{install_id}`, version {version}, money setting {money}.

## What is here

- `data/<table>.csv` — every table in the database, one file each: UTF-8 with a
  byte-order mark (so Excel shows Arabic correctly), a header row, dates and times
  in ISO 8601 (`2026-09-30T14:05:00+03:00`), and numbers exactly as stored, not
  rounded or formatted as money. An empty cell is an empty value (NULL).
- `attachments/` — every uploaded file, at the path the `attachments` table
  records in `relative_path`.
- `schema.sql` — the database's structure: the migrations, in the order applied.
- `manifest.json` — per table, its row count and the SHA-256 of its file, and the
  list of what was left out.

## How the tables relate

Every table has an `id`. A column named `<thing>_id` holds the `id` of a row in
that thing's table: `patients.owner_id` is an `owners.id`, `visits.patient_id` a
`patients.id`, `billing.visit_id` a `visits.id`, and so on. `schema.sql` states
each of these as a `REFERENCES` clause.

## What is left out, and why

{exclusions}

The license key and the update access token are not in the database, so they
are never in an export.

## This is not a backup

A backup (`.dump`, made by Back Up Now or every night) is the exact copy to
restore from. This export is for reading the records and for moving them
elsewhere.
"""


def export_dir():
    return os.path.join(config.DATA_DIR or ROOT, "exports")


def live_tables(db):
    return [r["table_name"] for r in db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name").fetchall()]


def _columns(db, table):
    return [r["column_name"] for r in db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position", (table,)).fetchall()]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")          # every stored digit, never an exponent
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (bytes, memoryview)):
        return b64encode(bytes(value)).decode("ascii")
    return str(value)


def _write_table(db, table, out):
    """Writes one table's CSV into `out` (a binary file) and returns its row
    count. A server-side cursor, so a long table is never all in memory."""
    columns = [c for c in _columns(db, table) if (table, c) not in EXCLUDED_COLUMNS]
    query = sql.SQL("SELECT {} FROM {}").format(sql.SQL(", ").join(map(sql.Identifier, columns)),
                                               sql.Identifier(table))
    params = ()
    if table in EXCLUDED_ROWS:
        column, values, _reason = EXCLUDED_ROWS[table]
        query += sql.SQL(" WHERE {} <> ALL(%s)").format(sql.Identifier(column))
        params = (values,)
    query += sql.SQL(" ORDER BY 1")
    text = io.TextIOWrapper(out, encoding="utf-8-sig", newline="")
    writer = csv.writer(text)
    writer.writerow(columns)
    count = 0
    with db.cursor(name=f"export_{table}", row_factory=tuple_row) as cur:
        cur.itersize = 2000
        cur.execute(query, params)
        for row in cur:
            writer.writerow([_cell(v) for v in row])
            count += 1
    text.flush()
    text.detach()
    return count


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_attachments(db, z):
    """Each file the attachments table records, at its recorded path; the
    ones not on disk are listed, not invented."""
    from vcs.domain.attachments import UPLOAD_ROOT
    root = os.path.realpath(UPLOAD_ROOT)
    added, missing = 0, []
    for row in db.execute("SELECT id, relative_path FROM attachments ORDER BY id").fetchall():
        path = os.path.realpath(os.path.join(root, row["relative_path"]))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            missing.append({"id": row["id"], "relative_path": row["relative_path"]})
            continue
        z.write(path, "attachments/" + os.path.relpath(path, root).replace(os.sep, "/"))
        added += 1
    return added, missing


def _schema_sql():
    from vcs.db import migrate
    parts = []
    for _version, name, path in migrate.migration_files():
        with open(path, encoding="utf-8") as f:
            parts.append(f"-- {name}\n{f.read().rstrip()}\n")
    return "\n".join(parts)


def exclusions():
    """What is left out, as data: for the manifest, the README and the page."""
    out = [{"table": t, "reason": r} for t, r in EXCLUDED_TABLES.items()]
    out += [{"table": t, "column": c, "reason": r} for (t, c), r in EXCLUDED_COLUMNS.items()]
    out += [{"table": t, "rows_where": f"{c} in {v}", "reason": r} for t, (c, v, r) in EXCLUDED_ROWS.items()]
    return out


def run(db, on_progress=None):
    """Makes one export in export_dir() and returns its file name. `db` is a
    connection of its own: everything is read in one read-only snapshot, so
    the tables agree with each other however long the export takes."""
    from vcs.web.core import VERSION
    progress = on_progress or (lambda *a, **k: None)
    db.rollback()
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    setting = money.load(db)
    made = clock.now()
    folder = export_dir()
    os.makedirs(folder, exist_ok=True)
    name = f"vcs-export-{made.strftime('%Y%m%d-%H%M%S')}.zip"
    tables = [t for t in live_tables(db) if t not in EXCLUDED_TABLES]
    manifest_tables = {}
    fd, partial = tempfile.mkstemp(prefix=".export-", suffix=".zip", dir=folder)
    os.close(fd)
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z, \
                tempfile.TemporaryDirectory(dir=folder) as scratch:
            for i, table in enumerate(tables):
                progress(0, fraction=i / max(len(tables), 1) * 0.8)
                path = os.path.join(scratch, f"{table}.csv")
                with open(path, "wb") as out:
                    rows = _write_table(db, table, out)
                manifest_tables[table] = {"rows": rows, "file": f"data/{table}.csv", "sha256": _sha256(path)}
                z.write(path, f"data/{table}.csv")
                os.remove(path)
            progress(1, fraction=0.85)
            attachments_added, attachments_missing = _add_attachments(db, z)
            progress(2, fraction=0.95)
            z.writestr("schema.sql", _schema_sql())
            manifest = {
                "app_version": VERSION, "exported_at": made.isoformat(timespec="seconds"),
                "install_id": config.INSTALL_ID, "money_setting": setting.code if setting else None,
                "tables": manifest_tables,
                "attachments": {"files": attachments_added, "missing": attachments_missing},
                "excluded": exclusions(),
            }
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            z.writestr("README.md", README.format(
                made=manifest["exported_at"], install_id=config.INSTALL_ID or "-", version=VERSION,
                money=manifest["money_setting"] or "not chosen",
                exclusions="\n".join(f"- `{e['table']}`" + (f" column `{e['column']}`" if "column" in e else "")
                                     + (f" rows where {e['rows_where']}" if "rows_where" in e else "")
                                     + f": {e['reason']}." for e in exclusions())))
        os.replace(partial, os.path.join(folder, name))
    finally:
        if os.path.exists(partial):
            os.remove(partial)
        db.rollback()
    _prune(folder)
    return name


def _prune(folder):
    for old in list_exports()[KEEP:]:
        try:
            os.remove(os.path.join(folder, old["name"]))
        except OSError:
            pass


def list_exports():
    """The finished exports, newest first: {"name", "size_bytes", "made"}."""
    folder = export_dir()
    try:
        names = [n for n in os.listdir(folder) if NAME.match(n)]
    except OSError:
        return []
    out = [{"name": n, "size_bytes": os.path.getsize(os.path.join(folder, n))} for n in names]
    return sorted(out, key=lambda e: e["name"], reverse=True)


def path_of(name):
    """The file for a download, or None: only a name this module makes, in
    its own folder -- never a path the request supplies."""
    if not NAME.match(name or ""):
        return None
    path = os.path.join(export_dir(), name)
    return path if os.path.isfile(path) else None
