"""
Verifying a license or a Developer Pass (plan §4).

    VCS1.<base64url(payload bytes)>.<base64url(signature)>

The signature covers the payload's exact bytes, and it is checked against the
trusted keys BEFORE the payload is read as anything, so no field of a token
is believed until the signature says it may be. Nothing is re-serialised, so
there is nothing to canonicalise.

A refusal is a TokenError whose `message` is a messages.Msg: English where it
is logged, the clinic's language where it is shown. None of them says more
than the person pasting the key needs.
"""
import base64
import binascii
import json
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from vcs.licensing.trusted_keys import TRUSTED_KEYS
from vcs.messages import Msg, N_

PREFIX = "VCS1"
LICENSE, DEV_PASS = "license", "dev_pass"
MAX_PASS_HOURS = 12                         # plan A2, whatever the pass says
PASS_FUTURE_SLACK = timedelta(minutes=10)   # a pass issued "later" than this is a clock problem

_REQUIRED = {
    LICENSE: {"v": int, "kind": str, "kid": str, "install_id": str, "license_id": str,
              "clinic_name": str, "issued_at": str, "expires_at": str,
              "grace_days": int, "warn_days": int, "entitlements": dict},
    DEV_PASS: {"v": int, "kind": str, "kid": str, "install_id": str, "pass_id": str,
               "developer": str, "issued_at": str, "expires_at": str},
}

# Keys trusted for the test suite and the test environment's launcher only.
_TEST_KEYS = {}


class TokenError(ValueError):
    """A token refused. `code` names the reason for tests and logs;
    `message` is what a person is shown."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def trust_for_tests(kid, public_key_bytes):
    """Trust a key for the rest of this process. For tests/conftest.py and
    scripts/test_launcher.py only; no production entry point calls it."""
    _TEST_KEYS[kid] = bytes(public_key_bytes)


def _trusted():
    return {**TRUSTED_KEYS, **_TEST_KEYS}


def _b64decode(text):
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise TokenError("malformed", Msg(N_(
            "This is not a VetClinicSystem key. Check that all of it was copied.")))


def _moment(value):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        moment = None
    if moment is None or moment.tzinfo is None:
        raise TokenError("fields", Msg(N_(
            "This key is missing information it needs. Ask your vendor for a new one.")))
    return moment


def _signed_payload(token):
    """The payload bytes of a token whose signature a trusted key made, and
    that key's kid."""
    text = "".join(str(token or "").split())       # keys arrive through WhatsApp
    parts = text.split(".")
    if len(parts) != 3 or not all(parts[1:]):
        raise TokenError("malformed", Msg(N_(
            "This is not a VetClinicSystem key. Check that all of it was copied.")))
    if parts[0] != PREFIX:
        raise TokenError("version", Msg(N_(
            "This key is for a different version of VetClinicSystem.")))
    payload, signature = _b64decode(parts[1]), _b64decode(parts[2])
    for kid, public in _trusted().items():
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(signature, payload)
            return payload, kid
        except (InvalidSignature, ValueError):
            continue
    # No trusted key made this signature. Which message to show is the only
    # thing the payload is read for, and nothing in it is acted on.
    try:
        claimed = json.loads(payload).get("kid")
    except (ValueError, AttributeError):
        claimed = None
    if claimed is not None and claimed not in _trusted():
        raise TokenError("unknown_key", Msg(N_(
            "This key was signed by a key this version of VetClinicSystem does not "
            "know. Ask your vendor for a new one.")))
    raise TokenError("signature", Msg(N_(
        "This key has been changed or damaged: it does not match its signature. "
        "Paste it again, or ask your vendor for a new one.")))


def verify(token, kind, install_id, now):
    """The payload of `token` -- a license or a Developer Pass for this
    install -- or a TokenError. `now` is the clinic clock's (clock.now()).

    A license past its expiry still verifies: expiry is a state (warning,
    grace, read-only), decided by the caller. A pass past its expiry does
    not: it opens nothing once it has run out."""
    payload_bytes, kid = _signed_payload(token)
    try:
        payload = json.loads(payload_bytes)
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or payload.get("kid") != kid:
        raise TokenError("fields", Msg(N_(
            "This key is missing information it needs. Ask your vendor for a new one.")))
    if payload.get("kind") != kind:
        raise TokenError("kind", Msg(
            N_("This is a Developer Pass, not a license key.") if kind == LICENSE
            else N_("This is a license key, not a Developer Pass.")))
    for field, typ in _REQUIRED[kind].items():
        value = payload.get(field)
        if not isinstance(value, typ) or isinstance(value, bool) or value == "":
            raise TokenError("fields", Msg(N_(
                "This key is missing information it needs. Ask your vendor for a new one.")))
    if payload["v"] != 1:
        raise TokenError("version", Msg(N_(
            "This key is for a different version of VetClinicSystem.")))
    if payload["install_id"] != install_id:
        raise TokenError("install", Msg(N_(
            "This key is for another installation (%(theirs)s). This installation's ID "
            "is %(ours)s."), theirs=payload["install_id"], ours=install_id or "—"))
    issued, expires = _moment(payload["issued_at"]), _moment(payload["expires_at"])
    if expires <= issued:
        raise TokenError("fields", Msg(N_(
            "This key is missing information it needs. Ask your vendor for a new one.")))
    if kind == LICENSE:
        if payload["grace_days"] < 0 or payload["warn_days"] < 0:
            raise TokenError("fields", Msg(N_(
                "This key is missing information it needs. Ask your vendor for a new one.")))
        return payload
    if expires - issued > timedelta(hours=MAX_PASS_HOURS):
        raise TokenError("too_long", Msg(N_(
            "This Developer Pass lasts longer than %(hours)s hours, which is not allowed."),
            hours=MAX_PASS_HOURS))
    if issued > now + PASS_FUTURE_SLACK:
        raise TokenError("future", Msg(N_(
            "This Developer Pass was issued in the future. Check this computer's clock.")))
    if now >= expires:
        raise TokenError("expired", Msg(N_("This Developer Pass has expired.")))
    return payload
