"""
The developer's session (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §7).

A Developer Pass, once verified, puts `developer = {name, pass_id,
expires_at}` in the session -- beside any clinic user's sign-in, never
instead of it. It ends at the pass's expiry, on /developer/logout, or when
the session does. No role or permission reaches it: there is no `developer`
permission (tests/test_developer_access.py holds that).
"""
from functools import wraps

from flask import redirect, request, session, url_for

from vcs import clock

KEY = "developer"


def start(payload):
    session[KEY] = {"name": payload["developer"], "pass_id": payload["pass_id"],
                    "expires_at": payload["expires_at"]}


def end():
    session.pop(KEY, None)


def current():
    """The signed-in developer, or None once the pass has run out."""
    dev = session.get(KEY)
    if not dev:
        return None
    try:
        expired = clock.now() >= clock.parse(dev["expires_at"])
    except (KeyError, TypeError, ValueError):
        expired = True
    if expired:
        end()
        return None
    return dev


def required(view):
    """A Developer page: only for a developer session, whoever else is
    signed in -- the clinic's Admin included."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current() is None:
            return redirect(url_for("developer.login", next=request.path))
        return view(*args, **kwargs)
    wrapper.vz_developer = True
    return wrapper
