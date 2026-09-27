"""
The Developer area (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §7-§8): the
vendor's pages at a clinic, reached with a Developer Pass signed for this one
install, never with a password, a role or a permission. It works with or
without a clinic sign-in (A12), in its own layout.

Sections land with the plan's phases; each page listed here does something
real.
"""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_babel import gettext as _

from vcs import clock, config
from vcs.domain import developer_audit
from vcs.licensing import tokens
from vcs.web import devsession
from vcs.web.core import VERSION, flash, get_db, is_safe_local_path, login_rate_limit_check, shown

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


@bp.route("/developer/audit")
@devsession.required
def audit():
    return render_template("developer_audit.html", developer=devsession.current(),
                           rows=developer_audit.recent(get_db()), audit_labels=developer_audit.LABELS)
