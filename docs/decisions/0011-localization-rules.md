# 0011 — What the Arabic setting needs from the code

## Context

English and Arabic are a clinic setting, applied to every page every request.
Most of what went wrong with Arabic in the predecessor apps was not a
translation: it was code that looked translated and was not, or that broke
only in Arabic, where nobody on the team read the pages. Each rule below
was found by a real failure, recorded in `archive/COMPARISON.md` §55–§63;
this record keeps the rules and the tests, and the archive keeps the story.

## Decision

**What is stored stays English; what is shown is translated.**

- A value stored in a column — a status, a method, a reason, a species — is
  stored as its English constant and shown through `|tr`, including behind a
  fallback (`{{ x.method|tr or "—" }}`). Routes and CHECK constraints compare
  against the English.
- An `<option>` carries the constant in `value=`. Without it the browser posts
  the option's text, and in Arabic that text is Arabic: `payments.method` once
  stored `نقدًا`, which the cash register counted as "Other".
- A message a background job stores (a self-check finding) is stored as the
  rendered English plus its msgid and arguments, and translated when shown.
  Translating where it is written freezes whichever language was active then.

**Everything a person reads goes through the catalogue.**

- Flash messages go through `core.flash` with `_()`, and a message returned
  from a background module is a `msg()` that translates when shown.
- Text written into an attribute — a confirm dialog, a field hint, a tooltip —
  goes through `_()` too; `ui.js` shows `data-confirm` as it is.
- Text inside an inline `<script>` goes through `|tojson`. Bare quotes do not
  break the script: they show `isn&#39;t` on screen, which nothing reports.
- A placeholder that JavaScript fills is written `{name}`; `%(name)s` means
  Jinja fills it at render — and Jinja always does, so a `%(name)s` the call
  does not supply is a 500 in every language.
- Emphasis inside a sentence is a placeholder, marked safe before `~` joins it
  (`'<b>'|safe ~ _('all') ~ '</b>'|safe`): `~` escapes its string operands
  first.
- Rewording an English sentence changes its msgid, so it falls back to English
  under Arabic until the new msgid has Arabic. `pybabel update`'s fuzzy
  matches are never accepted. Arabic written without the clinic's review goes
  into `ARABIC_REVIEW.md`.

**Digits.** A number shown to a person is in Arabic-Indic digits under Arabic.
A number anything parses back is Western: an `<input>`'s value (`<input
type=date>` requires ISO), a number written into a script (`const n = ٣;` is a
SyntaxError in Arabic only), a record code, a file path or error text inside a
message. PDFs stay English with Western digits and the Latin currency code,
permanently.

**Layout.** Arabic runs longer and right to left: a row has to give way rather
than push the page sideways (`min-width: 0` on what grows), and physical
`left`/`right` becomes logical `inline-start`/`end`. Status badges do not
wrap (the owner's decision), so an Arabic word is never split across lines.

## Consequences

Every template change is a small localisation review. In return the Arabic
pages are checked by the suite rather than by chance: a string that bypasses
the catalogue, an option without its constant, a script that breaks only in
Arabic and a page that overflows only in Arabic all fail a test.

## Held by

- `tests/test_catalogue.py` — every msgid the code uses has Arabic; no fuzzy
  entry, no doubled sentence, no dropped placeholder; no English written into
  an attribute.
- `tests/test_enum_labels.py` — options carry their constant; stored constants
  are shown through `|tr`, fallbacks included.
- `tests/test_untranslated_messages.py`, `test_selfcheck_i18n.py` — flashes and
  background messages; stored findings translate when shown.
- `tests/test_js_localization.py`, `test_js_strings.py`,
  `test_placeholder_args.py` — scripts and placeholders.
- `tests/test_localization.py` — the setting, digits (display and input),
  PDFs, the currency label; `test_nowrap_translations.py`; `test_bind_port.py`.
- `tests/test_browser.py` — in Arabic: no page overflows or spills out of its
  card, and no page raises a JavaScript error.
