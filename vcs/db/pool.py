"""
Postgres connection layer for VetClinicSystem.

This module exists so the rest of the codebase (the request layer, the domain modules,
auth.py, attachments.py, ...) can use a consistent, simple data-access style.
It provides:

  - psycopg (v3) connections, with psycopg's own '%s' placeholders (audit
    D7: a regex used to translate SQLite-style '?' to '%s', and it could not
    tell a placeholder from a '?' inside a string literal).
  - rows returned as plain dicts (via psycopg's dict_row): row["field"],
    row.get("field"), "field" in row.keys(), and Jinja's {{ row.field }}
    all work as expected.
  - IntegrityError re-exported for convenient importing at call sites.
"""
import os
import atexit
import threading

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

IntegrityError = psycopg.IntegrityError
# Re-exported so the error handlers can catch "the pool is exhausted"
# specifically (dbmod.PoolTimeout) and show a friendly "server is busy" message
# instead of a generic 500.
PoolTimeout = PoolTimeout
# Re-exported so the error handlers can catch "a numeric value didn't fit its
# column" specifically — an absurdly large id/quantity/etc. (a crafted URL, a
# huge ?page=, ...) raises this instead of a generic DB error; caught globally
# for a clean message instead of a raw 500 (see vcs/web/errors.py).
NumericValueOutOfRange = psycopg.errors.NumericValueOutOfRange

def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill it "
            "in, or run setup.py first."
        )
    return url


def connect():
    """
    Open a new, standalone connection outside the pool. Caller is
    responsible for closing it.

    Used only by code that doesn't run inside a normal web request and
    therefore has no g.db lifecycle to piggyback on: one-off maintenance
    scripts (setup.py, vcs/ops/reconcile_attachments.py) and the
    app's background scheduler (nightly backup). Those are low-frequency,
    long-or-uncertain-duration operations that don't belong sharing a
    small pool with request traffic, so they keep opening their own
    short-lived connections exactly as before.
    """
    conn = psycopg.connect(database_url(), row_factory=dict_row, autocommit=False)
    # In the clinic's time zone, and committed at once, so a later rollback
    # by the caller cannot undo it (clock.apply_to).
    from vcs import clock
    clock.apply_to(conn)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Connection pool — used for ordinary web request traffic (core.get_db() and
# hooks.close_db()). Previously every request opened a brand-new
# PostgreSQL connection with no limit; under a burst of LAN traffic
# (multiple clinic devices, each with Waitress's 8 worker threads) that
# could pile up faster than Postgres's own max_connections, degrading into
# connection-refused errors with no backpressure or bounded wait.
#
# A pool gives us three things a bare per-request connect() didn't:
#   - a hard cap on how many server-side connections this app can ever
#     hold open at once (DB_POOL_MAX_SIZE)
#   - reuse of already-open connections instead of a fresh TCP+auth
#     handshake on every single request
#   - a bounded wait (DB_POOL_TIMEOUT_SECONDS) with a clear error instead
#     of an unbounded hang when the pool is briefly exhausted
# ---------------------------------------------------------------------------
_pool = None
_pool_lock = threading.Lock()
_atexit_registered = False


def _pool_settings():
    """Read pool sizing from the environment with conservative defaults.
    A single-clinic LAN deployment rarely needs more than a handful of
    concurrent connections; these defaults comfortably cover Waitress's
    8 worker threads plus a few background-job connections without
    opening the door to unbounded growth."""
    min_size = int(os.environ.get("DB_POOL_MIN_SIZE", "2"))
    max_size = int(os.environ.get("DB_POOL_MAX_SIZE", "15"))
    timeout = float(os.environ.get("DB_POOL_TIMEOUT_SECONDS", "10"))
    max_lifetime = float(os.environ.get("DB_POOL_MAX_LIFETIME_SECONDS", "1800"))
    return min_size, max_size, timeout, max_lifetime


def init_pool():
    """Create the connection pool if it doesn't exist yet. Safe to call
    from multiple threads concurrently (e.g. two of Waitress's worker
    threads both handling the very first requests) — only one pool is
    ever created."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        min_size, max_size, timeout, max_lifetime = _pool_settings()
        _pool = ConnectionPool(
            conninfo=database_url(),
            kwargs={"row_factory": dict_row, "autocommit": False},
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_lifetime=max_lifetime,
            open=True,
        )
        # Hand the pool back before interpreter shutdown. Without this,
        # ConnectionPool.__del__ runs during finalisation and tries to join
        # its worker threads, which Python 3.14 refuses -- every test run
        # ended with a PythonFinalizationError traceback after the result
        # line, and any script that opens a pool would print the same. run.py
        # already calls close_pool() on its own shutdown paths; this covers
        # every other entry point (setup.py, the test runner)
        # without them each having to remember.
        global _atexit_registered
        if not _atexit_registered:
            atexit.register(close_pool)
            _atexit_registered = True
        return _pool


def get_pool():
    return _pool if _pool is not None else init_pool()


def getconn(timeout=None):
    """Borrow a connection from the pool. Raises db.PoolTimeout if none
    becomes free within the pool's configured timeout (or the timeout
    passed here) — callers should let this propagate to the normal error
    handler rather than hang."""
    return get_pool().getconn(timeout=timeout)


def putconn(conn):
    """Return a connection to the pool. The pool itself rolls back any
    transaction still open on the connection before reusing it, so a
    caller that forgot to commit/rollback can't leak state into the next
    request that borrows this connection — but every call site in this
    app should already have committed or rolled back explicitly before
    reaching this (see close_db() in vcs/web/hooks.py)."""
    get_pool().putconn(conn)


def close_pool():
    """Closes the pool and every connection in it. Called on graceful
    shutdown; safe to call even if the pool was never created."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


_ID_TABLES = frozenset({"owners", "patients", "visits", "inventory_list", "price_list",
                        "distributors", "distributor_bills"})


def next_row_id(db, table):
    """The next id from `table`'s own identity sequence, for a caller that
    needs the id before its INSERT (a flash message, log_change(), an
    attachment folder). Atomic like any nextval(); a rolled-back insert
    leaves a gap, which is harmless — ids are for joining, and staff see
    them as codes (codes.code), not as a count."""
    if table not in _ID_TABLES:
        raise ValueError(f"no generated id for {table!r}")
    return db.execute(f"SELECT nextval(pg_get_serial_sequence('{table}', 'id')) AS n").fetchone()["n"]


def run_script(con, sql_text):
    """
    Executes a multi-statement .sql file — psycopg executes one command at a
    time, so this splits on ';' — but only after stripping '--' line
    comments first, since a semicolon inside a comment (e.g. "for a date;
    a session becomes...") would otherwise be mistaken for a statement
    terminator and split a comment in half.
    """
    lines = []
    for line in sql_text.splitlines():
        idx = line.find("--")
        lines.append(line[:idx] if idx != -1 else line)
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
