# "Clean Up" Feature — Implementation Plan

Status: **BUILT AND SHIPPED** — designed 2026-08-24, implemented in both apps
the same day. This document is retained as the design record and the reasoning
behind the code; it is **not** outstanding work. Do not re-implement it.
See `COMPARISON.md` §6 for what actually shipped, including the POS refund
money-loss bug found while designing this (§3.7 below) which was fixed at the
same time. Status corrected 2026-08-26 — the line here previously still read
"draft for review, not yet executed", which was wrong for two days.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO, client-billing surfaces only
(POS, Visits, Inpatient, Boarding). Distributor billing and refunds are
explicitly out of scope — see §2.

This plan follows the ground rules in `CLAUDE.md`: it is written from each
app's **actual current code** (read directly, cited by file:line below, not
assumed from the other app), treats IQ and JO as siblings needing separate
tailored changes, and flags every money-adjacent decision explicitly per
§2.3 of that file.

## Decisions (resolved 2026-08-24, before implementation)

The three open questions this draft originally raised (old §9) were talked
through with the user directly. All three went with the recommended
option — recorded here so Sonnet doesn't need to re-derive or re-ask them:

| Question | Decision | Where it shows up below |
|---|---|---|
| Separate permission for Clean Up? | **No** — reuse the existing payment-recording permission per surface (`manage_visits` / `manage_inpatient` / `manage_boarding` / `process_pos_sales`). No new permission key in either app. | §3.5 |
| Flat cap or per-role cap? | **Flat global constant** — `CLEANUP_CAP = 1000` IQD / `Decimal("1.000")` JOD, same for every user. Not per-role. Schema still leaves room to add a per-role cap later without rework (see §3.3). | §3.3, §4.2 |
| Require a reason/note? | **No** — a single amount field, no required free text. `cleanup_applied_by` + the existing `auth.log_change()` entry already record who and how much. | §3.4 |

Also per the user's follow-up: **Boarding should be future-proofed for a
discount mechanic it doesn't have yet**, so that when one is eventually
added, Clean Up doesn't need rework to sit correctly on top of it. See
§3.6 — this is a documentation/design note for how the pieces already fit,
not new scope being built now (Boarding is not gaining a discount feature
in this pass).

A second round of questions came from the user asking specifically what
happens when a cleaned-up bill gets refunded. That investigation found a
real money-loss gap in POS refunds (not just a display gap) — see §3.7.
Resolved the same way, talked through with the user directly:

| Question | Decision | Where it shows up below |
|---|---|---|
| Partial retail refund pricing after a Clean Up? | **Unchanged** — still priced per-line at the exact discount-adjusted unit price, same as today. Only a new *aggregate* cap is added (§4.5) — it doesn't touch per-line pricing, it just stops a refund (in total, across all refunds on that sale) from exceeding what was actually collected. | §3.7, §4.5 |
| Snapshot the Clean Up amount on the refund record, or look it up live? | **Snapshot** — new `refunds.cleanup_amount_at_refund` column, written once at refund time, both apps. A refund's audit record is self-contained without cross-referencing the original bill/sale, even if that bill is edited further afterward. | §4.1, §4.5 |
| Bundle the refund fix into this same plan, or a separate follow-up? | **Same plan.** Shipping Clean Up without it opens a real cash-loss path on day one for POS (§3.7) — not something to defer. | §3.7, §4.5, §5.5, §7 |

---

## 1. What problem this actually solves

Investigated both codebases before designing anything, because the answer
turned out to be less obvious than the feature request implies.

**IQ already silently rounds every payable total to the nearest 250 IQD**
note (`money.round_to_denomination`, `mode="nearest"`), applied
unconditionally in `logic.compute_bill_totals()` — used by Visit billing,
Inpatient billing, and Boarding — and inline in `pos_checkout()`
([app.py:4510](webapps/vetclinicsystem_iq-main/app.py:4510)). This already
forces every IQ total to a multiple of 250, automatically, with no staff
action. It is *not* the feature being asked for: it's invisible, it can
round a total **up** by as much as 125 IQD (taking more than owed), and
staff have no control over it.

**JO has no equivalent at all.** There is no `money.py`, no
`SMALLEST_NOTE`, no denomination rounding anywhere.
`logic.compute_bill_totals()` in JO
([logic.py:419](webapps/vetclinicsystem_jo-main/logic.py:419)) just does
`round(subtotal * (1 - discount%/100), 3)` — an exact 3-decimal figure,
with fils-level remainders (`0.125`, `0.250`, ...) reaching the customer
routinely. This is the more literal case of the problem the user
described.

