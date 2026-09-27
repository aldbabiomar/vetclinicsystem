"""
The License page's shared half: the clinic's Settings -> License (for
`manage_settings`, plan L-5/A9) and the Developer area's copy show the same
panel and save a key the same way.
"""
from flask import request
from flask_babel import gettext as _

from vcs import config
from vcs.domain import developer_audit
from vcs.licensing import state, tokens
from vcs.web.core import flash, shown


def context():
    return dict(status=state.current(), install_id=config.INSTALL_ID, state_labels=state.LABELS)


def save_key(db, actor, pass_id=None):
    """Store the pasted key if it verifies for this install; record the
    attempt either way (never the key). True when saved."""
    before = state.current(db).state
    try:
        status = state.enter_key(db, request.form.get("license_key", ""))
    except tokens.TokenError as e:
        developer_audit.record(db, "license.entered", actor=actor, pass_id=pass_id, outcome="refused",
                               detail={"reason": e.code}, remote_addr=request.remote_addr)
        db.commit()
        flash(shown(e.message), "error")
        return False
    developer_audit.record(db, "license.entered", actor=actor, pass_id=pass_id,
                           target=status.payload.get("license_id"),
                           detail={"expires_at": status.payload.get("expires_at"), "state": status.state},
                           remote_addr=request.remote_addr)
    if status.state != before:
        developer_audit.record(db, "license.state_changed", actor=actor, pass_id=pass_id,
                               target=status.payload.get("license_id"),
                               detail={"from": before, "to": status.state}, remote_addr=request.remote_addr)
    db.commit()
    flash(_("License key saved. The license is now: %(state)s.", state=_(state.LABELS[status.state])), "success")
    return True
