"""
The pages outside any area: signing in and out, changing one's password, the
Dashboard, /health (the updater's probe), /favicon.ico, and the poll behind
the report pages' loading shells.
"""
import json
import threading
import time
import traceback
import uuid

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_babel import gettext as _

from vcs import auth, clock, jobs
from vcs.domain import alerts, settings
from vcs.errorlog import error_logger
from vcs.web.core import (PER_PAGE, VERSION, cached_dashboard_snapshot, flash, get_db, get_page, is_safe_local_path,
                          lan_address, page_count, page_offset, shown)

bp = Blueprint("main", __name__)


# Simple in-memory per-IP rate limit on login attempts — independent of
# (and in addition to) auth.py's existing per-USERNAME lockout, which
# doesn't slow down someone trying many different usernames from one
# source. No new dependency: a small sliding window keyed by client IP,
# reset lazily. This is intentionally generous (20 requests / 5 minutes)
# since a busy front desk can generate real login traffic from behind a
# single router's IP; it's meant to blunt automated spraying, not to
# police normal multi-person use of one shared network address.
_LOGIN_ATTEMPTS_BY_IP = {}
_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300
_LOGIN_RATE_LIMIT_MAX = 20
# Waitress serves from 8 threads, and they all update the dict above; the
# cleanup loop could meet a key another thread had just deleted (KeyError,
# a 500 on the login page) and two sign-ins could each read the list before
# either wrote it back, losing one from the count (audit B20).
_LOGIN_RATE_LIMIT_LOCK = threading.Lock()


def _login_rate_limit_check(ip):
    now = time.monotonic()
    window_start = now - _LOGIN_RATE_LIMIT_WINDOW_SECONDS
    with _LOGIN_RATE_LIMIT_LOCK:
        attempts = [t for t in _LOGIN_ATTEMPTS_BY_IP.get(ip, []) if t > window_start]
        attempts.append(now)
        _LOGIN_ATTEMPTS_BY_IP[ip] = attempts
        # Opportunistic cleanup so this dict doesn't grow unbounded over a
        # long-running process — cheap, and only runs on the (low-traffic)
        # login route.
        if len(_LOGIN_ATTEMPTS_BY_IP) > 1000:
            for k in list(_LOGIN_ATTEMPTS_BY_IP.keys()):
                if not [t for t in _LOGIN_ATTEMPTS_BY_IP[k] if t > window_start]:
                    del _LOGIN_ATTEMPTS_BY_IP[k]
        return len(attempts) <= _LOGIN_RATE_LIMIT_MAX


@bp.route("/jobs/status")
def jobs_status():
    """
    Polling endpoint for the report-page loading shells (Insights,
    Retention, Consignment Overview). Gated only by being logged in (like
    every other route, via require_login()) rather than by the specific
    report's own permission — job_id is an unguessable random token (see
    jobs.py's uuid4), so being able to supply one already implies having
    just been handed it by the page that started that job. Separate from
    /settings/job-status, which is permission-gated and has its own
    result-shaping for the Updates section — not reused here to avoid
    coupling two unrelated consumers.
    """
    job_id = request.args.get("job_id", "")
    state = jobs.status(job_id)
    if state is None:
        return jsonify({"status": "not_found"}), 404
    payload = {
        "status": state["status"],
        "steps": [shown(step) for step in state["steps"]],
        "current": state["current"],
        "fraction": state.get("fraction"),
        "started_at": state["started_at"],
    }
    if state["status"] == "error":
        payload["message"] = state.get("error")
    return jsonify(payload)