**Boarding has no discount mechanic in either app at all** — no
`discount_percent` column, no discount route. Its total comes from
`price_per_day × nights` (or a freely-typed manual figure), and — this
matters — **that manual total field has no cap and no audit trail
distinguishing "correction" from "money forgiven" today.** That's a real,
pre-existing gap, not something this feature introduces; worth being aware
of, but not this plan's job to close beyond what Clean Up itself needs.

**Confirmed with the user mid-investigation: Clean Up is a manual text
field the staff member types an amount into — not an automatic
suggestion/computation.** The design below reflects that.

---

## 2. Scope

### In scope (client billing, both apps)
| Surface | IQ route(s) | JO route(s) |
|---|---|---|
| POS | `pos_checkout` | `pos_checkout` |
| Visits | `visit_payment_add` | `visit_payment_add` |
| Inpatient | `inpatient_payment_add` | `inpatient_payment_add` |
| Boarding | `boarding_payment` | `boarding_payment` |

Wellness and Grooming were checked and are **not** separate billing
surfaces — `wellness_update`/`grooming_update`
([app.py:2462](webapps/vetclinicsystem_iq-main/app.py:2462),
[app.py:2493](webapps/vetclinicsystem_iq-main/app.py:2493)) only touch
status/reminder fields on `visits`; any money for a wellness or grooming
visit already flows through ordinary Visit billing, which is covered.

### In scope, narrowly — refunds (added after investigation, see §3.7)

