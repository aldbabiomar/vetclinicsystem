# IQ ↔ JO Divergence Audit

**Date:** 2026-08-24
**Versions audited:** VetClinicSystem IQ `v1.9.0`, VetClinicSystem JO `v1.7.0`
**Scope:** every tracked file in both repositories — schema, Python, templates,
CSS, JS, config.

This is a point-in-time audit, not a living document. `COMPARISON.md` remains
the narrative record that gets appended to as work lands; this file is the
systematic sweep behind it. Where the two disagree, re-run the method in
Appendix A rather than trusting either.

---

## Method

Naïvely diffing the two codebases is useless — every second line differs on
`IQ`/`JO`, `IQD`/`JOD`, `vetclinicsystemiq`/`vetclinicsystemjo`. So each shared
file was **normalized** (those tokens replaced with placeholders) and only then
diffed. What survives normalization is genuine divergence.

Six phases, each mechanical and reproducible:

1. File inventory — what exists in one app and not the other
2. Normalized diff of all 105 shared files — which have genuinely diverged
3. Money logic — traced end to end, every rounding and parsing site
4. Schema — table set, column set, every column type
5. Python — function and route inventories per module
6. Front-end — CSS tokens, selectors, templates, JS

---

## Executive summary

**The two apps are far closer than their file counts suggest, and the
divergence is overwhelmingly deliberate.**

- **Database structure is at complete parity.** Same 44 tables. Same column
  set in *every* table. Not one table or column exists in one app and not the
  other.
- **Of 61 column-type differences, 60 are the money conversion** — the single
  intended divergence. Exactly one is not (§4.2).
- **Routes are at parity**: IQ 147, JO 146; the differences are one naming
  variant and IQ's extra `/favicon.ico`.
- **JO's CSS is a strict subset of IQ's** — zero JO-only selectors, zero
  JO-only tokens.

Genuine gaps worth a decision are collected in §7. The headline ones: JO has
**no `:focus-visible` styling at all** (keyboard accessibility), JO is missing
IQ's `NumericValueOutOfRange` error handler, JO's folder-browser rows are
**unstyled** because the feature shipped without its CSS, and JO's weekend
definition is hardcoded where IQ's is configurable.

---

## 1. File inventory

| | IQ | JO |
|---|---|---|
| Tracked files | 131 | 109 |
| Shared | 105 | 105 |

**IQ-only (26).** Nearly all of it is the multi-palette branding system —
20 image assets: `error-{403,404,500}[-champet].png`, `favicon-v2*`,
`logo-{login,sidebar}-{light,dark}[-champet].png`, `favicon-champet.svg`.

Beyond images:
- `money.py` — the IQD rounding module (§3.1). The single most important
  file that exists in one app only.
- `static/rebuild.js`
- `templates/_back_link.html`

**JO-only (4).**
- `tests/test_no_raw_form_dates.py` — a static-analysis regression guard
  with no IQ equivalent
- `uploads/.gitkeep`

**Not real differences:** the launcher scripts appear in both "only" lists
purely because they are named `Start VetClinicSystem.command` in IQ and
`Start VetClinicSystem JO.command` in JO.

---

## 2. Divergence map

Of 100 shared **text** files, **18 are byte-identical after normalization** —
true parity. The remaining 82 differ. Ranked by differing lines:

| File | Δ lines | Nature |
|---|---:|---|
| `app.py` | 2437 | money types, helper factoring, per-app conventions |
| `logic.py` | 1479 | money math, 5 IQ-only functions |
| `CHANGELOG.md` | 575 | independent version histories — expected |
| `schema_postgres.sql` | 563 | almost entirely the money column conversion |
| `templates/inventory_catalog.html` | 444 | |
| `static/style.css` | 440 | IQ superset: palettes, focus, material layer |
| `templates/settings.html` | 405 | |
| `templates/refunds.html` | 228 | |
| `backup.py` | 203 | |
| `templates/inpatient_detail.html` | 179 | |
| `pdf_export.py` | 144 | money formatting `,.0f` vs `,.3f` |
| `setup.py` | 139 | |
| `auth.py` | 109 | |
| `templates/base.html` | 102 | |

Files at **true parity** after normalization include `jobs.py`, `scheduler.py`,
`attachments.py`, `db.py` structure, and most consignment templates.

---

## 3. Money logic — the core divergence

This is the divergence everything else defers to, and the reason
`CLAUDE.md` forbids copying a money-adjacent fix between the apps untested.

