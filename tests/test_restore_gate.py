"""
While a backup is being restored, nothing else touches the database
(audit S3).

The restore dropped and reloaded every table while the app went on serving
the other workstations from them: a POS sale in that window either failed
or wrote a row the restore then collided with, and pg_restore could stop
half way, leaving old and restored tables mixed. Now every request but the
restoring admin's progress poll gets a 503 page that reads no table, and
pg_restore runs as one transaction.
"""
import pytest

import backup
import db as dbmod
from conftest import needs_db


@pytest.fixture
def restoring(monkeypatch):
    """A restore in progress — and any database access an error, so a test
    passes only if the request never reached for a table."""
    def no_database(*a, **k):
        raise AssertionError("a request touched the database during a restore")
    monkeypatch.setattr(dbmod, "getconn", no_database)
    backup.restore_in_progress.set()
    yield
    backup.restore_in_progress.clear()


@needs_db
@pytest.mark.parametrize("method,url", [("GET", "/"), ("GET", "/visits"), ("POST", "/pos/checkout"),
                                        ("GET", "/login"), ("POST", "/settings")])
def test_every_page_waits_for_the_restore(client, restoring, method, url):
    """GUARD."""
    resp = client.open(url, method=method, data={})
    assert resp.status_code == 503, (url, resp.status_code)
    assert "Restoring a backup" in resp.get_data(as_text=True)
    assert resp.headers.get("Retry-After")


@needs_db
def test_the_restoring_admins_progress_poll_still_answers(client, restoring):
    """The progress bar of the person who started the restore keeps moving:
    answered from the session and the in-memory job, not a table."""
    resp = client.get("/settings/job-status?job_id=not-a-job")
    assert resp.status_code == 404 and resp.get_json() == {"status": "not_found"}


@needs_db
def test_static_files_still_load(client, restoring):
    assert client.get("/static/style.css").status_code == 200


@needs_db
def test_control_pages_are_served_when_no_restore_is_running(client):
    assert not backup.restore_in_progress.is_set()
    assert client.get("/").status_code == 200


def test_the_flag_is_set_for_the_restore_and_cleared_after_even_on_failure(monkeypatch):
    seen = []

    def failing_restore(*a, **k):
        seen.append(backup.restore_in_progress.is_set())
        raise RuntimeError("pg_restore exploded")

    monkeypatch.setattr(backup, "_run_restore_locked", failing_restore)
    try:
        with pytest.raises(RuntimeError):
            backup.run_restore(lambda: None, "/nowhere.dump")
        assert seen == [True], "the gate was not up while the restore ran"
        assert not backup.restore_in_progress.is_set(), "the gate stayed up after the restore ended"
    finally:
        backup.restore_in_progress.clear()   # a failure here must not 503 every later test


class _FakeProc:
    returncode = 0


@pytest.mark.parametrize("local_tools", [True, False])
def test_pg_restore_runs_as_one_transaction(monkeypatch, local_tools):
    """GUARD. All of the restore or none of it — with the local client tools
    and through the Docker fallback alike."""
    commands = []
    monkeypatch.setattr(backup.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if (name == "pg_restore") == local_tools or name == "docker" else None)
    monkeypatch.setattr(backup, "_pg_restore_toc_count", lambda cmd: 1)
    monkeypatch.setattr(backup, "_stream_restore_progress", lambda proc, total, on_count: "")
    monkeypatch.setattr(backup.subprocess, "Popen", lambda cmd, **k: commands.append(cmd) or _FakeProc())
    monkeypatch.setattr(backup.subprocess, "run", lambda *a, **k: None)
    backup._run_pg_restore("/tmp/x.dump")
    restore_cmd = [c for c in commands if "pg_restore" in c]
    assert restore_cmd and "--single-transaction" in restore_cmd[0], commands


# ---------------------------------------------------------------------------
# Audit S4 — dev mode's debugger listens on this computer only
# ---------------------------------------------------------------------------

def test_dev_mode_listens_on_this_computer_only_whatever_the_setting(monkeypatch):
    """GUARD. Werkzeug's debugger console runs Python for anyone past its
    PIN; bound to 0.0.0.0 that was anyone on the clinic network."""
    import app as app_module
    monkeypatch.setenv("VETCLINICSYSTEM_HOST", "0.0.0.0")
    assert app_module.listen_host(dev=True) == "127.0.0.1"


def test_control_the_clinic_server_listens_where_it_is_told(monkeypatch):
    import app as app_module
    monkeypatch.setenv("VETCLINICSYSTEM_HOST", "0.0.0.0")
    assert app_module.listen_host(dev=False) == "0.0.0.0"
    monkeypatch.delenv("VETCLINICSYSTEM_HOST")
    assert app_module.listen_host(dev=False) == "0.0.0.0"
