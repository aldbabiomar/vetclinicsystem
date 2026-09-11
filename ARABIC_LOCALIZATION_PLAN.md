# Arabic/English Toggle — Implementation Plan

> **STATUS: CLOSED — 2026-09-11.** Every section of this plan is executed and
> released as **IQ v1.15.0 / JO v1.13.0**. The catalogues are complete (IQ
> 1341 msgids, JO 1329) and the measured English left on the rendered pages is
> seven word instances per app: a shell command, a cash-audit note somebody
> typed, and two test-data usernames.
>
> **What this plan did not anticipate, and what it cost, is in `COMPARISON.md`
> §57** — read that before touching a template, an `<option>` or a `.po` file.
> The short version: translating the visible text of an `<option>` that has no
> `value=` changes what the form SUBMITS, and one of those fed the cash
> register a payment method it could not recognise, so the drawer count
> reported a surplus that was not real. §5 of this plan says "wrap every
> string" and says nothing about that, because nothing in a localization plan
> would.


Status: **draft for review** — written 2026-09-11, not yet executed.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO, both apps, both get a
language toggle in the UI switching every screen between English and
Arabic — the same way the existing dark/light toggle switches theme.
**PDF exports are explicitly and permanently excluded** — see §0.

This document is written to be handed to a **different** Claude Code
session with no memory of how it was produced. Everything it needs is
either in this file, in `CLAUDE.md`/`COMPARISON.md` (read those first — this
plan assumes their conventions, doesn't repeat them), or discoverable by
running the commands this file gives. Code is cited by **symbol and file**,
not line number — both apps were split into blueprints on 2026-09-10
(`COMPARISON.md` §49), and a line-number citation written before that split
is already known to have gone stale once (see the corrective note at the
top of `HOSTING_MIGRATION_PLAN.md`). Don't repeat that mistake here.

---

## 0. Hard boundary: PDF exports stay English, always

`pdf_export.py`, in both apps, is **out of scope for this entire project**.
Every PDF (receipts, bills, boarding invoices, insights exports — whatever
that module produces) renders in English regardless of which language the
UI is currently showing, **by explicit, deliberate instruction, not by
oversight**: veterinary science's working language is English, and the
person who owns this decision wants it that way permanently, not as a
"we'll get to it later."

Practically: do not touch `pdf_export.py`. Do not wrap any string in it with
a translation call. Do not make it locale-aware. §8 has a regression test
proving this boundary holds — that test should never need to change as a
consequence of anything else in this plan.

---

## 1. Why this isn't the same shape of change as dark/light mode

The person who asked for this explicitly used dark/light mode as the model,
and the toggle **mechanism** should genuinely copy it — but there is one
structural difference worth understanding before writing any code, because
it changes where the work has to happen.

Dark/light mode ([templates/base.html](webapps/vetclinicsystem_iq-main/templates/base.html)):
a nonce-carrying inline `<script>` reads `localStorage` before first paint
and sets a `data-theme="dark"` attribute on `<html>`; a toggle button
(`data-vzh="base-3"`, bound via `VZ.bind()` — never a raw `onclick=`, CSP
forbids that, see `CLAUDE.md`'s frontend-conventions section) flips it; CSS
rules like `html[data-theme="dark"] { ... }` do the rest. **None of this
touches the server.** The browser already has both light and dark CSS
values sitting in `style.css`; the attribute just picks which set applies.

Language can't work that way, because the *text itself* differs, and that
text is written into the HTML by Jinja2, on the server, before the browser
ever sees the page. There is no "both languages already sitting in the
page, pick one" the way there's no "both palettes already sitting in the
page" for theme — swapping language means the server has to know which one
to render, on every request, before it builds the response.

**Concretely, this means:**
- A `data-lang`-style attribute set by client-side JS *after* the page
  loads can't do the job — by the time it runs, the English (or Arabic)
  text is already rendered.
- The toggle instead needs to set something the *server* reads — a cookie,
  not (only) `localStorage` — and the server picks a locale before
  rendering.
- Switching language will cause a **real page reload** — cookie set, page
  re-requested, server renders it in the other language. Theme's switch is
  instant with no reload; language's can't be, without duplicating every
  page's content client-side, which isn't practical for an app this size.
  Worth saying plainly to whoever is coordinating this: it will look and
  feel like the same kind of toggle, but it will visibly reload the page.
  That's inherent to how the two features work, not an implementation gap.
- `<html lang="en">`/`<html dir="ltr">` need to be set **at render time**,
  server-side, not patched on after paint the way `data-theme` is — a
  direction flip that happens after the page has already painted LTR would
  be jarring and is also wrong for accessibility tooling that reads `lang`.

---

## 2. Decisions made while writing this plan

These were reasonable engineering calls made by the plan's author, not put
to the person who commissioned this — flagged here so they're visible and
easy to override if wrong, rather than buried as unstated assumptions.

| Decision | Choice | Rationale |
|---|---|---|
| i18n framework | **Flask-Babel** (`Flask-Babel>=4.0`, compatible with the pinned `Flask==3.1.3`) | The standard, maintained Flask/Jinja2 i18n extension, built on GNU gettext (`.po`/`.mo` files) — nothing like it exists in either app today (confirmed: no such package in `requirements.txt`, in either app). |
| Persistence | **Per-browser cookie**, not a per-user database column | Mirrors dark/light mode exactly, which is `localStorage`-only and has no DB column — that's the explicit model this feature was asked to follow. A logged-in user's language choice will not follow them to a different device; if that turns out to matter, it's a small later addition (a `users.preferred_language` column), not a redesign. |
| Default when never toggled | **English** | Matches today's actual behavior (nothing changes for a clinic that never touches the toggle), same as theme defaulting to light. |
| Register | **Modern Standard Arabic (MSA)**, formal/business register throughout | The correct default for business software; not colloquial/dialectal. Confirm with the translator (§3) if any specific string seems to call for something else. |
| Numerals | **Arabic-Indic (Eastern) numerals (٠١٢٣٤٥٦٧٨٩)** for display text, when Arabic is active | Changed 2026-09-11, overriding this plan's original default (Western numerals) — explicit instruction. Unlike everything else in this table, this doesn't come for free: nothing in either app formats numbers this way today, so it's real (small) implementation work, not a style choice with no cost. See §7 for the mechanism, and note the scope limit there — display text only, not form inputs, IDs, or PDFs. |
| Toggle placement | Next to the existing theme toggle button, same sidebar/header area, `templates/base.html` | Visual consistency — the two toggles should read as a matched pair. |
| Browser auto-detection | **Not implemented.** No `Accept-Language` sniffing. | The toggle is explicit, same as theme (which never auto-follows OS dark-mode preference either). Simpler, predictable, matches the existing pattern. |

None of these are irreversible — flag disagreement with any of them before
or during execution rather than treating this table as final.

---

## 3. The translation-ambiguity rule — read this before writing a single `.po` entry

This is the most important process rule in this document, and it exists
because of a specific, deliberate instruction: **the person commissioning
this speaks Arabic fluently and wants to be the one who resolves anything
genuinely unclear, rather than have an AI guess.**

### When to translate directly, no question needed

Plain, unambiguous, high-frequency software vocabulary with one obvious
correct Arabic rendering: `Save`, `Cancel`, `Delete`, `Edit`, `Search`,
`Add`, `Name`, `Phone`, `Date`, `Total`, `Status`, `Settings`, `Print`,
`Close`, `Back`, `Next`, page titles like `Owners`, `Patients`, `Visits`,
`Inventory`, `Price List`, `Boarding`, `Inpatient`. Translate these
directly and move on — asking about every one of ~400+ strings would defeat
the point of having a translator's help reserved for what actually needs
it.

### When to stop and ask — batch the questions, don't guess

Stop and ask whenever a string is any of the following. This bar is
supposed to be **low** — the instruction from the person commissioning this
was explicit: prompt on anything "troubling or ambiguous," not just on
things that would clearly be wrong.

- **Any clinical/veterinary/medical term** — species names, procedure
  names, drug/medication terms, diagnostic terminology, body-condition-
  score language, anything where an imprecise translation could be
  actually misleading in a clinical record, not just clumsy phrasing.
- **Any idiom or English phrasing that doesn't translate literally** — a
  turn of phrase, a warning message with a specific tone, anything where a
  direct word-for-word rendering would sound wrong or mean something
  different in Arabic.
- **Any string whose English source is itself ambiguous** — where the
  same English word plausibly means two different things depending on
  context, and picking the wrong one changes the Arabic entirely.
- **Anything money/legal/compliance-adjacent** — discount/refund/write-off
  language, audit trail wording, anything a clinic owner might treat as an
  official record.
- **Arabic grammatical agreement the translator should decide, not the
  executor** — Arabic plurals aren't a simple singular/plural split
  (singular, dual, 3–10, 11+ all take different forms) the way English
  gettext's `ngettext()` singular/plural pair assumes. Any string with a
  count in it (e.g. "3 items refundable", "{n} appointment(s) affected")
  needs the translator's call on how to phrase it — don't guess a plural
  form.
- **Any string the executing model is not genuinely confident about**, even
  if it's technically capable of producing *a* translation. If there's real
  doubt, that's the bar — ask.

### How to ask

Batch questions rather than interrupting one string at a time — after
finishing a natural unit of work (one blueprint's templates, say), compile
everything that needs a decision into one message, formatted as:

```
Batch N — {module/template name}:

1. English: "..."
   Where: {file/template, brief context — e.g. "flash message when a
   discount exceeds the role's cap"}
   Question: {what's unclear, or the specific options being weighed}

2. English: "..."
   ...
```

Don't proceed past a batch's ambiguous strings until answered — translate
everything else in that batch that didn't need a question, and come back to
fill in the answered ones once the reply arrives.

### One efficiency worth using: de-duplicate across both apps

IQ and JO share a large amount of identical or near-identical UI vocabulary
(`COMPARISON.md` confirms the two apps are structurally close — same
blueprint layout, same JS framework, largely the same template patterns).
**When the same English source string appears in both apps' templates,
ask about it once, not twice**, and apply the answer to both `.po` files.
Only ask separately for strings that are genuinely app-specific (anything
naming IQD vs. JOD, Iraq vs. Jordan, or wording that differs because the
underlying feature differs between the two — check `COMPARISON.md` §1 if
unsure whether something is shared or diverged before assuming either way).

---

## 4. Architecture

### 4.1 Dependency and config

`requirements.txt`, both apps — add:
```
Flask-Babel>=4.0,<5
```

`app.py`, both apps — alongside the existing `CSRFProtect(app)` setup (the
current code around there configures CSRF, session cookies, `ProxyFix`,
etc. — put this next to it, not in `core.py`; app-wide extension
initialization belongs where the other ones already are):

```python
from flask_babel import Babel, _

app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

def _select_locale():
    lang = request.cookies.get("lang")
    return lang if lang in ("en", "ar") else "en"

babel = Babel(app, locale_selector=_select_locale)
```

`_select_locale()` deliberately does **not** consult
`request.accept_languages` — per §2, the toggle is explicit-only, matching
theme's own behavior.

**Import-order note, per `CLAUDE.md`'s own documented gotcha for this
codebase:** `core.py` must be imported after `load_dotenv()` because it
reads an env var at import time; the Babel setup above has no such
constraint, but keep it in `app.py` near the other app-level config for the
same reason blueprints must never import from `app.py` — `_` (gettext) gets
imported from `flask_babel` directly in every blueprint file that needs it,
never from `app.py`, so there's no circular-import risk to introduce.

### 4.2 The toggle itself

A small route, alongside the other cross-cutting routes already kept in
`app.py` (like `/health` — not a blueprint, since it's truly app-wide, not
owned by one feature area):

```python
@app.route("/set-language/<lang>", methods=["POST"])
def set_language(lang):
    if lang not in ("en", "ar"):
        abort(404)
    resp = redirect(request.referrer or url_for("dashboard"))
    resp.set_cookie("lang", lang, max_age=60*60*24*365, samesite="Lax")
    return resp
```

`templates/base.html` — a toggle button next to the existing theme toggle
(same file, same area as `data-vzh="base-3"`'s theme button), a plain form
POST (no inline handler, consistent with the CSP rule):

```html
<form method="post" action="{{ url_for('set_language', lang='ar' if get_locale() == 'en' else 'en') }}" style="display:inline;">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button type="submit" class="theme-toggle-btn" aria-label="{{ _('Switch language') }}">
    {{ 'العربية' if get_locale() == 'en' else 'English' }}
  </button>
</form>
```

(`get_locale()` is Flask-Babel's own helper, available in templates once
`Babel(app, ...)` is configured — no extra wiring needed for that part.)

### 4.3 `<html lang>`/`<html dir>` — set at render time, not after paint

`templates/base.html`, the opening tag (currently
`<html lang="en" data-palette="{{ theme_palette or 'vetzone' }}">`):

```html
<html lang="{{ get_locale() }}" dir="{{ 'rtl' if get_locale() == 'ar' else 'ltr' }}" data-palette="{{ theme_palette or 'vetzone' }}">
```

This is the one piece that genuinely cannot follow theme's "client-side
script sets it after the fact" pattern (§1) — it has to be right in the
server-rendered markup from the first byte.

### 4.4 Translation file workflow (gettext / Babel)

`babel.cfg`, new file, both app roots:
```ini
[python: **.py]
[jinja2: templates/**.html]
```

One-time setup, both apps:
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel init -i messages.pot -d translations -l ar
```

This creates `translations/ar/LC_MESSAGES/messages.po` — a plain text file,
one `msgid` (English source) / `msgstr` (Arabic translation, initially
blank) pair per extracted string. This is the file that actually gets
filled in as §3's translation work proceeds — hand it to the translator
directly if that's easier than relaying strings through chat, or work
through it via the batch-question process in §3; either is fine, but the
`.po` file is the eventual source of truth either way.

Whenever new strings are added (mid-project, or the next time this app
changes and adds an English string):
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```
`update` merges new `msgid`s into the existing `.po` **without** clobbering
translations already filled in.

Compile before running the app with the new translations active:
```bash
pybabel compile -d translations
```
This produces the binary `.mo` file Flask-Babel actually loads at runtime —
**a step that's easy to forget after editing a `.po` file by hand**, and the
symptom of forgetting it is "I translated this and nothing changed," not an
error.

---

## 5. Wrapping every string — do this per module, not as one pass

This is the largest mechanical task in the project. Work through it in the
order below, testing after each phase rather than attempting all of it at
once — both because it's more reviewable, and because `CLAUDE.md` §7.3's
own house rule applies here as much as anywhere: **a change this size needs
to be verified live, not just written**.

**Current scope, measured 2026-09-11** (re-measure rather than trusting
these numbers if any time has passed — see the commands below):
- 63 template files, 58 of which contain hardcoded user-facing text.
- 369 `flash(...)` calls across `app.py` + `routes/*.py` alone (not
  counting `logic.py` or `core.py`'s validation error messages).

Re-derive current counts before starting:
```bash
find templates -name "*.html" | wc -l
grep -rlE ">[A-Z][a-z]+ [A-Za-z]" templates | wc -l
grep -rc "flash(" app.py routes/*.py | awk -F: '{sum+=$2} END {print sum}'
```

### 5.1 Order of work

1. **`core.py`** — the shared validation exceptions (`BadNumber`,
   `BadPhone`, `BadDate`, etc.) and any user-facing messages they carry.
   Small, foundational, touched by everything downstream.
2. **`app.py`'s own 13 cross-cutting routes** — dashboard, reports/insights,
   error handlers, the auth gate. Also foundational (every page inherits
   from things rendered here, e.g. `base.html`, nav).
3. **Each blueprint in `routes/`, one at a time**, in whatever order is
   convenient — `settings.py`, `admin.py`, `consignment.py`,
   `inventory.py`, `sales.py`, `clinical.py`. Each is self-contained enough
   to wrap, translate (§3), test, and move on without waiting on the
   others.
4. **`logic.py`** — check for any user-facing strings (as opposed to
   internal-only values); most of this module is queries/calculations, not
   display text, but confirm rather than assume.
5. **Templates**, matched to whichever blueprint they belong to — wrap each
   template's hardcoded strings as its corresponding backend module is
   done, rather than as a separate pass afterward.

### 5.2 The wrapping itself

Python-side, e.g. a flash message:
```python
# before
flash("That form was missing something the server needed.", "error")
# after
flash(_("That form was missing something the server needed."), "error")
```
(`from flask_babel import _` — imported directly in each `routes/*.py`
file and in `app.py`/`core.py` as needed; never re-exported through
`app.py` for a blueprint to import, per the no-blueprint-imports-from-
app.py rule.)

Template-side:
```jinja
<!-- before -->
<button>Save</button>
<!-- after -->
<button>{{ _('Save') }}</button>
```

For a string built with interpolated values, gettext's placeholder syntax,
not an f-string wrapped after the fact:
```python
flash(_("Only %(n)s left refundable from this sale.", n=remaining), "error")
```
(A count-carrying string like this is exactly the kind of thing §3 says to
flag — Arabic's plural rules don't map onto a single `%(n)s` slot the way
English's do. Ask rather than guessing at `ngettext()` plural forms.)

---

## 6. RTL layout

### 6.1 What's already known to need conversion

`static/style.css` has hardcoded physical (LTR-only) properties throughout
— confirmed examples as of 2026-09-11 (re-run the grep below rather than
trusting this list; it will have shifted by the time this is executed):

```bash
grep -n "margin-left\|margin-right\|padding-left\|padding-right\|float: *left\|float: *right\|text-align: *left\|text-align: *right\|^[^/]*\bleft:\|^[^/]*\bright:" static/style.css
```

Representative cases found at the time of writing: `margin-left: auto` on
a flex item; `text-align: right` used for numeric table columns (money,
quantities — `.num-col`, `.cell-input.num`); `text-align: left` on
progress panels and error reports; `border-left`/`border-right` used as a
colored flag stripe on table rows (`.row-flag-mismatch`, `.row-dirty`);
fixed-position toasts and the sidebar anchored with `left`/`right`
(`.auth-flash-wrap`, the mobile sidebar, `.vz-toast-stack`); the
appointment grid's cell borders (`.appt-cell`, `.appt-head-cell`,
`.appt-slot-label`).

### 6.2 The conversion approach

**Prefer CSS logical properties** — they flip automatically based on
document direction, with no duplicate ruleset needed:

| Physical (LTR-only) | Logical (direction-aware) |
|---|---|
| `margin-left` / `margin-right` | `margin-inline-start` / `margin-inline-end` |
| `padding-left` / `padding-right` | `padding-inline-start` / `padding-inline-end` |
| `text-align: left` / `right` | `text-align: start` / `end` |
| `border-left` / `border-right` | `border-inline-start` / `border-inline-end` |
| `left` / `right` (positioned elements) | `inset-inline-start` / `inset-inline-end` |

For the numeric-column case specifically (`.num-col`, money/quantity
inputs) — think before blindly converting `text-align: right` to
`text-align: end`. Numbers are conventionally still rendered
left-to-right even inside RTL text in Arabic business documents; "end" in
RTL means the *left* edge, which may or may not be what's wanted for a
column of digits. This is a good candidate for a §3-style question if
there's any doubt, rather than a mechanical find-and-replace.

**For anything logical properties can't clean up** (an icon that needs
horizontal mirroring, a layout pattern too irregular for a property
substitution), use the exact override idiom the codebase already
established for theme, applied to direction instead of theme:

```css
/* existing pattern, for reference */
html[data-theme="dark"] { /* ... */ }
html[data-theme="dark"] .brand .mark .brand-logo-light { display: none; }

/* same idiom, for RTL */
html[dir="rtl"] { /* ... */ }
html[dir="rtl"] .some-icon-that-needs-mirroring { transform: scaleX(-1); }
```

### 6.3 JS behavior audit

`static/behaviors.js`, `toast.js`, `progress.js`, and `ui.js` all need a
pass for hardcoded LTR-specific positioning logic — anything computing a
toast's slide-in direction, a modal's anchor position relative to a
trigger button, or similar layout math that assumes left-to-right. This
plan doesn't presuppose what's found there (their contents weren't audited
while writing this plan) — treat it as its own checklist item, and test
each interactive behavior visually in both directions once RTL is wired up
(§8's browser tier is the right place to add coverage once something
concrete is found).

---

## 7. Numbers, dates, and currency — Eastern Arabic-Indic digits, display only

Per §2's decision (changed 2026-09-11): numbers should render with
Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) when Arabic is active. Nothing in either
app does this today — `money.py` (IQ) and the JOD formatting (JO) both
produce plain Western-digit strings, and there's no numeral-system
handling anywhere in the codebase. This section is the mechanism.

### 7.1 The rule: convert at the last possible step, display-only

Never let an Eastern-digit string reach anything that parses numbers back,
stores them, or isn't meant to have them at all:

- **Money/quantity calculations, `parse_money`, storage, `DATABASE_URL`
  round-trips** — always Western digits, unaffected by locale. The
  substitution happens only when formatting a value *for display*, after
  every calculation is already done.
- **Editable `<input>` fields — leave as Western digits, deliberately.**
  HTML `<input type="number">`'s underlying value is a Western-digit string
  in every browser regardless of locale, and native number-input widgets'
  keyboard/spinner behavior is not reliably locale-aware across platforms.
  Converting an editable field's *displayed* value to Eastern digits risks
  a mismatch between what's shown and what a keyboard actually types, or
  what gets submitted. Scope this to **read-only rendered text** — table
  cells, totals, receipts-in-the-browser (not the PDF, which is excluded
  entirely, see below) — not form fields someone types into.
- **IDs/reference codes** (`V0001`, `INV301`, `PL301`-style values) —
  **never convert.** These are identifiers, not quantities being read
  numerically, and they may be matched/searched elsewhere in the code as
  literal strings.
- **PDF exports** — **never convert, full stop.** This falls directly out
  of §0's existing boundary: PDFs stay English, Western digits, regardless
  of locale. If a shared digit-substitution helper is ever tempting to
  reuse inside `pdf_export.py` for some reason, that's a sign something's
  been wired wrong — that module should never call it.

### 7.2 The mechanism

A small, pure, display-only helper:

```python
# core.py (the shared seam — this belongs alongside the other display-
# formatting helpers, not duplicated per blueprint)
_ARABIC_INDIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

def to_arabic_indic_digits(s):
    """Display-only. Never apply this to a value before it's parsed back
    (parse_money, a form's submitted value) or inside pdf_export.py (see
    ARABIC_LOCALIZATION_PLAN.md §0/§7) — only to already-formatted text on
    its way into a template."""
    return s.translate(_ARABIC_INDIC_DIGITS)
```

**Hook it into the existing `money` Jinja filter** — confirmed at
`app.py:379` (`@app.template_filter("money")`, currently
`return logic.fmt_money(v)`), which is the one existing choke point every
displayed money amount already passes through:

```python
@app.template_filter("money")
def money_filter(v):
    formatted = logic.fmt_money(v)
    if get_locale() == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted
```

This one change covers every template already using `|money` — no
per-template edits needed for money amounts specifically.

**Dates have no equivalent existing filter to hook into** — confirmed
(`grep -n "template_filter" app.py` currently returns only `money`).
Introduce one, mirroring the same pattern, rather than converting digits
ad hoc wherever a date happens to be printed:

```python
@app.template_filter("date")
def date_filter(d):
    formatted = logic.fmt_date(d)  # or whatever the existing display format is — confirm the real helper name before writing this
    if get_locale() == "ar":
        formatted = to_arabic_indic_digits(formatted)
    return formatted
```

Then, during §5's template pass, replace raw date rendering
(`{{ some_date }}`) with `{{ some_date|date }}` wherever a date is shown
as read-only text — the same module-by-module sweep already covers this,
it's not a separate pass.

Quantities in table cells (not inputs) follow the same `to_arabic_indic_digits()`
call directly, wherever they're rendered as plain text rather than through
a filter.

### 7.3 Two things worth a §3-style question, not a silent decision

- **Dates specifically** — an ISO-style date (`2026-09-11`) rendered with
  Eastern digits is a genuinely debatable choice; a lot of Arabic business
  software keeps dates in Western digits even when money/prose numbers use
  Eastern ones, because a date reads more like a computer-format value than
  a spoken number. Don't assume either way — ask.
- **Currency label placement** — "250 IQD" vs. an Arabic phrase that might
  conventionally put the currency word in a different position relative to
  the number. Same treatment: ask rather than assume an order.

---

## 8. Testing — per `CLAUDE.md` §7's own standards, not a lighter bar

Both apps have real, mature test suites (728/709 tests as of 2026-09-10,
per `CLAUDE.md`) built around a specific, explicit discipline: **a test
that passes has not yet been shown to catch anything** (§7.3) — every guard
needs a paired control, and every guard needs to be proven to fail when the
bug it protects against is reintroduced. Follow that discipline here, not a
lighter one just because this is a "feature," not a "fix."

### 8.1 Required tests

1. **Locale-switch guard + control.** Request a known page with the `lang`
   cookie set to `ar`; assert a known Arabic string (from the `.po` file)
   appears in the response. Request the same page with `lang=en` (or no
   cookie); assert the English string appears instead. This is the
   guard-and-control pair `CLAUDE.md` §7.3 explicitly asks for — prove both
   directions work, not just one.
2. **`<html lang>`/`<html dir>` guard.** Confirm both attributes flip
   correctly with the cookie, on at least one representative page per
   blueprint.
3. **PDF-stays-English regression test.** Generate a PDF export (any one
   `pdf_export.py` produces) with the `lang` cookie set to `ar`; assert the
   output is identical to generating it with `lang=en` (or at minimum,
   contains no Arabic text). This is the test proving §0's boundary holds,
   and it should keep passing forever, unaffected by anything else in this
   project.
4. **No-inline-handler / no-inline-style regression on the new toggle
   button.** The language toggle must follow the same `data-vzh`/`VZ.bind()`
   convention as the theme toggle — `tests/test_no_inline_handlers.py` and
   `tests/test_inline_styles.py` already exist and should catch a
   violation automatically; **run them**, don't just assume the new markup
   is compliant because it was written carefully.
5. **Browser-tier RTL check** (`tests/test_browser.py` — needs Playwright +
   a running app, per `CLAUDE.md` §7.1). Toggle to Arabic, confirm `dir="rtl"`
   is actually applied and at least one known layout element visibly
   reflows (not just that the attribute is present in the DOM — an
   attribute with no CSS behind it is a silent no-op).
6. **A "did I actually wrap everything" sweep — heuristic, not a hard
   gate.** Consider a source-scanning test flagging templates with long
   runs of un-wrapped Latin-alphabet text as a candidate for a missed
   string. **If writing this, follow `CLAUDE.md`'s own explicit warning
   about this exact mistake**: "If you write a test that parses source
   text, read `routes/*.py` too. Six tests do this, and after the split
   every one of them would have passed while checking a fraction of the
   surface." Enumerate templates via a live filesystem walk
   (`glob`/`os.walk` over `templates/`) and routes via the live blueprint
   registration (mirror `test_permissions.py`'s approach of pinning
   discovery against Flask's actual `url_map`, per that same file's
   documented convention) — never a hardcoded file list.
7. **Eastern-digit guard + control + boundary, three assertions in one
   test** (§7.1/§7.2). With `lang=ar`: (a) a rendered money total uses
   Eastern digits — the guard; (b) the same page's `<input>` fields still
   carry Western-digit values — the boundary, easy to break by applying
   the conversion one layer too high; (c) with `lang=en`, the same total
   renders in Western digits — the control. All three in one place, since
   they're one feature (§7.1's rule) and a change that passes (a) while
   silently breaking (b) is exactly the kind of partial fix `CLAUDE.md`
   §7.3 warns a single guard-only test would miss.

### 8.2 Prove the guards actually guard (§7.3)

For each test above that's a genuine guard (1, 2, 3, and 7 especially):
after writing it, **deliberately break the thing it protects** and confirm
the suite fails before considering the test done. For the PDF regression
test specifically, this means: temporarily make `pdf_export.py`
locale-aware (a throwaway change, reverted immediately after), confirm the
test **fails**, then revert and confirm it passes again. For test 7's
boundary assertion specifically: temporarily move the `to_arabic_indic_digits()`
call one layer too high (e.g., apply it to the raw value before it reaches
an `<input>`'s `value=` attribute, not just inside the `money`/`date`
filters) and confirm the boundary assertion catches it — that's the actual
failure mode §7.1 exists to prevent, not a hypothetical. Skipping this step
is exactly the failure mode `CLAUDE.md` §7.3 documents happening repeatedly
in this codebase already — a test that has never been watched to fail is
not yet known to test anything.

### 8.3 Where to run this

Per `CLAUDE.md` §5 — the isolated test environment, never a real install:
```bash
scripts/isolated_test_env.sh up iq   # port 5091
scripts/isolated_test_env.sh up jo   # port 5092
```
Full instructions for the three test tiers (pure / database / browser) are
in `CLAUDE.md` §7.1 — don't hand-copy that table here, it's gone stale by
omission twice already according to that same document; run `ls tests/`
and check for `pytest.importorskip` rather than trusting any static list,
including this plan's own §8.1 above.

```bash
scripts/isolated_test_env.sh down iq
scripts/isolated_test_env.sh down jo
```

---

## 9. Order of work, end to end

1. §0 — confirm understanding: `pdf_export.py` is untouched, permanently.
2. §4.1–4.4 — install Flask-Babel, wire the locale selector, `babel.cfg`,
   run `pybabel extract`/`init` to produce the first `messages.pot`/`.po`.
3. §5.1 order, one module at a time: `core.py` → `app.py`'s cross-cutting
   routes → each `routes/*.py` blueprint (with its matching templates) →
   `logic.py` if it turns out to need it.
4. For each module: wrap strings → run §3's translation-ambiguity process
   in batches → fill in `.po` entries → `pybabel compile` → **test that
   module live** (§8) before moving to the next.
5. §6 — RTL CSS conversion and the JS behavior audit, once enough of the
   app is wrapped to actually see it rendered in Arabic end to end.
6. §7 — confirm number/date/currency formatting decisions with the
   translator rather than assuming.
7. §8 in full, including 8.2's "break it and confirm the test fails" step
   for every guard.
8. Repeat steps 2–7 for the second app — per §3's efficiency note, most of
   the translation-question batches from the first app can be reused
   directly for the second; don't re-ask about shared vocabulary.
9. Release, per `RELEASE_WORKFLOW.md`: `VERSION`/`CHANGELOG.md` bump in
   each app independently (per `CLAUDE.md` §3, they don't need to match
   numbers), a dated append to `COMPARISON.md` recording that Arabic
   support landed (this is exactly the kind of cross-app change that
   document's own §4 says to record), and — per `CLAUDE.md`'s own top-of-
   file lesson about this exact folder's layout block going stale twice by
   omission — add this file's own line to `CLAUDE.md`'s layout block if it
   isn't there already by the time this ships.

---

## 10. Explicitly not in scope

- **PDF exports** (§0) — permanent exclusion, not deferred.
- **Per-account language persistence** — cookie-only, per §2; a future
  addition if it turns out to matter, not part of this pass.
- **Eastern-numeral conversion of editable form fields, IDs, or PDF
  exports** — §7.1's boundary. Eastern numerals apply to read-only display
  text only; everything else stays Western digits, deliberately.
- **Colloquial/dialectal Arabic** — MSA throughout, per §2.
- **Browser `Accept-Language` auto-detection** — explicit toggle only,
  matching theme's own behavior.
- **A third language, or any language-selection UI beyond a two-way
  toggle** — this plan is specifically "the same way light and dark mode
  work," i.e., a binary switch, not a language picker.
