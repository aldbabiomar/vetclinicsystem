"""
The static scripts' sentences reach the page in the clinic's language
(audit F2).

static/*.js cannot call gettext. base.html hands them `window.VZ_I18N`
(built from js_strings.JS_STRINGS) and `vzT(msgid, args)`; each script
looks its sentences up through a local `T()`. These hold the three ways that
goes wrong: a sentence left as a bare English literal, a T() whose text is
not registered (so it has no translation and shows in English), and the
page not carrying the translations at all.
"""
import source_files
import re
from pathlib import Path

import pytest

from vcs.web import js_strings
from conftest import needs_db

STATIC = source_files.STATIC_DIR
SCRIPTS = sorted(p for p in STATIC.glob("*.js"))

# Literals that are prose-shaped but are not shown to anyone.
NOT_SHOWN = {
    "use strict",
    "Enter", "Escape",           # key names compared with event.key
    "status check failed",      # progress.js: an internal Error, caught and replaced by a T() message
}

_LITERAL = re.compile(r"""(['"`])((?:(?!\1)[^\\\n]|\\.)*)\1""")


def _code(path):
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"(?m)(^|[^:])//.*$", r"\1", src)


def _t_calls(code):
    """(msgid, line) for every T("...") / vzT("...") -- the argument may be
    several literals joined with +."""
    out = []
    for m in re.finditer(r"\b(?:vzT|T)\(\s*", code):
        pos, parts = m.end(), []
        while True:
            lit = _LITERAL.match(code, pos)
            if not lit:
                break
            parts.append(lit.group(2))
            pos = lit.end()
            plus = re.match(r"\s*\+\s*", code[pos:])
            if not plus:
                break
            pos += plus.end()
        if parts:
            out.append(("".join(parts).replace("\\'", "'").replace('\\"', '"'), code[:m.start()].count("\n") + 1))
    return out


def test_every_sentence_a_script_looks_up_is_registered():
    """GUARD. An unregistered msgid has no translation: it shows in English."""
    registered = set(js_strings.JS_STRINGS)
    calls, unregistered = 0, []
    for path in SCRIPTS:
        for msgid, line in _t_calls(_code(path)):
            calls += 1
            if msgid not in registered:
                unregistered.append(f"{path.name}:{line}: {msgid!r}")
    assert calls >= 30, f"found only {calls} T() calls — the scan has drifted"
    assert not unregistered, "T() text not in js_strings.JS_STRINGS:\n  " + "\n  ".join(unregistered)


def test_no_script_shows_a_bare_english_sentence():
    """GUARD. Prose in a string literal that is not the argument of T()."""
    offenders, literals = [], 0
    for path in SCRIPTS:
        code = _code(path)
        inside_t = set()
        for m in re.finditer(r"\b(?:vzT|T)\(\s*", code):
            pos = m.end()
            while True:
                lit = _LITERAL.match(code, pos)
                if not lit:
                    break
                inside_t.add(lit.start())
                pos = lit.end()
                plus = re.match(r"\s*\+\s*", code[pos:])
                if not plus:
                    break
                pos += plus.end()
        for lit in _LITERAL.finditer(code):
            literals += 1
            # Markup is not prose -- including a tag the literal opens or
            # closes across a concatenation ('<button aria-label="' + ...).
            text = re.sub(r"<[^>]*>?|^[^<]*>", " ", lit.group(2))
            text = re.sub(r"\$\{[^}]*\}", " ", text)
            if lit.start() in inside_t or text.strip() in NOT_SHOWN:
                continue
            if re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", text) or re.fullmatch(r"\s*[A-Z][a-z]{2,}[.…!]?\s*", text):
                if re.fullmatch(r"\s*[a-z][a-z-]*(\s+[a-z][a-z-]*)*\s*", text):   # a class list
                    continue
                offenders.append(f"{path.name}:{code[:lit.start()].count(chr(10)) + 1}: {lit.group(2)[:70]!r}")
    assert literals >= 200, f"scanned only {literals} literals — the scan has drifted"
    assert not offenders, "English shown by a static script (wrap it in T()):\n  " + "\n  ".join(offenders)


@needs_db
def test_an_arabic_page_carries_the_scripts_sentences_in_arabic(client, db):
    saved = (db.execute("SELECT value FROM settings WHERE key='language'").fetchone() or {}).get("value")
    db.execute("INSERT INTO settings (key, value) VALUES ('language','ar') "
               "ON CONFLICT (key) DO UPDATE SET value=excluded.value")
    db.commit()
    try:
        page = client.get("/").get_data(as_text=True)
    finally:
        if saved is None:
            db.execute("DELETE FROM settings WHERE key='language'")
        else:
            db.execute("UPDATE settings SET value=? WHERE key='language'", (saved,))
        db.commit()
    m = re.search(r"window\.VZ_I18N = (\{.*?\});", page)
    assert m, "the page does not hand the scripts their sentences"
    import json
    table = json.loads(m.group(1))
    assert set(table) == set(js_strings.JS_STRINGS)
    assert table["Keep Editing"] != "Keep Editing" and re.search(r"[؀-ۿ]", table["Keep Editing"])


@pytest.mark.parametrize("msgid", js_strings.JS_STRINGS)
def test_each_registered_sentence_is_used_by_a_script(msgid):
    """No dead entries: each is something a script actually shows."""
    assert any(msgid == found for path in SCRIPTS for found, _line in _t_calls(_code(path))), msgid