### 3.1 The models

| | IQ | JO |
|---|---|---|
| Currency | IQD | JOD |
| Subunit in real use | none (whole numbers) | fils — 3 decimals, per ISO 4217 |
| Python type | `float` | `Decimal` |
| Storage | `DOUBLE PRECISION` | `NUMERIC(12,3)` |
| Smallest payable unit | 250 IQD note | 0.001 JOD |
| Rounding | `money.round_to_denomination()` | `round(x, 3)` |
| Display (`fmt_money`) | `f"{round(amount):,}"` | `f"{amount:,.3f}"` |

**IQ has `money.py`; JO has no equivalent and needs none.** It defines
`SMALLEST_NOTE = 250`, `CLEANUP_CAP = 1000`, and three helpers:
`round_to_denomination(amount, denom, mode)`, `fmt_money()`,
`is_denomination_valid()`.

`round_to_denomination` supports three modes, and the choice per call site is
deliberate:
- `"nearest"` — half-up via `math.floor(x/denom + 0.5)`, explicitly *not*
  Python's `round()`, which uses banker's rounding and would send an exact
  125 IQD to 0 ("free") depending on parity
- `"up"` — never let rounding reduce what the clinic is owed
- `"down"` — for change due; never hand back more cash than owed

### 3.2 `parse_money` — where the type divergence starts

Both reject non-finite input (`nan`/`inf`), for the same documented reason:
every downstream bound check (`x > cap`, `x < 0`) evaluates to `False` against
NaN, so an unchecked NaN doesn't merely bypass validation — it *appears to
pass* it.

- **IQ** returns `float`, guarded by `math.isfinite`.
- **JO** returns `Decimal`, guarded against `Decimal("nan")`/`Decimal("inf")`.
  Its docstring records the crucial property: mixing `Decimal` and `float` in
  one expression raises `TypeError` *at that line* — treated as a feature,
  since a silent float coercion would reintroduce exactly the precision loss
  the type exists to prevent. Plain `int` mixes with `Decimal` fine; `float`
  does not.

JO additionally has **`parse_quantity`** (no IQ equivalent) for the same
reason applied to quantities.

### 3.3 `compute_bill_totals` — the shared entry point

Both apps expose the same signature,
`compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0)`,
and both are the single place bill math lives. Internally they differ:

**IQ**
```
raw_total = subtotal * (1 - discount_percent / 100)
total     = money.round_to_denomination(raw_total)
if 0 < raw_total <= 125 and discount_percent < 100:
    total = money.SMALLEST_NOTE          # anti-"looks free" floor
total   = max(total - cleanup_amount, 0)
balance = money.round_to_denomination(total - paid)
```

**JO**
```
total   = round(subtotal * (1 - discount_percent / Decimal(100)), 3)
total   = max(total - cleanup_amount, 0)
paid    = round(paid or 0, 3)
balance = round(total - paid, 3)
```

Two IQ-only behaviours have no JO counterpart and should never be ported:
- the **anti-"looks free" floor** — a genuinely non-zero bill under 125 IQD is
  lifted to 250 rather than rounding to nothing; a 100% discount is exempt as
  an intentional waiver
- **rounding the balance**, not just the total

JO's code carries an explicit note that its `balance <= 0` check used to be
`balance <= 0.5`, inherited unchanged from the IQD fork where it absorbed
rounding noise. In JOD, 0.5 is 500 fils of real uncollected money, not noise —
the tolerance was removed. **This is the exact failure mode `CLAUDE.md` §2.3
warns about, and it has already bitten this codebase once.**

### 3.4 Rounding call sites

IQ calls `round_to_denomination` in **16 places** (5 `app.py`, 4 `logic.py`,
5 `pdf_export.py`, 2 internal). Each has a JO counterpart that does exact
`Decimal` arithmetic instead:

| Site | IQ | JO |
|---|---|---|
| `compute_bill_totals` total | `round_to_denomination(raw_total)` | `round(…, 3)` |
| `compute_bill_totals` balance | `round_to_denomination(total - paid)` | `round(total - paid, 3)` |
| `pos_checkout` total | `round_to_denomination(subtotal * (1 - d/100))` | `round(subtotal * (1 - d/Decimal(100)), 3)` |
| `pos_checkout` change due | `round_to_denomination(cash - total, mode="down")` | `round(cash - total, 3)` |
| `consignment_settlement_new` | `round_to_denomination(amount_paid)` | `round(amount_paid, 3)` |
| `refund_retail_save` | `round_to_denomination(total, mode="down")` | `round(total, 3)` |
| `refund_service_save` | `round_to_denomination(amount)` | *(no rounding — exact)* |

