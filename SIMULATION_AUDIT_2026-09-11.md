# Live-use simulation audit — IQ v1.13.0 / JO v1.11.0

**Date:** 2026-09-11
**Method:** both apps driven as real users through a full clinic day and then
through rare/hostile edge cases, in their own isolated test environments
(`scripts/isolated_test_env.sh`, IQ :5091 / JO :5092). Nothing here touched a
real install or a real database.
**Volume:** ~2,800 HTTP interactions per pass plus two full browser walks
(Chromium, 33 pages each), across all 149 routes.

> **STATUS: CLOSED — all six fixed, released 2026-09-11 as IQ v1.14.0 /
> JO v1.12.0**, with v1.14.1 / v1.12.1 immediately after so the new database
> constraints reach an *upgraded* install and not only a fresh one. The fix
> for each finding is recorded under it, below its evidence. `COMPARISON.md`
> §55 is the shipping record; `scripts/simulation/verify_fixes.py` re-checks
> all six (52 assertions, each paired with a control) and
> `scripts/simulation/prove_guards.py` reverts each fix and confirms the bug
> returns — 10/10. Suites after the work: **IQ 761, JO 736, zero skips**, and
> the hostile sweep below now reports **zero** findings where it found one.
>
> **Six defects found**, all reproduced live and re-run from a clean state.
> Two are money defects that lose real cash; one is a crash; one silently
> corrupts stock data in a way that disables a safety guard. Four affect
> **both** apps; two are IQ-only and are direct consequences of the
> 250-IQD denomination model (`COMPARISON.md` §1.1).
>
> Everything else held up extremely well — see §8, which is as much a part of
> this report as the findings. In 1,028 hostile GET probes per app, exactly
> one produced a 500.

---

## 1. Findings at a glance

| # | Severity | Apps | Area | Summary |
|---|---|---|---|---|
| **F1** (§2) ✅ | **High** | IQ | POS | A sale under 125 IQD records **total 0** — goods leave free and 100% of the tendered cash is handed back as change |
| **F2** (§3) ✅ | **High** | both | Inventory audit → POS | A stock count of `nan` is accepted and confirmed. IQ: the oversell guard is **defeated** (sold 500 units of an empty shelf). JO: POS checkout **crashes (500)** |
| **F3** (§4) ✅ | Medium | IQ | Refunds | A retail refund of a sale that collected 250 IQD is recorded as **0** — goods come back, customer is paid nothing |
| **F4** (§5) ✅ | Medium | both | Appointments | `GET /appointments?day=` (empty) → **HTTP 500** |
| **F5** (§6) ✅ | Medium | both | Inventory audit | Stock counts accept **negative** values |
| **F6** (§6) ✅ | Low | both | Inpatient | A case accepts a **discharge dated before admission** — a negative-length stay. Boarding guards this; inpatient does not |

Plus four non-defect observations in §7 — **#2 and #4 are also fixed and shipped**; #1 and #3 were left as recorded judgements (see §7).

---

## 2. F1 — POS has no anti-"looks free" floor

**IQ only. `routes/sales.py:299`.** JO is unaffected: it has no denomination
rounding at all, and its POS total is exact `Decimal`.

### What happens

`logic.compute_bill_totals()` — the path used by visits, inpatient and
boarding — deliberately refuses to let rounding turn a real bill into a free
one:

```python
# logic.py:474-483
total = money.round_to_denomination(raw_total)
# Never let rounding present a genuinely non-zero bill as "free" — but
# a 100% discount is an intentional waiver, not a rounding accident,
# so it's exempt from this floor.
if 0 < raw_total <= 125 and discount_percent < 100:
    total = money.SMALLEST_NOTE
```

**POS checkout does the rounding without the floor:**

```python
# routes/sales.py:299
total = money.round_to_denomination(subtotal * (1 - discount_percent / 100))
```

`round_to_denomination(120)` is `floor(120/250 + 0.5) * 250` = **0**. The sale
is then written with `total = 0`, and because change is computed as
`cash_received - total`, the customer gets **everything back**:

