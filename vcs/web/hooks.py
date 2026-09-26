"""
What runs around every request: the network allowlist, the null-byte guard,
the restore gate, the money setting and time zone, the sign-in gate, the
security headers, and giving the connection back to the pool.

register(app) attaches them in the order they must run: the restore gate
before any hook that reads a table (audit S3), the money setting before any
route, the sign-in gate last.
"""
import ipaddress
import os
import traceback

from flask import current_app, g, redirect, request, send_from_directory, session, url_for
from flask_babel import gettext as _

from vcs import auth, clock, money
from vcs.db import pool as dbmod
from vcs.errorlog import error_logger
from vcs.ops import backup
from vcs.web.core import csp_nonce, flash, get_db


# Optional network allowlist: comma-separated CIDR blocks (e.g.
# "192.168.1.0/24,10.0.0.5/32"). Unset by default — no behavior change
# for a normal single-router clinic LAN. Lets an operator whose network
# is bigger/flatter than that (e.g. one shared VLAN with other, unrelated
# devices) restrict which source addresses can reach the app at all,
# independent of and in addition to login/permissions.
_ALLOWED_NETWORKS = []
for _cidr in os.environ.get("VETCLINICSYSTEM_ALLOWED_NETWORKS", "").split(","):
    _cidr = _cidr.strip()
    if _cidr:
        _ALLOWED_NETWORKS.append(ipaddress.ip_network(_cidr, strict=False))


def _enforce_network_allowlist():
    if not _ALLOWED_NETWORKS:
        return None
    try:
        client_ip = ipaddress.ip_address(request.remote_addr)
    except (ValueError, TypeError):
        return ("Forbidden", 403)
    if not any(client_ip in net for net in _ALLOWED_NETWORKS):
        return ("Forbidden", 403)
    return None


def _reject_null_bytes():
    """A literal null byte in a path segment (e.g. /owners/OW001%00) or a
    query value reaches psycopg as a bound parameter and Postgres rejects
    it outright — surfacing as a raw, unhandled exception rather than a
    clean 400, since nothing upstream of the database layer ever checked
    for it. Every text/varchar column this app queries is affected the
    same way, so this is checked once, globally, rather than patched at
    each individual route."""
    if ("\x00" in request.path
            or any("\x00" in v for v in request.args.values())
            or any("\x00" in v for v in request.form.values())):
        return ("Bad Request", 400)
    # JSON-body routes (bulk-edit endpoints etc.) bypass request.form
    # entirely, so a null byte there reached Postgres unfiltered — the
    # form-value check above never runs for them. See ERROR_500_AUDIT.md
    # E-14.
    if request.method == "POST" and request.is_json and _has_null(request.get_json(silent=True)):
        return ("Bad Request", 400)
    return None


# What a restore lets through (audit S3): static files, and the progress poll
# of the admin who started it -- answered from the session and the in-memory
# job, never from a table.
RESTORE_PASSTHROUGH = {"static", "main.favicon_ico", "settings.settings_job_status"}


def _hold_requests_during_restore():
    """While a backup is being restored, answer 503 with a page that reloads
    itself, and touch no table. pg_restore is dropping and reloading every
    one of them, and the app used to go on serving the other workstations
    from them (audit S3). Registered before every hook that reads the
    database."""
    if not backup.restore_in_progress.is_set():
        return None
    if request.endpoint in RESTORE_PASSTHROUGH:
        g.restore_passthrough = True
        return None
    resp = send_from_directory(current_app.static_folder, "restoring.html", mimetype="text/html", max_age=0)
    resp.status_code = 503
    resp.headers["Retry-After"] = "15"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _load_money_setting():
    """Make the clinic's money setting (IQ / JO) active for this request —
    money.fmt(), money.require() and every rounding rule read it from here.
    Read once per request, straight from the settings table, so a change in
    Settings applies on the very next request. A database that cannot be
    reached leaves it unset rather than failing here: the route (or the error
    page) is the right place for that error to surface."""
    if request.endpoint == "static" or g.get("restore_passthrough"):
        return None
    zone = None
    try:
        db = get_db()
        setting = money.load(db)
        zone = clock.load(db, setting)
        # The session's zone decides what `::date` means in SQL, and which
        # zone psycopg attaches to timestamps it reads. Applied first thing
        # and committed at once — nothing else is in this transaction yet —
        # so a rollback later in the request cannot undo it. Only when the
        # pooled connection is in a different zone, to save a round trip.
        if getattr(db.info.timezone, "key", None) != zone:
            clock.apply_to(db, zone)
            db.commit()
    except Exception:
        setting = None
    g.money_token = money.set_current(setting)
    g.clock_token = clock.set_current(zone)
    return None


def _unload_money_setting(exc):
    token = g.pop("money_token", None)
    if token is not None:
        money.reset_current(token)
    token = g.pop("clock_token", None)
    if token is not None:
        clock.reset_current(token)


def _has_null(value):
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_null(k) or _has_null(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_null(v) for v in value)
    return False