**Change due is the most user-visible behavioural difference.** IQ rounds it
*down* to a 250 note so the clinic never hands back more cash than it owes,
absorbing the shortfall. JO returns the exact figure to the fils.

### 3.5 Money-adjacent helpers

- **`flash_cash_denomination_warning`** — IQ only. Warns when an amount is not
  payable with available notes. Meaningless in JOD; correctly absent.
- **`cleanup_amount_error` / `discount_percent_error`** — IQ factors these into
  shared helpers; JO inlines the equivalent checks at each site. Same rules,
  different structure. Both were followed as-is when boarding discounts were
  added, rather than being unified.

---

## 4. Schema

### 4.1 Structure — complete parity

- **44 tables in each. Identical table set.**
- **Every shared table has an identical column set.** Zero columns exist in
  one app and not the other.

This is a stronger result than expected and is the clearest evidence the two
schemas have been kept deliberately in step.

### 4.2 Column types — 61 differences, 60 of them money

The money conversion is consistent and principled:

| Purpose | IQ | JO |
|---|---|---|
| Money amounts | `DOUBLE PRECISION` | `NUMERIC(12,3)` |
| Quantities | `DOUBLE PRECISION` | `NUMERIC(10,3)` |
| Discount percentages | `DOUBLE PRECISION` | `NUMERIC(5,2)` |

JO retains `DOUBLE PRECISION` on exactly the columns that are **not** currency
and never mix with it — `weight_kg` (×2), `stock_counted`,
`received_since_prior`, `reorder_threshold`, `target_coverage_days`,
`change_qty`. That restraint is correct and worth preserving.

**The one non-money type difference:**

| Column | IQ | JO |
|---|---|---|
| `users.password_changed_at` | `TEXT` (nullable) | `TEXT NOT NULL DEFAULT ''` |

Each app is *internally* consistent — schema and migration agree within each —
so this is a genuine IQ↔JO divergence, not drift inside either. It has a
behavioural consequence (§5.3).

---

## 5. Python modules

### 5.1 Function inventory

| Module | IQ | JO | Divergence |
|---|---:|---:|---|
| `app.py` | 217 | 214 | see below |
| `logic.py` | 88 | 83 | 5 IQ-only |
| `auth.py` | 19 | 18 | `is_system_admin` IQ-only |
| `backup.py` | 22 | 22 | same set |
| `updater.py` | 26 | 26 | same set |
| `pdf_export.py` | 12 | 12 | same set |
| `db.py` | 12 | 12 | same set |
| `attachments.py`, `jobs.py`, `scheduler.py`, `setup.py`, `import_seed.py`, `reconcile_attachments.py`, `autostart.py`, `desktop_shortcut.py` | — | — | **same function set in all eight** |

**`app.py` differences that are only naming:**
`_consignment_{receiving,returns,shrinkage}_context` (IQ) vs
`_consignment_*_page_context` (JO); `inventory_catalog_barcode_generate` (IQ)
vs `inventory_catalog_create_barcode` (JO).

**`app.py` differences that are real:**

| Function | Only in | Meaning |
|---|---|---|
| `static_asset` | IQ | palette-branched asset filenames — multi-palette only |
| `favicon_ico` | IQ | serves the branded `.ico` |
| `flash_cash_denomination_warning` | IQ | 250-note payability warning |
| `cleanup_amount_error`, `discount_percent_error` | IQ | shared validators; JO inlines |
| `handle_numeric_out_of_range` | IQ | **error handler JO lacks — §7.2** |
| `clean_date_filter` | JO | Jinja date filter |
| `parse_quantity` | JO | Decimal quantity parsing |

**`logic.py` — 5 IQ-only functions:** `count_audit_sessions`,
`patient_inpatient_cases`, `patient_outpatient_visits`, `vet_users`,
`weekday_is_weekend`.

### 5.2 Routes

IQ 147, JO 146. The only differences:

- `/favicon.ico` — IQ only (branding)
- `/inventory-catalog/<id>/barcode/generate` (IQ) vs
  `/inventory-catalog/<id>/create-barcode` (JO) — same feature, different path

