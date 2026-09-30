"""
The settings only the vendor changes (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md
§9, §11.5, owner decisions L-2, L-3): the money setting, the colour palette,
the monitoring ping URL and the vendor's message. The Developer area writes
them through these functions, which carry the rules they always had -- the
money setting's lock, the palette registry, the ping URL's https and its
secrecy in the change log.

POST /settings refuses these keys from anyone, the clinic's system Admin
included: they are gated `developer` in SETTING_FIELD_PERMISSION, and no one
holds that, because it is not a permission.
"""
from flask_babel import gettext as _

from vcs import auth, money
from vcs.domain import settings, vendor_message
from vcs.web import palettes
from vcs.web.core import strict_date

DEVELOPER = "developer"          # a gate in the settings registry, not a permission
KEYS = (money.SETTING_KEY, "theme_palette", "heartbeat_url", *vendor_message.KEYS)


class Refused(ValueError):
    """A value the rules refuse; str() is the message to show."""


def _store(db, key, value):
    db.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
               "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))


def save_money_setting(db, value, actor=None):
    """(old code, new code) when it changed, else None. Changeable only
    while no money has been recorded: after that, switching would
    reinterpret every stored amount in another currency."""
    value = (value or "").strip().upper()
    if value not in money.SETTINGS:
        raise Refused(_("Not a valid money setting."))
    current = money.current().code if money.current() else None
    if value == current:
        return None
    if current is not None and money.is_locked(db):
        raise Refused(_("The money setting can't be changed once money has been recorded — "
                        "every stored amount is in %(currency)s.", currency=money.current().currency))
    _store(db, money.SETTING_KEY, value)
    auth.log_change(db, "settings", money.SETTING_KEY, "update", {money.SETTING_KEY: (current, value)},
                    actor=actor)
    return current, value


def save_palette(db, value, actor=None):
    """(old, new) when it changed, else None. Only the registry's palettes
    have CSS behind them."""
    if not palettes.is_palette(value):
        raise Refused(_("Not a valid color palette."))
    old = settings.get_setting(db, "theme_palette")
    if old == value:
        return None
    _store(db, "theme_palette", value)
    auth.log_change(db, "settings", "theme_palette", "update", {"theme_palette": (old, value)}, actor=actor)
    return old, value


def _secret_state(value):
    return "set" if (value or "").strip() else "not set"


def save_heartbeat_url(db, value, actor=None):
    """("set"/"not set", same) when it changed, else None. The URL is a
    credential -- anyone holding it can send a fake ping and silence the
    alert that fires when this machine goes dark -- so it is https or
    nothing, and the change log records that it changed, never the value."""
    value = (value or "").strip()
    if value and not value.lower().startswith("https://"):
        raise Refused(_("The monitoring ping URL must start with https://"))
    old = settings.get_setting(db, "heartbeat_url") or ""
    if old == value:
        return None
    _store(db, "heartbeat_url", value)
    change = (_secret_state(old), _secret_state(value))
    auth.log_change(db, "settings", "heartbeat_url", "update", {"heartbeat_url": change}, actor=actor)
    return change


def save_vendor_message(db, text, level, expires_at, enabled):
    """{"text", "level", "expires_at", "enabled"} as saved, or None when
    nothing changed. Plain text, at most MAX_LENGTH characters; an enabled
    message needs some."""
    text = (text or "").strip()
    expires_at = (expires_at or "").strip()
    if level not in vendor_message.LEVELS:
        raise Refused(_("Not a valid message level."))
    if len(text) > vendor_message.MAX_LENGTH:
        raise Refused(_("The message is longer than %(n)s characters.", n=vendor_message.MAX_LENGTH))
    if enabled and not text:
        raise Refused(_("Write the message before turning it on."))
    if expires_at:
        try:
            expires_at = strict_date(expires_at).isoformat()
        except ValueError:
            raise Refused(_("Not a valid date."))
    new = {"text": text, "level": level, "expires_at": expires_at, "enabled": bool(enabled)}
    if new == vendor_message.stored(db):
        return None
    _store(db, vendor_message.TEXT, text)
    _store(db, vendor_message.LEVEL, level)
    _store(db, vendor_message.EXPIRES, expires_at)
    _store(db, vendor_message.ENABLED, "1" if enabled else "0")
    return new


def clear_vendor_message(db):
    """True when there was something to clear."""
    return db.execute("DELETE FROM settings WHERE key = ANY(%s)",
                      (list(vendor_message.KEYS),)).rowcount > 0