@bp.route("/favicon.ico")
def favicon_ico():
    # Safari (and some other browsers) probe this exact root-level path
    # directly, independent of the <link rel="icon"> tag in base.html --
    # without this route there is nothing at /favicon.ico at all (only at
    # /static/favicon.svg), so the probe 404s and Safari can fall back to
    # whatever it last had cached for this origin.
    #
    # Unlike IQ, this app ships a single SVG icon and no .ico, and has no
    # palette to choose between -- so this serves that SVG with its real
    # mimetype rather than pretending to be an ICO. Every browser that
    # probes this path also understands SVG icons, and an SVG served
    # honestly beats a 404.
    return send_from_directory(current_app.static_folder, "favicon.svg", mimetype="image/svg+xml")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        if not _login_rate_limit_check(request.remote_addr):
            flash(_("Too many login attempts from this network. Please wait a few minutes and try again."), "error")
            return render_template("login.html")
        db = get_db()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        locked, minutes_left, unlock_at = auth.login_lock_status(db, username)
        if locked:
            flash(_("Too many failed attempts for that account. Try again in about %(minutes_left)s minute(s) (around %(strftime)s).", minutes_left=minutes_left, strftime=unlock_at.strftime('%H:%M')), "error")
            return render_template("login.html", lockout_unlock_at=unlock_at.isoformat(timespec="seconds"))
        row = db.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()
        # verify_password() runs unconditionally, even for a username that
        # doesn't exist — against a dummy hash in that case (see
        # auth._DUMMY_PASSWORD_HASH's own comment) — so a nonexistent/
        # disabled username doesn't respond measurably faster than a real
        # one and leak which usernames exist via response timing.
        password_ok = auth.verify_password(row["password_hash"] if row else auth._DUMMY_PASSWORD_HASH, password)
        ok = row and row["active"] and password_ok
        auth.log_login(db, row["id"] if row else None, username, bool(ok))
        if not ok:
            flash(_("Incorrect username or password, or account is disabled."), "error")
            return render_template("login.html")
        # Clears any pre-auth session state (e.g. a CSRF token issued to
        # the anonymous login page) rather than letting it survive into
        # the authenticated session — a fresh login starts a fresh session.
        session.clear()
        session["user_id"] = row["id"]
        session["username"] = row["full_name"]
        session["password_changed_at"] = clock.token(row["password_changed_at"])
        # Gives the session an actual server-enforced expiry (see
        # PERMANENT_SESSION_LIFETIME above) instead of relying solely on
        # the browser dropping the cookie on close — which doesn't happen
        # on a front-desk machine left open for a whole shift.
        session.permanent = True
        auth.refresh_session_permissions(db, row)
        nxt = request.args.get("next")
        if not is_safe_local_path(nxt):
            nxt = url_for("main.dashboard")
        return redirect(nxt)
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    db = get_db()
    forced = bool(auth.current_user(db)["must_change_password"])
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = db.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if not auth.verify_password(user["password_hash"], current):
            flash(_("Current password is incorrect."), "error")
        elif auth.password_error(new, user["username"]):
            flash(auth.password_error(new, user["username"]), "error")
        elif new != confirm:
            flash(_("New password and confirmation don't match."), "error")
        else:
            changed_at = clock.now().isoformat(timespec="seconds")
            db.execute("UPDATE users SET password_hash=%s, must_change_password=false, password_changed_at=%s WHERE id=%s",
                       (auth.hash_password(new), changed_at, user["id"]))
            auth.log_change(db, "users", user["id"], "update", {"password": ("(hidden)", "(self-service change)")})
            db.commit()
            # Keeps this session logged in through its own change — only
            # OTHER sessions for this user (e.g. a stolen cookie elsewhere)
            # get invalidated by require_login()'s mismatch check.
            session["password_changed_at"] = clock.token(changed_at)
            flash(_("Password updated."), "success")
            return redirect(url_for("main.dashboard"))
    return render_template("change_password.html", forced=forced)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@bp.route("/")