```python
# routes/sales.py:196
change_given = max(money.round_to_denomination(cash_received - total, mode="down"), 0)
```

### Reproduced

Measured directly against the running app. The same subtotals through the two
code paths:

| subtotal | POS stores | bill path stores | |
|---|---|---|---|
| 10 | **0** | 250 | diverges |
| 50 | **0** | 250 | diverges |
| 100 | **0** | 250 | diverges |
| 120 | **0** | 250 | diverges |
| 125 | 250 | 250 | agrees |
| 250 | 250 | 250 | agrees |

A real sale recorded by the app during the run:

```
sales.id=1  subtotal=10  total=0  cash_received=50000  change_given=50000
```

Two units of stock were decremented, the customer paid nothing, and the drawer
was told to return the entire 50,000 IQD tendered.

### Why this is reachable in a real clinic

Two independent routes, both realistic:

1. **Low unit price.** Anything whose line total lands under 125 IQD — a single
   tablet dispensed from a per-tablet price, a small consumable. (With the
   default 25% role cap, any cart subtotal ≤ 166 IQD reaches it.)
2. **A discount from a role with a high cap.** Confirmed live with a
   "Clinic Owner" role at a 95% cap: a **2,000 IQD item at 94% discount** →
   raw 120 → `total = 0`, and all 250,000 IQD tendered returned as change.
   Admin's own 25% cap blocks this route, so it needs a manager-type role —
   which the app fully supports creating.

Note this is *not* the same as the intended 100%-discount waiver, which the
bill path explicitly exempts. This fires at 94%, 50%, or 0%.

### The fix, as shipped

The two paths diverged because the floor is written inline in `logic.py` and
nothing shares it. Put it in `money.py` so the rule has one home:

```python
# money.py
def payable_total(raw_total, discount_percent=0, denom=SMALLEST_NOTE):
    """Round a payable amount to the note, without ever presenting a
    genuinely non-zero charge as free. A 100% discount is an intentional
    waiver, not a rounding accident, so it stays exempt.
    Single source of truth for POS and compute_bill_totals alike — these
    two had drifted apart, which is what this function exists to prevent."""
    total = round_to_denomination(raw_total, denom)
    if 0 < raw_total <= denom / 2 and (discount_percent or 0) < 100:
        return denom
    return total
```

```python
# routes/sales.py — replace line 299
raw_total = subtotal * (1 - discount_percent / 100)
total = money.payable_total(raw_total, discount_percent)
```

```python
# logic.py — replace lines 474-483 with the same call
total = money.payable_total(raw_total, discount_percent)
```

**Shipped as written**, in IQ v1.14.0. `prove_guards.py` reverts
`pos_checkout` to the bare `round_to_denomination` and confirms a 100 IQD cart
goes back to `total = 0`; `test_simulation_findings.py` pairs each floor
assertion with a control (a 10,000 IQD sale still records 10,000) and adds
`test_both_money_paths_agree_at_every_boundary`, which walks twelve subtotals
through *both* paths and fails if they ever disagree again — the drift itself,
not just today's symptom.

---

## 3. F2 — A `nan` stock count is accepted, and disables the oversell guard

**Both apps. `routes/inventory.py:870` (IQ) / `:830` (JO), in
`_save_audit_lines()`.**

### What happens

Every money field in both apps goes through `parse_money()`, which exists
specifically to reject non-finite input. Its own comment says why:

> `float()` happily parses `"nan"`/`"inf"`/`"-inf"` without raising — and every
> bound check elsewhere in the app (`x > cap`, `x < 0`, etc.) silently
> evaluates to False against NaN, so an unchecked NaN doesn't just slip past
> validation, it appears to *pass* every check downstream.

`_save_audit_lines()` does not use it. It calls `float()` directly:

```python
# routes/inventory.py:869-875
vals = (
    float(stock), float(received),
    float(threshold) if threshold else None,
    ...
)
```