Refunds are **not** getting a Clean Up feature of their own (no "round
this refund down" action) — that would be new scope nobody asked for.
What *is* in scope is a targeted integrity fix: a Clean Up applied at
collection time must be correctly accounted for if that bill is later
refunded, or the refund can hand back more than the clinic ever collected.
Investigated and found this is a real gap for POS specifically (§3.7) —
not a hypothetical, and not deferred. Concretely, in scope:
- `refund_retail_save` (IQ + JO) — a new aggregate cap.
- `refunds.cleanup_amount_at_refund` — a new snapshot column, written by
  both `refund_retail_save` and `refund_service_save`.
- Showing the relevant `cleanup_amount` on the refund lookup screens.

### Explicitly out of scope
- **Distributor billing** (`distributor_payment_new`, consignment
  settlements) — per the user's instruction; the person billed there is a
  supplier, not a client.
- **A general refund-side Clean Up action** — e.g. rounding a refund
  amount down for the clinic's convenience. Nobody asked for this; only
  the correctness fix above is in scope.
- **Boarding refunds** — out of scope because there's no such thing to fix:
  confirmed the `refunds` table has no `boarding_id` column and
  `refund_service_save` only accepts `visit_id`/`inpatient_case_id` in
  either app. Boarding isn't refundable through this system today,
  independent of Clean Up.
- **Retroactively touching the existing 250-IQD auto-rounding in IQ** —
  left exactly as-is. Clean Up is a new, additional, explicit action layered
  on top of it, not a replacement.

---

## 3. Design

### 3.1 Where it lives: attached to the payment step, not the discount step

Two candidate designs were considered:
1. Attach Clean Up to the *discount* action (`visit_discount_save`,
   `inpatient_discount_save`, and inline in POS's discount handling).
2. Attach Clean Up to the *payment-recording* action (`visit_payment_add`,
   `inpatient_payment_add`, `boarding_payment`, and POS checkout, which
   *is* the payment step).

**Going with (2).** Reasoning: Boarding has no discount step at all, so
design (1) has no home there — it would need an entirely separate
mechanism just for Boarding, breaking the "one consistent feature"
premise. Design (2) is uniform across all four surfaces, and matches the
real workflow better: staff sees the actual number they're about to
collect at the moment they're collecting it, not earlier while still
deciding on a discount.

### 3.2 What it changes

Clean Up reduces the bill's **total** (not just the payment amount) by the
typed amount, so `balance = total - paid` still zeroes out correctly and
every report/export that reads `total` (there are several — see §7) picks
up the adjustment automatically instead of needing to learn a second
concept.

- IQ: `billing.total`, `inpatient_cases.total`, `boarding_sessions.billed_total`, `sales.total`
- JO: same four columns, `NUMERIC(12,3)` throughout

### 3.3 The cap — cumulative per bill, not per submission

Visits, Inpatient, and Boarding can all be paid off across **multiple**
payments over time. If the cap applied per-submission, it would be
trivially bypassable by splitting one large write-off into several
under-cap ones across repeat visits to the payment form. So:

- Each bill/case/session/sale gets a **cumulative** `cleanup_amount`
  column — the running total ever forgiven on that bill.
- Each new payment submission's typed Clean Up amount is **added** to
  that running total (same incremental spirit as `payments.amount`
  itself, which already accumulates across multiple rows).
- Server-side validation on every submission:
  ```
  0 <= new_cleanup_amount
  existing_cleanup_amount + new_cleanup_amount <= CLEANUP_CAP
  new_cleanup_amount <= current_balance   # never forgive more than what's actually owed
  ```
- `CLEANUP_CAP = 1000` (IQD) / `Decimal("1.000")` (JOD) — a flat global
  constant, not per-role (**decided** — see Decisions box above). A
  per-role cap mirroring `roles.discount_cap` would be a natural future
  extension if ever wanted; not built now.
- POS is single-shot (one sale, no repeat payments), so "cumulative" is
  moot there in practice — the cap just applies once, directly, same as
  everywhere else.

New total after Clean Up: `max(previous_total - cleanup_amount, 0)`. Unlike
IQ's existing anti-"looks free" guard on the *automatic* 250-rounding
(`compute_bill_totals`'s `<= 125` exemption — a guard against **rounding**
accidentally erasing a real bill), Clean Up is an **explicit, deliberate,
capped staff action**. Zeroing out a small genuine remainder on purpose is
the intended use, not a bug to guard against — the cap itself is the
abuse guard here, not an additional floor.

### 3.4 Audit trail

Every surface already has an established pattern for this
(`discount_applied_by` next to `discount_percent`). Mirrored exactly:

- New column `cleanup_applied_by` (last user who added to the running
  total — same "who touched it last" semantics as `discount_applied_by`,
  not a full history column).
- Full history comes for free from the existing `auth.log_change()` call
  each route already makes on the same row — add `cleanup_amount` to the
  `changes` dict passed there, same as `discount_percent` already is.
- No new logging mechanism needed; this reuses what's already there.

### 3.5 Permission gating

**Decided** (see Decisions box above): no new permission. Gated by
whatever permission already guards that surface's payment route:
`process_pos_sales` (POS), `manage_visits`, `manage_inpatient`,
`manage_boarding` — all confirmed present, identically named, in both
apps' `auth.PERMISSIONS`
([auth.py:36](webapps/vetclinicsystem_iq-main/auth.py:36) IQ,
[auth.py:42](webapps/vetclinicsystem_jo-main/auth.py:42) JO).

### 3.6 Future-proofing: Boarding has no discount mechanic yet, but will

Boarding is the one surface with no `discount_percent` column or route at
all today (§1). The user wants this feature built so that adding a
Boarding discount later doesn't require reworking Clean Up. It already
doesn't, and it's worth spelling out exactly why, so nobody has to
re-derive this when that feature actually gets built:

- `boarding_billing_summary_from_fields()`
  ([logic.py:544](webapps/vetclinicsystem_iq-main/logic.py:544) IQ) already
  calls the *same* shared `compute_bill_totals(subtotal, discount_percent,
  paid, cleanup_amount)` helper that Visits and Inpatient use — it just
  passes a hardcoded `0` for `discount_percent` today, since there's
  nothing else to pass.
- That helper already applies discount **before** Clean Up in its internal
  order of operations (subtotal → discount → denomination-round [IQ only]
  → Clean Up), per §3.2/§4.3 of this plan. This is the same order
  Visits and Inpatient already use, so Boarding gaining a discount later
  automatically composes the same way — no reordering, no special-casing.
- The day this repo adds Boarding discounts, the change is: add
  `boarding_sessions.discount_percent` / `discount_applied_by` (mirroring
  `billing`/`inpatient_cases` exactly), a `/boarding/<id>/discount` route
  (mirroring `visit_discount_save`/`inpatient_discount_save`), and swap
  that hardcoded `0` for the real column value. **Nothing in the Clean Up
  implementation itself changes.**
- Concretely, this plan is asking Sonnet to *not* hardcode anything about
  "Boarding has no discount" into the Clean Up code paths in a way that
  would need undoing later — e.g. don't special-case Boarding's
  `compute_bill_totals()` call differently from Visits/Inpatient's, even
  though today's call site passes a literal `0`.
- **Not building Boarding discounts now** — no new column, no new route,
  no UI. This section is scope-guarding for a future feature, not a
  request to build it in this pass.

### 3.7 Refunds: the gap this feature would otherwise create

The user asked directly: when a cleaned-up bill gets refunded, does the
refund show and record that? Investigated before answering — the finding
changes what "done" means for this feature, so it's captured here rather
than assumed away.

**Visits & Inpatient service refunds are already money-safe, just silent.**
`refund_service_save`
([app.py:5496](webapps/vetclinicsystem_iq-main/app.py:5496)) caps the
refundable amount against `SUM(payments.amount) - already_refunded`, never
against `billing.total`/`inpatient_cases.total`. A Clean Up amount is
never *paid* — `payments.amount` only ever reflects real cash collected —
so the existing cap already correctly excludes it from what can be
refunded. No over-refund risk here. The gap is purely traceability: no
visible link today ties a refund back to the bill's `cleanup_amount`.

**POS retail refunds are a real, unguarded money-loss path.**
`refund_retail_save`
([app.py:5369](webapps/vetclinicsystem_iq-main/app.py:5369)) never reads
`sales.total` at all. It rebuilds the refund amount bottom-up from
`refundable_sale_items()`
([logic.py:1607](webapps/vetclinicsystem_iq-main/logic.py:1607)) — each
line's `unit_price × (1 - discount_percent/100)`, summed per submission,
capped only by per-line remaining quantity. That math has no path to
`sales.cleanup_amount` at all. Concretely: a sale collects 24,000 IQD
after a 750 IQD Clean Up (`sales.total = 24,000`); a full return later
recomputes ~24,750 from the line items and pays back 750 IQD more than the
clinic ever received. **This is a real cash-loss bug this feature would
introduce**, not a hypothetical — confirmed identical in JO
([logic.py:1151](webapps/vetclinicsystem_jo-main/logic.py:1151)).

Side finding, not caused by Clean Up: this same line-item math already
ignores IQ's *existing* 250-IQD denomination rounding too, an existing
drift of up to ~125 IQD. The fix below closes that incidentally.

**Boarding has no refund path at all**, independent of Clean Up — see §2.

**Decided fix** (per the Decisions box, all recommended options):
1. Add an aggregate cap to `refund_retail_save`, both apps: the total
   refunded across this submission plus everything already refunded
   against that sale can never exceed `sales.total`. Per-line pricing for
   a partial refund is otherwise **untouched** — still priced at the exact
   discount-adjusted unit price, same as today. The cap only bites when a
   refund (or the sum of several) would exceed what was actually
   collected — in practice, that means whichever refund happens to be the
   one that would cross the line absorbs the Clean Up amount, rather than
   every refund being proportionally scaled down. This is the smallest
   change that closes the money-loss path.
2. Add `refunds.cleanup_amount_at_refund` — written once, at refund time,
   by both `refund_retail_save` and `refund_service_save`, from the
   relevant sale's/bill's current `cleanup_amount`. A snapshot, not a live
   lookup: the user chose this specifically so a refund's audit record
   stays self-contained even if the original bill is touched again later.
3. Show it on screen at refund time — §5.5.

---

## 4. Per-app implementation

CLAUDE.md §2 applies directly here: below is written from each app's own
current code, not copy-pasted from the other. Where the two are
structurally identical (schema shape, route shape), that's stated — where
they diverge (validation helper existing vs. inline, float vs. Decimal), it's
called out explicitly.

### 4.1 Schema changes

**IQ** — add via `setup.py`'s `INCREMENTAL_SCHEMA_STATEMENTS` list (the
existing idempotent-migration mechanism —
[setup.py:139](webapps/vetclinicsystem_iq-main/setup.py:139)) *and* to the
relevant `CREATE TABLE` blocks in `schema_postgres.sql` for fresh installs,
per that file's own documented convention:

```sql
ALTER TABLE billing ADD COLUMN IF NOT EXISTS cleanup_amount DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE billing ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE inpatient_cases ADD COLUMN IF NOT EXISTS cleanup_amount DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE inpatient_cases ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE boarding_sessions ADD COLUMN IF NOT EXISTS cleanup_amount DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE boarding_sessions ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS cleanup_amount DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS cleanup_amount_at_refund DOUBLE PRECISION NOT NULL DEFAULT 0;
```

**JO** — same four tables, same mechanism
([setup.py:137](webapps/vetclinicsystem_jo-main/setup.py:137) —
confirmed JO has its own equivalent `INCREMENTAL_SCHEMA_STATEMENTS` /
`apply_incremental_migrations()`, just invoked from inside `apply_schema()`
rather than as a separate top-level `main()` step like IQ), `NUMERIC(12,3)`
to match every other money column in JO's schema:

```sql
ALTER TABLE billing ADD COLUMN IF NOT EXISTS cleanup_amount NUMERIC(12,3) NOT NULL DEFAULT 0;
ALTER TABLE billing ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE inpatient_cases ADD COLUMN IF NOT EXISTS cleanup_amount NUMERIC(12,3) NOT NULL DEFAULT 0;
ALTER TABLE inpatient_cases ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE boarding_sessions ADD COLUMN IF NOT EXISTS cleanup_amount NUMERIC(12,3) NOT NULL DEFAULT 0;
ALTER TABLE boarding_sessions ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS cleanup_amount NUMERIC(12,3) NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS cleanup_applied_by TEXT;
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS cleanup_amount_at_refund NUMERIC(12,3) NOT NULL DEFAULT 0;
```

`cleanup_amount_at_refund` is deliberately on `refunds`, not derived —
per the Decisions box, a snapshot written once at refund time, not a live
lookup against the original bill.

### 4.2 The cap constant and validation helper

**IQ** — add to `money.py` (the existing home for IQD constants like
`SMALLEST_NOTE`):
```python
CLEANUP_CAP = 1000  # IQD — flat ceiling on cumulative Clean Up per bill
```
Add a validation helper next to the existing `discount_percent_error()`
([app.py:345](webapps/vetclinicsystem_iq-main/app.py:345)) — IQ already
factors this kind of check into one shared function used by all three
discount routes, so `cleanup_amount_error()` follows the same convention:
```python
def cleanup_amount_error(new_amount, existing_amount, balance):
    if new_amount < 0:
        return "Clean Up amount can't be negative."
    if existing_amount + new_amount > money.CLEANUP_CAP:
        return f"Clean Up can't exceed {money.CLEANUP_CAP} IQD total on this bill."
    if new_amount > balance:
        return "Clean Up can't exceed the remaining balance."
    return None
```

**JO** — add to `app.py` near `parse_money`/`Decimal` money helpers (JO has
no `money.py` to extend — confirmed no such module exists in JO at all,
§1):
```python
CLEANUP_CAP = Decimal("1.000")  # JOD — flat ceiling on cumulative Clean Up per bill
```
**Important divergence, verified directly rather than assumed:** unlike
IQ, JO has **no shared `discount_percent_error()` helper** — every
discount route in JO (`visit_discount_save`, `inpatient_discount_save`,
the inline POS check) repeats the same `cap = auth.discount_cap_for()` /
flash-and-redisplay check inline
([app.py:1977](webapps/vetclinicsystem_jo-main/app.py:1977),
[:2220](webapps/vetclinicsystem_jo-main/app.py:2220),
[:4379](webapps/vetclinicsystem_jo-main/app.py:4379),
[:4909](webapps/vetclinicsystem_jo-main/app.py:4909)). Follow JO's actual
existing convention here rather than introducing IQ's factored-out style
unprompted — write the same validation inline at each of the four payment
routes in JO, not as a new shared function. (If JO's own maintainer wants
to factor this out generally, that's a separate refactor, not something to
sneak in via this feature.)

### 4.3 Backend — money math

**IQ**, in `logic.py`:
- `compute_bill_totals(subtotal, discount_percent, paid)` → add a
  `cleanup_amount=0` parameter; final total becomes
  `max(money.round_to_denomination(raw_total) - cleanup_amount, 0)`
  (Clean Up applies *after* the existing 250-rounding, not before —
  it's an additional explicit step on top).
- `visit_billing_summary()` ([logic.py:445](webapps/vetclinicsystem_iq-main/logic.py:445)ish),
  `inpatient_billing_summary()`, `boarding_billing_summary_from_fields()`
  all call `compute_bill_totals()` already — thread the stored
  `cleanup_amount` through from each row.
- `refresh_visit_billing_total()`, `refresh_inpatient_total()`,
  `refresh_boarding_total()` — unchanged in shape, just now reflect the
  cleanup-adjusted total since they read from the summary functions above.
- `pos_checkout()` in `app.py` — total becomes
  `max(money.round_to_denomination(subtotal * (1 - discount_percent/100)) - cleanup_amount, 0)`.

**JO**, in `logic.py` — same shape, no denomination-rounding step to layer
on top of (per §1, JO has none):
`compute_bill_totals()` total becomes
`max(round(subtotal * (1 - discount_percent/Decimal(100)), 3) - cleanup_amount, 0)`.

### 4.4 Backend — the four payment routes, each app

Each of `visit_payment_add`, `inpatient_payment_add`, `boarding_payment`
gains:
1. Parse `cleanup_amount` from the form (`parse_money`, defaulting to 0 —
   same parsing helper every other money field on that route already
   uses).
2. Look up the bill's current `cleanup_amount` and balance (already
   fetched on every one of these routes today, to validate the payment
   amount itself — [app.py:5341](webapps/vetclinicsystem_iq-main/app.py:5341)
   in IQ's `boarding_payment` is a representative example: it already
   locks the row and reads `balance` before accepting a payment).
3. Validate via `cleanup_amount_error()` (IQ) / inline checks (JO), per §4.2.
4. `UPDATE ... SET cleanup_amount = cleanup_amount + ?, cleanup_applied_by = ?`
   in the same statement/transaction as the payment insert and the
   existing `refresh_*_total()` call — same commit boundary as everything
   else on that route.
5. `auth.log_change()` — add `cleanup_amount` to the changes dict, same
   pattern as `discount_percent` elsewhere.

`pos_checkout()` gains a `cleanup_amount` form field, validated the same
way (existing_amount is always 0 for a brand-new sale), stored directly on
the `sales` INSERT alongside `discount_percent`/`discount_applied_by`.

### 4.5 Backend — the refund fix (§3.7)

**`refund_retail_save`, both apps** — add one aggregate check, after the
existing per-line remaining-quantity validation and before the INSERT:
```python
already_refunded_total = db.execute(
    "SELECT COALESCE(SUM(amount),0) s FROM refunds WHERE sale_id=? AND refund_type='retail'",
    (sale_id,)
).fetchone()["s"]
if already_refunded_total + rounded_total > sale["total"] + <tiny epsilon>:
    flash(f"That's more than this sale actually collected ({sale['total']} "
          f"{currency}, after any Clean Up applied at sale time) minus what's "
          f"already been refunded.", "error")
    return redisplay()
```
Everything upstream of this (per-line pricing, `rounded_total` itself) is
**unchanged** — per the Decisions box, partial refund pricing stays exact
per-line math. This check only ever fires once the sum of refunds on a
sale would exceed what the sale's `total` actually was, which is exactly
the case a Clean Up creates. Note `sale["total"]` already reflects
`cleanup_amount` once §4.3's change lands, so this needs no separate
reference to `cleanup_amount` itself — it's implicitly covered by reading
`total`.

Write the snapshot on both refund routes, same INSERT that already writes
`refund_method`/`processed_by`:
```python
cleanup_amount_at_refund = sale["cleanup_amount"]        # retail
cleanup_amount_at_refund = billing_or_case["cleanup_amount"]  # service — from
                                                                # whichever of
                                                                # visit_id/case_id
                                                                # is set; sum if both
```

**`refund_service_save`, both apps** — no cap change (§3.7 confirmed the
existing `SUM(payments.amount)`-based cap is already correct). Only the
`cleanup_amount_at_refund` snapshot write is new here.

---

## 5. Frontend

### 5.1 Insertion point — the existing "Record Payment" form/modal

All three non-POS surfaces already have a small, self-contained payment
form with an `amount` field, checked and near-identical in structure
across both apps (native `<form>`, no client-side total logic to keep in
sync):

- IQ Visits: [templates/visit_detail.html:133](webapps/vetclinicsystem_iq-main/templates/visit_detail.html:133)
- IQ Inpatient: [templates/inpatient_detail.html:167](webapps/vetclinicsystem_iq-main/templates/inpatient_detail.html:167)
- IQ Boarding: modal at [templates/boarding.html:76-98](webapps/vetclinicsystem_iq-main/templates/boarding.html:76)
- JO: same three files, same structure, confirmed directly — the payment
  modal markup is close to line-for-line identical to IQ's, differing
  only in how the modal opens/closes (JO: plain
  `element.style.display = 'flex'/'none'`; IQ: `window.VZSpring.present(...)`
  — **do not port IQ's modal JS into JO**, it has no such framework, per
  `CLAUDE.md` §1).

Add one field to each of these three forms:
```html
<div class="field"><label>Clean Up (max {{ CLEANUP_CAP }} {{ currency }})</label>
  <input type="number" step="{{ money step }}" min="0" name="cleanup_amount" value="0"></div>
```
Text-input semantics per the user's clarification — no auto-fill, no
suggested value, staff types whatever figure they want (subject to
server-side validation).

### 5.2 POS

IQ's `pos.html` already mirrors the server's total math in client-side JS
for a live preview (`Math.round(rawTotal / 250) * 250` at
[templates/pos.html:141](webapps/vetclinicsystem_iq-main/templates/pos.html:141)).
Add a `cleanupInput` next to the existing `discountInput`
([templates/pos.html:21](webapps/vetclinicsystem_iq-main/templates/pos.html:21)),
subtract it in `renderCart()`'s total calculation, and add a matching
hidden field (same pattern as `discountHidden` at
[templates/pos.html:42](webapps/vetclinicsystem_iq-main/templates/pos.html:42)).
**Client-side total math is a preview only** — `pos_checkout()` recomputes
and validates the authoritative total server-side regardless of what the
hidden field carries, same trust boundary as the discount field today.

JO's POS page: check its equivalent JS live-total block (structure not
yet read line-by-line for JO specifically — verify before writing, since
JO's frontend conventions differ per `CLAUDE.md` §1) and add the same
field without assuming it mirrors IQ's exact JS.

### 5.3 Receipts and exports — a real gap found during investigation, not optional polish

`pdf_export.py` in IQ derives the "Discount" line shown on every receipt
and bill export by **subtracting**, not by reading a stored discount
figure:
```python
data.append([f"Discount ({summary['discount_percent']:.0f}%)", f"-{summary['subtotal'] - summary['total']:,.0f}"])
```
([pdf_export.py:179-181](webapps/vetclinicsystem_iq-main/pdf_export.py:179),
repeated at lines 233-235, 323-325, 406-408 for POS receipts, visit bills,
and inpatient bills respectively). Once `cleanup_amount` also reduces
`total`, this line would silently **absorb the Clean Up amount into the
displayed "Discount" line** on every printed receipt and PDF export —
mislabeling a till write-off as a pricing discount, which directly
undermines the feature's stated purpose (an accurate, auditable
paper trail matching what's actually collected).

Required fix, all four call sites in `pdf_export.py`:
- Discount line: `subtotal - round_to_denomination(subtotal*(1-discount%))`
  (the pre-cleanup figure) instead of `subtotal - total`.
- New separate `"Clean Up"` line: `-cleanup_amount`, shown only when
  `cleanup_amount > 0`, same conditional-row pattern already used for the
  discount line.
- `Total` row unchanged (still reads the final stored `total`, which
  already reflects both).

JO's `pdf_export.py` needs the same audit and fix — check its
discount-line computation directly rather than assuming it matches IQ's
exact line numbers.

### 5.4 Cash Register — verified, no change needed

`logic.cash_register_ledger()`
([logic.py:2382](webapps/vetclinicsystem_iq-main/logic.py:2382)) and
`cash_register_totals()` read `sales.total` / `payments.amount` /
`refunds.amount` directly off the tables — whatever's actually stored.
Since Clean Up updates `total` in place (not a separate shadow figure),
the day's Cash Register reconciliation automatically reflects it with no
code change. This is, in fact, exactly the mechanism the user described
wanting: what the system counts and what physically changes hands now
match, because Clean Up is baked into the same `total` everything else
already reads.

### 5.5 Refund screens — show the Clean Up amount (§3.7)

`refunds.html`, both apps:
- **Retail lookup panel** — the JS-driven sale lookup already populated
  from `/api/sales/<id>/refundable-items`
  ([app.py:1429](webapps/vetclinicsystem_iq-main/app.py:1429)). Add
  `cleanup_amount` to that endpoint's JSON response, and render a plain
  info line ("This sale had a 750 IQD Clean Up applied") next to the sale
  total when it's non-zero — so staff processing a refund can see, before
  submitting, why the aggregate cap in §4.5 might reject a full-price
  refund.
- **Service refund form** — same treatment next to the existing
  refundable-balance display for the selected visit/case.

No new page, no new route — both are additions to lookups/panels that
already exist.

---

## 6. Anti-abuse summary (defense in depth)

1. Server-side cap, enforced on every submission regardless of client-side
   JS — `existing_cleanup_amount + new_amount <= CLEANUP_CAP`.
2. Can never exceed the actual outstanding balance — no forgiving more
   than what's owed.
3. Gated by the same permission already required to record a payment on
   that surface at all — no new blanket access.
4. `cleanup_applied_by` + `auth.log_change()` entry on every use — fully
   attributable, same audit trail every other money-adjacent action in
   both apps already gets.
5. Cumulative, not per-submission — closes the "many small write-offs"
   bypass explicitly (§3.3).

---

## 7. Testing plan

Per `CLAUDE.md` §5 — replicate and verify live in each app's own isolated
test environment, never a real install:

```bash
./scripts/isolated_test_env.sh up iq   # port 5091
./scripts/isolated_test_env.sh up jo   # port 5092
```

Per surface, per app:
- Apply a discount (where applicable) producing a non-round total, record
  a partial payment with a Clean Up amount under the cap — confirm total,
  balance, and status update correctly.
- Attempt to exceed the cap in one submission — rejected.
- Split Clean Up across two payments whose sum exceeds the cap — second
  submission rejected (validates §3.3's cumulative tracking specifically).
- Attempt a Clean Up larger than the current balance — rejected.
- Zero/blank Clean Up — behaves exactly as before this feature (regression
  check).
- Export/print a receipt or bill PDF with a Clean Up applied — confirm the
  new "Clean Up" line appears and the "Discount" line no longer silently
  includes it (§5.3).
- Full day cycle through Cash Register: sale/payment with Clean Up applied
  → audit the day → confirm system total matches counted cash exactly
  (this is the feature's actual purpose — test it end to end, not just
  the write path).
- IQ only: confirm Clean Up correctly layers on top of the existing
  250-IQD auto-rounding rather than interfering with it.
- Role/permission pass per `CLAUDE.md` §5's own reminder: JO's 3 fixed
  roles vs. IQ's arbitrary custom roles — confirm a custom IQ role with
  `manage_visits` but not `manage_inpatient` can Clean Up on Visits but
  correctly gets refused on Inpatient.

Refunds (§3.7/§4.5/§5.5), both apps — this is the scenario the whole
refund fix exists for, test it directly rather than just its unit pieces:
- POS sale with a Clean Up applied, then a **full** retail refund of every
  line — confirm the refunded amount equals `sales.total` (post-Clean Up),
  not the pre-Clean Up line-item sum. This is the exact over-refund this
  fix closes; confirm it's actually closed, not just that the cap code
  runs.
- Same setup, refund in **two partial submissions** whose combined value
  would exceed `sales.total` — confirm the second submission is rejected,
  and that the first partial refund's per-line pricing was untouched
  (§4.5 — partial pricing stays exact, only the aggregate is capped).
- Confirm `refunds.cleanup_amount_at_refund` is written correctly on both
  the retail and service refund paths, and that it displays on §5.5's
  refund lookup screens.
- Visit/Inpatient service refund on a bill with a Clean Up applied —
  confirm the existing `SUM(payments.amount)`-based cap was already
  correct (§3.7) and still behaves the same; this is a regression check,
  not expected to need a behavior change.
- Confirm Boarding still has no refund path at all — regression check
  that this feature didn't accidentally add one.

```bash
./scripts/isolated_test_env.sh down iq
./scripts/isolated_test_env.sh down jo
```

---

## 8. Release checklist

Per `RELEASE_WORKFLOW.md` — not a plain commit+push:
- `VERSION` + `CHANGELOG.md` bump in **each** app independently (not
  required to match version numbers between them).
- Dated append to `COMPARISON.md` once shipped — this closes a
  denomination-rounding-adjacent gap called out implicitly in §1.1 of that
  file, worth a note there specifically since it's exactly the kind of
  money-model divergence that section tracks.
- Confirm `git remote -v` before first push in each repo, per CLAUDE.md §3.

---

## 9. Status

All open questions this draft originally raised here have been resolved
directly with the user — see the **Decisions** box at the top of this
document, and §3.6 for the Boarding future-proofing note. Nothing left
outstanding; ready for implementation as written.