def dashboard():
    db = get_db()
    snap = cached_dashboard_snapshot(db)
    # "Needs Admin Review" is a cross-cutting oversight panel that doesn't map
    # to one single permission from the checklist — shown to anyone with at
    # least one of the Admin-group permissions, as the closest match to "some
    # kind of clinic administrator" (its previous Admin-only gate, made
    # granular so a custom role with equivalent permissions still sees it).
    is_overseer = (auth.has_permission("manage_users_roles") or auth.has_permission("manage_settings")
                   or auth.has_permission("view_logins_changes"))
    all_missed = alerts.missed_items(db) if is_overseer else []
    missed_page = get_page()
    missed_total = len(all_missed)
    missed_offset = page_offset(missed_page)
    missed = all_missed[missed_offset:missed_offset + PER_PAGE]
    opex_due = alerts.opex_reminder_due(db) if auth.has_permission("view_financial_reports") else False
    # A blank Date Billed silently drops that bill from every P&L figure
    # forever (reports.py counts a bill in the month of its date_billed) — this
    # is the visible half of the fix in visit_billing_save(), which now
    # defaults date_billed instead of allowing it blank going forward; this
    # catches anything that slipped through before that fix, or via direct
    # SQL. See ORPHANED_RECORDS_AUDIT.md F-06.
    unbilled_count = 0
    if auth.has_permission("view_financial_reports"):
        unbilled_count = db.execute(
            "SELECT COUNT(*) c FROM billing WHERE date_billed IS NULL AND total > 0"
        ).fetchone()["c"]
    backup_alert = None
    schema_pending = None
    self_check = None
    self_check_modal = False
    if auth.has_permission("manage_settings"):
        from vcs.ops import backup as backup_mod
        backup_alert = alerts.backup_alert_message(backup_mod.last_backup(db))
        # Migration files this code ships that the database has not applied
        # (schema.py) — only possible if a release was started without its
        # schema step. Worth an admin's attention before anything breaks.
        from vcs.db import migrate as schema_mod
        schema_pending = [name for _, name in schema_mod.pending(db)] or None
        # Layer 1 of operational monitoring. Reads the last *recorded* result
        # rather than running a fresh check: run_self_check() probes the disk
        # and write-tests the backup folder, neither of which has any business
        # happening on every dashboard load. scheduler.py runs it daily (20
        # minutes after the backup) and once at startup.
        if settings.get_setting(db, "selfcheck_enabled", "1") != "0":
            from vcs.ops import selfcheck
            row = selfcheck.latest(db)
            if row and row["status"] != "ok":
                try:
                    findings = json.loads(row["findings"] or "[]")
                except (TypeError, ValueError):
                    findings = []
                self_check = {"status": row["status"], "ran_at": row["ran_at"],
                              "findings": findings}
                # The modal, not the banner, is the point: a dismissible
                # banner is what is already being scrolled past. Three
                # consecutive failing days, holders of manage_settings only.
                self_check_modal = (row["status"] == "fail"
                                    and selfcheck.consecutive_fail_days(db) >= 3)
        # backup_alert_message() predates the self-check and every case it
        # reports (never run / failed / stranded / stale) is now covered by a
        # backup_* finding, in more detail. With both on screen the admin got
        # the same news twice in two different shapes -- once in the health
        # banner and once as a toast, since toast.js converts a .flash into
        # one. Reported 2026-08-31 off a real Test C dashboard.
        #
        # Suppressed only when the banner is actually carrying a backup
        # finding. If the self-check is switched off, has never run, or is
        # reporting something unrelated (a low disk, a rolled-back update),
        # this older alert is the only backup warning there is and must
        # survive -- the two also disagree by design, because the self-check's
        # staleness threshold is configurable (selfcheck_backup_max_age_days)
        # while this one is fixed at 2 days.
        if self_check and backup_alert and any(
                str(f.get("code", "")).startswith("backup_")
                for f in self_check["findings"]):
            backup_alert = None
    return render_template("dashboard.html", snap=snap, lan_address=lan_address(), missed=missed,
                            is_overseer=is_overseer, opex_due=opex_due, backup_alert=backup_alert,
                            unbilled_count=unbilled_count, schema_pending=schema_pending,
                            self_check=self_check, self_check_modal=self_check_modal,
                            missed_page=missed_page, missed_total_pages=page_count(missed_total),
                            missed_total=missed_total)


@bp.route("/health")
def health():
    """Used by updater.py to confirm a new release actually boots and can
    reach the database — not just that the process started. No auth
    required (harmless — reveals nothing beyond the version string; the
    updater probes this on a throwaway localhost port before the release
    it's checking is ever promoted)."""
    try:
        get_db().execute("SELECT 1")
        return {"status": "ok", "version": VERSION}, 200
    except Exception:
        # This endpoint is in OPEN_ENDPOINTS -- no login required -- so
        # whatever it returns is readable by anyone who can reach the app.
        # It used to return str(e), and psycopg's connection errors carry the
        # database host, port and user inline:
        #   connection to server at "127.0.0.1", port 5432 failed:
        #   FATAL: password authentication failed for user "vetclinic"
        # That path is reachable whenever the pool has no live connection --
        # the app starting before Postgres is the obvious way. The reference
        # id ties this response to the full traceback in logs/errors.log,
        # which is already access-controlled.
        #
        # updater.py's _probe_health() only reads `status`, and the Settings
        # page's restart poll only checks that the request succeeds, so
        # nothing consumes the old free-text detail.
        error_id = uuid.uuid4().hex[:8].upper()
        error_logger.error(f"[{error_id}] /health check failed\n" + traceback.format_exc())
        return {
            "status": "error",
            "detail": f"The application could not reach its database. "
                      f"Reference {error_id} — see logs/errors.log on the server.",
        }, 503
