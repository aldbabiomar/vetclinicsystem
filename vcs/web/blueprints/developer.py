"""
The Developer area (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §7-§8): the
vendor's pages at a clinic, reached with a Developer Pass signed for this one
install, never with a password, a role or a permission. It works with or
without a clinic sign-in (A12), in its own layout.

Sections land with the plan's phases; each page listed here does something
real.
"""
import io
import os

from flask import Blueprint, abort, jsonify, make_response, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _

from vcs import auth, clock, config, money
from vcs.domain import developer_audit, settings, vendor_message
from vcs.licensing import tokens
from vcs.messages import Msg, N_
from vcs.web import devsession, export_jobs, license_pages, update_jobs, vendor_settings
from vcs.web.core import (VERSION, flash, get_db, is_safe_local_path, login_rate_limit_check, money_setting_label,
                          shown)

bp = Blueprint("developer", __name__)


@bp.route("/developer/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        if not login_rate_limit_check(request.remote_addr):
            flash(_("Too many sign-in attempts from this computer. Wait a few minutes and try again."), "error")
            return render_template("developer_login.html", install_id=config.INSTALL_ID), 429
        try:
            payload = tokens.verify(request.form.get("dev_pass", ""), tokens.DEV_PASS,
                                    config.INSTALL_ID, clock.now())
        except tokens.TokenError as e:
            developer_audit.record(db, "developer.login_failed", actor="dev:?", outcome="refused",
                                   detail={"reason": e.code}, remote_addr=request.remote_addr)
            db.commit()
            flash(shown(e.message), "error")
            return render_template("developer_login.html", install_id=config.INSTALL_ID), 400
        devsession.start(payload)
        developer_audit.record(db, "developer.login", actor=developer_audit.developer_actor(payload["developer"]),
                               pass_id=payload["pass_id"], detail={"expires_at": payload["expires_at"]},
                               remote_addr=request.remote_addr)
        db.commit()
        target = request.args.get("next", "")
        return redirect(target if is_safe_local_path(target) and target.startswith("/developer/")
                        else url_for("developer.home"))
    if devsession.current():
        return redirect(url_for("developer.home"))
    return render_template("developer_login.html", install_id=config.INSTALL_ID)


@bp.route("/developer/logout", methods=["POST"])
def logout():
    devsession.end()
    flash(_("You have signed out of the Developer area."), "success")
    return redirect(url_for("developer.login"))


@bp.route("/developer/")
@devsession.required
def home():
    return render_template("developer_home.html", developer=devsession.current(),
                           install_id=config.INSTALL_ID, version=VERSION)


@bp.route("/developer/license", methods=["GET", "POST"])
@devsession.required
def license():
    dev = devsession.current()
    if request.method == "POST":
        license_pages.save_key(get_db(), actor=developer_audit.developer_actor(dev["name"]), pass_id=dev["pass_id"])
        return redirect(url_for("developer.license"))
    return render_template("developer_license.html", developer=dev, **license_pages.context())


@bp.route("/developer/audit")
@devsession.required
def audit():
    return render_template("developer_audit.html", developer=devsession.current(),
                           rows=developer_audit.recent(get_db()), audit_labels=developer_audit.LABELS)


def _actor():
    """How the vendor is named in both logs: the Developer Audit and the
    clinic's own change log (plan §7.3)."""
    return developer_audit.developer_actor(devsession.current()["name"])


def _audit(action, *, target=None, outcome="ok", detail=None):
    dev = devsession.current()
    developer_audit.record(get_db(), action, actor=developer_audit.developer_actor(dev["name"]),
                           pass_id=dev["pass_id"], target=target, outcome=outcome, detail=detail,
                           remote_addr=request.remote_addr)


# ---------------------------------------------------------------------------
# Configuration: the money setting and the palette (L-2, L-3)
# ---------------------------------------------------------------------------
@bp.route("/developer/configuration", methods=["GET", "POST"])
@devsession.required
def configuration():
    db = get_db()
    if request.method == "POST":
        try:
            money_change = (vendor_settings.save_money_setting(db, request.form["money_setting"], actor=_actor())
                            if request.form.get("money_setting") else None)
            palette_change = (vendor_settings.save_palette(db, request.form["theme_palette"], actor=_actor())
                              if request.form.get("theme_palette") else None)
        except vendor_settings.Refused as e:
            db.rollback()
            _audit("config.refused", outcome="refused", detail={"reason": str(e)})
            db.commit()
            flash(str(e), "error")
            return redirect(url_for("developer.configuration"))
        if money_change:
            _audit("config.money_setting", target=money.SETTING_KEY,
                   detail={"from": money_change[0], "to": money_change[1]})
        if palette_change:
            _audit("config.palette", target="theme_palette",
                   detail={"from": palette_change[0], "to": palette_change[1]})
        db.commit()
        if money_change:
            from vcs.ops import scheduler
            scheduler.reschedule(settings.get_setting(db, "backup_time", "02:00") or "02:00",
                                 zone=clock.load(db, money.load(db)))
            flash(_("Money setting saved: %(name)s. It locks itself once the first price or amount is recorded.",
                    name=money_setting_label(money_change[1])), "success")
        if palette_change or not money_change:
            flash(_("Configuration saved."), "success")
        return redirect(url_for("developer.configuration"))
    return render_template(
        "developer_configuration.html", developer=devsession.current(), install_id=config.INSTALL_ID,
        money_setting=money.current(), money_settings=list(money.SETTINGS.values()),
        money_locked=money.is_locked(db), settings=settings.get_all(db))


# ---------------------------------------------------------------------------
# Monitoring: the heartbeat ping (moved from Settings; storage unchanged, A6)
# ---------------------------------------------------------------------------
def _masked(value):
    return f"…{value[-6:]}" if value else None


@bp.route("/developer/monitoring", methods=["GET", "POST"])
@devsession.required
def monitoring():
    db = get_db()
    if request.method == "POST":
        value = "" if request.form.get("remove") else request.form.get("heartbeat_url", "")
        try:
            change = vendor_settings.save_heartbeat_url(db, value, actor=_actor())
        except vendor_settings.Refused as e:
            flash(str(e), "error")
            return redirect(url_for("developer.monitoring"))
        if change:
            _audit("heartbeat.changed", target="heartbeat_url", detail={"url": change[1]})
        db.commit()
        flash(_("Monitoring saved."), "success")
        return redirect(url_for("developer.monitoring"))
    current = settings.get_all(db)
    return render_template("developer_monitoring.html", developer=devsession.current(),
                           ping_url=_masked(current.get("heartbeat_url") or ""),
                           heartbeat_install_id=current.get("heartbeat_install_id"))


# ---------------------------------------------------------------------------
# Updates: the clinic's GitHub token, and the same controls as Settings (L-1, L-8)
# ---------------------------------------------------------------------------
def _update_history(limit=20):
    """The last lines of the updates log in the data folder. It never holds
    the token: the updater logs what it did, not how it was authorised."""
    from vcs.ops import updater
    if not updater.DATA_DIR:
        return []
    try:
        with open(os.path.join(updater.DATA_DIR, "logs", "updates.log"), encoding="utf-8") as f:
            return f.read().splitlines()[-limit:][::-1]
    except OSError:
        return []


@bp.route("/developer/updates")
@devsession.required
def updates():
    from vcs.ops import updater
    return render_template("developer_updates.html", developer=devsession.current(), app_version=VERSION,
                           repository=updater.GITHUB_REPO, token=updater.masked_token(),
                           history=_update_history(), configured=updater.is_configured())


@bp.route("/developer/updates/token", methods=["POST"])
@devsession.required
def updates_token():
    from vcs.ops import updater
    had = bool(updater.read_token())
    if request.form.get("remove"):
        updater.remove_token()
        flash(_("The access token is removed; updates are off until a new one is set."), "success")
    else:
        token = "".join(request.form.get("token", "").split())
        if not token:
            flash(_("Paste the token first."), "error")
            return redirect(url_for("developer.updates"))
        updater.save_token(token)
        flash(_("Access token saved."), "success")
    _audit("update.token_changed", target="github_token",
           detail={"token": "set" if updater.read_token() else "not set", "was": "set" if had else "not set"})
    get_db().commit()
    return redirect(url_for("developer.updates"))


@bp.route("/developer/updates/test", methods=["POST"])
@devsession.required
def updates_test():
    from vcs.ops import updater
    ok, message = updater.check_connection()
    flash(shown(message), "success" if ok else "error")
    return redirect(url_for("developer.updates"))


@bp.route("/developer/updates/status")
@devsession.required
def updates_status():
    payload, status = update_jobs.status()
    return jsonify(payload), status


@bp.route("/developer/updates/check")
@devsession.required
def updates_check():
    payload, status = update_jobs.check()
    return jsonify(payload), status


@bp.route("/developer/updates/apply", methods=["POST"])
@devsession.required
def updates_apply():
    payload, status = update_jobs.start_apply()
    if status == 200:
        _audit("update.started", target=payload.get("tag"))
        get_db().commit()
    return jsonify(payload), status


@bp.route("/developer/updates/rollback", methods=["POST"])
@devsession.required
def updates_rollback():
    payload, status = update_jobs.start_rollback()
    if status == 200:
        _audit("update.rollback_started")
        get_db().commit()
    return jsonify(payload), status


@bp.route("/developer/job-status")
@devsession.required
def job_status():
    payload, status = update_jobs.job_status(request.args.get("job_id", ""))
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# System: what the app already knows about its health (§11.1)
# ---------------------------------------------------------------------------
ERROR_LOG_LINES = 60
SELF_CHECK_STATUS = {"ok": N_("All clear"), "warn": N_("Warnings"), "fail": N_("Problems found")}
# The logs' own words for how something went, as the System page says them.
STATUS_LABELS = {**SELF_CHECK_STATUS, "success": N_("Succeeded"), "failed": N_("Failed"),
                 "running": N_("Running"), "pass": N_("Passed")}


@bp.route("/developer/system")
@devsession.required
def system():
    from vcs.ops import redact, system_info
    db = get_db()
    errors = redact.log(redact.tail(system_info.error_log_path(), ERROR_LOG_LINES), redact.known_secrets(db))
    return render_template("developer_system.html", developer=devsession.current(), info=system_info.gather(db),
                           errors=errors, error_lines=ERROR_LOG_LINES, status_labels=STATUS_LABELS)


@bp.route("/developer/system/self-check", methods=["POST"])
@devsession.required
def system_self_check():
    """The daily self-check, now: the same run and the same record as the
    scheduler's."""
    from vcs.ops import selfcheck
    db = get_db()
    result = selfcheck.run_self_check(db)
    selfcheck.record(db, result)
    _audit("selfcheck.run", detail={"status": result["status"]})
    db.commit()
    flash(_("Self-check finished: %(status)s.", status=shown(Msg(SELF_CHECK_STATUS[result["status"]]))),
          "success" if result["status"] == "ok" else "error")
    return redirect(url_for("developer.system"))


# ---------------------------------------------------------------------------
# Support: the support bundle (§11.2) and restoring administrator access (§11.3)
# ---------------------------------------------------------------------------
def _system_admins(db):
    return db.execute(
        "SELECT u.id, u.username, u.full_name, u.active, u.must_change_password FROM users u "
        "JOIN roles r ON r.id = u.role_id WHERE r.is_system ORDER BY u.username").fetchall()


@bp.route("/developer/support")
@devsession.required
def support():
    return render_template("developer_support.html", developer=devsession.current(),
                           admins=_system_admins(get_db()))


@bp.route("/developer/support/bundle", methods=["POST"])
@devsession.required
def support_bundle():
    from vcs.ops import support_bundle as bundle
    db = get_db()
    data, name = bundle.build(db), bundle.filename()
    _audit("support_bundle.generated", target=name, detail={"bytes": len(data)})
    db.commit()
    response = send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True, download_name=name)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/developer/support/recover", methods=["POST"])
