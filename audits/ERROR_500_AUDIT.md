# VetClinicSystem IQ & JO — Error 500 Audit

**Scope:** every action or edge case that can produce an unhandled exception — the branded
500 page with the copyable traceback box, a raw Werkzeug error page, or (in two cases) a
process that won't start at all. Originally audited against JO only (2026-08-24); extended
to cover IQ the same day, since every finding needed independent verification against IQ's
actual current code per `CLAUDE.md` §1-2 — the two apps diverged in real ways (JO:
`Decimal`/JOD 3-decimal money via `NUMERIC` columns; IQ: `float`/IQD via `DOUBLE PRECISION`
columns, plus a `money.py` denomination-rounding module JO doesn't have) and several
findings turned out to already be fixed in one app but not the other.

**Codebase reviewed (both apps):** `app.py`, `logic.py`, `auth.py`, `db.py`,
`attachments.py`, `backup.py`, `scheduler.py`, `jobs.py`, `pdf_export.py`, `barcode.py`,
`setup.py`, `schema_postgres.sql`, `static/progress.js`, all templates, plus IQ-specific
`money.py`, `autostart.py`, `reconcile_attachments.py`.

**Neither app is in production yet** (confirmed with the user 2026-08-24) — so, as with the
original JO-only pass, fixes are written as direct code edits with no migration concerns,
and severity language below describes impact *once deployed*, not damage already happening.

---

## Executive summary

The error-handling scaffolding here is unusually good in both apps — `inject_globals()` is
wrapped so a dead database can't cause a second exception while rendering the first one's
error page, `close_db()` swallows and logs teardown failures, `parse_money()` rejects NaN
and Infinity, `clean_date_filter()` degrades bad filters to no filter, and there's a global
null-byte guard. The 500s that remain fall into six patterns:

1. **Two settings values can brick the app.** A malformed `backup_time` makes the process
   fail to start. A malformed `appt_start_time` breaks Appointments *and* the Settings page
   that would let you fix it. Neither is validated server-side. **IQ already fixed both**,
   by unrelated work earlier today — see E-01/E-02.
2. **A documented error handler was never written.** `db.py` exports `PoolTimeout`
   specifically so `app.py` can show a friendly "server is busy" message. Nothing catches
   it, in either app. Under LAN load every request that can't get a connection is a raw 500.
3. **Unvalidated input reaching database `CHECK` constraints.** Several constraints are
   enforced at the route level in one place and not in another — most notably `bcs`, which
   is range-checked nowhere at all, in either app.
4. **Numeric overflow — JO only, in practice.** JO's `NUMERIC(12,3)` tops out at
   999,999,999.999; nothing bounds what goes in, so a phone number typed into a price field
   is a 500. **IQ's equivalent columns are `DOUBLE PRECISION`**, whose range makes this
   specific failure mode a non-issue for money fields — see E-06.
5. **Unvalidated foreign keys.** Distributor and price-list-link IDs are taken from the form
   and inserted without an existence check, in both apps.
6. **Missing error handlers for 400.** Fourteen `request.form["key"]` sites raise
   `BadRequestKeyError`; with no `400` handler registered in either app, those render
   Werkzeug's bare white page instead of the app's own.

Both research passes independently confirmed a stale premise in the original audit's own
framing: custom-role creation, backup restore, the folder browser, and manual barcode entry
were described as IQ-only. **They are not** — JO gained all of them in a parity pass earlier
today (see `COMPARISON.md`). Every shared route in those areas was diffed line-for-line
between the two apps and found essentially identical; sweeping them for IQ-specific new
findings turned up nothing (see "IQ-only sweep" below) — those newer areas of both
codebases are noticeably better-guarded than the older routes E-01–E-18 cover.

18 findings below, each with **JO status** and **IQ status** verified fresh against current
code (not assumed from one app to the other, per `CLAUDE.md` §2). One finding (E-16) turned
out not to be a live bug in either app — kept in the numbering with a correction note rather
than silently dropped. §Decisions records what was resolved with the user before this
document was finalized. §Reproduction checklist at the end is a manual QA script, now
covering both apps.

**Severity key:** 🔴 app-wide or unrecoverable without direct SQL · 🟠 reliably reachable by
normal use · 🟡 requires a tampered request or an unlikely value

---

## 🔴 E-01 — A malformed `backup_time` stops the app from starting

**Files:** `app.py`, `scheduler.py` (`start`, `reschedule`), `settings_page`

`scheduler.start()` is called unguarded at boot, and the time string is parsed with no error
handling: `int("abc")` raises `ValueError` outside any request context, and the process dies
with a raw traceback — the clinic's system does not come up. The only recovery is editing
the `settings` table directly in Postgres.

**JO status: still open, unchanged.** `scheduler.py:36,41,58` still does
`hour, _, minute = time_str.partition(":"); int(hour or 2)` unguarded. `settings_page`
(`app.py:5540-5599`) has no `TIME_FIELDS`/HH:MM validation before writing `backup_time`.
`scheduler.start()` at `app.py:5796` has no try/except at boot.

**IQ status: already fixed**, by unrelated work earlier today:
- `scheduler.py:26-39` — a new `_parse_hour_minute(time_str)` helper wraps
  `datetime.strptime(..., "%H:%M")` in `try/except (TypeError, ValueError)`, falling back to
  `02:00`. Used by both `start()` (line 54) and `reschedule()` (line 73). Never raises.
- `app.py:5805-5814` — `TIME_FIELDS = ["appt_start_time", "appt_end_time", "backup_time"]`
  validates HH:MM format server-side before any write, with a comment citing this exact
  failure mode.
- Residual, minor: the `scheduler.start()` call at boot (`app.py:6071-6072`) still isn't
  wrapped in try/except — now cosmetic, since `_parse_hour_minute` can no longer raise, but
  a future non-parsing exception from apscheduler itself would still be unguarded.

**Fix (JO only — port IQ's own fix verbatim, adapted to JO's `VETCLINICSYSTEMJO_DATA_DIR`
naming and existing comment style):**

```python
# app.py — settings_page(), alongside NUMERIC_RANGES
TIME_FIELDS = ["appt_start_time", "appt_end_time", "backup_time"]
for key in TIME_FIELDS:
    val = request.form.get(key)
    if val is None or val.strip() == "":
        continue
    try:
        datetime.strptime(val.strip(), "%H:%M")
    except ValueError:
        flash(f"{key.replace('_', ' ').title()} must be a time in HH:MM format.", "error")
        return redirect(url_for("settings_page"))
```

```python
# scheduler.py — one parser, used by both start() and reschedule()
def _parse_hour_minute(time_str, default=(2, 0)):
    """Never raises. A malformed stored value falls back to the default
    rather than taking the whole process down at startup."""
    try:
        hour, _, minute = (time_str or "").partition(":")
        h, m = int(hour), int(minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (TypeError, ValueError):
        pass
    return default
```

Belt and braces on both apps' startup call, since a scheduler failure should never be
fatal (IQ still lacks this too, per the residual note above):

```python
try:
    import scheduler
    scheduler.start(get_db=dbmod.connect, close_db=lambda c: c.close())
except Exception:
    error_logger.error("Nightly backup scheduler failed to start:\n" + traceback.format_exc())
    print("  !! Nightly backups are NOT scheduled — see logs/errors.log. The app will still run.")
```

---

## 🔴 E-02 — A malformed `appt_start_time` breaks Appointments *and* the page that would fix it

**Files:** `logic.py` (`generate_slots`), `settings_page`

The slot *length* is carefully guarded; the two *times* are not — `datetime.strptime(start,
"%H:%M")` / `..(end, ...)` are unguarded, and `settings_page` validates them only as
`if start and end and start >= end` (a string comparison, which happily accepts `"9am"` vs
`"6pm"`). Because `settings_page` calls `orphaned_appointments()` (which calls
`generate_slots`) **before** the save, once a bad value is stored, `/settings` 500s on POST
before it can write the corrected one — Appointments, Settings, and the fix are all
unreachable; recovery requires direct SQL.

**JO status: still open, unchanged.** `logic.py:1853-1854` —
`t0 = datetime.strptime(start, "%H:%M")` / `t1 = ...` still unguarded inside
`generate_slots()`.

**IQ status: already fixed**, alongside E-01. `logic.py:1775-1784` wraps both `strptime`
calls in `try/except (TypeError, ValueError)`, falling back to `"09:00"`/`"18:00"`, with a
comment citing the same defensive rationale.

**Fix (JO only — port IQ's shape):**

```python
def generate_slots(db):
    def _time_setting(key, default):
        raw = get_setting(db, key, default) or default
        try:
            return datetime.strptime(raw.strip(), "%H:%M")
        except (AttributeError, ValueError):
            return datetime.strptime(default, "%H:%M")
    t0 = _time_setting("appt_start_time", "09:00")
    t1 = _time_setting("appt_end_time", "18:00")
    ...
```

`generate_slots` already returns `[]` when `t1 <= t0`, and both callers handle an empty slot
list, so falling back to defaults is safe.

---

## 🔴 E-03 — `PoolTimeout` is exported to be caught, and never caught

**Files:** `db.py` (`PoolTimeout` export, `getconn`), `app.py` (`get_db`)

```python
# db.py
# Re-exported so app.py can catch "the pool is exhausted" specifically
# (dbmod.PoolTimeout) and show a friendly "server is busy" message instead
# of a generic 500.
PoolTimeout = PoolTimeout
```

The handler the comment describes does not exist, in either app. This matters more than it
looks: the pool caps at 15 connections with a 4-second request timeout, and `require_login()`
calls `get_db()` on **every single request** — exhaustion doesn't degrade one page, it 500s
everything at once, including the pages a user would retry on. `/insights` opens 7
concurrent pool connections of its own via `ThreadPoolExecutor`, which is one realistic way
to get there.

**JO status: open, unchanged.** `db.py:21,27` still exports `PoolTimeout` with the
"so app.py can catch..." comment; grepping every `.py` file for `PoolTimeout` returns zero
handler hits.

**IQ status: open, unchanged, same gap.** `db.py:21,27` — identical export, identical
comment, identical absence of a handler. IQ's error-handler block (`app.py:767-829`) has
handlers for 403/404/413/`BadNumber`/`BadPhone`/`dbmod.NumericValueOutOfRange` (see E-06)
but nothing for `dbmod.PoolTimeout`.

**Fix (both apps — identical, IQ already has the exact pattern to copy from in its own
`NumericValueOutOfRange` handler at `app.py:821-829`):**

```python
# app.py, alongside the other error handlers
@app.errorhandler(dbmod.PoolTimeout)
def handle_pool_timeout(e):
    error_logger.error(f"DB pool exhausted on {request.method} {request.path}")
    if request.accept_mimetypes.best == "application/json" or request.path.startswith("/api/"):
        return jsonify({"error": "The system is busy right now — try again in a moment."}), 503
    return render_template("error_busy.html"), 503
```

Worth pairing with a cheap guard on `/insights` in both apps: cap its `ThreadPoolExecutor`
at, say, `max_workers=3` instead of `len(job_defs)`, so one report can't take half the pool.

---

## 🟠 E-04 — No `400` handler: fourteen `f["key"]` sites render a raw Werkzeug page

**File:** `app.py` — 14 sites in each app

Neither app registers a `400` handler, and `handle_unexpected_error` passes `HTTPException`
straight through in both. `request.form["key"]` on a missing key raises
`BadRequestKeyError`, a `BadRequest` subclass — so the user gets Werkzeug's unstyled white
"400 Bad Request" page with none of the app's navigation, and no flash explaining what
happened. Reachable whenever a field is missing rather than empty: a disabled input, a JS
error that removes a field, an autofill quirk, or any non-browser client. Note these keys
being *present but empty* is a separate problem — `f["name"] == ""` passes `NOT NULL` and
creates a nameless record — so the fix should cover both.

**JO status: open, unchanged in shape — line numbers shifted** from the original audit
(the `visit_new_patient` function was restructured by unrelated work earlier today, splitting
out a `_parse_visit_fields()` helper). Current line numbers, both apps:

| Route | Key | JO line | IQ line |
|---|---|---|---|
| `owner_new` | `name` | 1533 | 1561 |
| `owner_edit` | `name` | 1583 | 1611 |
| `patient_edit` | `animal_name`, `species` | 1663 | 1691 |
| `visit_new_patient` | `owner_name` | 1827 | 1855 |
| `visit_new_patient` | `animal_name`, `species` | 1841 | 1869 |
| `price_list_new` | `name`, `category` | 2536 | 2586 |
| `price_list_edit` | `name`, `category` | 2580 | 2706 |
| `inventory_catalog_new` | `name` | 2748 | 2810 |
| `inventory_catalog_edit` | `name` | 2778 | 2893 |
| `distributor_new` | `name` | 3054 | 3160 |
| `distributor_edit` | `name` | 3090 | 3189 |
| `inpatient_new` | `patient_id` | 4662 | 4672 |
| `appointment_new` | `slot_label` | 5064 | 5077 |
| `appointment_new` | `pet_name`, `owner_name` | 5104 | 5119 |

**IQ status: open, identical shape, at the line numbers above.** No `@app.errorhandler(400)`,
no `required_field()` helper in either app. Fix is identical in shape for both — no
money-type or role-model dependency here.

**Decision (resolved 2026-08-24):** roll `required_field()` out across all fourteen sites in
both apps, including the behavior change it implies (rejecting a currently-accepted blank
value, e.g. an empty owner name) — not just patching the missing-key crash. See §Decisions.

**Fix.** A global handler for the shape, plus real validation at the sites that matter:

```python
@app.errorhandler(400)
def bad_request(e):
    flash("That form was missing something the server needed. "
          "Please reload the page and try again.", "error")
    return _fallback_redirect()
```

And a small helper for required text, used in place of `f["..."]`:

```python
def required_field(f, key, label):
    """Returns the stripped value, or None (with a flash already set) if
    it's missing or blank. Covers both the KeyError case and the
    empty-string case, which NOT NULL does not."""
    val = (f.get(key) or "").strip()
    if not val:
        flash(f"{label} is required.", "error")
        return None
    return val
```

```python
# e.g. owner_new()
name = required_field(f, "name", "Owner name")
if name is None:
    return render_template("owner_form.html", owner=None)
```

---

## 🟠 E-05 — `bcs` is range-checked nowhere, and the database has a `CHECK`

**Files:** `schema_postgres.sql` (`visits`, `inpatient_cases`), four call sites per app

```sql
bcs INTEGER CHECK (bcs BETWEEN 1 AND 9),   -- Body Condition Score, 1-9 scale
```

Every route parses it with `parse_int()` and nothing else — that guarantees only that it's
an integer, not that it's in range. Submitting `0`, `10`, or `-3` reaches the database and
raises `CheckViolation` → 500.

**JO status: open, unchanged.** `schema_postgres.sql:408,550` — the CHECK on both `visits`
and `inpatient_cases`. Call sites `app.py:1874, 2025, 4654, 4730` all still
`parse_int(f.get("bcs"))` unbounded.

**IQ status: open, identical shape.** `schema_postgres.sql:323,457` — identical CHECK. Call
sites `app.py:1896 (_parse_visit_fields), 2065 (visit_edit), 4661 (inpatient_new), 4745
(inpatient_edit)` — identical unbounded `parse_int(f.get("bcs"))`. IQ's
`NumericValueOutOfRange` handler does **not** help here — a bad `bcs` raises
`psycopg.errors.CheckViolation`, a different exception class, still uncaught.

**Decision (resolved 2026-08-24):** reject `0` (and anything outside 1-9) as invalid, rather
than silently coercing it to `NULL`. See §Decisions.

**Fix (both apps — identical):**

```python
BCS_MIN, BCS_MAX = 1, 9

def parse_bcs(raw):
    """Mirrors the CHECK (bcs BETWEEN 1 AND 9) constraint so an out-of-range
    value is a friendly flash rather than a raw CheckViolation."""
    val = parse_int(raw)
    if val is not None and not (BCS_MIN <= val <= BCS_MAX):
        raise BadNumber(f"Body Condition Score must be between {BCS_MIN} and {BCS_MAX}.")
    return val
```

Use it in all four routes per app. Since `BadNumber` already has a global handler in both
apps, a route that forgets to catch it degrades gracefully rather than 500ing.

---

## 🟠 E-06 — Money and quantity fields have no upper bound — JO's schema can overflow; IQ's can't (for money), but IQ has its own gap on plain integers

**Files:** `app.py` (`parse_money`, `parse_int`), `schema_postgres.sql`

**JO status: open, unchanged, exactly as originally described.** `parse_money` returns any
finite `Decimal`; the columns behind it do not accept any finite decimal:

| Column type | Used for | Max value |
|---|---|---|
| `NUMERIC(12,3)` | every money amount | 999,999,999.999 |
| `NUMERIC(10,3)` | quantities | 9,999,999.999 |
| `NUMERIC(5,2)` | `discount_percent` | 999.99 |
| `INTEGER` | `lead_time_days` | 2,147,483,647 |

Anything larger raises `numeric field overflow` (a psycopg `DataError`) → 500. The realistic
trigger isn't an attacker, it's a fat finger — a Jordanian mobile number is 10 digits; tabbing
one field too far and typing a phone number into Cost Price, Sale Price, Manual Amount, or a
payment amount overflows `NUMERIC(12,3)`. Affected: every `parse_money()` call site across
price list, inventory cost, visit/inpatient/boarding billing, all payment routes, POS
quantities and cash received, distributor bills, consignment receiving, cash-register
payouts.

**IQ status: does not apply to money/quantity fields; a related but narrower gap exists on
plain `INTEGER` columns, and IQ already has a partial safety net JO lacks.** IQ's schema
uses `DOUBLE PRECISION` for *every* money and quantity column — zero `NUMERIC` columns exist
in IQ's `schema_postgres.sql`. `DOUBLE PRECISION`'s range is ~±1.8×10³⁰⁸; a 10-digit phone
number typed into a price field doesn't come close to overflowing it. `parse_money` is
unbounded exactly like JO's, but IQ's column type makes that irrelevant to *this* failure
mode.

IQ does still have genuinely overflowable `INTEGER` columns (e.g. `distributors
.lead_time_days`, written via unbounded `parse_int(f.get("lead_time_days"))` at
`app.py:3152,3184`). But IQ already has a global safety net JO doesn't: `db.py:29-33`
re-exports `psycopg.errors.NumericValueOutOfRange` (the same SQLSTATE Postgres raises for
both "numeric field overflow" and "integer out of range"), and `app.py:821-829` registers
`@app.errorhandler(dbmod.NumericValueOutOfRange)` that flashes "That number is too large to
be a valid value here." and redirects, instead of 500ing. So an oversized `lead_time_days`
in IQ today already degrades to a flash — not a crash.

**Decision (resolved 2026-08-24):** keep the vague overflow-message wording ("too large —
check for a typo") rather than naming the exact numeric limit — precise, but exposes a
schema detail and reads as noise next to the actual cause. See §Decisions.

**Fix (JO — bound at the parse layer):**

```python
# The widest value any NUMERIC(12,3) column in this schema can hold. Checked
# here, once, rather than at each call site — an amount past this is always a
# typo (a phone number into a price field is the common one), and letting it
# reach Postgres turns that typo into a 500 mid-form instead of a flash.
MAX_MONEY = Decimal("999999999.999")

def parse_money(raw, required=False):
    ...
    if not val.is_finite():
        raise BadNumber(raw)
    if abs(val) > MAX_MONEY:
        raise BadNumber(f"{raw} is too large — check for a typo.")
    return val
```

Add an explicit `parse_quantity()` capped at `Decimal("9999999.999")` for the POS cart,
refund lines, and inpatient billing quantities. Same treatment for `parse_int` against
`2147483647`.

**Fix (IQ — much smaller scope, since money/quantity fields aren't at risk):** port JO's
`PoolTimeout`-style handler pattern that IQ already applies to `NumericValueOutOfRange` — no
change needed there, it already works. The one gap worth closing is bounding `parse_int` for
IQ's own `INTEGER` columns as defense-in-depth / nicer messaging (the existing
`NumericValueOutOfRange` handler already prevents a crash, this would just make the message
proactive rather than reactive):

```python
# app.py — parse_int, IQ's own (float-based) money type, do NOT reuse JO's Decimal MAX_MONEY constant
MAX_INT = 2_147_483_647

def parse_int(raw, required=False):
    ...
    if val is not None and abs(val) > MAX_INT:
        raise BadNumber(f"{raw} is too large — check for a typo.")
    return val
```

No `MAX_MONEY`/`parse_quantity` needed in IQ — `DOUBLE PRECISION` already has no practical
ceiling for this app's real values, and adding an artificial one would only reintroduce the
exact class of bug this finding is about, in reverse.

---

## 🟠 E-07 — `visit_edit` writes `case_status` and `visit_type` without validating them

**File:** `app.py` (`visit_edit`)

```python
new_case_status = f.get("case_status", visit["case_status"])
...
new_vals = {"visit_type": f.get("visit_type"), ..., "case_status": new_case_status, ...}
```

`CASE_STATUSES` is defined at module level and used to populate the template dropdown, but
never checked server-side. The column has a `CHECK (case_status IN (...))`; any other value
→ `CheckViolation` → 500. `visit_type` has no `CHECK` so it silently accepts garbage instead
(a data-quality problem rather than a 500, but the same missing validation). Contrast:
`price_list_new`/`_edit`, `inventory_catalog_new`/`_edit`, `appointment_new`, and
`visit_billing_save` all *do* validate their enum fields against a module-level list, with a
comment explaining exactly why. `visit_edit` is the one that was missed — in both apps.

**JO status: open, unchanged.** `app.py:2015` through the `UPDATE` at line 2056 — no
`CASE_STATUSES` membership check.

**IQ status: open, identical shape.** `app.py:2055` — same
`new_case_status = f.get("case_status", visit["case_status"])`, same absence of a check
before the `UPDATE`. Not helped by `NumericValueOutOfRange` — this is a `CheckViolation`.

**Fix (both apps, identical):**

```python
if new_case_status not in CASE_STATUSES:
    flash("Case status must be one of: " + ", ".join(CASE_STATUSES) + ".", "error")
    return redirect(url_for("visit_edit", visit_id=visit_id))
visit_type = f.get("visit_type")
if visit_type not in ("Outpatient", "Inpatient"):
    flash("Visit type must be Outpatient or Inpatient.", "error")
    return redirect(url_for("visit_edit", visit_id=visit_id))
```

---

## 🟠 E-08 — The two bulk-edit endpoints skip the category validation their single-row twins do

**Files:** `app.py` (`price_list_bulk_edit`, `inventory_catalog_bulk_edit`)

The single-row edit routes validate category against `PRICE_CATEGORIES`/
`INVENTORY_CATEGORIES`; the bulk JSON endpoints saving the same column do not. The default
for `price_list_bulk_edit` is `""` — not in the `CHECK` list either — so any bulk save where
a row's `category` is absent from the payload is a `CheckViolation`, and because these
routes save many rows in one transaction, one bad row 500s the entire batch: the technician
loses every edit they just made across the whole page, with no indication which row caused
it. Reachable from any client-side bug that drops or mangles the field, not only tampering.

**JO status: open, unchanged.** `price_list_bulk_edit` (`app.py:2602-2667`): no
`PRICE_CATEGORIES` check, defaults to `""`. `inventory_catalog_bulk_edit`
(`app.py:2800-2837`): same gap against `INVENTORY_CATEGORIES` (default `"Medical"` is valid,
but a bad *supplied* value isn't checked).

**IQ status: open, line-for-line identical logic.** `price_list_bulk_edit`
(`app.py:2600-2668`) and `inventory_catalog_bulk_edit` (`app.py:2821-2910`) reproduce the
same gaps verbatim — the only diff from JO is docstring wording and an unrelated
`has_negative(cost_price)` check IQ's inventory version already has. Both apps already have
the `errors[item_id]` per-row mechanism the fix uses — just not wired to category or name.

**Decision (resolved 2026-08-24):** per-row errors, not atomic-whole-batch rejection — these
pages are used for 50-row edits; losing everything on one typo is worse than a partial save.
See §Decisions.

**Fix (both apps, identical shape):**

```python
category = fields.get("category", "")
if category not in PRICE_CATEGORIES:
    errors[item_id] = "Category must be one of: " + ", ".join(PRICE_CATEGORIES) + "."
    continue
```

Same shape in `inventory_catalog_bulk_edit` against `INVENTORY_CATEGORIES`. Also add `name`
to the per-row validation in both — `fields.get("name", "")` currently lets an empty name
through `NOT NULL`.

---

## 🟠 E-09 — `distributor_id` and `linked_item_id` are inserted without an existence check

**Files:** `app.py` (`inventory_catalog_new`/`_edit`/`_bulk_edit`, `price_list_new`/`_edit`/`_bulk_edit`)

`inventory_list.distributor_id` and `price_list.linked_item_id` both have real FKs; neither
value is checked against its referenced table before insert. `price_list_new` *does* query
`linked_item_id` — but only to check whether it's already linked from another active row,
never that it names a real `inventory_list` row at all. A stale picker (item deactivated,
page not reloaded) or any client-side bug → `ForeignKeyViolation` → 500.

**JO status: open, unchanged.** Confirmed no existence check in `inventory_catalog_new`
(`app.py:2729-2754`); `price_list_new`'s `linked_item_id` check (`app.py:2517-2530`) only
verifies non-duplication, never existence.

**IQ status: open, identical.** `inventory_catalog_new` (`app.py:2788-2812`) and
`price_list_new` (`app.py:2549-2595`) reproduce the same gaps verbatim (IQ's `price_list_new`
additionally flashes a `money.is_denomination_valid(sale_price)` warning after insert —
unrelated rounding-hygiene check, not a validation fix). `ForeignKeyViolation` isn't caught
by `NumericValueOutOfRange` either.

**Fix (both apps, identical):**

```python
distributor_id = f.get("distributor_id") or None
if distributor_id and not db.execute(
        "SELECT 1 FROM distributors WHERE id=?", (distributor_id,)).fetchone():
    flash("That distributor no longer exists — reload the page and pick again.", "error")
    return redirect(url_for("inventory_catalog"))
```

```python
if linked_item_id and not db.execute(
        "SELECT 1 FROM inventory_list WHERE id=?", (linked_item_id,)).fetchone():
    flash("That inventory item no longer exists — reload the page and pick again.", "error")
    return redirect(url_for("price_list"))
```

In the bulk routes, use `errors[item_id]` rather than a redirect, per E-08.

---

## 🟠 E-10 — `inpatient_new` and `boarding_new` accept any `patient_id`

**Files:** `app.py` (`inpatient_new`, `boarding_new`)

Both columns are `NOT NULL REFERENCES patients(id)`; a nonexistent ID is a
`ForeignKeyViolation` → 500. `visit_new_existing` gets this right (checks existence before
proceeding) — the pattern to copy. All three routes use the same live-search picker
submitting a hidden `patient_id`; if a user types in the search box and submits without
clicking a result, or the search JS fails, the hidden field can hold a stale or partial
value.

**JO status: open, unchanged.** `inpatient_new` (`app.py:4638-4662`) passes `f["patient_id"]`
straight to `_create_inpatient_case` with zero check. `boarding_new` (`app.py:4127-4148`)
checks non-empty but never queries `patients`.

**IQ status: open, same gap, though `boarding_new` was lightly restructured by unrelated
work today.** `inpatient_new` (`app.py:4642-4672`) — identical, unchecked at line 4672.
`boarding_new` (`app.py:4127-4180`) now fetches `patient_row` up front (to support the
redisplay-on-error label from that unrelated work) — but still never checks
`if not patient_row:` before the `INSERT INTO boarding_sessions` at `app.py:4166-4173`,
which uses `patient_id` directly regardless. Same `ForeignKeyViolation` exposure as JO,
reached via a slightly different code path.

**Fix (both apps — for IQ, note `patient_row` is already fetched; just add the guard):**

```python
patient_id = (f.get("patient_id") or "").strip()
if not patient_id or not db.execute(
        "SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
    flash("Pick a patient from the search results first.", "error")
    return redirect(url_for("boarding_page"))    # or inpatient_new
```

In IQ's `boarding_new`, reuse the already-fetched `patient_row` instead of a second query:
`if not patient_id or not patient_row:`.

---

## 🟠 E-11 — `inventory_catalog_edit` dereferences a row it never checked for `None`

**File:** `app.py` (`inventory_catalog_edit`)

```python
old = db.execute("SELECT * FROM inventory_list WHERE id=?", (item_id,)).fetchone()
new_vals = {..., "notes": f.get("notes", old["notes"]), "active": old["active"]}
```

No `if not old:` guard. `POST /inventory-catalog/NOPE/edit` → `TypeError: 'NoneType' object
is not subscriptable` → 500. Sibling routes (`inventory_catalog_toggle`, `price_list_edit`,
`patient_edit`, `boarding_edit`) all guard correctly in both apps, so this is a one-off
omission, not a pattern — reachable by a bookmarked/hand-edited URL or a typo'd ID.

**JO status: open, unchanged.** `app.py:2777-2781` — unguarded, subscripted at line 2781.

**IQ status: open, identical.** `app.py:2892-2896` — same pattern, `old["notes"]` at 2895,
`old["active"]` at 2896.

**Fix (both apps, identical):**

```python
old = db.execute("SELECT * FROM inventory_list WHERE id=?", (item_id,)).fetchone()
if not old:
    flash("Inventory item not found.", "error")
    return redirect(url_for("inventory_catalog"))
```

---

## 🟡 E-12 — `visit_new_patient`'s `IntegrityError` fallback assumes it knows which constraint fired

**File:** `app.py` (`visit_new_patient`)

```python
except dbmod.IntegrityError:
    db.rollback()
    oid = db.execute("SELECT id FROM owners WHERE phone=?", (owner_phone,)).fetchone()["id"]
```

The intent (recover from losing the `idx_owners_phone_unique` race by adopting the owner
that won) is right, but the handler catches `IntegrityError` generically and then assumes
the winner exists. Two ways that breaks: the violation was a *different* constraint (a
`NOT NULL` on `owners.name` from an empty `owner_name`, say) — the `SELECT` finds nothing,
`None["id"]` → `TypeError` → 500; or `owner_phone` is `None` (phone left blank, which is
allowed) — `WHERE phone = NULL` matches nothing in SQL, same crash. `owner_new` handles the
same race correctly, with an `if existing:` check and a fallback flash — the sibling to copy.

**Note — this is the same underlying bug the `ORPHANED_RECORDS_AUDIT.md` companion document
discusses under its F-03 write-up.** Both documents flag it; fix it once, it closes both.

**JO status: open, unchanged in substance — line shifted to 1829-1836** (was 1783-1790;
`visit_new_patient` was restructured by the unrelated `_parse_visit_fields()` work today,
which fixed the *commit-ordering* problem this function used to have — see
`ORPHANED_RECORDS_AUDIT.md` F-02/F-03 — but did not touch this specific
`except IntegrityError:` block). Same two failure modes still reproduce.

**IQ status: open, identical, at line 1857-1864.** Same restructuring happened in IQ too
(same unrelated work, both apps), same untouched `IntegrityError` fallback, same unguarded
`.fetchone()["id"]`.

**Fix (both apps — mirror `owner_new`'s shape):**

```python
except dbmod.IntegrityError:
    db.rollback()
    existing = db.execute("SELECT id FROM owners WHERE phone=?", (owner_phone,)).fetchone() \
        if owner_phone else None
    if not existing:
        flash("That owner couldn't be saved — check the name and phone number "
              "and try again.", "error")
        return redirect(url_for("visit_new_patient"))
    oid = existing["id"]
    flash(f"Owner {oid} already has this phone number on file — the new pet was "
          f"added to their existing profile.", "success")
```

---

## 🟡 E-13 — `inventory_status()` parses two settings with a bare `int()`

**File:** `logic.py` (`inventory_status` / the function reading `audit_overdue_days`,
`expiry_soon_days`)

```python
audit_overdue_days = int(get_setting(db, "audit_overdue_days", 35))
expiry_soon_days = int(get_setting(db, "expiry_soon_days", 60))
```

Both are validated by `settings_page`'s `NUMERIC_RANGES` block, so the *form* can't put a bad
value there — but `import_seed.py` writes settings straight from `seed_data.json` with no
validation. A typo in the seed file, or any direct SQL, makes `int()` raise — and this
function is called by Inventory Status, the Ordering Sheet, POS checkout, the POS lookup
API, the Consignment Overview, and the Dashboard's low-stock badge. One bad character in a
seed file takes out most of the app, including the home page. Same shape as E-02's
`generate_slots` gap — worth fixing together with one shared helper.

**JO status: open, unchanged.** `logic.py:190-191` — both bare `int()` calls, unguarded.

**IQ status: open, identical.** `logic.py:189-190` — same two bare `int()` calls, no
defensive helper anywhere in `logic.py`.

**Fix (both apps, identical):**

```python
# logic.py
def int_setting(db, key, default):
    """Never raises. Settings can be written by import_seed.py (unvalidated)
    and by hand, so a stored non-numeric value must degrade to the default
    rather than take down every page that reads it."""
    try:
        return int(get_setting(db, key, default))
    except (TypeError, ValueError):
        return int(default)
```

---

## 🟡 E-14 — The null-byte guard doesn't cover JSON request bodies

**File:** `app.py` (`_reject_null_bytes`)

The docstring says this is checked "once, globally" — but `request.form` is empty for a
JSON body, so the five JSON-body routes bypass it and a null byte there reaches Postgres
unhandled.

**JO status: open.** `app.py:144-153` checks `request.path`, `request.args.values()`,
`request.form.values()` — no `request.get_json()` coverage. Affected sites:
`api_browse_folder_new`, `price_list_bulk_edit`, `inventory_catalog_bulk_edit`,
`inventory_catalog_barcode_manual`, `consignment_items_bulk_edit`.

**IQ status: open in substance, though the function was independently rewritten with a
small improvement.** `app.py:127-150` now also checks raw `request.query_string` bytes
(catches an encoded null before Werkzeug decodes it) in addition to path/args/form — a real
improvement over JO's version, but still doesn't touch `request.get_json()`. Same five
JSON-body routes exist in IQ at the equivalent lines.

**Correction to the original finding's site list (applies to both apps equally):**
`inventory_catalog_barcodes_bulk_print` was listed as affected but actually reads its
payload via `request.form.get("items")` (a JSON *string* inside a form field, parsed with
`json.loads`), not `request.get_json()` — it **is** already covered by the existing guard
(form values are checked). Verified identical in both apps' current code; drop it from the
affected-site list.

**Practical note:** `inventory_catalog_barcode_manual`'s own regex validation
(`^[A-Za-z0-9 .\-_]+$`) already rejects a null byte as an invalid character before it could
reach the database, in both apps — so that specific site's exposure is more theoretical than
the other four.

**Fix (both apps, identical):**

```python
def _has_null(value):
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_null(k) or _has_null(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_null(v) for v in value)
    return False

@app.before_request
def _reject_null_bytes():
    if ("\x00" in request.path
            or any("\x00" in v for v in request.args.values())
            or any("\x00" in v for v in request.form.values())
            or (request.is_json and _has_null(request.get_json(silent=True)))):
        return ("Bad Request", 400)
    return None
```

(IQ: keep its existing raw-`query_string` check too — this fix is additive, not a
replacement.)

---

## 🟡 E-15 — `generate_barcode()` raises a `RuntimeError` the user never sees

**Files:** `barcode.py`, `app.py` (barcode-generate route)

```python
def generate_barcode(db):
    for _ in range(50):
        ...
    raise RuntimeError("Could not generate a unique barcode — try again.")
```

**JO status: open, unchanged.** `barcode.py:18-27` unchanged.
`inventory_catalog_create_barcode` (`app.py:2856-2865`) calls `generate_barcode(db)` with no
try/except around it — `RuntimeError` propagates uncaught → 500.

**IQ status: already fixed.** `barcode.py` is byte-identical to JO's (still raises the same
`RuntimeError`), but the calling route — renamed `inventory_catalog_barcode_generate`
(`app.py:2984-3016`, part of the manual-barcode-entry feature added earlier) — already
wraps the call:
```python
try:
    code = barcode_mod.generate_barcode(db)
except RuntimeError as e:
    return jsonify({"error": str(e)}), 500
```
Status is `500` rather than a dedicated `503`, but the actual defect (message never reaching
the user) is resolved. No further action needed for IQ.

**Fix (JO only — port IQ's shape):**

```python
try:
    code = barcode_mod.generate_barcode(db)
except RuntimeError as e:
    return jsonify({"error": str(e)}), 500
```

---

## ~~🟡 E-16 — `logic.boarding_billing_summary` passes a possibly-`None` row downstream~~ — correction: already fixed in both apps, not a live bug

**File:** `logic.py` (`boarding_billing_summary_from_fields`)

The original finding described `b` (the `boarding_sessions` row) as unchecked before being
subscripted. **Re-reading the current function in both apps shows this is not accurate** —
current `logic.py:545-568` opens with:

```python
if not b:
    subtotal = 0
elif b["total_is_auto"] and not b["dismissed"] and b["price_per_day"]:
    ...
```

This guard is present and correctly short-circuits before any subscript. Both apps have the
identical function body. Either this was already fixed before the original audit was
written and the audit mis-read the function, or something else explains the mismatch —
either way, **this is not an open finding in either app.** Kept in the numbering (rather
than silently deleted) so a future pass doesn't waste time re-deriving the same conclusion.
No fix needed.

---

## 🟡 E-17 — An expired CSRF token gives a raw 400 page

**File:** `app.py` (`CSRFProtect(app)`, no handler registered)

Not a 500, but the same failure surface and considerably more likely than most items here.
`PERMANENT_SESSION_LIFETIME` defaults to 12 hours and a front-desk machine can be left open
for an entire shift or longer. When the session expires with a form still open, submitting
it raises `CSRFError` (a `BadRequest` subclass) and — with no 400 handler (E-04) — the user
gets Werkzeug's bare page reading "The CSRF token has expired," which means nothing to a
receptionist, and loses whatever they had typed.

**JO status: open, unchanged.** `app.py:79` — `CSRFProtect(app)`, no `CSRFError` import or
handler anywhere.

**IQ status: open, identical.** `app.py:63` — same instantiation, no handler.

**Fix (both apps, identical):**

```python
from flask_wtf.csrf import CSRFError

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash("Your session expired while this page was open. Please log in again — "
          "you may need to re-enter what you were working on.", "error")
    return redirect(url_for("login"))
```

---

## 🟡 E-18 — Confirmed-clean areas, for the record

Worth stating explicitly so these don't get re-audited later. Confirmed no 500 path in
either app in:

* **SQL injection / dynamic `ORDER BY`** — `visits_list`, `patients_list`, `pos_history` and
  the inpatient views all map the `sort` parameter through a whitelist dict with a safe
  default, in both apps.
* **The `?` → `%s` placeholder translation** — grepped every SQL string in both codebases;
  none contains a literal `?` inside a string literal, none contains a literal `%` alongside
  bound parameters. The comment's caveat still stands for future changes, in both apps.
* **Pagination** — `get_page()` (`app.py:549` IQ, `551` JO) catches `ValueError`, clamps to
  `MAX_PAGE`, in both.
* **Division by zero** — guarded by a truthiness check on the denominator throughout
  `logic.py`, in both.
* **Background jobs** — `jobs.py`'s `runner()` (line 77 IQ, 74 JO) catches `Exception` and
  records `status: "error"`; a crash inside Insights, Retention, Backup, Restore or Update
  cannot 500 the polling request, in either app.
* **`inject_globals()`** (`app.py:722` IQ, `711` JO) — wrapped in a bare `except` with
  static fallbacks, specifically so a dead database can't throw a second exception while
  rendering the first one's error page, in both.
* **PDF export routes** — all check the record exists with a `SELECT 1` before calling into
  `pdf_export`, in both apps (not re-verified line-by-line this pass, no reason to expect
  divergence).
* **Attachment serving** — path traversal in `/files/<path:relpath>` is neutralised because
  the row lookup is by exact `relative_path` match; `send_from_directory` raises a clean 404,
  in both apps.

**Not independently re-verified this pass, flagged rather than asserted:** the IQ research
pass spot-checked anchor points for these (function signatures/line numbers) and found IQ
structurally parallel to JO in every case checked, but did not re-derive each guarantee from
first principles the way the original JO pass did. No reason to believe divergence, but
noting the confidence level honestly.

---

## IQ-only sweep — no new findings

Both custom-role CRUD, in-app backup restore, the folder-browser API, and manual barcode
entry exist in **both** apps now (a stale premise in the original audit — JO gained all of
these in a parity pass earlier today; see `COMPARISON.md`). Sweeping the genuinely
IQ-specific modules (`autostart.py`, IQ's more mature `backup.py` with its
`maintenance_lock`, `money.py`) for the same bug classes found no unguarded path in any of
them — every OS-interacting call is wrapped in `try/except OSError` or `except Exception`,
every route returns `(ok, message)` tuples rather than raising. These are newer, better-
guarded areas of the codebase than E-01–E-18's older routes. No E-19+ findings.

---

## Could not verify without a live database

**`auth.log_change()` writes typed values into `TEXT` columns.** `audit_log.old_value` and
`new_value` are `TEXT`, but values passed in (`diff_dict()`) are often `Decimal`/`float`
(any money field), `bool`, or `date`. Postgres removed implicit casts to `text` in 8.3, so
whether this works depends on how psycopg 3 types the parameter.

**JO status: unverified, same gap.** No `_as_text()` helper in `auth.py`.

**IQ status: unverified, same gap — but the specific failure mode may differ.** No
`_as_text()` helper either. Since IQ's money type is `float` (not JO's `Decimal`), psycopg 3
typically infers a Python `float` as `double precision`, not `numeric` — the exact "column
is of type text but expression is of type numeric" error anticipated for JO's `Decimal`
fields may not be IQ's actual failure mode (could still fail on `bool`/`date` values the same
way). Flagging, not asserting — this needs the same live-DB verification in both apps.

**Fix, worth applying regardless of whether it's currently firing (both apps, identical):**

```python
def _as_text(v):
    return None if v is None else str(v)
...
(uid, uname, ts, "update", table_name, record_id, field, _as_text(old), _as_text(new)),
```

**Decision (resolved 2026-08-24):** live verification is available — the isolated test
environment (`scripts/isolated_test_env.sh`) gives real Postgres access for both apps. This
will be exercised directly rather than left as a written-but-untested fix, once
implementation begins. See §Decisions.

---

## Reproduction checklist

A manual QA pass, run against **both** apps. Each line should produce a **flash message or
a branded error page**, never a traceback box or a raw white page. Port numbers per
`scripts/isolated_test_env.sh`: IQ 5091, JO 5092.

**Settings (E-01, E-02)** — these need `curl`, since the form inputs are `type="time"`:
```bash
# Should be rejected with a flash, not a 500 — and the app should still restart afterwards
curl -X POST http://127.0.0.1:$PORT/settings -b cookies.txt \
     -d "csrf_token=$TOKEN&appt_start_time=9am&appt_end_time=6pm"
curl -X POST http://127.0.0.1:$PORT/settings -b cookies.txt \
     -d "csrf_token=$TOKEN&backup_time=nope"
# JO only (IQ already passes this): restart the app afterward — it must come up.
# Then: open /appointments and /settings on both apps. Both must render.
```

**Forms — do these in the browser, on both apps:**
- [ ] New Visit → set Body Condition Score to `0`, save. (E-05)
- [ ] JO only: any price field → type a 10-digit phone number, save. (E-06 — not reachable
      the same way in IQ; use an oversized `lead_time_days` on a distributor instead, which
      IQ already handles via its `NumericValueOutOfRange` flash)
- [ ] Visit → Edit → change Case Status via devtools to `Discharged`, save. (E-07)
- [ ] Price List → Bulk edit, blank one row's category via devtools, Save Changes. (E-08)
- [ ] Boarding → New, submit with the search box typed in but no result clicked. (E-10)
- [ ] Visit → New Patient, leave the owner phone blank and the owner name blank. (E-12)
- [ ] Log in, wait for the session to expire (or clear the cookie), submit an open form. (E-17)

**URLs — paste directly, on both apps:**
- [ ] `POST /inventory-catalog/NOPE/edit` (E-11)
- [ ] `/owners/OW001%00` → should be a clean 400 (already handled; confirms the guard)
- [ ] `/visits?page=abc` and `/visits?page=-5` → should render page 1

**Load (E-03), on both apps:**
```bash
seq 1 30 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
    -b cookies.txt http://127.0.0.1:$PORT/insights
# Expect 200s and 503s. Any 500 means the PoolTimeout handler is missing or not firing.
```

**Seed path (E-13), on both apps:** put `"audit_overdue_days": "soon"` into
`seed_data.json`'s settings, run `setup.py`, then open the Dashboard.

---

## Decisions — resolved 2026-08-24, before implementation

Talked through with the user directly; recorded here so implementation doesn't need to
re-derive or re-ask them.

| Question | Decision | Where it shows up |
|---|---|---|
| E-06 overflow message wording | Vague ("too large — check for a typo"), not a precise numeric limit. Applies to JO's `parse_money`/`parse_quantity` and IQ's `parse_int`. | E-06 |
| E-03 busy page | New `error_busy.html` (not a reused `error_500.html`, which carries the traceback box), 503 status, manual refresh button — not auto-refresh (avoids amplifying load at exactly the wrong moment at a front desk). | E-03 |
| E-05 BCS = 0 | Reject as invalid, same as any other out-of-range value — do not silently coerce to `NULL`. | E-05 |
| E-08 bulk-edit failure semantics | Per-row errors, not atomic-whole-batch rejection — these pages are used for 50-row edits. | E-08 |
| E-04 `required_field()` scope | Include the behavior change (rejecting currently-accepted blank values, e.g. an empty owner name) across all fourteen sites, both apps — not just the missing-key crash. | E-04 |
| E-03/general verification access | Resolved operationally — `scripts/isolated_test_env.sh` gives real isolated-Postgres access for both apps; fixes will be verified live, not just described. | throughout |

---

## Suggested order of work

**First — the two that can take the system down.** E-01 and E-02, **JO only** (IQ already
has both fixed). Roughly 30 lines total across `app.py`, `scheduler.py` and `logic.py`,
copied from IQ's own already-working versions. E-13 shares the helper pattern (both apps),
fold it in.

**Second — the missing handlers.** E-03 (`PoolTimeout` → 503, both apps), E-04 (`400`
handler + `required_field()`, both apps), E-17 (`CSRFError`, both apps). Additive, touch
nothing existing, each converts a whole class of raw error page into a branded one.

**Third — validation at the parse layer.** E-06 (JO: `MAX_MONEY`/`parse_quantity`; IQ:
bounded `parse_int` only — much smaller scope) and E-05 (`parse_bcs`, both apps, identical).
Single-function changes each call site inherits.

**Fourth — per-route validation.** E-07, E-08, E-09, E-10, E-12. Mechanical, both apps, each
already has a correct sibling elsewhere in its own file to copy from.

**Fifth — the one-offs.** E-11, E-14, E-15 (**JO only** — IQ already fixed), the `_as_text()`
change.

**Already done, no action needed:** E-01, E-02, E-15 (IQ only, verified fixed by earlier
unrelated work); E-16 (both apps, was never actually a live bug).

**Note on overlap with the orphaned-records audit.** E-12 here and F-03's `IntegrityError`
discussion in `ORPHANED_RECORDS_AUDIT.md` are the same bug — fix once. F-01 there (teardown
committing on crash) and F-04 there (no `BadDate` handler) are the same code region as
E-03/E-04/E-17 here, both apps: until F-01 lands, every 500 in this document also commits
whatever the route had already written, so fixing the crashes and fixing the partial-commits
are the same piece of work approached from two sides. Do F-01 first.
