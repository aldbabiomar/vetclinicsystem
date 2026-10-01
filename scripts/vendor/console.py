#!/usr/bin/env python3
"""
The Vendor Console (docs/plans/VENDOR_CONSOLE_PLAN.md): the vendor's own web
app for licensing clinics -- a list of clinics and where each license stands,
new clinics with one setup code, renewals, Developer Passes, and making the
signing key the first time.

    python scripts/vendor/console.py [--data-dir ~/vcs-vendor-keys] [--port 5099]

It runs on the vendor's computer only and listens on 127.0.0.1. Every key
operation is vcs_vendor.py's, so the console and the command line cannot
drift. What it keeps -- the clinics, the licenses issued and the passes'
IDs -- is a SQLite file beside the key; a clinic's update token and ping URL
go into its setup code and are never written down here.

Because any web page open in the vendor's browser can send requests to
127.0.0.1, the console refuses a request for any other host name (DNS
rebinding), wants a CSRF token on every form, and holds the key only while
unlocked: in memory, until Lock or 30 idle minutes.
"""
import argparse
import errno
import os
import secrets
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import vcs_vendor  # noqa: E402
from flask import Flask, abort, flash, g, redirect, render_template, request, url_for  # noqa: E402
from flask_wtf.csrf import CSRFError, CSRFProtect  # noqa: E402

DEFAULT_DATA_DIR = "~/vcs-vendor-keys"
DEFAULT_PORT = 5099
IDLE_MINUTES = 30
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_PASS_HOURS = 12

