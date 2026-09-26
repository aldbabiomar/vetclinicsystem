"""
Audit B20's smaller items: two races with nothing to stop them.

  - Start Audit looked for today's draft and then created one, so two
    people pressing it at once got two drafts for one day. One draft per day
    is now a partial unique index, and the insert yields to it.
  - The login rate limiter's dict was updated from Waitress's 8 threads with
    no lock: its cleanup could meet a key another thread had just deleted.
"""
import threading
import time

from vcs import clock
from vcs.domain import logic
from conftest import ADMIN_ID, needs_db


def _drafts_today(db):
    return db.execute("SELECT id FROM audit_sessions WHERE audit_date=? AND status='Draft'",
                      (clock.today(),)).fetchall()


@needs_db
def test_two_people_starting_an_audit_at_once_get_one_draft(client, db, flask_app):
    """GUARD. The first Start is the test's own connection, not yet
    committed; the second is the route, from another thread. It must wait
    for the first, then open that same draft."""
    assert not _drafts_today(db), "a draft for today already exists — the test would prove nothing"
    out = {}
    try:
        with flask_app.test_request_context():   # it writes the audit log, which reads the session
            first = logic.get_or_create_draft_session(db, clock.today(), ADMIN_ID)
        t = threading.Thread(target=lambda: out.setdefault("resp", client.post("/audit-history/start")), daemon=True)
        t.start()
        time.sleep(0.8)
        waited = t.is_alive()
        db.commit()
        t.join(15)
        drafts = _drafts_today(db)
        assert out["resp"].status_code == 302, "the second Start failed"
        assert [d["id"] for d in drafts] == [first], f"{len(drafts)} drafts for one day"
        assert out["resp"].headers["Location"].endswith(f"/audit-history/session/{first}")
        assert waited, "the second Start did not wait for the first"
    finally:
        db.rollback()
        for d in _drafts_today(db):
            db.execute("DELETE FROM audit_log WHERE table_name='audit_sessions' AND record_id=?", (str(d["id"]),))
            db.execute("DELETE FROM audit_sessions WHERE id=?", (d["id"],))
        db.commit()


@needs_db
def test_control_starting_an_audit_twice_in_a_row_reopens_the_same_draft(client, db):
    try:
        a = client.post("/audit-history/start").headers["Location"]
        b = client.post("/audit-history/start").headers["Location"]
        assert a == b and len(_drafts_today(db)) == 1
    finally:
        for d in _drafts_today(db):
            db.execute("DELETE FROM audit_log WHERE table_name='audit_sessions' AND record_id=?", (str(d["id"]),))
            db.execute("DELETE FROM audit_sessions WHERE id=?", (d["id"],))
        db.commit()


def test_the_login_rate_limiter_updates_its_record_under_a_lock(monkeypatch):
    """GUARD. The lock itself, recorded: every read-modify-write of the
    per-address record happens while it is held."""
    import app as app_module
    held = []

    class Recording:
        def __init__(self):
            self.inside = False

        def __enter__(self):
            self.inside = True
            held.append("enter")

        def __exit__(self, *exc):
            self.inside = False

    rec = Recording()
    monkeypatch.setattr(app_module, "_LOGIN_RATE_LIMIT_LOCK", rec)

    class Watched(dict):
        def __setitem__(self, k, v):
            assert rec.inside, "the rate limiter wrote its record without the lock"
            super().__setitem__(k, v)

    monkeypatch.setattr(app_module, "_LOGIN_ATTEMPTS_BY_IP", Watched())
    assert app_module._login_rate_limit_check("10.9.9.9") is True
    assert held == ["enter"]


def test_control_the_rate_limiter_still_limits():
    import app as app_module
    ip = "10.9.9.10"
    app_module._LOGIN_ATTEMPTS_BY_IP.pop(ip, None)
    results = [app_module._login_rate_limit_check(ip) for _ in range(app_module._LOGIN_RATE_LIMIT_MAX + 1)]
    app_module._LOGIN_ATTEMPTS_BY_IP.pop(ip, None)
    assert results[:-1] == [True] * app_module._LOGIN_RATE_LIMIT_MAX and results[-1] is False
