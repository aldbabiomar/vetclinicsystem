"""
The vendor's message to the clinic (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md
§11.5, A13): one plain-text message, a level, and a last day to show it, set
in the Developer area and shown at the top of every page, labelled as coming
from the vendor. Plain text, escaped like any other text: it is never HTML.
"""
from datetime import date

from vcs import clock
from vcs.domain import settings

TEXT = "vendor_message_text"
LEVEL = "vendor_message_level"
EXPIRES = "vendor_message_expires_at"     # a date: shown through the end of that day
ENABLED = "vendor_message_enabled"        # "1" / "0": turned off, the text is kept
KEYS = (TEXT, LEVEL, EXPIRES, ENABLED)

LEVELS = ("info", "warning")
MAX_LENGTH = 1000


def stored(db):
    """The message as saved, shown or not."""
    rows = {r["key"]: r["value"] for r in db.execute(
        "SELECT key, value FROM settings WHERE key = ANY(%s)", (list(KEYS),)).fetchall()}
    level = rows.get(LEVEL)
    return {"text": rows.get(TEXT) or "",
            "level": level if level in LEVELS else "info",
            "expires_at": rows.get(EXPIRES) or "",
            "enabled": rows.get(ENABLED) == "1"}


def expired(message, today=None):
    if not message["expires_at"]:
        return False
    try:
        return (today or clock.today()) > date.fromisoformat(message["expires_at"])
    except ValueError:
        return True          # a date that cannot be read shows nothing rather than forever


def current(db, today=None):
    """What the clinic sees now: the message, or None -- off, empty, or past
    its last day."""
    message = stored(db)
    if not message["enabled"] or not message["text"].strip() or expired(message, today):
        return None
    return message
