"""
Settings, and the installation-maintenance actions behind it.

The ordinary clinic settings (clinic name, appointment hours, alert windows)
sit behind `manage_settings`. Everything that administers the INSTALL rather
than the clinic -- backups, restore, autostart, and the folder picker
they share -- sits behind `manage_maintenance`, so that the Settings page's own
gate and the server's gate are the same condition. They were not, until
2026-09-10: the page hid these controls while every route behind them accepted
a `manage_settings` holder's request.

Shared request-layer pieces come from vcs.web.core, never from the factory
that registers this blueprint (vcs/web/blueprints/__init__.py says why).

Endpoint names carry the `settings.` prefix Flask gives every blueprint route:
`url_for("settings.settings_page")`, not `url_for("settings_page")`.
"""
import os
from datetime import datetime

from flask_babel import gettext as _
from flask import (
    Blueprint, g, jsonify, redirect, render_template, request, session, url_for
)

from vcs import auth
from vcs.db import pool as dbmod
from vcs import jobs
from vcs.domain import appointments, logs, members, settings
from vcs import clock
from vcs import money
from vcs.web import export_jobs, license_pages, update_jobs, vendor_settings
from vcs.web.core import flash, display_number, list_join, shown, parse_percent, BadNumber, DATA_DIR as _data_dir, VERSION, get_db, lan_address

bp = Blueprint("settings", __name__)


def _browse_roots(db):
    """The only directories the Settings folder/file pickers may browse.

    This endpoint used to resolve whatever ?path= it was given with
    os.path.abspath() and list it, with no confinement at all -- so any
    logged-in user who could reach it could enumerate /, /etc, /Users and
    /var/log on the clinic machine. It still has to browse the *server's*
    disk (pg_dump/pg_restore run there, see the docstring on
    api_browse_folder), so the fix is a root, not removal.
    """
    roots = []
    for candidate in (os.path.expanduser("~"),
                      settings.get_setting(db, "backup_dir"),
                      _data_dir):
        if candidate and os.path.isdir(candidate):
            real = os.path.realpath(candidate)
            if real not in roots:
                roots.append(real)
    return roots


def _within_roots(path, roots):
    """True if `path` is one of `roots` or lives beneath one.

    commonpath(), never startswith(): '/Users/omar-evil' must not pass a
    '/Users/omar' check. realpath() first so a symlink cannot step outside
    a root either.
    """
    real = os.path.realpath(path)
    for root in roots:
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            # Different drives on Windows -- not comparable, so not inside.
            continue
    return False


def _outside_roots_error(roots):
    where = list_join(roots) if roots else _("the backup folder")
    return jsonify({"error": _("That folder is outside the areas this app can browse (%(where)s).", where=where)}), 400


@bp.route("/api/browse-folder")
@auth.permission_required("manage_maintenance")
def api_browse_folder():
    """
    Lists subfolders (and, when ?ext= is given, matching files too) of a
    path on THIS SERVER's filesystem — used by both the Backup Folder
    picker and the Restore File picker on Settings. This has to browse the
    server's disk, not the browser's — pg_dump/pg_restore (see backup.py)
    run on the server, so a client-side file picker (which can only see
    the browser's own machine) would pick the wrong computer's files
    entirely whenever Settings is opened from a different machine than
    the one running the app.
    """
    db = get_db()
    requested = request.args.get("path", "").strip()
    ext = (request.args.get("ext") or "").strip().lower()
    if requested:
        path = os.path.abspath(requested)
    else:
        configured = settings.get_setting(db, "backup_dir")
        path = os.path.abspath(configured) if configured and os.path.isdir(configured) else os.path.expanduser("~")

    if not os.path.isdir(path):
        return jsonify({"error": _("“%(path)s” isn’t a folder VetClinicSystem can see on this computer.", path=path)}), 400

    roots = _browse_roots(db)
    if not _within_roots(path, roots):
        return _outside_roots_error(roots)

    try:
        entries = os.listdir(path)
    except OSError as e:
        return jsonify({"error": _("Can’t open that folder: %(error)s", error=e.strerror or str(e))}), 400

    folders, files = [], []
    for name in entries:
        if name.startswith("."):
            continue
        full = os.path.join(path, name)
        if os.path.isdir(full) and not os.path.islink(full):
            folders.append(name)
        elif ext and os.path.isfile(full) and name.lower().endswith(ext):
            files.append(name)
    folders.sort(key=str.lower)
    files.sort(key=str.lower)

    parent = os.path.dirname(path)
    if parent == path or not _within_roots(parent, roots):
        parent = None
    return jsonify({
        "current": path,
        "parent": parent,
        "folders": folders,
        "files": files,
    })