`float("nan")` succeeds, Postgres accepts `NaN` into both `double precision`
and `numeric`, and the audit can then be **confirmed and locked** — the app
reports *"Audit confirmed and locked. Inventory Status and Ordering Sheet now
reflect these counts."*

### Consequence — and it differs per app

This is a single root cause with two different downstream failures, exactly
the pattern `CLAUDE.md` §1 warns about.

**IQ — the oversell guard is defeated.** The check is a plain comparison:

```python
# routes/sales.py:166
if status and qty > status["current_stock"]:
```

`500 > nan` is `False`, so the sale proceeds. Reproduced live, with a control:

```
counted 5   -> sell 500: blocked   ['Only 5.0 unit of Test Retail Item in stock — sale blocked.']
counted NaN -> sell 500: SOLD — OVERSELL GUARD DEFEATED   ['Sale #22 completed — total 500,000 IQD.']
     sale id=22 subtotal=500000.0 total=500000.0  (nothing was in stock)
```

**JO — POS checkout crashes.** The same line, with `Decimal` on the left:

```
File "routes/sales.py", line 308, in _priced_cart_lines
    if status and qty > status["current_stock"]:
decimal.InvalidOperation: [<class 'decimal.InvalidOperation'>]
```

Every checkout of that item returns a 500 until the count is corrected — the
till stops working.

### The fix, as shipped — three layers

**1. Validate at the point of entry** (both apps), reusing the guard that
already exists rather than adding a new one:

```python
# routes/inventory.py, in _save_audit_lines()
try:
    stock_v    = parse_money(stock, required=True)
    received_v = parse_money(received) or 0
    threshold_v = parse_money(threshold)
    target_v    = parse_money(target)
except BadNumber:
    raise BadNumber(iid)
if has_negative(stock_v, received_v, threshold_v, target_v):
    raise BadNumber(iid)           # see F5 — covers the negative case too
vals = (stock_v, received_v, threshold_v,
        (1 if critical == "Y" else (0 if critical == "N" else None)),
        target_v, expiry or None, notes or None)
```

`audit_session_save()` and `audit_session_confirm()` already catch `BadNumber`
and re-render with *"Audit counts must be valid numbers"*, so both surfaces
inherit the fix with no further change. In JO this also removes a raw Python
`float` being written to the column, which is contrary to JO's
Decimal-throughout rule (§7, observation 3).

**2. Fail closed at the consumer**, so a count already stored cannot defeat the
guard:

```python
# routes/sales.py, _priced_cart_lines()
cur = status["current_stock"] if status else None
if status and (cur is None or cur != cur or qty > cur):   # cur != cur catches NaN
    return 0, [], notices, (
        f"{status['name']} has no usable stock count — run an inventory audit "
        "before selling it.")
```

This also removes JO's crash, because the NaN is caught before the `Decimal`
comparison is attempted.

**3. A database constraint**, so no future code path can reintroduce it:

```sql
ALTER TABLE audit_session_lines
  ADD CONSTRAINT audit_lines_stock_sane
  CHECK (stock_counted >= 0 AND stock_counted <> 'NaN'::float8);
```

⚠️ **The `<> 'NaN'` half is load-bearing and not obvious.** In Postgres
`'NaN' >= 0` evaluates to **true** (NaN sorts above all values), so a plain
`CHECK (stock_counted >= 0)` would *not* catch this. `'NaN' = 'NaN'` is also
true for both `float8` and `numeric`, which is what makes `<> 'NaN'` work.
Verified against both test databases before proposing it.

---

## 4. F3 — A retail refund can be recorded as zero

**IQ only. `routes/sales.py:507`.**

Retail refunds round **down**, which is deliberate and correctly reasoned —
the comment says a refund is money leaving the clinic, so rounding must never
push it above what the lines add up to. What is not handled is the case where
rounding down reaches zero:

```python
rounded_total = money.round_to_denomination(total, mode="down")
```

Because F1's floor means a small sale collects exactly 250 IQD, refunding that
same line rounds `240 → 0`, `200 → 0`, `130 → 0`. Reproduced at all three:

