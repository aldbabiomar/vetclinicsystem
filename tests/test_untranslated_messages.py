"""
Every message a person reads can be translated (audit F1).

base.html renders a flash as {{ message }} — no translation at render — so
a message not wrapped in _() where it is made shows in English in an Arabic
clinic. The audit found ~30 per app, plus every message built by a helper
and flashed later. These scans hold the three shapes that happened:

  1. flash()/refuse() given a string literal, an f-string, a concatenation,
     %-formatting, .format(), or a ternary with a literal branch;
  2. a JSON error ({"error": "..."}) or a bulk editor's errors[key] = "..."
     as a bare literal;
  3. backup.py / updater.py / autostart.py — which run outside a request, so
     cannot translate — returning a message that is not a messages.Msg (the
     page translates a Msg when it shows it: core.shown()).
"""
import source_files
import ast

import pytest

from conftest import needs_db
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
REQUEST_LAYER = [*source_files.web_modules(), source_files.module("core")]
BACKGROUND = [source_files.module(m) for m in ("backup", "updater", "autostart")]


def _untranslated(node):
    """Why this expression is an untranslated message, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
        return "string literal"
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return "concatenation or %-formatting"
    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "format":
        return ".format()"
    if isinstance(node, ast.IfExp):
        return _untranslated(node.body) or _untranslated(node.orelse)
    return None


def test_no_flash_is_given_an_untranslated_message():
    offenders, seen = [], 0
    for path in REQUEST_LAYER:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("flash", "refuse")
                    and node.args):
                seen += 1
                why = _untranslated(node.args[0])
                if why:
                    offenders.append(f"{path.name}:{node.lineno} ({why})")
    assert seen >= 300, f"scanned only {seen} flash()/refuse() calls — the scan has drifted"
    assert not offenders, "untranslated flash message(s):\n  " + "\n  ".join(offenders)


def test_no_json_or_bulk_editor_error_is_an_untranslated_literal():
    offenders, seen = [], 0
    for path in REQUEST_LAYER:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Subscript) and getattr(t.value, "id", None) == "errors" for t in node.targets):
                seen += 1
                why = _untranslated(node.value)
                if why:
                    offenders.append(f"{path.name}:{node.lineno} errors[...] ({why})")
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "error":
                        seen += 1
                        why = _untranslated(v)
                        if why:
                            offenders.append(f"{path.name}:{node.lineno} {{'error': ...}} ({why})")
    assert seen >= 35, f"scanned only {seen} error messages — the scan has drifted"
    assert not offenders, "untranslated error message(s):\n  " + "\n  ".join(offenders)


def test_the_background_modules_return_only_translatable_messages():
    """A (ok, message) or (ok, path, message) return: the message must be a
    Msg (or empty, or passed through from another call) — never a literal."""
    offenders, seen = [], 0
    for path in BACKGROUND:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)):
                continue
            first = node.value.elts[0] if node.value.elts else None
            if not (isinstance(first, ast.Constant) and isinstance(first.value, bool)):
                continue
            seen += 1
            why = _untranslated(node.value.elts[-1])
            if why:
                offenders.append(f"{path.name}:{node.lineno} ({why})")
    assert seen >= 40, f"scanned only {seen} (ok, message) returns — the scan has drifted"
    assert not offenders, ("a background message that the page cannot translate — make it "
                           "messages.Msg(N_(...)):\n  " + "\n  ".join(offenders))


@needs_db
def test_a_msg_reads_as_english_and_translates_when_shown(flask_app):
    """The mechanism itself: stored and logged as English, shown in the
    clinic's language."""
    from flask_babel import force_locale

    from vcs.web import core
    from vcs.messages import Msg, N_

    m = Msg(N_("Backup saved to %(path)s"), path="/x.dump")
    assert m == "Backup saved to /x.dump" and isinstance(m, str)
    with flask_app.test_request_context(), force_locale("ar"):
        shown = core.shown(m)
    assert shown != "Backup saved to /x.dump" and "/x.dump" in shown, shown


def test_every_flash_goes_through_core_flash():
    """A variable flashed as it is — `flash(err)` — may hold a messages.Msg,
    which the literal scans above cannot see. core.flash() translates one on
    the way in, so the request layer must use it and never flask.flash."""
    offenders, modules = [], 0
    for path in source_files.web_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "flask" and any(a.name == "flash" for a in node.names):
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr == "flash" and getattr(node.value, "id", None) == "flask":
                offenders.append(f"{path.name}:{node.lineno}")
    assert modules >= 7
    assert not offenders, "flask.flash used directly (use core.flash):\n  " + "\n  ".join(offenders)


@needs_db
def test_core_flash_puts_a_msg_into_the_clinics_language(flask_app):
    """GUARD. A flashed message is stored as plain text; a Msg has to be
    translated on the way in."""
    from flask import get_flashed_messages
    from flask_babel import force_locale

    from vcs.web import core
    from vcs.messages import Msg, N_

    with flask_app.test_request_context(), force_locale("ar"):
        core.flash(Msg(N_("Backup saved to %(path)s"), path="/x.dump"), "success")
        [(category, text)] = get_flashed_messages(with_categories=True)
    assert category == "success" and text != "Backup saved to /x.dump" and "/x.dump" in text, text


@needs_db
def test_a_background_jobs_message_reaches_the_page_translated(client, db):
    """GUARD. A backup / restore / update runs in a thread with no request,
    returns a Msg, and the Settings page polls for it: the poll translates
    the result and the live step labels for the clinic's language."""
    import time

    from vcs import jobs
    from vcs.messages import Msg, N_

    saved = (db.execute("SELECT value FROM settings WHERE key='language'").fetchone() or {}).get("value")
    db.execute("INSERT INTO settings (key, value) VALUES ('language','ar') "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value")
    db.commit()
    try:
        def task(update):
            update(0, Msg(N_("Restoring database (%(done)s/%(total)s objects)"), done=3, total=9))
            return {"ok": True, "message": Msg(N_("Backup saved to %(path)s"), path="/x.dump")}
        job_id = jobs.start(["step"], task)
        for _ in range(50):
            payload = client.get(f"/settings/job-status?job_id={job_id}&kind=backup").get_json()
            if payload["status"] == "done":
                break
            time.sleep(0.05)
        assert payload["message"] != "Backup saved to /x.dump" and "/x.dump" in payload["message"]
        assert "Restoring database" not in payload["steps"][0], payload["steps"]
    finally:
        if saved is None:
            db.execute("DELETE FROM settings WHERE key='language'")
        else:
            db.execute("UPDATE settings SET value=? WHERE key='language'", (saved,))
        db.commit()
