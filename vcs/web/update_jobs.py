"""
Checking for, applying and rolling back updates, and following the job: the
work behind Developer -> Updates. Updates are the vendor's alone since
2026-10-02, when the owner took them off the clinic's Settings page (plan
L-8, reversed); the job status is also what Settings polls for a backup or a
restore. Each returns (JSON payload, HTTP status) for the calling route to send.
"""
from flask_babel import gettext as _

from vcs import jobs
from vcs.messages import Msg, N_
from vcs.web.core import VERSION, shown

NO_TOKEN = N_("No access token is set for updates on this install, so updates are off. "
              "Your vendor sets one in the Developer area.")


def status():
    """What the Updates card draws, with no network call (COMPARISON.md §46)."""
    from vcs.ops import updater
    configured = updater.is_configured()
    return {"configured": configured,
            "current_version": updater.current_version() if configured else VERSION}, 200


def _no_token(updater):
    if updater.read_token():
        return None
    return {"configured": True, "current_version": updater.current_version(),
            "error": shown(Msg(NO_TOKEN))}, 400


def check():
    from vcs.ops import updater
    if not updater.is_configured():
        return {"configured": False, "current_version": VERSION}, 200
    refused = _no_token(updater)
    if refused:
        return refused
    try:
        available, latest = updater.is_update_available()
    except Exception as exc:
        return {"configured": True, "current_version": updater.current_version(),
                "error": shown(updater.describe_check_failure(exc))}, 502
    return {"configured": True, "current_version": updater.current_version(), "available": available,
            "latest_tag": latest.get("tag_name"), "latest_body": latest.get("body")}, 200


def start_apply():
    from vcs.ops import updater
    if not updater.is_configured():
        return {"error": _("Updates aren't set up on this install yet.")}, 400
    refused = _no_token(updater)
    if refused:
        return {"error": refused[0]["error"]}, 400
    try:
        available, latest = updater.is_update_available()
    except Exception as exc:
        return {"error": shown(updater.describe_check_failure(exc))}, 502
    if not available:
        return {"error": _("Already on the latest version.")}, 400
    tag_name, tarball_url = latest.get("tag_name"), latest.get("tarball_url")

    def task(update):
        ok, message = updater.apply_update(tag_name, tarball_url, on_progress=update)
        return {"ok": ok, "message": message}

    job_id = jobs.start(
        [_("Backing up database"), _("Downloading release"), _("Validating release"),
         _("Applying database changes"), _("Verifying the new version"),
         _("Switching to the new version")],
        task,
    )
    return {"job_id": job_id, "tag": tag_name}, 200


def start_rollback():
    from vcs.ops import updater
    if not updater.is_configured():
        return {"error": _("Updates aren't set up on this install yet.")}, 400
    candidates = [n for n in updater.list_releases() if n != updater.active_release_name()]
    if not candidates:
        return {"error": _("No previous release available to roll back to.")}, 400

    def task(update):
        update(0)
        ok, message = updater.rollback_to_previous()
        return {"ok": ok, "message": message}

    return {"job_id": jobs.start([_("Rolling back")], task)}, 200


def job_status(job_id):
    """The progress panel's poll. Step labels and the result are translated
    here, for the person looking: the job ran in a thread with no request,
    and its messages are messages.Msg (audit F1)."""
    state = jobs.status(job_id)
    if state is None:
        return {"status": "not_found"}, 404
    payload = {"status": state["status"], "steps": [shown(step) for step in state["steps"]],
               "current": state["current"], "fraction": state.get("fraction"),
               "started_at": state["started_at"]}
    if state["status"] == "done":
        result = state.get("result") or {}
        payload["ok"] = result.get("ok")
        payload["message"] = shown(result.get("message"))
    elif state["status"] == "error":
        payload["message"] = state.get("error")
    return payload, 200