```
unit 240: sale collected 250.0 but the refund was recorded as 0
unit 200: sale collected 250.0 but the refund was recorded as 0
unit 130: sale collected 250.0 but the refund was recorded as 0
```

The customer hands the goods back, the item is restocked, the sale's
refundable balance is consumed — and the refund pays out nothing.

Service refunds are **not** affected: they round to nearest
(`routes/sales.py:648`), so 240 → 250. Confirmed live, with a control.

### The fix, as shipped

Keep the "never round a refund up past the line total" intent, but never
settle a real refund at zero. Refund the smallest note, capped by what the
sale actually collected:

The clamp has to sit **after** `already_refunded_total` is computed (it is
queried at line 514, below the rounding) and **before** the aggregate cap check,
so that cap still governs the result:

```python
# routes/sales.py — line 507 stays as it is; insert after already_refunded_total
rounded_total = money.round_to_denomination(total, mode="down")
already_refunded_total = db.execute(
    "SELECT COALESCE(SUM(amount),0) s FROM refunds WHERE sale_id=? AND refund_type='retail'",
    (sale_id,)).fetchone()["s"]

# Rounding DOWN must never settle a real return at zero — the customer would
# hand the goods back and be paid nothing. Pay the smallest note instead,
# but only if this sale still has that much left to give back.
if total > 0 and rounded_total == 0:
    headroom = sale["total"] - already_refunded_total
    if headroom < money.SMALLEST_NOTE:
        flash("This sale has no refundable value left to pay out — the "
              "smallest note is 250 IQD. Refund it against the original "
              "sale total instead.", "error")
        return redisplay()
    rounded_total = money.SMALLEST_NOTE

if already_refunded_total + rounded_total > sale["total"] + 1e-9:
    ...          # existing cap check, unchanged
```

The explicit refusal matters: without it, a sale whose refundable headroom is
already exhausted would fall through the cap check with `rounded_total = 0` and
record a zero refund again — the exact outcome being fixed.

**Shipped as written above**, after correcting the first draft of this
proposal, which placed the clamp at line 507 and referenced
`already_refunded_total` — a variable not defined until line 514. It would not
have run.

If the clinic would rather always refuse than ever round a refund up, the
alternative is to flash in every zero case. Either is defensible; silently
recording a refund of zero is the one outcome that should not remain.

---

## 5. F4 — `/appointments?day=` returns HTTP 500

**Both apps. `routes/clinical.py:2146` (IQ) / `:2118` (JO).**

```python
selected_day = request.args.get("day", today_iso)   # "" when ?day= is empty
try:
    logic.parse_date(selected_day)
except ValueError:
    flash("That date wasn't valid, showing today instead.", "error")
    selected_day = today_iso
```

The default only applies when `day` is **absent**. When it is present but
empty, `selected_day` is `""` — and `parse_date("")` **returns `None` rather
than raising**, so the `except` never fires:

```python
# logic.py:17-19
def parse_date(v):
    if v is None or v == "":
        return None
```

`""` then reaches Postgres as a date parameter:

```
psycopg.errors.InvalidDatetimeFormat: invalid input syntax for type date: ""
CONTEXT:  unnamed portal parameter $1 = ''
```

This is specifically the *empty* value. `?day=abc` and `?day=2026-13-45` are
both handled correctly and fall back to today — and every other date filter in
both apps (`/visits`, `/pos/history`, `/cash-register`, `/admin/logs`,
`/refunds`) handles an empty value fine. Appointments is the only one.

Reachable by clearing the date field in the appointment book's own filter, or
by any link built from an empty variable.

### The fix, as shipped

Treat present-but-empty as absent, and make the guard depend on the parse
result rather than on an exception that `parse_date` does not raise:

```python
week_anchor  = request.args.get("week") or today_iso
selected_day = request.args.get("day") or today_iso
try:
    if logic.parse_date(selected_day) is None:
        raise ValueError(selected_day)
except ValueError:
    flash("That date wasn't valid, showing today instead.", "error")
    selected_day = today_iso
```

