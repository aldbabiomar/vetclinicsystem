"""
The install's license: where it is kept, and what state it is in
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §5.2-§6).

The key lives in `<data dir>/license/license.key` -- not the database, so a
restored backup cannot roll it back and it never travels in a backup, an
export or a support bundle (A4). Beside it, `state.json` keeps the latest
moment the app has seen, mirrored in the settings table; the later of the two
counts. A clock more than a day behind it is a clock wound back.

The state is worked out at start-up, at every sign-in, after a key is
entered and on the daily tick, and cached here. An invalid or missing license
never stops the app from starting; it only sets the state.
"""
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import timedelta

from vcs import clock, config, paths
from vcs.licensing import tokens
from vcs.messages import Msg, N_

ACTIVE, EXPIRING, GRACE, READ_ONLY = "active", "expiring", "grace", "read_only"
INVALID, MISSING, CLOCK_WRONG = "invalid", "missing", "clock_wrong"
WRITABLE = frozenset({ACTIVE, EXPIRING, GRACE})
CLOCK_SLACK = timedelta(hours=24)          # time-zone and NTP corrections
MAX_SEEN_SETTING = "license_max_seen_at"

# What a person reads for each state.
LABELS = {
    ACTIVE: N_("Active"),
    EXPIRING: N_("Expiring soon"),
    GRACE: N_("Expired, in its grace period"),
    READ_ONLY: N_("Read-only"),
    INVALID: N_("Not valid"),
    MISSING: N_("No license key"),
    CLOCK_WRONG: N_("The computer's clock is wrong"),
}


@dataclass
class Status:
    state: str
    message: str = ""                      # a messages.Msg when there is one
    payload: dict = field(default_factory=dict)
    expires_at: object = None              # aware datetimes
    read_only_from: object = None
    days_left: int = None

    @property
    def writable(self):
        return self.state in WRITABLE


_cached = None
_lock = threading.Lock()


def license_dir():
    """<data dir>/license, or <checkout>/license without a data dir -- the
    same fallback the error log uses."""
    return os.path.join(config.DATA_DIR or paths.ROOT, "license")


def _key_path():
    return os.path.join(license_dir(), "license.key")


def _state_path():
    return os.path.join(license_dir(), "state.json")


def _write_atomically(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def stored_key():
    try:
        with open(_key_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _max_seen(db):
    seen = []
    try:
        with open(_state_path(), encoding="utf-8") as f:
            seen.append(clock.parse(json.load(f)["max_seen_at"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if db is not None:
        row = db.execute("SELECT value FROM settings WHERE key=%s", (MAX_SEEN_SETTING,)).fetchone()
        try:
            if row and row["value"]:
                seen.append(clock.parse(row["value"]))
        except (TypeError, ValueError):
            pass
    return max(seen) if seen else None


def _remember_seen(db, moment):
    stamp = moment.isoformat()
    try:
        _write_atomically(_state_path(), json.dumps({"max_seen_at": stamp}))
    except OSError:
        pass                                # the database copy still holds it
    if db is not None:
        db.execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                   "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (MAX_SEEN_SETTING, stamp))


def evaluate(db=None, now=None, key=None):
    """The license's state now. Records the latest moment seen (§5.3); the
    caller commits, as with any helper."""
    now = now or clock.now()
    key = key if key is not None else stored_key()
    if not key:
        return Status(MISSING, Msg(N_(
            "This installation has no license key. Ask your vendor for one, then enter it on the "
            "License page.")))
    try:
        payload = tokens.verify(key, tokens.LICENSE, config.INSTALL_ID, now)
    except tokens.TokenError as e:
        return Status(INVALID, e.message)
    seen = _max_seen(db)
    if seen is not None and now < seen - CLOCK_SLACK:
        return Status(CLOCK_WRONG, Msg(N_(
            "This computer's clock is behind the time the app last saw. Correct the date and "
            "time, then sign in again.")), payload)
    if seen is None or now > seen:
        _remember_seen(db, now)
    expires = clock.parse(payload["expires_at"])
    read_only_from = expires + timedelta(days=payload["grace_days"])
    days_left = (expires - now).days
    if now < expires - timedelta(days=payload["warn_days"]):
        state = ACTIVE
    elif now < expires:
        state = EXPIRING
    elif now < read_only_from:
        state = GRACE
    else:
        state = READ_ONLY
    return Status(state, "", payload, expires, read_only_from, days_left)


def refresh(db=None, now=None):
    """Work the state out again and cache it: every session sees a renewal at
    once (§6.2)."""
    global _cached
    status = evaluate(db, now)
    with _lock:
        _cached = status
    return status


def current(db=None):
    """The cached state, worked out on first use."""
    return _cached if _cached is not None else refresh(db)


def enter_key(db, key, now=None):
    """Store a pasted key -- if, and only if, it verifies for this install.
    The new status is cached at once. Raises tokens.TokenError otherwise, and
    nothing is written."""
    now = now or clock.now()
    key = "".join(str(key or "").split())
    tokens.verify(key, tokens.LICENSE, config.INSTALL_ID, now)
    _write_atomically(_key_path(), key + "\n")
    return refresh(db, now)
