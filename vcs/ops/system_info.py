"""
What the app already knows about its own health, in one place, for
Developer -> System and the support bundle
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11.1).

Nothing here is new health infrastructure: it reads the self-check's last
result, the backup and restore logs, the restore verification, the schema's
migrations and the updater's log, and asks the database two questions.
Clinic data is never read, and file paths are reduced to their names.
"""
import json
import os
import platform
import time

from vcs import config
from vcs.paths import ROOT


def _name(path):
    return os.path.basename(path) if path else None


def _moment(value):
    return value.isoformat(timespec="seconds") if hasattr(value, "isoformat") else value


def _database(db):
    from vcs.ops import backup
    try:
        db.execute("SELECT 1").fetchone()
        version = db.execute("SHOW server_version").fetchone()["server_version"]
        reachable = True
    except Exception:
        db.rollback()
        version, reachable = None, False
    try:
        _user, _password, name, host, port = backup._pg_conn_parts()
    except Exception:
        host = port = name = None
    from vcs.ops import pgtools
    server = int(version.split(".")[0]) if version and version.split(".")[0].isdigit() else None
    return {"reachable": reachable, "server_version": version, "mode": config.DB_MODE,
            "host": host, "port": port, "name": name, "tools": pgtools.describe(server)}


def _self_check(db):
    from vcs.ops import selfcheck
    row = selfcheck.latest(db)
    if not row:
        return None
    try:
        findings = json.loads(row["findings"] or "[]")
    except (TypeError, ValueError):
        findings = []
    return {"status": row["status"], "ran_at": _moment(row["ran_at"]), "findings": findings,
            "disk_free_bytes": row.get("disk_free_bytes")}


def _backups(db):
    from vcs.ops import backup
    success = db.execute("SELECT * FROM backup_log WHERE status='success' ORDER BY id DESC LIMIT 1").fetchone()

    def row(r):
        return r and {"status": r["status"], "started_at": _moment(r["started_at"]),
                      "finished_at": _moment(r["finished_at"]), "file": _name(r["filepath"]),
                      "size_bytes": r["filesize_bytes"], "triggered_by": r["triggered_by"],
                      "failed": bool(r["error"])}
    return {"last": row(backup.last_backup(db)), "last_success": row(success),
            "recent_restores": [{"status": r["status"], "started_at": _moment(r["started_at"]),
                                 "file": _name(r["source_file"]), "triggered_by": r["triggered_by"]}
                                for r in backup.recent_restores(db, limit=5)]}


def _restore_verification(db):
    from vcs.domain import settings
    from vcs.ops import selfverify
    raw = settings.get_setting(db, selfverify.SETTING_KEY)
    try:
        stored = json.loads(raw) if raw else None
    except ValueError:
        return None
    return stored and {"at": stored.get("at"), "result": stored.get("result")}


def _schema(db):
    from vcs.db import migrate
    applied = db.execute("SELECT version, filename, applied_at FROM schema_migrations "
                         "ORDER BY version").fetchall()
    return {"applied": [{"version": r["version"], "file": r["filename"], "applied_at": _moment(r["applied_at"])}
                        for r in applied],
            "pending": [name for _, name in migrate.pending(db)]}


def uptime_seconds():
    return int(time.monotonic() - config.STARTED_MONOTONIC)


def gather(db):
    """Everything above, for a page or a bundle. Each part that cannot be
    read says so rather than stopping the rest."""
    from vcs.web.core import VERSION
    out = {"app": {"version": VERSION, "python": platform.python_version(),
                   "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
                   "uptime_seconds": uptime_seconds(), "install_id": config.INSTALL_ID,
                   "layout": "release" if config.DATA_DIR else "checkout"}}
    for key, part in (("database", _database), ("self_check", _self_check), ("backups", _backups),
                      ("restore_verification", _restore_verification), ("schema", _schema)):
        try:
            out[key] = part(db)
        except Exception as e:
            db.rollback()
            out[key] = {"unavailable": type(e).__name__}
    return out


def error_log_path():
    from vcs.errorlog import ERROR_LOG_PATH
    return ERROR_LOG_PATH


def updates_log_path():
    return os.path.join(config.DATA_DIR or ROOT, "logs", "updates.log")