@bp.route("/api/browse-folder/new-folder", methods=["POST"])
@auth.permission_required("manage_maintenance")
def api_browse_folder_new():
    data = request.get_json(silent=True) or {}
    parent = os.path.abspath((data.get("path") or "").strip())
    name = (data.get("name") or "").strip()
    if not name or "/" in name or "\\" in name:
        return jsonify({"error": _("Enter a plain folder name (no slashes).")}), 400
    if not os.path.isdir(parent):
        return jsonify({"error": _("That parent folder no longer exists.")}), 400
    roots = _browse_roots(get_db())
    if not _within_roots(parent, roots):
        return _outside_roots_error(roots)
    new_path = os.path.join(parent, name)
    try:
        os.makedirs(new_path, exist_ok=True)
    except OSError as e:
        return jsonify({"error": _("Couldn’t create that folder: %(error)s", error=e.strerror or str(e))}), 400
    return jsonify({"ok": True, "path": new_path})


# ---------------------------------------------------------------------------
# Settings (Admin only)
# ---------------------------------------------------------------------------
# Which permission each field of the Settings form needs. The POST refuses a
# field the user cannot change and the template draws only the fields it can
# (setting_editable), from this one table — audit S1 was four maintenance
# fields hidden by the template and still saved by the POST. A field not
# listed here needs manage_settings, the route's own gate.
SETTING_FIELD_PERMISSION = {
    "backup_dir": "manage_maintenance",
    "backup_time": "manage_maintenance",
    "backup_retention": "manage_maintenance",
    "log_retention_days": "manage_maintenance",
    # Set by the vendor, in the Developer area (licensing plan L-2, L-3):
    # `developer` is a gate, not a permission, so no one -- the system Admin
    # included -- can save these here (vcs/web/vendor_settings.py).
    **{key: vendor_settings.DEVELOPER for key in vendor_settings.KEYS},
}


@bp.app_template_global("setting_editable")
def setting_editable(key):
    """For the template: may the signed-in user change this field?"""
    return auth.has_permission(SETTING_FIELD_PERMISSION.get(key, "manage_settings"))


@bp.route("/settings/license", methods=["GET", "POST"])
@auth.permission_required("manage_settings")
def settings_license():
    """The clinic enters its license key here (plan L-5, A9). Allowed while
    read-only: it is how a clinic gets out of read-only."""
    if request.method == "POST":
        db = get_db()
        license_pages.save_key(db, actor=f"user:{auth.current_user(db)['username']}")
        return redirect(url_for("settings.settings_license"))
    return render_template("settings_license.html", **license_pages.context())


