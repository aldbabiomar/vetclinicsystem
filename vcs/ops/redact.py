"""
Redaction, for text that leaves the clinic's computer or is shown in the
Developer area: the support bundle and the error-log tail on Developer ->
System (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11.1-§11.2, §13).

`text()` removes, wherever they appear: this install's own secrets, by value
(the database password, SECRET_KEY, the update token, the license key, the
monitoring ping URL); anything shaped like a token (`ghp_…`, `github_pat_…`,
`VCS1.…`); the credentials in a URL; e-mail addresses; and runs of digits
long enough to be a phone number. `log()` does that and, on a log's message
lines, also removes quoted literals and the values PostgreSQL quotes in an
error's DETAIL -- a failed insert can quote a patient's or an owner's name.

It is a net, not a proof: a name written into a message without quotes gets
through. That is why the bundle carries no clinic data to begin with, and
why its README tells the clinic it may read the ZIP before sending it.
"""
import os
import re
from urllib.parse import unquote, urlsplit

MARK = "[redacted]"

TOKEN_SHAPES = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|VCS1\.[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)")
URL_CREDENTIALS = re.compile(r"\b([a-z][a-z0-9+.\-]*://)[^\s/@:]+(?::[^\s/@]*)?@", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b")
# Seven digits or more, optionally led by + and broken by single spaces or
# dashes -- but not a date (2026-09-30), which would otherwise match.
PHONE = re.compile(r"(?<![\w\-+])(?!\d{4}-\d{2}-\d{2})\+?\d(?:[ \-]?\d){6,}(?![\w\-])")
# PostgreSQL's DETAIL: `Key (name)=(Bella) already exists.` and
# `Failing row contains (12, Bella, …).`
PG_DETAIL = re.compile(r"(Key \([^)]*\)=\().*?(\) (?:already exists|is not present|conflicts))|"
                       r"(Failing row contains \().*(\))")
QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")

# A value shorter than this is left to the patterns: replacing every "test"
# in a log would redact the log, not the secret.
MIN_SECRET_LENGTH = 6


def known_secrets(db=None):
    """This install's secret values, as they are configured now."""
    values = [os.environ.get("SECRET_KEY") or ""]
    try:
        values.append(unquote(urlsplit(os.environ.get("DATABASE_URL") or "").password or ""))
    except ValueError:
        pass
    try:
        from vcs.ops import updater
        values.append(updater.read_token() or "")
    except Exception:
        pass
    try:
        from vcs.licensing import state
        with open(state._key_path(), encoding="utf-8") as f:
            values.append(f.read().strip())
    except OSError:
        pass
    if db is not None:
        from vcs.domain import settings
        for key in settings.SECRET_KEYS:
            values.append(settings.get_setting(db, key) or "")
    return sorted({v for v in values if len(v) >= MIN_SECRET_LENGTH}, key=len, reverse=True)


def text(value, secrets=()):
    """Every rule except quoted literals, which would empty a JSON file."""
    for secret in secrets:
        value = value.replace(secret, MARK)
    value = TOKEN_SHAPES.sub(MARK, value)
    value = URL_CREDENTIALS.sub(lambda m: m.group(1) + MARK + "@", value)
    value = EMAIL.sub(MARK, value)
    return PHONE.sub(MARK, value)


def structure(value, secrets=()):
    """`text()` on every string inside a JSON-shaped value, so the file it
    becomes is still JSON. Numbers are left as numbers: a byte count or a
    version is not a phone number, and no number in a bundle comes from a
    clinic record."""
    if isinstance(value, str):
        return text(value, secrets)
    if isinstance(value, dict):
        return {k: structure(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [structure(v, secrets) for v in value]
    return value


def _message_line(line):
    """A log's own words, as opposed to a traceback's frames and source
    lines, which are indented and name files in quotes worth keeping."""
    line = PG_DETAIL.sub(lambda m: (m.group(1) or m.group(3)) + MARK + (m.group(2) or m.group(4)), line)
    return QUOTED.sub(lambda m: m.group(0)[0] + MARK + m.group(0)[0], line)


def log(value, secrets=()):
    value = text(value, secrets)
    return "\n".join(line if line[:1].isspace() else _message_line(line) for line in value.split("\n"))


def tail(path, lines=500):
    """The last `lines` lines of a text file, or "" when there is none."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""