Apply the same `or today_iso` to `week_anchor` on the line above it: `?week=`
happens not to 500 today only because `logic.week_dates("")` tolerates it,
which is luck rather than design.

---

## 6. F5 / F6 — two smaller data-integrity gaps

### F5 — negative stock counts are accepted

**Both apps, same line as **F2** (§3).** A count of `-5` is stored as `-5.0`. It
does not disable the oversell guard (`qty > -5` is true, so sales are blocked),
but it is not a possible physical count, it flows into Inventory Status and the
Ordering Sheet, and it makes the shelf look permanently un-sellable with no
explanation. **Fixed by the same `has_negative()` check in F2's patch**, and by
the `>= 0` half of the CHECK constraint.

### F6 — an inpatient case can be discharged before it was admitted

**Both apps. `routes/clinical.py` `inpatient_edit()`.** Boarding has an
explicit guard:

```python
# routes/clinical.py:1478 — boarding_edit()
if dismissal_date and entry_date and str(dismissal_date) < str(entry_date):
    flash("A stay can't end before it starts — check the dates.", "error")
```

`inpatient_edit()` has no equivalent. Reproduced with a control, in both apps:

```
control: discharge today      flashes=['Case updated.']
                              stored admission=2026-09-11 dismissal=2026-09-11
discharge before admission    flashes=['Case updated.']
                              stored admission=2026-09-11 dismissal=2024-01-01
>>> ACCEPTED: discharged 2024-01-01, admitted 2026-09-11 — a negative-length stay
```

A real typo (`2024` for `2026`) produces a stay of negative length that feeds
length-of-stay reporting and the case's own billing period.

**The fix, as shipped** — mirrors boarding's guard, in `inpatient_edit()` right after
`edited_dismissal_date` is parsed:

```python
if dismissed and edited_dismissal_date and old["admission_date"] and \
        str(edited_dismissal_date) < str(old["admission_date"]):
    flash("A case can't be discharged before it was admitted — check the dates.", "error")
    return redirect(url_for("clinical.inpatient_detail", case_id=case_id))
```

Worth checking the same pair in `inpatient_new()` if admission and discharge
can both be set there.

---

## 7. Observations — not defects, but worth a decision

1. **The login rate limiter cannot be waited out while anyone is retrying.**
   `_login_rate_limit_check()` (`app.py:221`) appends a timestamp on *every*
   attempt, including ones it rejects. A user who keeps trying after being
   limited keeps extending their own 5-minute window indefinitely. This is
   defensible as anti-brute-force, but the message — *"Please wait a few
   minutes and try again"* — tells them to do the one thing that prevents
   recovery. Consider not recording attempts that were already refused, or
   saying "wait 5 minutes **without retrying**". (This caught out this audit's
   own tooling for ~15 minutes.)

2. **A cash-drawer discrepancy is flashed as an error although it was
   recorded.** `routes/sales.py:805` flashes *"Audit recorded for …: Surplus of
   5,000 IQD"* in the `error` category. The audit **did** save. Staff reading a
   red banner will reasonably retry. A `warning` category (or wording that
   leads with "Recorded") would separate "this failed" from "this saved, and
   the drawer is off".

3. **JO writes a raw `float` into a money-adjacent column.** `_save_audit_lines()`
   is the same code in both apps, but JO's rule is `Decimal` from parse through
   storage. `stock_counted` is a quantity, not currency, so nothing is wrong
   today — but it is the one place JO's type discipline is not applied, and
   F2's fix removes it for free.

4. **One endpoint name differs between the apps for the same feature:**
   `inventory.inventory_catalog_barcode_generate` (IQ) vs
   `inventory.inventory_catalog_create_barcode` (JO). The URL is identical; only
   the endpoint name differs. Harmless until shared tooling or a ported test
   does a `url_for()` by name. Otherwise the two route tables are identical —
   149 routes each.

---

## 8. What was tested and found correct

This matters as much as the findings: these areas were attacked deliberately
and held. Re-testing them is probably not the best use of the next session.

