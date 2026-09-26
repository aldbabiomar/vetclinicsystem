"""
The Arabic catalogue, checked as a whole against the code that uses it.

Pure tier: no database, no app. Each guard runs its detector on a crafted bad
entry first (the control), so a detector that cannot fire fails loudly instead
of reporting a clean catalogue.

What these exist for:

  - A msgid the code uses but the catalogue lacks renders English in an
    Arabic-configured clinic, silently. Changing an English sentence changes
    its msgid, so every rewording creates one. The money setting reworded
    ~20 messages at once (JOD -> %(currency)s); nothing else would have said
    they had all fallen back to English.
  - Six translations were found to be the same sentence two or three times
    over, one after another (from an earlier batch edit). They rendered as
    one long run-on line, and the existing Arabic-characters check passed
    them, because they WERE Arabic.
  - A placeholder dropped or misspelled in a translation is either a value
    that silently disappears (a refund message with no amount) or a KeyError
    at render.

The one-line-regex check in test_localization.py only sees entries whose
msgid and msgstr each fit on one line; these parse the file with Babel, so a
wrapped entry is checked like any other.
"""
import source_files
import pathlib
import re

import pytest

from babel.messages.extract import extract_from_dir
from babel.messages.frontend import parse_mapping_cfg
from babel.messages.pofile import read_po

ROOT = pathlib.Path(__file__).resolve().parent.parent
PO = source_files.CATALOGUE

# Directories that babel.cfg's patterns can never match but a walk would
# still descend into (the predecessor clones under webapps/ alone hold two
# more copies of every template).
_SKIP_DIRS = {"webapps", "tests", "scripts", "docs", "translations", "static",
              "venv", "node_modules", "migrations"}


def _text(value):
    """msgid/msgstr are a str, or a tuple for plural entries."""
    return value if isinstance(value, str) else value[0]


def _catalogue():
    with open(PO, "rb") as f:
        return read_po(f, locale="ar")


def _extracted_msgids():
    """Every msgid the code passes to a gettext function, extracted the way
    `pybabel extract -F babel.cfg .` does."""
    with open(ROOT / "babel.cfg") as f:
        method_map, options_map = parse_mapping_cfg(f)

    def keep_dir(path):
        rel = pathlib.Path(path).relative_to(ROOT)
        return not any(part in _SKIP_DIRS for part in rel.parts)

    found = {}
    for filename, _lineno, message, _comments, _context in extract_from_dir(
            str(ROOT), method_map, options_map, directory_filter=keep_dir):
        found.setdefault(_text(message), filename)
    return found


def _missing(extracted, catalogue):
    """msgids used by the code that have no Arabic in the catalogue."""
    translated = {_text(m.id) for m in catalogue
                  if m.id and _text(m.string).strip() and not m.fuzzy}
    return sorted(mid for mid in extracted if mid not in translated)


def _repeats_itself(text):
    """True when a translation is one sentence written out more than once,
    back to back — the shape the six doubled entries had."""
    s = text.strip()
    for k in range(2, 6):
        if len(s) % k == 0:
            part = s[: len(s) // k]
            if len(part) >= 8 and part * k == s:
                return True
    return False


def _placeholders(text):
    """Named %-placeholders and the {brace} slots the inline JS fills."""
    return sorted(re.findall(r"%\(\w+\)[sdf]|\{\w+\}", text))


# ---------------------------------------------------------------------------
# Every string the code uses is translated
# ---------------------------------------------------------------------------

def test_control_a_msgid_missing_from_the_catalogue_is_reported():
    catalogue = _catalogue()
    known = next(_text(m.id) for m in catalogue if m.id and _text(m.string))
    extracted = {known: "x", "A sentence no catalogue has ever held.": "x"}
    assert _missing(extracted, catalogue) == ["A sentence no catalogue has ever held."]


def test_the_extraction_actually_reaches_python_and_templates():
    """Guards the test below against passing because the walk found nothing:
    a string from a blueprint, one from core.py and one from a template must
    all be among the extracted msgids."""
    extracted = _extracted_msgids()
    assert len(extracted) > 1000
    assert "Money Setting" in extracted                                  # templates/settings.html
    assert "Not a valid money setting." in extracted                     # routes/settings.py
    assert any(m.startswith("Heads up: this amount") for m in extracted)  # core.py


def test_every_string_the_code_uses_has_arabic():
    missing = _missing(_extracted_msgids(), _catalogue())
    assert not missing, (
        f"{len(missing)} msgid(s) used by the code have no Arabic, so they render in "
        f"English under the Arabic setting — rewording an English string changes its "
        f"msgid. Add them to translations/ar/LC_MESSAGES/messages.po (never with "
        f"fuzzy matching) and run `pybabel compile -d translations`: {missing[:8]}")


def test_the_catalogue_carries_no_fuzzy_entries():
    """A fuzzy entry is Babel's guess, and gettext does not serve it — worse,
    it LOOKS reviewed. One batch of guesses once turned "Rewards Card" into
    the Arabic for "ignore"."""
    fuzzy = [_text(m.id) for m in _catalogue() if m.id and m.fuzzy]
    assert not fuzzy, f"fuzzy entries: {fuzzy[:5]}"


# ---------------------------------------------------------------------------
# No translation is the same sentence written twice
# ---------------------------------------------------------------------------

def test_control_a_doubled_translation_is_detected():
    one = "تمت إعادة تعيين كلمة المرور."
    assert _repeats_itself(one * 2)
    assert _repeats_itself(one * 3)
    assert not _repeats_itself(one)
    assert not _repeats_itself("لا لا")          # too short to be a doubled sentence


def test_no_translation_repeats_itself():
    doubled = [_text(m.id) for m in _catalogue()
               if m.id and _repeats_itself(_text(m.string))
               and not _repeats_itself(_text(m.id))]
    assert not doubled, f"these translations are one sentence repeated: {doubled}"


# ---------------------------------------------------------------------------
# Placeholders survive translation
# ---------------------------------------------------------------------------

def test_control_a_dropped_placeholder_is_detected():
    en = "Refund of %(amount)s %(currency)s recorded."
    assert _placeholders(en) != _placeholders("تم تسجيل استرداد بقيمة %(amount)s.")
    assert _placeholders(en) == _placeholders("تم تسجيل استرداد بقيمة %(amount)s %(currency)s.")
    assert _placeholders("{price} each") != _placeholders("{prcie} للوحدة")


def test_every_translation_keeps_its_placeholders():
    wrong = [(_text(m.id), _placeholders(_text(m.id)), _placeholders(_text(m.string)))
             for m in _catalogue()
             if m.id and _text(m.string)
             and _placeholders(_text(m.id)) != _placeholders(_text(m.string))]
    assert not wrong, f"placeholder sets differ (msgid, en, ar): {wrong[:5]}"