**Everything else is route-for-route identical.**

### 5.3 Error handlers

IQ registers 13, JO 12. The missing one is
**`@app.errorhandler(dbmod.NumericValueOutOfRange)`** — and JO's `db.py`
doesn't export the exception at all (IQ's `db.py` line 32 does).

Consequence: an out-of-range number reaching a numeric column gives IQ a
friendly *"That number is too large to be a valid value here."* In JO it falls
through to the generic `Exception` handler — so not a raw 500, but a generic
error page instead of a specific message.

### 5.4 Session invalidation on password change

The same security control, implemented with different null-handling:

- **IQ** — `if session.get("password_changed_at") != user["password_changed_at"]:`
- **JO** — `if user["password_changed_at"] and session.get(...) != user[...]:`

JO's truthiness guard exists because its column is `NOT NULL DEFAULT ''`, so a
user who has never changed their password holds `''`. Both are safe on the
normal path: JO stamps a real timestamp on any change or reset, which activates
the check. Worth recording because the two are *not* interchangeable — porting
IQ's line into JO would make every never-changed user's session invalidate
against `''`.

### 5.5 Weekend definition

- **IQ** — `DEFAULT_WEEKEND_DAYS = {5, 6}`, overridable per-deployment via a
  `settings.weekend_days` row, read by `logic.weekday_is_weekend(db)`
- **JO** — hardcoded `WEEKDAY_IS_WEEKEND = [F,F,F,F,F,T,T]` with a comment
  noting Jordan's Sunday–Thursday work week

Same effective default (Fri/Sat). JO simply cannot be reconfigured.

---

## 6. Front-end

### 6.1 CSS — JO is a strict subset

| | IQ | JO |
|---|---:|---:|
| Lines | 806 | 600 |
| Selectors | 286 | 249 |
| Palette blocks | 8 | 4 |
| Distinct tokens | 37 | 29 |
| **JO-only selectors** | — | **0** |
| **JO-only tokens** | — | **0** |

IQ's 8 palette blocks are 2 palettes (default + ChamPet) × light/dark; JO's 4
are 1 palette × light/dark.

**IQ-only tokens (8):**
- `accent-alt`, `accent-alt-ink`, `accent-alt-tint` — the chart/grooming
  accent; exists to stay distinguishable across four palettes, so JO has no
  use for it
- `primary-pastel`, `sidebar-active-ink` — extra palette tokens
- `material-structural-blur`, `material-floating-blur`,
  `sidebar-bg-translucent` — a translucency/blur layer (§6.2)

### 6.2 Three substantive front-end gaps in JO

1. **`:focus-visible` — IQ 12 rules, JO 0.** JO has no visible keyboard-focus
   indicator anywhere. Accessibility gap, not cosmetic.
2. **Translucency layer — IQ 8 `backdrop-filter` uses, JO 1.** IQ has a
   translucent, blurred sidebar and surfaces; JO is flat.
3. **`.folder-browser-row` is used but unstyled in JO.** JO's
   `settings.html` builds these rows with the identical JS to IQ (same class,
   same inline `cursor`/`padding`), but JO's stylesheet has **zero** rules for
   the class. IQ supplies the row separators and hover feedback. The feature
   was ported without its CSS.

### 6.3 Templates

JO lacks `templates/_back_link.html` (and the matching `.back-link` CSS). Every
other template exists in both.

---

## 7. Findings — worth a decision

Ordered by consequence. None is a data-integrity risk.

> **Status, 2026-08-25 — 7.1 through 7.5 are closed.** All five were
> implemented and verified live in the isolated test environments (IQ :5091,
> JO :5092), then torn down. Shipped as IQ v1.10.0 / JO v1.8.0. 7.6 was assessed
> on 2026-08-25 and deliberately left open as low-value. That assessment turned
> up **7.7 below — a live 500 in IQ that this audit missed**; it is now fixed and
> shipped (IQ v1.10.1 / JO v1.8.1). Per-finding notes are inline below.

**7.1 JO has no `:focus-visible` styling.** Anyone navigating JO by keyboard
gets no visible focus indicator. IQ's 12 rules could be ported directly — they
are palette-token based and carry no IQ-specific assumptions. *Recommend
fixing.*
> **Closed 2026-08-25.** Ported verbatim into JO's `static/style.css` ahead of
> the Toast section, including the `tr[tabindex="0"]` inset-outline rule.
> Verified live: a Tab-focused input renders `2px solid #B21C43` at `2px`
> offset, and `:focus-visible` matches. JO went 0 → 12 rules.