**Hostile input — 1,028 GET probes per app, one failure.** Every id-taking
detail route (22 of them) against 14 malformed ids — `0`, `-1`, 20-digit
numbers, `' OR '1'='1`, `../../etc/passwd`, `<script>`, a 300-char id — and
every list/search route against 22 nasty values including SQL wildcards
`%`/`_`, quote-injection shapes, RTL override characters, emoji, 500-char
strings, `1e999` and malformed dates. Plus 9 pagination values (`0`, `-1`,
`1e9`, `abc`, `100001`, …) against 14 paginated views. **Only F4 produced a
500.** Search wildcards are correctly escaped; no SQL injection surfaced
anywhere.

**Concurrency — four races, all correctly serialized** (both apps):

| Race | Result |
|---|---|
| Two tills selling the **last unit** simultaneously | 1 sale recorded, not 2 |
| Two staff paying the **same bill** simultaneously | bill 1,000, payments 1,000 — no double-take |
| Two receptionists booking the **same vet slot** | 1 appointment, not 2 |
| Two registrations with the **same phone number** | 1 owner — the unique index holds |

The `FOR UPDATE` row locks and the idempotency key do what they claim.
Double-submitting a checkout with one idempotency key created exactly one sale.

**Permissions.** A genuine custom role holding only `manage_patients`, with a
real user in it (through the forced first-login password change): **44 of 45
pages denied, 1 reachable** — the one it should be. No write route leaked, and
it could not promote itself to Admin via `/admin/users/<id>/role`. Verified in
both apps.

**Auth.** CSRF is enforced against both a missing and a forged token. Every
protected page and POST redirects a logged-out visitor to `/login`. Twelve
failed logins triggers lockout, and the network-level limiter fires as well.

**Money guards on the bill path** (both apps) — all correctly refused:
overpayment beyond the balance, negative payments, discounts of `150`, `-5`,
`abc`, `NaN`, a cleanup write-off beyond its cap, and a second full payment
against an already-settled bill. POS separately refused zero/negative/text/
fractional/exponent quantities, cash tendered below the total, payouts beyond
the drawer, and negative cash counts.

**Attachments.** Eight uploads including `../../escape.png`,
`shell;rm -rf.png`, an RTL-disguised `.exe`, an SVG with an inline handler, an
empty file and a 3 MB file — none stored under a traversal-shaped path.
`/files/../../../../etc/passwd` and its URL-encoded variant served nothing.
`POST /settings/restore-now` refused both `/etc/passwd` and a traversal path.

**Browser walk** (Chromium, 33 pages per app): **zero CSP violations, zero
inline `on*=` handlers, zero console errors, zero uncaught JS exceptions, no
horizontal overflow at 375 px, and no native `confirm()`/`alert()`** — the two
conventions in `CLAUDE.md` are genuinely holding in the rendered DOM, not just
in the source-scanning tests. The job-polling pages (`/retention`,
`/insights`, `/consignment`) redirect to `?job_id=…` and render correctly; an
`ERR_ABORTED` on the first navigation is that redirect, not a fault.

**JO's money model came through clean.** None of F1/F3 apply to it, and its
exact `Decimal` arithmetic produced correct totals and refunds at every
boundary tested (`0.240` refunded as `0.240`). The divergence is doing exactly
what `COMPARISON.md` §1.1 says it should.

---

## 9. Reproducing any of this

The simulation harness is checked in at `scripts/simulation/`. Every script is
self-locating, so run them from anywhere:

```
scripts/simulation/
├── vzsim.py                  harness: login, CSRF, flash parsing, findings log
├── vzform.py                 reads real <select>/<input> options out of a page
├── day.py                    Phase 1 — the full clinic day, both apps
├── edge_money.py             POS/refund/cash money boundaries
├── edge_money2.py            refund rounding + bill-path payment ceilings
├── edge_sweep.py             1,028 hostile GET probes per app
├── edge_post.py              NaN/unicode/long-text/stale-write through forms
├── edge_perm.py              narrow custom role against every route
├── edge_concurrent.py        four races + CSRF/auth/lockout
├── edge_rest.py              attachments, barcodes, lifecycles, settings
├── browser.py                Chromium walk: CSP, handlers, console, mobile
└── repro_*.py                one focused reproduction per finding
```