@bp.route("/settings", methods=["GET", "POST"])
@auth.permission_required("manage_settings")
def settings_page():
    db = get_db()
    if request.method == "POST":
        # One definition of who may change what (audit S1): refused here, on
        # the server, before anything is validated or saved — hiding a field
        # in the template is not a permission.
        denied = [k for k, perm in SETTING_FIELD_PERMISSION.items()
                  if k in request.form and not auth.has_permission(perm)]
        if any(SETTING_FIELD_PERMISSION[k] == vendor_settings.DEVELOPER for k in denied):
            flash(_("Nothing was saved: the money setting, the color palette, the monitoring ping "
                    "and the vendor's message are set by your vendor."), "error")
            return redirect(url_for("settings.settings_page"))
        if denied:
            flash(_("Nothing was saved: your role can't change the backup and log-retention settings."), "error")
            return redirect(url_for("settings.settings_page"))
        # (field, min, max) — keeps schedule generation and alert windows sane.
        NUMERIC_RANGES = {
            "audit_overdue_days": (1, 3650),
            "expiry_soon_days": (1, 3650),
            "appt_slot_minutes": (5, 240),
            "backup_retention": (1, 3650),
            # Backups are nightly, so one missed night is noise and two is a
            # pattern. Capped at 30: a threshold beyond that is indistinguishable
            # from switching the check off, which selfcheck_enabled already does
            # honestly.
            "selfcheck_backup_max_age_days": (1, 30),
            # Floor of 90 days is deliberate and load-bearing: auth
            # .login_lock_status() reads login_log to decide whether an
            # account is locked out, so pruning inside that window would
            # silently disarm the lockout.
            "log_retention_days": (logs.LOG_RETENTION_MIN_DAYS, logs.LOG_RETENTION_MAX_DAYS),
            # How long a newly issued rewards card lasts. Whole months, so
            # this belongs here (int) -- unlike the RATE below, which is a
            # percentage and is parsed like every other percentage in the app.
            "member_term_months": (1, members.MEMBER_TERM_MONTHS_MAX),
        }
        for key, (lo, hi) in NUMERIC_RANGES.items():
            val = request.form.get(key)
            if val is None or val.strip() == "":
                continue
            try:
                n = int(val)
            except ValueError:
                flash(_("%(title)s must be a whole number.", title=key.replace('_', ' ').title()), "error")
                return redirect(url_for("settings.settings_page"))
            if n < lo or n > hi:
                flash(_("%(title)s must be between %(lo)s and %(hi)s.", title=key.replace('_', ' ').title(), lo=lo, hi=hi), "error")
                return redirect(url_for("settings.settings_page"))

        # Time-of-day fields — validated as real HH:MM before anything else
        # touches them. appt_start_time/appt_end_time feed straight into
        # appointments.generate_slots()'s datetime.strptime(..., "%H:%M") (used by
        # Appointments, New Visit, Grooming, and Inpatient's vet pickers),
        # and backup_time feeds scheduler.reschedule()'s CronTrigger — an
        # unvalidated value there doesn't just break one page, it can raise
        # at the next app *startup* (scheduler.start() runs unguarded before
        # the server starts serving), making the whole app fail to launch
        # until someone fixes the row directly in the database. The <input
        # type="time"> in the template stops this in the normal UI, but
        # that's client-side only, so it's validated here too. See
        # ERROR_500_AUDIT.md E-01/E-02.
        # `language` drives which catalogue every page renders from, and its
        # value reaches Flask-Babel directly. A whitelist rather than trusting
        # the form, same reasoning as every other settings field validated
        # here — and an unknown locale would otherwise fall back silently,
        # which reads as "the setting did not save".
        SUPPORTED_LANGUAGES = ("en", "ar")
        lang_val = request.form.get("language")
        if lang_val is not None and lang_val not in SUPPORTED_LANGUAGES:
            flash(_("Not a valid language."), "error")
            return redirect(url_for("settings.settings_page"))
        TIME_FIELDS = ["appt_start_time", "appt_end_time", "backup_time"]
        for key in TIME_FIELDS:
            val = request.form.get(key)
            if val is None or val.strip() == "":
                continue
            try:
                datetime.strptime(val.strip(), "%H:%M")
            except ValueError:
                flash(_("%(title)s must be a valid time (HH:MM).", title=key.replace('_', ' ').title()), "error")
                return redirect(url_for("settings.settings_page"))

        # The rewards-card rate is a PERCENTAGE, so it goes through
        # parse_percent like the staff discount it sits beside -- not through
        # NUMERIC_RANGES above, which is int() only and would refuse a
        # fractional rate that a staff discount already accepts. 0 (the
        # default) means the programme is off.
        rate_val = request.form.get("member_discount_percent")
        if rate_val is not None and rate_val.strip() != "":
            try:
                rate = parse_percent(rate_val)
            except BadNumber:
                flash(_("Member discount must be a valid number."), "error")
                return redirect(url_for("settings.settings_page"))
            if rate is None or not 0 <= rate <= members.MEMBER_RATE_MAX:
                flash(_("Member discount must be between 0%% and %(max)s%%.", max=members.MEMBER_RATE_MAX), "error")
                return redirect(url_for("settings.settings_page"))

        # The Time Zone (clock.py): an IANA name, or blank for automatic
        # (the money setting's zone, else this computer's). Blank DELETES the
        # key rather than storing "", so "automatic" has one representation.
        tz_val = request.form.get(clock.SETTING_KEY)
        tz_change = None
        if tz_val is not None:
            tz_val = tz_val.strip()
            if tz_val and not clock.is_valid(tz_val):
                flash(_("Not a valid time zone."), "error")
                return redirect(url_for("settings.settings_page"))
            old_tz = settings.get_setting(db, clock.SETTING_KEY) or ""
            if tz_val != old_tz:
                tz_change = (old_tz, tz_val)

        start = request.form.get("appt_start_time")
        end = request.form.get("appt_end_time")
        if start and end and start >= end:
            flash(_("Day Ends At must be after Day Starts At."), "error")
            return redirect(url_for("settings.settings_page"))

        # Snapshot before the change — appt_start_time/appt_end_time/
        # appt_slot_minutes feed generate_slots(), which day_grid() (and
        # appointments.orphaned_appointments()) key every appointment's slot_label
        # against. Comparing the orphaned count before/after this save is
        # how we know whether *this specific change* just stranded any
        # existing bookings, without hand-duplicating the slot-generation
        # logic here to simulate it separately.
        orphaned_before = len(appointments.orphaned_appointments(db))
        for key in ["clinic_name", "clinic_location", "audit_overdue_days", "expiry_soon_days", "opening_date",
                    "appt_start_time", "appt_end_time", "appt_slot_minutes",
                    "backup_dir", "backup_time", "backup_retention", "language",
                    "selfcheck_backup_max_age_days", "log_retention_days",
                    # The rewards-card rate and term. Validated above since the
                    # rewards card shipped, but missing from this list in the
                    # predecessor JO app — so saving Settings never stored
                    # them and the programme could not be switched on.
                    "member_discount_percent", "member_term_months"]:
            val = request.form.get(key)
            if val is not None:
                old = settings.get_setting(db, key)
                db.execute(
                    "INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, val),
                )
                if old != val:
                    auth.log_change(db, "settings", key, "update", {key: (old, val)})
        # selfcheck_enabled is a checkbox, and an unchecked box submits
        # nothing at all — so it cannot go through the loop above, where a
        # missing key means "left alone". It would switch on and never off.
        # The hidden companion field is what distinguishes "this form was
        # submitted and the box was clear" from "this form doesn't have the
        # field", e.g. a POST from an older cached page.
        if request.form.get("selfcheck_present"):
            val = "1" if request.form.get("selfcheck_enabled") else "0"
            old = settings.get_setting(db, "selfcheck_enabled")
            db.execute(
                "INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("selfcheck_enabled", val),
            )
            if old != val:
                auth.log_change(db, "settings", "selfcheck_enabled", "update",
                                {"selfcheck_enabled": (old, val)})
        if tz_change:
            if tz_change[1]:
                db.execute("INSERT INTO settings (key,value) VALUES (%s,%s) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (clock.SETTING_KEY, tz_change[1]))
            else:
                db.execute("DELETE FROM settings WHERE key=%s", (clock.SETTING_KEY,))
            auth.log_change(db, "settings", clock.SETTING_KEY, "update", {clock.SETTING_KEY: tz_change})
        db.commit()
        if request.form.get("backup_time") or tz_change:
            # A new zone (chosen, or arriving with a money setting while on
            # automatic) moves the nightly jobs to the clinic's 02:00.
            from vcs.ops import scheduler
            scheduler.reschedule(settings.get_setting(db, "backup_time", "02:00") or "02:00",
                                 zone=clock.load(db, money.load(db)))
        flash(_("Settings saved."), "success")
        newly_orphaned = len(appointments.orphaned_appointments(db)) - orphaned_before
        if newly_orphaned > 0:
            flash(_("Heads up: changing the scheduling hours/slot length just made %(n)s upcoming "
                    "appointment(s) stop matching a slot on the grid. They're still booked — check "
                    "Appointments for the \"need attention\" list to reschedule them.",
                    n=display_number(newly_orphaned)), "error")
        return redirect(url_for("settings.settings_page"))
    rows = db.execute("SELECT * FROM settings").fetchall()
    stored = {r["key"]: r["value"] for r in rows}
    from vcs.ops import backup as backup_mod
    from vcs.ops import autostart  # An 'in_progress' marker that was never updated to 'success'/'failed'
    # means the process died mid-restore — the database may be in a
    # partially restored state. See ORPHANED_RECORDS_AUDIT.md F-20.
    restore_marker = backup_mod.read_restore_marker()
    incomplete_restore = bool(restore_marker and restore_marker.get("status") == "in_progress")
    return render_template(
        "settings.html", settings=stored, lan_address=lan_address(),
        recent_backups=backup_mod.recent_backups(db),
        recent_restores=backup_mod.recent_restores(db),
        autostart_supported=autostart.is_supported(),
        autostart_enabled=autostart.is_enabled(),
        incomplete_restore=incomplete_restore,
        app_version=VERSION,
        money_settings=list(money.SETTINGS.values()),
        money_locked=money.is_locked(db),
        time_zones=clock.all_zone_names(),
        time_zone_automatic=clock.resolve(None, money.current()),
    )


@bp.route("/settings/backup-now", methods=["POST"])
@auth.permission_required("manage_maintenance")
def settings_backup_now():
    from vcs.ops import backup as backup_mod  # Checked here, before a job is started, rather than only inside
    # run_backup(): otherwise clicking Back Up Now with no folder set spins up
    # a progress panel that runs through its steps and then reports failure,
    # which reads as "the backup broke" rather than "you haven't set this up
    # yet". Nothing to do here is not an error worth a job.
    if not settings.get_setting(get_db(), "backup_dir"):
        return jsonify({"error": _("No backup folder configured yet — set one above, "
                                 "then Save Settings, before backing up.")}), 400

    def task(update):
        # Runs in a background thread — needs its own DB connection,
        # since g.db belongs to this request and gets closed at request
        # teardown long before a background thread finishes. Also keeps
        # run_backup() from committing on the request's own connection,
        # which would otherwise commit any other pending write this
        # request happened to have made as a side effect of taking a
        # backup. See ORPHANED_RECORDS_AUDIT.md F-24.
        conn = dbmod.connect()
        try:
            ok, message = backup_mod.run_backup(conn, triggered_by="manual", on_progress=update)
            return {"ok": ok, "message": message}
        finally:
            conn.close()

    job_id = jobs.start(
        [_("Checking backup folder"), _("Dumping database"),
         _("Applying retention policy"), _("Done")],
        task,
    )
    return jsonify({"job_id": job_id})


@bp.route("/settings/restore-now", methods=["POST"])
@auth.permission_required("manage_maintenance")
def settings_restore_now():
    source_file = (request.form.get("source_file") or "").strip()
    from vcs.ops import backup as backup_mod  # Path confinement + provenance check — only a .dump file inside the
    # configured backup folder AND recorded in this app's own backup_log
    # as a successful backup can be restored. Runs on the request's own
    # (still-open) connection, before that connection is released and
    # before any restore work starts, so an invalid/unauthorized path
    # never gets anywhere near pg_restore.
    ok, resolved_source, message = backup_mod.resolve_restorable_backup(get_db(), source_file)
    if not ok:
        flash(shown(message), "error")
        return redirect(url_for("settings.settings_page"))

    # pg_restore --clean issues DROP TABLE (and similar) against every
    # table in the database — including ones this very request already
    # touched, like `users` via require_login()'s lookup a moment ago.
    # Release this request's own connection back to the pool first so it
    # isn't still holding a read lock on those tables when pg_restore
    # tries to drop them.
    conn = g.pop("db", None)
    if conn is not None:
        conn.commit()
        dbmod.putconn(conn)

    # The restore is about to DROP and recreate every table — close the
    # whole pool so no other pooled-but-idle connection (e.g. a second
    # admin's open tab) is left holding cached plans/catalog snapshots
    # across it. getconn() transparently reopens a fresh pool on the next
    # request.
    dbmod.close_pool()

    def task(update):
        ok, message = backup_mod.run_restore(dbmod.connect, resolved_source,
                                              triggered_by="manual", on_progress=update)
        return {"ok": ok, "message": message}

    job_id = jobs.start(
        [_("Checking backup file"), _("Restoring database"), _("Reconciling schema"),
         _("Recording result"), _("Done")],
        task,
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------------------
# Data Export (licensing plan §11.4): the clinic's own copy of everything it
# recorded, in files any spreadsheet opens. manage_maintenance, like backups
# (A8); allowed in read-only mode (A7).
# ---------------------------------------------------------------------------
@bp.route("/settings/data-export")
@auth.permission_required("manage_maintenance")
def settings_data_export():
    from vcs.ops import data_export
    return render_template(
        "data_export.html", exports=data_export.list_exports(), exclusions=data_export.exclusions(),
        exp={"start": url_for("settings.settings_data_export_start"),
             "job": url_for("settings.settings_job_status"),
             "download": url_for("settings.settings_data_export_download", name="NAME")})


@bp.route("/settings/data-export/start", methods=["POST"])
@auth.permission_required("manage_maintenance")
def settings_data_export_start():
    from vcs.domain import developer_audit
    payload, status = export_jobs.start(actor=developer_audit.user_actor(auth.current_user(get_db())["username"]))
    return jsonify(payload), status


@bp.route("/settings/data-export/<name>")
@auth.permission_required("manage_maintenance")
def settings_data_export_download(name):
    return export_jobs.download(name)


@bp.route("/settings/job-status")
@auth.permission_required("manage_maintenance")
def settings_job_status():
    """Polled by the progress panels of Backup Now and Restore Now. (Updates
    are the vendor's: Developer -> Updates polls developer.job_status.)"""
    payload, status = update_jobs.job_status(request.args.get("job_id", ""))
    if (request.args.get("kind") == "restore" and payload.get("status") == "done"
            and payload.get("ok")):
        # The restore just replaced every row in the database, including
        # `users` -- force a fresh login on this browser rather than leaving
        # a session tied to data that may no longer match what is there now.
        session.clear()
    return jsonify(payload), status


@bp.route("/settings/autostart", methods=["POST"])
@auth.permission_required("manage_maintenance")
def settings_autostart():
    from vcs.ops import autostart
    enable = request.form.get("autostart_enabled") == "on"
    ok, message = autostart.enable() if enable else autostart.disable()
    flash(shown(message), "success" if ok else "error")
    return redirect(url_for("settings.settings_page"))