**7.2 JO is missing the `NumericValueOutOfRange` handler.** Needs one line in
`db.py` to export the exception and one handler in `app.py`, both copyable
verbatim. *Recommend fixing.*
> **Closed 2026-08-25.** Both added, the handler placed exactly where IQ has
> it (immediately before the `PoolTimeout` handler). Verified by inspecting
> the live `error_handler_spec` in both apps: `NumericValueOutOfRange` →
> `handle_numeric_out_of_range` in each. JO's handler count is now 13,
> matching IQ.

**7.3 JO's folder-browser rows are unstyled.** Three CSS rules, portable as-is.
*Recommend fixing.*
> **Closed 2026-08-25.** All three rules added at IQ's placement (before the
> Tables section). Verified live in JO's Settings folder browser: 10 rows, each
> resolving a real `1px solid var(--line-soft)` bottom border, the hover
> background, and the `:last-child` border removal.

**7.4 JO's weekend is hardcoded.** Fine while JO is single-deployment. Becomes
a real limitation if JO is ever installed somewhere with a different work week.
*Decide, don't default.*
> **Closed 2026-08-25 — decided in favour of making it configurable.** The
> constant `WEEKDAY_IS_WEEKEND` became `DEFAULT_WEEKEND_DAYS = {5, 6}` plus
> `weekday_is_weekend(db)`, which reads a `settings.weekend_days` row
> (comma-separated 0-6, same numbering as `EXTRACT(DOW)`). Verified live: no
> setting → Fri/Sat (identical to the old hardcoded list), `'0,6'` → Sun/Sat,
> `'4,5'` → Thu/Fri, and a malformed value falls back to the default rather
> than raising. No UI yet — it is a settings row, deliberately.

**7.5 `users.password_changed_at` nullability differs.** Both apps behave
correctly today. Worth aligning only as tidiness — and if aligned, §5.4's guard
must move with it.
> **Closed 2026-08-25.** IQ aligned to JO's stricter `TEXT NOT NULL DEFAULT ''`,
> in the schema and via three idempotent migration statements (backfill NULLs →
> `SET DEFAULT` → `SET NOT NULL`, in that order — `SET NOT NULL` fails on any
> existing NULL). **§5.4's guard moved with it, as this finding required:** IQ's
> session check had relied on `NULL == None` comparing equal, so without the
> truthiness guard the change would have logged out every existing IQ user once.
> Verified by simulating a pre-existing install — column dropped back to
> nullable with a real NULL row, then re-running the migrations: converged to
> `not null / ''::text` with zero NULLs, 73 statements applied, no
> `migration_failures` entry.

**7.6 IQ has no automated tests; JO has one.** `tests/test_no_raw_form_dates.py`
guards a real past incident and applies equally to IQ. Both now have
`tests/test_desktop_shortcut_target.py`.
> **Assessed 2026-08-25, left open — low value.** IQ already passes this test:
> 0 offenders across 21 date fields and 248 `f.get`/`f[]` reads in `app.py`. It
> is not *vacuous* on IQ (the idiom it greps for is genuinely used there), so it
> would work as a regression tripwire — but it only scans `app.py`, only where
> the form variable is literally named `f`, and its docstring cites
> `data_integrity_framework.md`, **which exists in neither repo**. Porting it
> as-is would copy a dangling reference. Nice-to-have, not scheduled.
>
> **CLOSED 2026-08-26 — ported to IQ, and strengthened in both apps.** Rather
> than copy the weak version across, all three weaknesses above were fixed and
> the result was written into both apps (tailored per app, not shared: IQ's
> allowed-wrapper list is `clean_date(` only, JO's also has
> `clean_date_filter(`, which IQ has no equivalent of). It now scans every
> root module rather than `app.py` alone, captures the form object instead of
> assuming it is named `f`, and matches the whole file rather than line by
> line. The dangling `data_integrity_framework.md` reference is replaced by
> `COMPARISON.md` §21, which describes the real incident. Two control tests and
> an anti-vacuity floor were added, and both were mutation-proven. Full writeup
> in `COMPARISON.md` §28.

---

### 7.7 — found while assessing 7.6, and missed by this audit