def add_security_headers(resp):
    """Baseline defense-in-depth headers. Doesn't replace anything (Jinja
    autoescaping + parameterized SQL are the real XSS/injection defenses),
    just closes off a few classes of browser-side attack cheaply."""
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    # Baseline CSP. script-src carries a per-request nonce rather than
    # 'unsafe-inline' — the sitewide template rewrite this used to say was
    # "not worth it" was done on 2026-09-10 (review finding S6): every on*=
    # attribute became a listener in static/behaviors.js, and every inline
    # <script> carries nonce="{{ csp_nonce }}". A nonce authorises <script>
    # blocks only, never inline handlers, and a browser that sees one ignores
    # 'unsafe-inline' altogether — which is why the attributes had to go first
    # rather than alongside.
    #
    # style-src still allows 'unsafe-inline' because of the inline style=
    # attributes that remain (review finding M8); tightening it is that
    # finding's job, not this one's.
    #
    # connect-src and frame-ancestors are spelled out rather than left to
    # inherit. The effective policy did not change: connect-src falls back to
    # default-src 'self', and X-Frame-Options: DENY above already blocks
    # framing. IQ has always listed both explicitly and JO has not — an
    # undocumented textual divergence with no behavioural difference, now
    # closed in the direction of saying what is meant.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        f"script-src 'self' 'nonce-{csp_nonce()}'; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return resp


def close_db(exc):
    db = g.pop("db", None)
    failed = g.pop("db_failed", False)
    if db is not None:
        try:
            try:
                if exc is None and not failed:
                    db.commit()
                else:
                    db.rollback()
            except Exception:
                # teardown_appcontext runs after the response has already
                # been built, outside the request-handling flow that
                # @app.errorhandler(Exception) covers — an exception raised
                # here (e.g. the connection died mid-request, so this
                # commit/rollback itself fails) would otherwise propagate
                # straight past Flask to Waitress, replacing the app's own
                # already-built response with a raw, unbranded fault page.
                # Logged and swallowed instead.
                error_logger.error("close_db(): commit/rollback failed\n" + traceback.format_exc())
        finally:
            # Always return the connection to the pool, even if the
            # commit/rollback above raised (e.g. the connection dropped
            # mid-request) — the pool discards a connection it can't
            # reuse and opens a replacement, so this can never leak a
            # connection reference the way an un-guarded db.close() call
            # that never ran would have.
            dbmod.putconn(db)


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
OPEN_ENDPOINTS = {"main.login", "static", "main.health", "main.logout", "main.favicon_ico"}


def _warn_if_submission_will_be_lost():
    """Say so when a signed-out request was carrying data.

    require_login() redirects to /login with ?next=<path>, and login() then
    redirects to that path with a GET -- so the body of a POST is gone. The
    person sees an empty form and no indication that anything was lost, which
    on a front desk means a whole visit or bill quietly typed twice. This does
    not preserve the submission (see FULL_APP_REVIEW U2 for the stash option);
    it makes the loss visible, which is the part that actually hurt.
    """
    if request.method != "GET":
        flash(_("You were signed out before that could be saved, so nothing was stored. "
              "Please sign in and enter it again."), "error")


def require_login():
    if request.endpoint in OPEN_ENDPOINTS or request.endpoint is None:
        return
    if g.get("restore_passthrough"):
        # During a restore: the session alone, no table (see above).
        return None if session.get("user_id") else ("", 401)
    if not session.get("user_id"):
        _warn_if_submission_will_be_lost()
        return redirect(url_for("main.login", next=request.path))
    db = get_db()
    user = auth.current_user(db)
    if not user:
        session.clear()
        return redirect(url_for("main.login"))
    # A password change/reset stamps users.password_changed_at with a new
    # value (see change_password()/admin_user_reset_password()) — a
    # session whose login predates that no longer matches what's stored
    # here, so a stolen cookie stops working the moment the password it
    # was issued under is replaced, instead of staying valid for the rest
    # of PERMANENT_SESSION_LIFETIME. An empty stored value (pre-migration
    # row, or an old session from before this check existed) is treated as
    # "nothing to compare against yet" rather than an automatic mismatch.
    if user["password_changed_at"] and not clock.same_instant(session.get("password_changed_at"),
                                                               user["password_changed_at"]):
        session.clear()
        flash(_("Your password was changed — please log in again."), "error")
        _warn_if_submission_will_be_lost()
        # Back to the page they were on after signing in again, as the
        # signed-out path above does (audit P14: the predecessor apps did
        # one or the other -- a reason, or the way back -- never both).
        return redirect(url_for("main.login", next=request.path))
    auth.refresh_session_permissions(db, user)
    if user["must_change_password"] and request.endpoint != "main.change_password":
        return redirect(url_for("main.change_password"))


def register(app):
    """Attach this module's hooks to the app, in the order they run."""
    app.before_request(_enforce_network_allowlist)
    app.before_request(_reject_null_bytes)
    app.before_request(_hold_requests_during_restore)
    app.before_request(_load_money_setting)
    app.teardown_request(_unload_money_setting)
    app.after_request(add_security_headers)
    app.teardown_appcontext(close_db)
    app.before_request(require_login)
