"""
The change and sign-in logs: a day's entries, and pruning them after
the retention period.
"""
from datetime import timedelta

from vcs import auth as authmod
from vcs import clock
from vcs.domain import dates, settings


# ---------------------------------------------------------------------------
# Audit / login log pages
# ---------------------------------------------------------------------------
def changes_on_date(db, day_str):
    start, end = dates.day_bounds(day_str)
    return db.execute("SELECT * FROM audit_log WHERE timestamp >= %s AND timestamp < %s ORDER BY timestamp DESC",
                      (start, end)).fetchall()


def logins_on_date(db, day_str):
    start, end = dates.day_bounds(day_str)
    rows = db.execute("SELECT * FROM login_log WHERE timestamp >= %s AND timestamp < %s ORDER BY timestamp DESC",
                      (start, end)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["device"] = authmod.describe_device(r["user_agent"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Log retention
# ---------------------------------------------------------------------------
# audit_log, login_log, backup_log and restore_log were never pruned. audit_log
# grows fastest -- log_change() writes one row per CHANGED FIELD on every
# update, plus one per create and delete -- and all four sit inside every
# pg_dump, so they inflate backup duration, backup size and restore time
# indefinitely. That interacts with two things already known: the shutdown
# backup that "may not finish" on a large database (COMPARISON.md §18) and the
# restore drill's runtime.
#
# self_check_log already had its own prune; these four are the ones that did
# not.
RETENTION_TABLES = [
    ("audit_log", "timestamp"),
    ("login_log", "timestamp"),
    ("backup_log", "started_at"),
    ("restore_log", "started_at"),
]


# Floor of 90 days is far above auth.LOCKOUT_LOOKBACK_HOURS, which reads
# login_log to decide whether an account is locked out -- pruning inside that
# window would silently disarm the lockout. test_log_retention.py asserts the
# relationship rather than trusting this comment.
LOG_RETENTION_MIN_DAYS = 90


LOG_RETENTION_MAX_DAYS = 3650


LOG_RETENTION_DEFAULT_DAYS = 730


PRUNE_BATCH = 5000


def prune_old_logs(db, now=None):
    """Delete log rows older than the configured window. Returns
    {table: rows_deleted}.

    Batched rather than one DELETE per table: a first run against years of
    history would otherwise hold a single long transaction over the tables the
    app writes to on every request. Each batch commits on its own, so an
    interrupted prune leaves a consistent database and simply resumes next time.
    """
    try:
        days = int(settings.get_setting(db, "log_retention_days", LOG_RETENTION_DEFAULT_DAYS)
                   or LOG_RETENTION_DEFAULT_DAYS)
    except (TypeError, ValueError):
        days = LOG_RETENTION_DEFAULT_DAYS
    days = max(LOG_RETENTION_MIN_DAYS, min(days, LOG_RETENTION_MAX_DAYS))
    cutoff = ((now or clock.now()) - timedelta(days=days)).isoformat(timespec="seconds")

    deleted = {}
    for table, column in RETENTION_TABLES:
        total = 0
        while True:
            cur = db.execute(
                f"DELETE FROM {table} WHERE ctid IN ("
                f"  SELECT ctid FROM {table} WHERE {column} < %s LIMIT {PRUNE_BATCH})",
                (cutoff,),
            )
            n = cur.rowcount or 0
            db.commit()
            total += n
            if n < PRUNE_BATCH:
                break
        deleted[table] = total
    return deleted