**`logic.parse_date()` validated a 10-character prefix, not the value.**
Byte-identical in both apps. `datetime.strptime(str(v)[:10], "%Y-%m-%d")`
truncated *before* validating, so `"2026-08-25garbage"` returned a real `date`
and raised nothing — which defeated every route guarding a user-supplied
`?date=` with a bare `try: parse_date(x) / except ValueError:`. The unvalidated
string reached the query and a real `DATE` column turned it into a Postgres cast
error: **IQ `/visits` and `/refunds` were a reproducible 500**, confirmed live.
JO's `/cash-register` and appointments `week=`/`day=` share the bare-guard shape.

**This audit missed it, and the reason is instructive.** IQ's inline
`try/except parse_date` *looked* equivalent to JO's `clean_date_filter()` — and
has better UX, since IQ flashes a message where JO silently drops the filter —
so the sweep accepted it by reading rather than running. That is precisely the
"the surrounding code looks the same, so it must apply the same way" trap
`CLAUDE.md` §2.2 exists to prevent. **Related, and also missed: IQ has zero
occurrences of `clean_date_filter` — it only ever received the write-side half
of JO's 2026-08-23 date fix (`9034cf6`).**

**Closed 2026-08-25.** Fixed in the shared helper in both apps rather than at
the call sites, so it closes the class: `date.fromisoformat()` falling back to
`datetime.fromisoformat().date()`. The fallback is load-bearing — `TEXT` columns
`backup_log.started_at` and `visits.case_status_changed_at` store a full
`isoformat()` stamp and legitimately relied on the truncation. Shipped as
**IQ v1.10.1 / JO v1.8.1**. Full writeup in `COMPARISON.md` §21.

---

## 8. Deliberate divergences — do not "fix"

Recorded so a future sweep doesn't file them as gaps:

1. **The entire money model** (§3) — currency, type, storage, rounding,
   formatting, the anti-"looks free" floor, note-rounded change due.
2. **`money.py` existing only in IQ.**
3. **Multi-palette branding** — the ChamPet palette, `static_asset()`,
   `/favicon.ico`, and 20 branded image assets. The *palette* axis is IQ-only;
   light/dark is in both.
4. **`--accent-alt*` tokens** — IQ-only by construction.
5. **`flash_cash_denomination_warning`** — meaningless in JOD.
6. **Phone-number format** — different country codes and lengths.
7. **Helper factoring** — IQ's shared `cleanup_amount_error` /
   `discount_percent_error` vs JO's inline checks. Both were deliberately
   preserved when boarding discounts were added.
8. **`_page_context` naming** and the barcode route path.

---

## Appendix A — reproducing this audit

```bash
# 1. file inventory
cd webapps/vetclinicsystem_iq-main && git ls-files | sort > /tmp/iq.txt
cd ../vetclinicsystem_jo-main      && git ls-files | sort > /tmp/jo.txt
comm -3 /tmp/iq.txt /tmp/jo.txt

# 2. normalized diff — replace naming tokens, then diff
#    VetClinicSystem IQ|JO -> «APP», VETCLINICSYSTEMIQ|JO -> «ENV»,
#    vetclinicsystemiq|jo -> «slug», vetclinicsystem_iq|jo -> «repo»,
#    IQD|JOD -> «CUR», Start VetClinicSystem[ JO] -> «LAUNCH»

# 3. money surface
grep -rn "round_to_denomination" webapps/vetclinicsystem_iq-main/*.py
grep -c "NUMERIC(12,3)" webapps/vetclinicsystem_jo-main/schema_postgres.sql

# 4. schema — parse CREATE TABLE blocks, compare table/column/type sets
# 5. python — regex ^def (\w+)\( and @app.route("([^"]+)" per module
# 6. css — parse :root / html[data-*] blocks for --tokens; compare selectors
```

Full scripted versions of phases 2, 4, 5 and 6 were run to produce this
document; each is a short Python script over both trees.

---

## Appendix B — parity scorecard

| Dimension | Result |
|---|---|
| Tables | **44 = 44**, identical set |
| Columns per table | **identical in all 44** |
| Column types | 61 differ — **60 are the money conversion** |
| Routes | 147 vs 146 — 1 naming variant + IQ's favicon |
| Modules with identical function sets | **8 of 15** |
| Error handlers | 13 vs 12 |
| CSS selectors | IQ superset — **0 JO-only** |
| CSS tokens | IQ superset — **0 JO-only** |
| Shared files byte-identical after normalization | 18 of 100 |
