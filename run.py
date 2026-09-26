"""
Start VetClinicSystem: `python3 run.py`.

Checks the database answers, starts the scheduler, tidies what a killed run
left behind, and serves the app with Waitress on the clinic network
(VETCLINICSYSTEM_DEV=1: Flask's debug server, on this computer only).
"""
import os
import signal
import sys
import traceback

from vcs import config, create_app
from vcs.db import pool as dbmod
from vcs.errorlog import error_logger
from vcs.web.core import lan_address


def _check_database():
    try:
        probe = dbmod.connect()
        probe.execute("SELECT 1 FROM settings LIMIT 1")
        probe.close()
    except Exception as e:
        raise SystemExit(
            f"Could not reach the Postgres database ({e}).\n"
            "Run: python3 setup.py first."
        )


def _start_scheduler():
    try:
        from vcs.ops import scheduler
        scheduler.start(get_db=dbmod.connect, close_db=lambda c: c.close())
    except Exception:
        # A scheduler failure should never take the whole app down — the
        # front desk still needs to open. See ERROR_500_AUDIT.md E-01.
        error_logger.error("Nightly backup scheduler failed to start:\n" + traceback.format_exc())
        print("  !! Nightly backups are NOT scheduled — see logs/errors.log. The app will still run.")


def _boot_housekeeping():
    try:
        from vcs.ops import backup
        conn = dbmod.connect()
        try:
            reaped = backup.reap_stale_running(conn)
            if reaped:
                print(f"  Reaped {reaped} stale 'running' backup log row(s) from an earlier, killed run.")
        finally:
            conn.close()
        # Makes "no restore has happened" provable rather than assumed —
        # see ORPHANED_RECORDS_AUDIT.md F-20.
        backup.ensure_no_restore_marker()
    except Exception:
        error_logger.error("Boot-time backup/restore-marker housekeeping failed:\n" + traceback.format_exc())


def _graceful_shutdown(signum, frame):
    """
    Runs on SIGTERM/SIGINT (Ctrl-C)/SIGBREAK — sent by the OS on
    shutdown/restart/logout, or by a person closing the launcher window.
    Every write this app makes is already committed per-request (see
    close_db() in vcs/web/hooks.py), so there's no in-flight "unsaved"
    transaction sitting on the server side to lose here. What this actually
    guards against is Postgres (running in Docker or as a local service)
    getting killed abruptly in the same shutdown sequence with nothing
    recent to fall back on — so: take one more backup as a last safety net,
    then exit cleanly instead of being hard-killed mid-request.
    """
    print("\nVetClinicSystem is shutting down — taking a final backup first...")
    try:
        db = dbmod.connect()
        try:
            from vcs.ops import backup
            ok, message = backup.run_backup(db, triggered_by="shutdown")
            print(message if ok else f"Final backup failed: {message}")
        finally:
            db.close()
    except Exception as e:
        print(f"Could not take a final backup during shutdown: {e}")
    # Closes every pooled connection cleanly rather than letting them
    # get dropped mid-socket-close when the process exits.
    dbmod.close_pool()
    sys.exit(0)


def main():
    app = create_app()
    _check_database()
    _start_scheduler()
    _boot_housekeeping()

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    # Windows sends SIGBREAK (not SIGTERM) for Ctrl-Break / console-close —
    # SIGTERM delivery there is only reliable when running as a proper
    # Windows service, which this app doesn't. SIGINT (Ctrl-C) already
    # works the same on both platforms.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _graceful_shutdown)

    # Bind address/port configurable instead of hardcoded — default
    # 0.0.0.0:5050. BEHIND_TLS_PROXY is how this app supports HTTPS: via a
    # reverse proxy in front, not by binding Waitress to a different scheme.
    dev = os.environ.get("VETCLINICSYSTEM_DEV") == "1"
    host = config.listen_host(dev)
    scheme = "https" if config.BEHIND_TLS_PROXY else "http"

    if dev:
        # Flask's dev server — convenient for local debugging only; not used
        # for normal clinic operation.
        app.run(debug=True, host=host, port=config.BIND_PORT)
    else:
        from waitress import serve
        print("VetClinicSystem is running — reachable on the clinic network at "
              f"{scheme}://{lan_address()}:{config.BIND_PORT}")
        serve(app, host=host, port=config.BIND_PORT, threads=8)


if __name__ == "__main__":
    main()