SCHEMA = """
CREATE TABLE IF NOT EXISTS clinics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    install_id TEXT NOT NULL UNIQUE,
    money_setting TEXT,
    palette TEXT,
    time_zone TEXT NOT NULL,
    made_with TEXT NOT NULL,            -- 'setup code' | 'installed'
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    license_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    warn_days INTEGER NOT NULL,
    grace_days INTEGER NOT NULL,
    key_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    pass_id TEXT NOT NULL,
    developer TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

STATES = {  # what a license's dates mean today, as the clinic's app works it out
    "active": "Active", "expiring": "Expiring soon", "grace": "In grace", "read_only": "Read-only",
}


def license_state(expires_at, warn_days, grace_days, now):
    expires = datetime.fromisoformat(expires_at)
    if now < expires - timedelta(days=warn_days):
        return "active"
    if now < expires:
        return "expiring"
    if now < expires + timedelta(days=grace_days):
        return "grace"
    return "read_only"


def _money_settings():
    from vcs import money
    return [(code, s.name) for code, s in money.SETTINGS.items()]


def _palettes():
    from vcs.web import palettes
    return palettes.choices(), palettes.DEFAULT


def _trusted(kid):
    from vcs.licensing.trusted_keys import TRUSTED_KEYS
    return kid in TRUSTED_KEYS


def create_console(data_dir=DEFAULT_DATA_DIR, idle_minutes=IDLE_MINUTES):
    data_dir = vcs_vendor.refuse_inside_repo(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    ledger = data_dir / "console.sqlite3"
    if not ledger.exists():
        ledger.touch(mode=0o600)
    ledger.chmod(0o600)

    app = Flask(__name__, template_folder=str(HERE / "console_templates"),
                static_folder=str(HERE / "console_static"), static_url_path="/static")
    app.config.update(SECRET_KEY=secrets.token_hex(32), SESSION_COOKIE_SAMESITE="Strict",
                      WTF_CSRF_TIME_LIMIT=None, LEDGER=str(ledger), DATA_DIR=str(data_dir),
                      IDLE_SECONDS=idle_minutes * 60)
    app.key_state = {"key": None, "path": None, "last": 0.0}
    CSRFProtect(app)

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["LEDGER"])
            g.db.row_factory = sqlite3.Row
            g.db.executescript(SCHEMA)
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        con = g.pop("db", None)
        if con is not None:
            con.close()

    def setting(key, default=None):
        row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def put_setting(key, value):
        db().execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))

    def key_path():
        return setting("key_path") or str(data_dir / "signing.pem")

    def unlocked():
        return app.key_state["key"]

    def lock():
        app.key_state.update(key=None, path=None, last=0.0)

    # --- guards -------------------------------------------------------------
    @app.before_request
    def only_this_computer():
        """A page elsewhere can reach 127.0.0.1 through a name it controls
        (DNS rebinding); the browser then sends that name as Host."""
        host = request.host.rsplit(":", 1)[0] if not request.host.startswith("[") else request.host[1:].split("]")[0]
        if host not in LOOPBACK:
            abort(400)

    @app.before_request
    def lock_when_idle():
        state = app.key_state
        if state["key"] is not None:
            if time.monotonic() - state["last"] > app.config["IDLE_SECONDS"]:
                lock()
                flash("The key was locked after a quiet spell. Unlock it to carry on.", "info")
            else:
                state["last"] = time.monotonic()

    @app.after_request
    def headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; frame-ancestors 'none'; "
                                                   "form-action 'self'; base-uri 'none'")
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.errorhandler(CSRFError)
    def form_refused(_error):
        """A form without this session's token: one left open from before the
        console was last started (its tokens end with it), or one posted from
        another page. Refused either way; said plainly rather than as a bare
        "Bad Request"."""
        return render_template("refused.html"), 400

    def needs_key(view):
        def wrapper(*a, **kw):
            if not Path(key_path()).expanduser().exists():
                return redirect(url_for("start"))
            if not unlocked():
                return redirect(url_for("unlock", next=request.path))
            return view(*a, **kw)
        wrapper.__name__ = view.__name__
        return wrapper

    @app.context_processor
    def common():
        key = unlocked()
        kid = vcs_vendor.kid_for(vcs_vendor.public_bytes(key)) if key else None
        return {"unlocked": key is not None, "kid": kid, "kid_trusted": kid and _trusted(kid)}

    def when(args):
        """vcs_vendor's end date: the last second of that day at the clinic.
        Its refusals are SystemExit sentences; here they are shown."""
        if args.days is not None and args.days < 1:
            return None, "A license lasts at least 1 day."
        try:
            return vcs_vendor._expiry(args), None
        except SystemExit as e:
            return None, str(e)

    def issue_license(clinic, end, warn_days, grace_days):
        key = unlocked()
        payload = vcs_vendor.license_payload(key, clinic["install_id"], clinic["name"], end,
                                             grace_days=grace_days, warn_days=warn_days)
        text = vcs_vendor.sign(key, payload)
        db().execute("INSERT INTO licenses (clinic_id, license_id, issued_at, expires_at, warn_days, grace_days, "
                     "key_text) VALUES (?,?,?,?,?,?,?)",
                     (clinic["id"], payload["license_id"], payload["issued_at"], payload["expires_at"],
                      warn_days, grace_days, text))
        return text, payload

    def days_or_date(form):
        mode = form.get("length", "days")
        try:
            days = int(form.get("days") or 0)
        except ValueError:
            days = 0
        return SimpleNamespace(days=days if mode == "days" else None,
                               expires=form.get("expires", "") if mode == "date" else None,
                               time_zone=form.get("time_zone") or vcs_vendor.DEFAULT_TIME_ZONE)

    def windows(form):
        try:
            warn, grace = int(form.get("warn_days", 14)), int(form.get("grace_days", 14))
        except ValueError:
            return None, None, "Warning and grace are whole numbers of days."
        if warn < 0 or grace < 0:
            return None, None, "Warning and grace must be 0 days or more."
        return warn, grace, None

    def clinic_or_404(clinic_id):
        row = db().execute("SELECT * FROM clinics WHERE id=?", (clinic_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    # --- the key --------------------------------------------------------------
    @app.route("/start", methods=["GET", "POST"])
    def start():
        """First run: make the signing key, or point at the one there is."""
        if request.method == "POST":
            path = request.form.get("path", "").strip() or key_path()
            if request.form.get("action") == "existing":
                if not Path(path).expanduser().is_file():
                    flash(f"No file at {path}.", "error")
                    return redirect(url_for("start"))
                put_setting("key_path", path)
                db().commit()
                return redirect(url_for("unlock"))
            passphrase = request.form.get("passphrase", "")
            if passphrase != request.form.get("again", ""):
                flash("The two passphrases differ.", "error")
                return redirect(url_for("start"))
            try:
                kid, public = vcs_vendor.keygen(path, passphrase)
            except SystemExit as e:
                flash(str(e), "error")
                return redirect(url_for("start"))
            put_setting("key_path", path)
            db().commit()
            return render_template("key_made.html", path=path, kid=kid, public=public.hex())
        return render_template("start.html", path=key_path())

    @app.route("/unlock", methods=["GET", "POST"])
    def unlock():
        if not Path(key_path()).expanduser().exists():
            return redirect(url_for("start"))
        if request.method == "POST":
            try:
                key = vcs_vendor.load_key(key_path(), request.form.get("passphrase", ""))
            except SystemExit as e:
                flash(str(e), "error")
                return redirect(url_for("unlock", next=request.args.get("next", "")))
            app.key_state.update(key=key, path=key_path(), last=time.monotonic())
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("clinics"))
        return render_template("unlock.html", path=key_path())

    @app.route("/lock", methods=["POST"])
    def lock_now():
        lock()
        flash("Locked. The key is no longer in memory.", "info")
        return redirect(url_for("unlock"))

    @app.route("/key")
    @needs_key
    def key_page():
        public = vcs_vendor.public_bytes(unlocked())
        return render_template("key.html", path=key_path(), public=public.hex())

    # --- clinics ----------------------------------------------------------------
    @app.route("/")
    @needs_key
    def clinics():
        now = datetime.now(timezone.utc)
        rows = db().execute(
            "SELECT c.*, l.license_id, l.expires_at, l.warn_days, l.grace_days FROM clinics c "
            "LEFT JOIN licenses l ON l.id = (SELECT id FROM licenses WHERE clinic_id = c.id ORDER BY id DESC LIMIT 1) "
            "ORDER BY c.name").fetchall()
        listed = []
        for r in rows:
            state = (license_state(r["expires_at"], r["warn_days"], r["grace_days"], now)
                     if r["expires_at"] else None)
            ends = datetime.fromisoformat(r["expires_at"]).astimezone(ZoneInfo(r["time_zone"])) if r["expires_at"] else None
            listed.append({**dict(r), "state": state, "ends": ends})
        counts = {s: sum(1 for c in listed if c["state"] == s) for s in STATES}
        return render_template("clinics.html", clinics=listed, counts=counts, states=STATES)

    @app.route("/clinics/new", methods=["GET", "POST"])
    @needs_key
    def clinic_new():
        palette_choices, palette_default = _palettes()
        form = request.form
        if request.method == "POST":
            name = form.get("name", "").strip()
            money_setting = form.get("money_setting", "")
            palette = form.get("palette") or palette_default
            end, problem = when(days_or_date(form))
            warn, grace, window_problem = windows(form)
            token, ping = form.get("github_token", "").strip(), form.get("heartbeat_url", "").strip()
            problem = (problem or window_problem
                       or (not name and "Give the clinic's name.")
                       or (money_setting not in dict(_money_settings()) and "Choose IQ or JO.")
                       or (palette not in dict(palette_choices) and "Choose a palette from the list.")
                       or (ping and not ping.lower().startswith("https://")
                           and "The monitoring ping URL must start with https://"))
            if problem:
                flash(problem, "error")
                return render_template("clinic_new.html", form=form, money_settings=_money_settings(),
                                       palettes=palette_choices, palette_default=palette_default,
                                       default_zone=vcs_vendor.DEFAULT_TIME_ZONE), 400
            cur = db().execute(
                "INSERT INTO clinics (name, install_id, money_setting, palette, time_zone, made_with, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (name, str(uuid.uuid4()), money_setting, palette,
                 form.get("time_zone") or vcs_vendor.DEFAULT_TIME_ZONE, "setup code",
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            clinic = clinic_or_404(cur.lastrowid)
            text, payload = issue_license(clinic, end, warn, grace)
            db().commit()
            return _setup_code_page(clinic, text, token, ping)
        return render_template("clinic_new.html", form={}, money_settings=_money_settings(),
                               palettes=palette_choices, palette_default=palette_default,
                               default_zone=vcs_vendor.DEFAULT_TIME_ZONE)

    def _setup_code_page(clinic, license_text, token, ping):
        import setup
        code = setup.make_setup_code(license_text, clinic["money_setting"], clinic["palette"],
                                     github_token=token or None, heartbeat_url=ping or None)
        return render_template("shown_once.html", kind="setup", clinic=clinic, text=code,
                               has_secrets=bool(token or ping))

    @app.route("/clinics/installed", methods=["GET", "POST"])
    @needs_key
    def clinic_installed():
        """A clinic already set up with its own installation ID."""
        form = request.form
        if request.method == "POST":
            name, install_id = form.get("name", "").strip(), form.get("install_id", "").strip().lower()
            end, problem = when(days_or_date(form))
            warn, grace, window_problem = windows(form)
            try:
                valid_id = str(uuid.UUID(install_id)) == install_id
            except ValueError:
                valid_id = False
            problem = (problem or window_problem or (not name and "Give the clinic's name.")
                       or (not valid_id and "An installation ID is 36 characters: letters, digits and four dashes, "
                                            "as the clinic's License page shows it."))
            if not problem and db().execute("SELECT 1 FROM clinics WHERE install_id=?", (install_id,)).fetchone():
                problem = "That installation is already in the list: open it there to renew."
            if problem:
                flash(problem, "error")
                return render_template("clinic_installed.html", form=form,
                                       default_zone=vcs_vendor.DEFAULT_TIME_ZONE), 400
            cur = db().execute(
                "INSERT INTO clinics (name, install_id, time_zone, made_with, created_at) VALUES (?,?,?,?,?)",
                (name, install_id, form.get("time_zone") or vcs_vendor.DEFAULT_TIME_ZONE, "installed",
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            clinic = clinic_or_404(cur.lastrowid)
            text, _payload = issue_license(clinic, end, warn, grace)
            db().commit()
            return render_template("shown_once.html", kind="license", clinic=clinic, text=text)
        return render_template("clinic_installed.html", form={}, default_zone=vcs_vendor.DEFAULT_TIME_ZONE)

    @app.route("/clinics/<int:clinic_id>")
    @needs_key
    def clinic(clinic_id):
        row = clinic_or_404(clinic_id)
        now = datetime.now(timezone.utc)
        zone = ZoneInfo(row["time_zone"])
        licenses = [{**dict(l), "state": license_state(l["expires_at"], l["warn_days"], l["grace_days"], now),
                     "ends": datetime.fromisoformat(l["expires_at"]).astimezone(zone)}
                    for l in db().execute("SELECT * FROM licenses WHERE clinic_id=? ORDER BY id DESC",
                                          (clinic_id,)).fetchall()]
        passes = db().execute("SELECT * FROM passes WHERE clinic_id=? ORDER BY id DESC LIMIT 20",
                              (clinic_id,)).fetchall()
        # A renewal runs a year from where the last license ends, or from
        # today if that has passed, so renewing early costs the clinic nothing.
        base = max(licenses[0]["ends"].date(), now.astimezone(zone).date()) if licenses else now.astimezone(zone).date()
        renew_to = base.replace(year=base.year + 1) if not (base.month == 2 and base.day == 29) \
            else base.replace(year=base.year + 1, day=28)
        return render_template("clinic.html", clinic=row, licenses=licenses, passes=passes, states=STATES,
                               renew_to=renew_to.isoformat(), developer=setting("developer_name", ""))

    @app.route("/clinics/<int:clinic_id>/license", methods=["POST"])
    @needs_key
    def clinic_license(clinic_id):
        row = clinic_or_404(clinic_id)
        form = request.form
        args = SimpleNamespace(days=None, expires=form.get("expires", ""), time_zone=row["time_zone"])
        end, problem = when(args)
        warn, grace, window_problem = windows(form)
        if problem or window_problem:
            flash(problem or window_problem, "error")
            return redirect(url_for("clinic", clinic_id=clinic_id))
        text, _payload = issue_license(row, end, warn, grace)
        db().commit()
        return render_template("shown_once.html", kind="license", clinic=row, text=text)

    @app.route("/clinics/<int:clinic_id>/setup-code", methods=["POST"])
    @needs_key
    def clinic_setup_code(clinic_id):
        """A new setup code for a clinic made here that lost its first one:
        the latest license, and the secrets typed again (they are not kept)."""
        row = clinic_or_404(clinic_id)
        latest = db().execute("SELECT key_text FROM licenses WHERE clinic_id=? ORDER BY id DESC LIMIT 1",
                              (clinic_id,)).fetchone()
        ping = request.form.get("heartbeat_url", "").strip()
        if row["made_with"] != "setup code" or latest is None:
            flash("A setup code is for a clinic made here that has not been installed yet.", "error")
            return redirect(url_for("clinic", clinic_id=clinic_id))
        if ping and not ping.lower().startswith("https://"):
            flash("The monitoring ping URL must start with https://", "error")
            return redirect(url_for("clinic", clinic_id=clinic_id))
        return _setup_code_page(row, latest["key_text"], request.form.get("github_token", "").strip(), ping)

    @app.route("/clinics/<int:clinic_id>/pass", methods=["POST"])
    @needs_key
    def clinic_pass(clinic_id):
        row = clinic_or_404(clinic_id)
        developer = request.form.get("developer", "").strip()
        try:
            hours = float(request.form.get("hours", vcs_vendor.DEFAULT_PASS_HOURS))
        except ValueError:
            hours = 0
        if not developer or not 0 < hours <= MAX_PASS_HOURS:
            flash(f"Give your name, and between 1 and {MAX_PASS_HOURS} hours.", "error")
            return redirect(url_for("clinic", clinic_id=clinic_id))
        payload = vcs_vendor.pass_payload(unlocked(), row["install_id"], developer, hours=hours)
        text = vcs_vendor.sign(unlocked(), payload)
        db().execute("INSERT INTO passes (clinic_id, pass_id, developer, issued_at, expires_at) VALUES (?,?,?,?,?)",
                     (clinic_id, payload["pass_id"], developer, payload["issued_at"], payload["expires_at"]))
        put_setting("developer_name", developer)
        db().commit()
        return render_template("shown_once.html", kind="pass", clinic=row, text=text,
                               until=datetime.fromisoformat(payload["expires_at"]).astimezone(ZoneInfo(row["time_zone"])))

    return app


def serve(app, port=DEFAULT_PORT, open_browser=True):
    """On this computer only: the loopback address is not an option."""
    from waitress import serve as waitress_serve
    url = f"http://127.0.0.1:{port}/"
    print(f"Vendor Console: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    try:
        waitress_serve(app, host="127.0.0.1", port=port, threads=4)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(f"Port {port} is already in use. The console may already be running: {url}\n"
                         f"To start it on another port: --port {port + 1}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="The Vendor Console, on this computer only.")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help="the folder with the signing key and the console's records (outside the code)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    serve(create_console(args.data_dir), port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