Each `repro_*.py` is self-contained and prints a before/after table. Bring the
environments up first, then run any script with a throwaway venv's Python
(the dev clones have no `venv/` of their own):

```bash
scripts/isolated_test_env.sh up iq && scripts/isolated_test_env.sh up jo
```

```bash
/tmp/vz_iq_test_venv/bin/python scripts/simulation/repro_pos_floor.py
```

**Two things that cost time and will cost it again:**

- A run that trips the login lockout leaves the *network* limiter armed for
  5 minutes, and every retry — including a health check — restarts that
  window. Wait it out without touching `/login`.
- The seeded `PL301` is a **price-list** id; POS keys on the **inventory** id
  (`INV301`) via `price_list.linked_item_id`. Posting `PL301` to
  `/pos/checkout` produces *"has no sale price set"*, which reads like a data
  bug and is not one.

---

## 10. What shipped, in the order it shipped

All six findings and observations #2 and #4 are in
**IQ v1.14.0 / JO v1.12.0**, with **v1.14.1 / v1.12.1** following the same day
for F2's third layer on the upgrade path (§3).

| | Landed as | Notes |
|---|---|---|
| F1 | `money.payable_total()`, called by both paths | IQ only — JO has nothing to round |
| F2 | parse at entry + fail closed at the consumer + CHECK constraint | IQ uses `parse_money`, JO `parse_quantity` — each app's own cart parser |
| F3 | clamp after `already_refunded_total`, before the cap check | IQ only |
| F4 | `or today_iso` **and** a check on the parse result | both — either half alone fixes it, which is why the mutation test reverts both |
| F5 | the same `has_negative()` call as F2 | both |
| F6 | boarding's date guard, mirrored into `inpatient_edit` | both |
| Obs 2 | new `.flash.warning`, from tokens both apps already had | both |
| Obs 4 | JO's barcode endpoint renamed to IQ's | JO only |

Observations #1 (the login rate limiter extending its own window on every
retry) and #3 (JO's raw `float` into a column — resolved incidentally by F2's
`parse_quantity`) were left as recorded judgements rather than changes; #1 in
particular is a deliberate anti-brute-force trade-off whose only real fault is
its wording.

**Verification, all re-runnable:** `verify_fixes.py` — 52 assertions, every
guard paired with a control — and `prove_guards.py` — 10/10 guards confirmed by
reverting each fix and watching the bug return. The hostile sweep of §8 now
reports zero findings. Suites: **IQ 761, JO 736, zero skips.**

Two of this session's own tests were caught being blind before they were
trusted, which is the §7.3 discipline working rather than an aside: the first
NaN test ran against a *confirmed* audit session, which refuses every save
regardless of value — five assertions passing while proving nothing; and the
first F4 mutation reverted only half a two-part fix and correctly reported
NOT PROVEN.

---

## 11. Superseded — the original suggested order of work

1. **F2** first — it is the only finding that both corrupts stored data and
   takes a till offline (JO), and its fix is one shared function plus a
   constraint.
2. **F1**, with the shared `money.payable_total()` helper, so the two paths
   cannot drift apart again.
3. **F3**, which is most of the way fixed once F1 stops producing sales whose
   collected total is a rounded-up 250.
4. **F4**, a two-line fix.
5. **F6** and **F5**, both small guards.

For each, follow `CLAUDE.md` §7.3: reintroduce the bug after fixing and confirm
the suite goes red, and pair every guard test with a control. Three of these
six (F2, F4, F6) are in code that is identical in both apps but, per `CLAUDE.md`
§1, each still needs its fix verified against that app's own types — F2 in
particular fails differently on each side.

`COMPARISON.md` will need a dated section once these land.
