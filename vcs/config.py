"""
The install's configuration: its .env, and the settings read from the
environment.

The package imports this module first (vcs/__init__.py), so .env is loaded
before any module reads os.environ -- several read it at import time (the
pool's DATABASE_URL, the updater's GITHUB_REPO, core's
DB_REQUEST_TIMEOUT_SECONDS). No module has to be "imported after
load_dotenv()" any more.

On the versioned-release layout (VETCLINICSYSTEM_DATA_DIR set by the
launcher -- see updater.py / setup.py --enable-updates) .env lives in the
data dir, not beside the code: an update replaces the code's folder, and its
working directory at launch is not guaranteed. Otherwise load_dotenv()'s
normal upward search. load_dotenv() never overrides a variable that is
already set, which is how the tests and the isolated test env pass theirs.
"""
import os
import time

from dotenv import load_dotenv

DATA_DIR = os.environ.get("VETCLINICSYSTEM_DATA_DIR")
if DATA_DIR:
    load_dotenv(os.path.join(DATA_DIR, ".env"))
else:
    load_dotenv()

# When this process started, for the heartbeat's uptime figure. Monotonic,
# so a clock change does not bend it.
STARTED_MONOTONIC = time.monotonic()

# ---------------------------------------------------------------------------
# Network/session hardening — this app binds to every interface on the LAN
# by default (see listen_host() below), which is fine for a single-clinic
# deployment as long as it's paired with real compensating controls. None of
# this changes default behavior for an operator who doesn't configure
# anything: every knob below is opt-in via environment variable, same as
# .env.example already does for SECRET_KEY etc.
# ---------------------------------------------------------------------------

# If a reverse proxy (nginx/Caddy/etc) is terminating TLS in front of this
# app, set BEHIND_TLS_PROXY=1 so Flask (a) trusts the proxy's
# X-Forwarded-For/X-Forwarded-Proto/X-Forwarded-Host headers for the real
# client IP and scheme instead of the proxy's own, and (b) marks the
# session cookie Secure (browsers refuse to send Secure cookies over plain
# HTTP, so this must stay off for a plain-HTTP LAN deployment — Waitress
# itself doesn't terminate TLS, by its own design, so TLS here always means
# "there's a reverse proxy in front", never "pass Waitress a certificate").
BIND_PORT = int(os.environ.get("VETCLINICSYSTEM_PORT", "5050"))
BEHIND_TLS_PROXY = os.environ.get("BEHIND_TLS_PROXY") == "1"

# A login session's server-enforced expiry. session.permanent is set at a
# successful login, so PERMANENT_SESSION_LIFETIME actually takes effect —
# without it a session lasted "until the browser drops the cookie", which
# never happens on a front-desk machine left open for a whole shift.
SESSION_LIFETIME_HOURS = float(os.environ.get("SESSION_LIFETIME_HOURS", "12"))

# Max size for any incoming request body (mainly file uploads — X-rays,
# bloodwork PDFs, etc). 100 MB gives generous headroom for a large scan
# while still blocking accidental/abusive multi-GB uploads from filling
# the clinic machine's disk. Flask turns anything over this into a 413,
# handled with a friendly flash instead of a raw error page (errors.py).
MAX_UPLOAD_MB = 100


def secret_key():
    """SECRET_KEY, refusing to start without a real one. The unset check
    alone doesn't catch someone hand-copying .env.example to .env instead of
    running setup.py (which is what actually replaces the placeholder with a
    real random key) — that would otherwise boot fine with a well-known,
    publicly-visible-in-source-control value signing every session cookie and
    CSRF token."""
    key = os.environ.get("SECRET_KEY")
    if not key or key == "change-me":
        raise SystemExit(
            "SECRET_KEY is not set (or still the placeholder value). Copy "
            ".env.example to .env (setup.py does this for you, with a real "
            "random key) before starting the app."
        )
    return key


def listen_host(dev):
    """The address the server listens on. The clinic's server: every
    interface by default (VETCLINICSYSTEM_HOST overrides), so the other
    workstations can reach it. Dev mode: this computer only, always (audit
    S4) — it runs Werkzeug's debugger, whose console executes Python for
    anyone who gets past its PIN, and on 0.0.0.0 that was anyone on the LAN."""
    if dev:
        return "127.0.0.1"
    return os.environ.get("VETCLINICSYSTEM_HOST", "0.0.0.0")
