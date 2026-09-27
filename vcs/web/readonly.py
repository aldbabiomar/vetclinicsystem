"""
Read-only mode (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §6.3-§6.4): one
registry of what may still write, enforced in one before_request hook -- not
a check inside each route, which is how a rule goes missing from a sibling
(SEAM_RULES.md). tests/test_license.py walks the live url_map against it.

A session signed in while the license was writable keeps writing until it
ends: read-only begins at a sign-in, never in the middle of someone's task.
GET is never refused. Background jobs never pass through here.
"""
from flask import render_template, request, session

from vcs.licensing import state

SESSION_KEY = "license_state"          # the state this session signed in under
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# What still writes when the license has run out (plan A7, as the owner
# confirmed): signing in and one's own password; the license key itself;
# backups, restore and updates; user administration, so a departing
# employee can still be disabled; and, for the animals already in the
# clinic, notes and owner calls on admitted inpatient cases. Payments are
# refused: that is the reason to renew.
ALLOWED = frozenset({
    "main.login", "main.change_password",
    "settings.settings_license",
    "settings.settings_backup_now", "settings.settings_restore_now",
    "settings.settings_updates_apply", "settings.settings_updates_rollback",
    "admin.admin_user_new", "admin.admin_user_toggle", "admin.admin_user_reset_password",
    "admin.admin_user_role",
    "clinical.inpatient_update_add", "clinical.inpatient_update_edit", "clinical.inpatient_contact_add",
})
# The vendor's own tools, reached only with a Developer Pass.
ALLOWED_PREFIXES = ("developer.",)


def allowed(endpoint):
    return endpoint in ALLOWED or endpoint.startswith(ALLOWED_PREFIXES)


def remember_sign_in_state(db):
    """At sign-in: work the license out again, and keep the state this
    session begins under."""
    status = state.refresh(db)
    session[SESSION_KEY] = status.state
    return status


def refuse_writes_when_read_only():
    if request.method not in WRITES or request.endpoint is None or allowed(request.endpoint):
        return None
    if session.get(SESSION_KEY) in state.WRITABLE:
        return None
    status = state.current()
    if status.writable:
        return None
    return render_template("read_only.html", status=status), 403