@devsession.required
def support_recover():
    """A new temporary password for one of the clinic's system administrators
    (§11.3), through the clinic's own reset path: they must change it at
    their next sign-in, their other sessions end, and their sign-in lockout
    is cleared. The password is on this response and nowhere else -- not a
    flash (which would put it in the session cookie), not a log, not the
    audit."""
    db = get_db()
    try:
        user_id = int(request.form.get("user_id", ""))
    except ValueError:
        abort(400)
    target = next((u for u in _system_admins(db) if u["id"] == user_id), None)
    if target is None or not target["active"]:
        _audit("admin.recovered", target=str(user_id), outcome="refused")
        db.commit()
        flash(_("Only an active system administrator's access can be restored here."), "error")
        return redirect(url_for("developer.support"))
    password = auth.temporary_password(target["username"])
    auth.reset_password(db, user_id, password)
    auth.log_change(db, "users", user_id, "update", {"password": ("(hidden)", "(reset by vendor)")}, actor=_actor())
    _audit("admin.recovered", target=str(user_id), detail={"username": target["username"]})
    db.commit()
    response = make_response(render_template("developer_recovered.html", developer=devsession.current(),
                                             user=target, password=password))
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Vendor message (§11.5, A13)
# ---------------------------------------------------------------------------
@bp.route("/developer/vendor-message", methods=["GET", "POST"], endpoint="vendor_message")
@devsession.required
def vendor_message_page():
    db = get_db()
    if request.method == "POST":
        if request.form.get("clear"):
            if vendor_settings.clear_vendor_message(db):
                _audit("vendor_message.cleared")
            db.commit()
            flash(_("The message is cleared."), "success")
            return redirect(url_for("developer.vendor_message"))
        try:
            change = vendor_settings.save_vendor_message(
                db, request.form.get("text"), request.form.get("level", "info"),
                request.form.get("expires_at"), bool(request.form.get("enabled")))
        except vendor_settings.Refused as e:
            flash(str(e), "error")
            return redirect(url_for("developer.vendor_message"))
        if change:
            _audit("vendor_message.changed", detail=change)
        db.commit()
        flash(_("The message is saved."), "success")
        return redirect(url_for("developer.vendor_message"))
    return render_template("developer_vendor_message.html", developer=devsession.current(),
                           message=vendor_message.stored(db), showing=vendor_message.current(db),
                           levels=vendor_message.LEVELS, max_length=vendor_message.MAX_LENGTH)


# ---------------------------------------------------------------------------
# Data export (§11.4): the same as Settings -> Data Export
# ---------------------------------------------------------------------------
@bp.route("/developer/data-export")
@devsession.required
def data_export():
    from vcs.ops import data_export as export
    return render_template(
        "developer_data_export.html", developer=devsession.current(), exports=export.list_exports(),
        exclusions=export.exclusions(),
        exp={"start": url_for("developer.data_export_start"), "job": url_for("developer.job_status"),
             "download": url_for("developer.data_export_download", name="NAME")})


@bp.route("/developer/data-export/start", methods=["POST"])
@devsession.required
def data_export_start():
    payload, status = export_jobs.start(actor=_actor(), pass_id=devsession.current()["pass_id"])
    return jsonify(payload), status


@bp.route("/developer/data-export/<name>")
@devsession.required
def data_export_download(name):
    return export_jobs.download(name)
