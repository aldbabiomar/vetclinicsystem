# Rewards Card (Member Discount) — Implementation Plan

Status: **CLOSED — executed and released 2026-09-19 as IQ v1.17.0 / JO v1.15.0.**
See `COMPARISON.md` §63 for what actually differed between the two apps, the
three bugs the suites caught in the work itself, and the mutation run that
proved the guards. Kept as the decision trail, not as a to-do list.
**Open decisions resolved by the clinic owner 2026-09-19** (second-pass
table below): A9 is overridden, memberships now have a fixed term, and the
§9 ranking rewrite is in scope for the same release.
Scope: VetClinicSystem_IQ and VetClinicSystem_JO. A rewards card for the
clinic's best customers that gives a flat **percentage** discount on every
bill, applied automatically, on visits, inpatient, boarding and POS.

**This document is written to be handed to a different Claude session.**
Read, in this order, before touching code: `CLAUDE.md`, `COMPARISON.md` §1.1
(money types), §57–§58 (localization — the language is a clinic *setting*
now, not a cookie), and `SEAM_RULES.md` in full. This feature is a
seam-rule feature: it puts one new rule on four payment paths that are
already shaped differently from each other, which is exactly the situation
every entry in `SEAM_RULES.md` §2 came from.

Code is cited by **symbol and file**. Line numbers are given as of
2026-09-19 to save a search, and **will drift** — grep the symbol, don't
trust the number.

---

## Decisions

### Made by the clinic owner (2026-09-19)

| Question | Decision |
|---|---|
| Percentage or fixed amount? | **Percentage.** |
| Staff discount on a member's bill? | **Not allowed.** The card's discount is the only discount a member's bill can carry. Staff cannot add, raise or replace it. |
| Items marked not discountable? | **The card discounts eligible items only; the rest are charged in full.** This is deliberately *different* from staff discounts, where one non-discountable item blocks the discount on the whole bill. |
| Which app? | **Both**, each built against its own money model. |

### Made by the clinic owner (2026-09-19, second pass)

Asked because the first draft either left these open or settled them on an
author's guess. **Where these disagree with the A-table below, these win.**

| Question | Decision |
|---|---|
| Undoing a member discount that landed on the wrong bill | **An admin-only "Remove member discount" action** — §7.3. Remove-only: it can set the discount to zero, never add or raise one, so "card only" is untouched. **Overrides A9.** |
| Is selecting a customer at POS required? | **No — optional, opt-in.** No prompt, no skip step, nothing added to the walk-in path. Accepted consequence: `sales.owner_id` is NULL on most sales, so §9's POS figures are partial by design. |
| Does the card apply to a stay admitted *before* enrollment? | **No — A2 confirmed as written, all four surfaces.** A 10-day inpatient stay admitted the day before someone enrolls carries no discount, though the whole bill accrued after they joined. This was put to the owner explicitly and accepted; **do not "fix" it later without asking again.** |
| The §9 ranking rewrite | **In scope, same release as the card** — including relabelling the two "Lifetime" tiles on `/insights`, which will drop sharply (§9.1). |
| Does a card expire? | **Yes — a fixed term.** A clinic-wide `member_term_months` setting (default 12) pre-fills the expiry date on the enroll form, and staff may edit it for one card. See §5.1. |
| Is there a record of a revocation? | **The change log is enough** — no reason field. Accepted consequence: re-enrolling someone overwrites `member_since`, so the owner page shows the newer join date for a returning member. `log_change()` still holds both events. |
| Warning before a card lapses | **A badge on the owner page and the members list** within 30 days. No new screen, no notification system, no scheduler job. |

### Made by the plan's author — override any of these before starting

| # | Decision | Why |
|---|---|---|
| A1 | **Reuse the bill's one discount slot** (`discount_percent`) and add `discount_source` (`'staff'` \| `'member'`), rather than adding a second discount column. | Every money reader in both apps already reads `discount_percent`. A second column is one more thing each reader must learn, and a reader that forgets it computes a **silently** wrong total, refund or receipt. With one slot, the failure mode of a missed change is a guard refusing something (loud). The owner's "card only" decision also means a bill never carries both, so one slot is enough. |
| A2 | **Membership is decided once, when the bill is created**, and the rate is snapshotted onto the bill. Enrolling a customer later, unenrolling them, or changing the rate in Settings never alters an existing bill. | Predictable and auditable: a receipt's discount can always be explained from the bill itself. It also can't be used to retro-discount a large open bill by enrolling someone mid-stay. **Confirmed by the owner 2026-09-19** with the inpatient consequence stated explicitly (second-pass table). Expiry rides on the same rule: a bill created while the card was valid keeps its discount after the card lapses. |
| A3 | **Eligibility is snapshotted per line**: new `discountable` column on `visit_billing_lines`, `inpatient_billing`, `sale_items`, copied from `price_list.can_discount` at insert. | `can_discount` can be edited at any time. Without a snapshot, flipping it later would silently change a past bill's total the next time it's recomputed, and would misprice refunds. This is the same reason `unit_price`/`unit_cost` are already snapshotted. |
| A4 | **Boarding stays and Manual visit bills count as fully discountable.** | They have no item lines to check, and staff discounts already apply to their whole amount today. |
| A5 | **Enrollment is a staff action** behind a new permission `manage_rewards`, admin-only by default. The ranking only *suggests* who to enroll; it never enrolls anyone. | A physical card that's been handed to someone shouldn't lapse on its own when the ranking shifts. **Note, 2026-09-19:** cards now DO lapse on their own — but on a date fixed when the card was issued (§5.1), never because the ranking moved. This decision is unchanged; it was only ever about the ranking. |
| A6 | **The rate lives in Settings**, range **0–50%**, where 0 means the program is off. | One rate, per the owner's "flat" decision. The 50% ceiling is a guess at a sane bound — change it if the clinic wants otherwise. |
| A7 | **Card number is optional**, unique when set, and treated as an **identifier**: never converted to Eastern Arabic digits (`ARABIC_LOCALIZATION_PLAN.md` §7.1 rule for IDs). | Not every clinic will print numbered cards; a member flag works without one. |
| A8 | **The ranking uses a trailing 12-month window**, subtracts refunds, and includes POS sales once they're linked to an owner. | See §9. |
| A9 | ~~No v1 way to strip a member discount off an existing bill.~~ **OVERRIDDEN by the owner, 2026-09-19 — build §7.3.** The original reasoning ("if the clinic needs a correction path later, it's an admin-only action added on purpose, not a loophole") describes exactly what was built; it just ships in v1 rather than later. | Without it, a member discount on the wrong bill is **permanent** for visits, inpatient and boarding: §7.1's refusal blocks staff from typing `0` just as it blocks typing `15`. POS could be corrected by refunding and re-ringing; the other three had no path at all. The realistic causes are a wrong customer picked at POS, a pet registered under the wrong owner, and a card enrolled on a duplicate owner row. |

---

## 1. What exists today (verified in both apps, 2026-09-19)

- **One discount slot per bill.** `billing`, `inpatient_cases`,
  `boarding_sessions` and `sales` each carry `discount_percent` +
  `discount_applied_by`. Every staff entry point checks the role cap through
  one shared function, `discount_percent_error()` in `core.py`, against
  `auth.discount_cap_for()`.
- **The four surfaces take discounts differently.** Visits and inpatient have
  a separate discount route (`visit_discount_save`, `inpatient_discount_save`);
  boarding takes the discount **inside the payment form** (`boarding_payment`);
  POS takes it **inline at checkout** (`pos_checkout` → `_record_sale`).
- **`price_list.can_discount` defaults to `FALSE`.** Today a single
  non-discountable line blocks a staff discount on the whole bill, enforced
  at five guard sites (see §7.2). **Operational consequence for launch:** the
  clinic must go through the Price List marking what's discountable, or the
  card will discount nothing. Put this in the release notes (§13).
  **Corrected 2026-09-19 — this is smaller than it reads.** `can_discount` is
  already a per-row checkbox in the *existing* bulk editor
  (`templates/price_list.html:76` → `price_list_bulk_edit`,
  `routes/inventory.py:242`), so it's a page-at-a-time bulk save, not
  item-by-item. No new tooling is needed; don't build any.
- **POS sales have no owner.** `sales` has no link to `owners`.
- **`owners`** is `id, name, phone, address, notes` — identical in both apps.
- **The ranking** is `logic.client_value()`, shown on `/insights` — identical
  in both apps apart from rounding precision. It sums every payment ever
  (no time window), never subtracts `refunds`, and excludes POS entirely
  (its own docstring: POS sales are "anonymous walk-in transactions").
- **Permissions:** both apps' `auth.seed_default_roles_and_permissions()`
  re-grants every permission to system roles on every launch. A new key in
  `PERMISSIONS` therefore needs **no grant migration**. (IQ's `setup.py`
  still carries a hand-written grant for `manage_cash_register` — it predates
  that backfill and is **not** the pattern to copy.)

---

## 2. The core change: one calculation, eligible lines only

Today every discount is applied to the whole subtotal. The new formula:

```
raw_total = discountable_subtotal × (1 − d) + (subtotal − discountable_subtotal)
```

**The property that makes this safe:** for a *staff* discount, the existing
guards guarantee there are no non-discountable lines whenever `d > 0`, so
`discountable_subtotal == subtotal` and the formula reduces to exactly
today's `subtotal × (1 − d)`. Changing the one shared calculation is a
behavioural **no-op for every staff-discounted bill** — it only changes
anything on member bills. That's what lets this be one function instead of
a second code path, and it is checked explicitly in §11.2 and at the §12
step-3 checkpoint.

### 2.1 Every place discount math happens — all must change

Built by a regex sweep for `discount` near `/ 100`, `Decimal(100)`,
`/100.0` and `* (1 -`. **The first, narrower version of that sweep missed
every `pdf_export.py` site in both apps** (the `x["discount_percent"] / 100`
shape didn't match) — `CLAUDE.md` §5's "a checker that could not fail" in
miniature. Re-run the broad version before starting and reconcile against
this table:

```bash
grep -n "discount" *.py routes/*.py | grep -E "/ ?100|Decimal\(100\)|/100\.0|\* ?\(1 ?-"
```

| Site | IQ | JO | What it does | Change |
|---|---|---|---|---|
| `logic.compute_bill_totals` | logic.py:501 | logic.py:502 | bill math for visits, inpatient, boarding | new required `discountable_subtotal` (§2.2) |
| POS checkout total | routes/sales.py:312 (`money.payable_total`) | routes/sales.py:458 | cart total | same formula, from per-line eligibility (§2.4) |
| `logic.refundable_sale_items` | logic.py:1721 | logic.py:1263 | prices each returned item | apply `d` only where the line's `discountable` snapshot is true |
| `logic.vet_performance` | logic.py:1482 | logic.py:2243 | per-vet revenue | **read stored `billing.total`** — it already drifts today (ignores IQ's 250-rounding and Clean Up); member discounts would make it worse |
| `logic.revenue_by_category` | ~1357–1382: **apportions** the stored total by each line's *raw* share | 2155, 2163, 2169, 2175: **re-derives** each line × (1 − d) | revenue split by category | IQ: weight the apportionment by the *discounted* line amount. JO: `* (1 − CASE WHEN discountable THEN d ELSE 0 END)`; Manual rows stay whole-amount (A4) |
| `logic._revenue_and_cogs_by_month`, inpatient | apportions the stored `inpatient_cases.total` | logic.py:1026: **re-derives** each line × (1 − case discount) | monthly P&L | IQ: same weighting fix. **JO: this one changes the P&L *total*, not just a split** — without the fix, JO understates revenue on every member bill with a non-discountable item |
| `pdf_export.py` — five copies | 181, 238, 333, 421, 499 | 181, 238, 334, 421, 499 | the "Discount" line on every receipt/export | replace all five with **one helper** reading `pre_cleanup_total` from the summary (§8.2) |
| POS live preview (JS) | templates/pos.html:142 | templates/pos.html:139 | on-screen total before checkout | per-line, using the `discountable` flag from the lookup API |

**This is a real IQ/JO divergence, not a port.** JO re-derives revenue per
line in two reports where IQ reads or apportions stored totals. On today's
bills the two agree; on a member bill they don't. Fix each in its own shape.

### 2.2 `compute_bill_totals`

```python
def compute_bill_totals(subtotal, discount_percent, paid, cleanup_amount=0, *,
                        discountable_subtotal):
```

**Keyword-only, required, no default — on purpose.** A default of
`discountable_subtotal=subtotal` would let any caller that forgets it treat
everything as discountable, silently. Callers: the three summaries in
`logic.py` (visit, inpatient, boarding) and four in `routes/clinical.py`
(IQ 976, 1637, 1643, 1996 — find JO's by grep). Seam Rule 6 (§11.1) keeps
it that way.

- **IQ:** compute `raw_total` with the formula, then
  `money.payable_total(raw_total, discount_percent)` (rounding + the
  anti-"looks free" floor, **once, on the total — never per line**), then
  subtract Clean Up. Order unchanged from today.
- **JO:** `Decimal` throughout, `round(raw_total, 3)`. No `payable_total`,
  no rounding step — JO has nothing to round (`CLAUDE.md` §1). JO's test
  that fails 20 tests if IQ's rounding is ever ported across must stay green.

### 2.3 Summaries expose three new keys

`visit_billing_summary`, `inpatient_billing_summary` and
`boarding_billing_summary_from_fields` each add:

- `discountable_subtotal` — sum over lines where the snapshot is true; the
  whole subtotal for Manual visits and boarding (A4).
- `discount_source`
- `pre_cleanup_total` — the rounded total before Clean Up. Receipts read
  this instead of re-deriving it (§8.2).

### 2.4 POS

`_priced_cart_lines` returns each line's `discountable` alongside its price.
`pos_checkout` computes `discountable_subtotal` from those lines and uses the
same formula. Store the flag on each `sale_items` row.

---

## 3. Schema (both apps)

Add every statement to `setup.py`'s `INCREMENTAL_SCHEMA_STATEMENTS` **and**
to the matching `CREATE TABLE` in `schema_postgres.sql`. No money columns
are added — the rate is a setting — so the float/Decimal split doesn't
reach the schema here.

```sql
-- Membership
ALTER TABLE owners ADD COLUMN IF NOT EXISTS is_member BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE owners ADD COLUMN IF NOT EXISTS member_card_number TEXT;
ALTER TABLE owners ADD COLUMN IF NOT EXISTS member_since DATE;
ALTER TABLE owners ADD COLUMN IF NOT EXISTS member_enrolled_by TEXT REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE owners ADD COLUMN IF NOT EXISTS member_expires_on DATE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_owners_member_card
    ON owners(member_card_number) WHERE member_card_number IS NOT NULL;

-- Where a bill's discount came from (A1)
ALTER TABLE billing           ADD COLUMN IF NOT EXISTS discount_source TEXT NOT NULL DEFAULT 'staff' CHECK (discount_source IN ('staff','member'));
ALTER TABLE inpatient_cases   ADD COLUMN IF NOT EXISTS discount_source TEXT NOT NULL DEFAULT 'staff' CHECK (discount_source IN ('staff','member'));
ALTER TABLE boarding_sessions ADD COLUMN IF NOT EXISTS discount_source TEXT NOT NULL DEFAULT 'staff' CHECK (discount_source IN ('staff','member'));
ALTER TABLE sales             ADD COLUMN IF NOT EXISTS discount_source TEXT NOT NULL DEFAULT 'staff' CHECK (discount_source IN ('staff','member'));

-- POS customer link
ALTER TABLE sales ADD COLUMN IF NOT EXISTS owner_id TEXT REFERENCES owners(id) ON DELETE RESTRICT;

-- Per-line eligibility snapshot (A3): backfill TRUE, then drop the default
ALTER TABLE visit_billing_lines ADD COLUMN IF NOT EXISTS discountable BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE inpatient_billing   ADD COLUMN IF NOT EXISTS discountable BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE sale_items          ADD COLUMN IF NOT EXISTS discountable BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE visit_billing_lines ALTER COLUMN discountable DROP DEFAULT;
ALTER TABLE inpatient_billing   ALTER COLUMN discountable DROP DEFAULT;
ALTER TABLE sale_items          ALTER COLUMN discountable DROP DEFAULT;
```

**Why backfilling `TRUE` is correct for every existing row:** the column
only matters when `d > 0`. Every existing bill with `d > 0` has a staff
discount, and the guards guaranteed all its lines were discountable at the
time. Bills with no discount are unaffected by the value.

**Why the default is then dropped:** so a future insert site that forgets
the column fails loudly on `NOT NULL`, instead of silently marking a
non-discountable item as discountable. In `schema_postgres.sql` write the
column as `discountable BOOLEAN NOT NULL` with **no** default. Expect test
fixtures that insert lines directly to start failing on this — that's the
column doing its job; update the fixtures.

Settings keys (no schema change): `member_discount_percent` default `'0'`,
and `member_term_months` default `'12'` (§5.1).

**`member_expires_on` is nullable and NULL means "never expires."** Only
reachable by clearing the field on purpose; the enroll form always pre-fills
it. Nullable rather than `NOT NULL` so the helper in §5.1 stays a single
expression and so any row predating the column reads as unexpired — which is
correct, since no such row can have `is_member = TRUE`.

---

## 4. Snapshot eligibility at every line insert

| Table | IQ | JO | Where `can_discount` comes from |
|---|---|---|---|
| `visit_billing_lines` | logic.py:482 (`save_visit_billing_lines`) | logic.py:483 | `price_list` by `price_id` |
| `inpatient_billing` | routes/clinical.py:1962 (`inpatient_billing_add`) | routes/clinical.py:1917 | `price_list` by `price_id` |
| `sale_items` | routes/sales.py:229 (`_record_sale`) | routes/sales.py:376 | `price_list` via `linked_item_id` — reuse the join in `non_discountable_line_names_for_items` rather than writing a second one |

**POS lookup API** (`api_inventory_lookup`, `routes/inventory.py`) must
return `discountable` for each item so the live preview can compute
per-line. It has **two branches** (barcode and name search) — add it to
**both**. The two apps' versions of this function differ in structure (JO
precomputes a `status_by_item` map; IQ calls `inventory_status_by_id` per
row), so add the field in each app's own shape rather than copying one over.

---

## 5. Membership

- **Routes** (in `routes/clinical.py`, beside the owner routes — no new
  blueprint): `POST /owners/<owner_id>/rewards/enroll` (takes an optional
  card number) and `POST /owners/<owner_id>/rewards/unenroll`, both behind
  `@auth.permission_required("manage_rewards")`, both taking the owner row
  `FOR UPDATE`, both writing `auth.log_change()`. Endpoint names carry the
  blueprint prefix (`url_for("clinical.owner_rewards_enroll", ...)`).
- **Permission:** add `("manage_rewards", "Manage Rewards Members", "Patients & Visits")`
  to `auth.PERMISSIONS` and to `ADMIN_ONLY_TODAY`. No migration (§1).
- **`owner_detail.html`:** a Rewards section — status, card number, member
  since, enrolled by, and Enroll/Unenroll controls for `manage_rewards`.
- **`owners_list.html`:** a members-only filter and a member badge.
- **Settings:** `member_discount_percent` in `routes/settings.py`'s
  `NUMERIC_RANGES` as `(0, 50)` (A6), and `member_term_months` as `(1, 120)`.
  IQ parses the rate with `parse_money` → float; JO → `Decimal`. Read it
  through one helper in each app so the four bill-creation sites can't parse
  it four ways. The term is a plain integer in both apps — it is not money,
  so it must not go through `parse_money`/`Decimal` at all.
- **Owner search for POS:** `GET /api/owners/search?q=` behind
  `process_pos_sales`, matching name, phone or card number, returning `id,
  name, phone, is_member`. Use `logic.like_pattern()` for the `ILIKE` —
  `test_search_wildcards.py` exists because raw user input in a `LIKE` was
  already a bug here. `api_patients_search` in `routes/clinical.py` is the
  shape to follow. **Selecting a customer is optional and opt-in** (owner,
  2026-09-19): no prompt, no skip step, nothing added to the walk-in path.
  Staff fill it only when a card is presented, so `sales.owner_id` is NULL on
  most sales — §9's POS figures are partial **by design**, and nothing may be
  built that assumes otherwise.

### 5.1 Expiry (owner decision, 2026-09-19)

Cards are **fixed-term**. `member_term_months` (Settings, default 12)
pre-fills `member_expires_on` on the enroll form as `today + term`; staff may
edit that one date for that one card. Renewal is just re-enrolling — no
separate action.

Six things to get right, because most of them are the kind that look fine and
are wrong by one day:

1. **Enforce lazily, at read time. Do NOT add a scheduler job.** Active
   membership is one expression, behind **one helper per app**:
   `is_member AND (member_expires_on IS NULL OR member_expires_on >= today)`.
   A nightly job that flips expired members would be a second source of truth
   and, worse, one that fails **silently** when it stops running — see
   `CLAUDE.md` §7 on this scheduler's existing wall-clock traps. A comparison
   cannot stop running.
2. **Never flip `is_member` at expiry.** Enrollment and expiry are separate
   facts; collapsing them loses the distinction between "lapsed" and "never
   a member", which the owner page and the §9 badge both need.
3. **The card works *through* its expiry date** — `>= today`, inclusive.
   Test the boundary day itself, not just "before" and "after"; an off-by-one
   here is a card that dies a day early, and nobody reports it as a bug.
4. **Use naive `date.today()`**, matching the 83 existing `date.today()` /
   `datetime.now()` sites. The app has **no** timezone helper and runs on the
   clinic PC, so local time *is* clinic time. Do not "improve" this to UTC —
   that would put these two dates one day out of step with every other date
   in the app.
5. **Expiry is checked only at bill creation**, exactly like membership (A2).
   A bill created while the card was valid keeps its discount after the card
   lapses. No new rule, no re-check, nothing to recompute.
6. **Badge within 30 days**, on the owner page and the members list only
   (§10 for the Arabic). No new screen and no notification system.

---

## 6. Apply the member discount when a bill is created (A2)

At each creation site: find the owner (via the patient for visits, inpatient
and boarding; the selected customer for POS). If `owner.is_member` **and**
the rate is > 0, write `discount_source='member'`,
`discount_percent=<rate>`, `discount_applied_by=<current user>`. Otherwise
leave the defaults.

| Surface | Creation site, IQ | JO |
|---|---|---|
| Visit | `INSERT INTO billing` in `visit_billing_save`, routes/clinical.py:989 | routes/clinical.py:962 |
| Inpatient | `INSERT INTO inpatient_cases` in `_create_inpatient_case`, routes/clinical.py:666 | routes/clinical.py:658 |
| Boarding | `INSERT INTO boarding_sessions` in `boarding_new`, routes/clinical.py:1434 | routes/clinical.py:1383 |
| POS | `INSERT INTO sales` in `_record_sale`, routes/sales.py:218 | routes/sales.py:365 |

Two things to get right:

- **The visit insert is an UPSERT.** Set the member fields in the `INSERT`
  column list only. The `ON CONFLICT (visit_id) DO UPDATE` clause **must not**
  list any discount field, or every later billing save would overwrite the
  snapshot (breaking A2).
- **`import_seed.py`'s billing insert** (line 226, both apps) is historical
  data — leave it on the `'staff'` default.
- **The member rate must bypass the role cap.** `discount_percent_error()`
  (`core.py:358`) rejects anything above `auth.discount_cap_for()`
  (`auth.py:322`, the user's personal override or their role's cap). That
  check exists for *staff discretion* and must not be on this path: a 10%
  member rate written by a receptionist whose cap is 5% would otherwise fail
  the range check and **block bill creation outright** for that role, on
  every member's bill, from the day the card goes live. The plan did not
  say this before 2026-09-19; it is the most likely way this feature breaks
  on day one for a non-admin. Write `discount_percent` directly at these four
  sites and leave `discount_percent_error()` to the staff entry points in
  §7.1. A test for it is in §11.3.

---

## 7. "Card only": refuse staff discounts on member bills, and scope the old guards

This is the step most likely to produce a `SEAM_RULES.md` entry. Do it
carefully and test every site.

### 7.1 Refuse — four staff entry points

On a bill with `discount_source='member'`, each of these must **refuse**
with a flash (not silently ignore the input):

1. `visit_discount_save` — routes/clinical.py
2. `inpatient_discount_save` — routes/clinical.py
3. `boarding_payment`'s discount field — the discount arrives in the same
   submission as the payment, so the refusal has to happen before the
   balance checks that use it
4. `pos_checkout` — when the selected customer is a member, any non-zero
   `discount_percent` from the form is refused

Hide the staff-discount inputs on member bills in `visit_detail.html`,
`inpatient_detail.html`, `boarding.html` and `pos.html`, and show "Member
discount — N% on eligible items" instead. **The server-side refusal is the
rule; hiding the input is a convenience.**

### 7.2 Scope the non-discountable guards to staff discounts

These five sites block non-discountable items whenever a bill has a discount
(IQ lines; find JO's with `grep -n non_discountable_line_names`):

| IQ site | Route | What happens on a member bill if left alone |
|---|---|---|
| routes/clinical.py:941 | `visit_billing_save` | **every non-discountable item is refused — member visit billing breaks** |
| routes/clinical.py:1932 | `inpatient_billing_add` | **every non-discountable procedure is refused** |
| routes/clinical.py:1057 | `visit_discount_save` | route already refuses member bills (§7.1) |
| routes/clinical.py:2044 | `inpatient_discount_save` | route already refuses member bills (§7.1) |
| routes/sales.py:289 | `pos_checkout` | keyed on the staff `discount_percent`, which must be 0 for members |

The first two fire on `discount_percent > 0` and would break billing for
every member the moment the card is live. Add `and discount_source ==
'staff'` to both. The other three are safe as written only because of §7.1
— which is exactly why Seam Rule 7 tests them as a group rather than
one at a time.

### 7.3 The one way back out: admin-only removal (owner decision, 2026-09-19)

**Overrides A9.** §7.1 refuses *every* staff submission on a member bill,
which blocks typing `0` just as firmly as typing `15` — so without this, a
member discount on the wrong bill is permanent for visits, inpatient and
boarding. (POS could be corrected by refunding and re-ringing; the other
three had nothing.) It happens for ordinary reasons: the wrong customer
picked out of the POS search, a pet registered under the wrong owner, a card
enrolled on a duplicate owner row.

`POST /<surface>/<id>/rewards/remove-discount`, one per surface, or one route
taking the surface as a parameter — whichever fits each app's own routing
better; do not force them to match across apps.

- Behind `@auth.permission_required("manage_rewards")`, admin-only (§5).
- **Remove-only, and this is the whole design.** It sets
  `discount_percent = 0` and `discount_source = 'staff'`. It accepts **no
  percentage from the request at all** — there is no field to post. That is
  what keeps the owner's "card only" decision intact: the action cannot add
  a discount, cannot raise one, and cannot be turned into a staff-discount
  back door by a caller passing a number. **Do not add a percent parameter
  "for symmetry" later.**
- Takes the bill row `FOR UPDATE` and writes `auth.log_change()`, in the same
  transaction, per that function's docstring.
- Once `discount_source` is back to `'staff'` with `0`, the bill is an
  ordinary non-member bill: §7.1 stops refusing it and §7.2's guards apply
  normally. Re-checked deliberately — the state it leaves behind must be a
  state the rest of the system already understands, not a fourth kind of bill.
- Surfaced only on a member bill, only to someone holding the permission.

Note the asymmetry with §7.1 and keep it: staff cannot *change* a member
discount, and an admin can only *delete* one. Neither can set a number.

---

## 8. Everything downstream that reads a discount

### 8.1 Refunds
`refundable_sale_items` applies `d` per line only where `discountable` is
true (§2.1). Without this, a member's returned item is refunded at the full
non-member price. The aggregate cap added with Clean Up (a sale's total
refunds can never exceed `sales.total`) still bounds the worst case, but
partial returns would still be overpaid. Service refunds are capped by
`payments` and need no change.

### 8.2 Receipts and PDF exports
Replace the five copied blocks in `pdf_export.py` with **one** helper used
by all five exports. It reads `pre_cleanup_total` from the summary rather
than re-deriving `subtotal × (1 − d)`, and labels the row by source:
`Discount (5%)` for staff, `Member discount (10%)` for members. **Every
receipt must satisfy subtotal − discount − Clean Up = total** — assert it
(§11.2); the old re-derivation would break it on any member bill with a
non-discountable line. Before adding the label, check `pdf_export.py`'s
current language convention (it was English-only when
`ARABIC_LOCALIZATION_PLAN.md` shipped — confirm in `COMPARISON.md` §57–§58
rather than assuming).

### 8.3 Reports
`vet_performance` → stored `billing.total`. `revenue_by_category` and the
inpatient part of `_revenue_and_cogs_by_month` → per §2.1, **in each app's
own shape**.

### 8.4 Screens that show a discount
`visit_detail.html`, `inpatient_detail.html`, `boarding.html`,
`pos_receipt.html`, `pos_history.html`, `cash_register.html`, `pos.html` —
label by `discount_source`. The cash register ledger reads stored totals, so
only its label changes.

---

## 9. Fix the ranking so it's a good list to enroll from

`logic.client_value()`, both apps:

- **Window:** a `months_back` parameter, default 12 — filter `payments.date`,
  `refunds.refund_date` and `sales.sale_date`.
- **Subtract refunds:** service refunds via `visit_id`, `inpatient_case_id`
  **and `boarding_id`** (boarding refunds exist now), plus retail refunds on
  owner-linked sales.
- **Include POS sales** that have an `owner_id`.
- **Return `is_member`.** `insights.html` shows a member badge and links
  each name to the owner page, where staff can enroll.
- JO keeps its 3-decimal rounding.

`/insights` is a **loading shell** that polls a background job. Any browser
check of this list must wait for `.vz-progress-shell` to disappear first
(`CLAUDE.md` §5); three tools here have already been fooled by it.

### 9.1 The tiles change too — don't ship the list without them

`client_value()` does not only feed the Top Clients table. `insights.html`
also renders two stat tiles from its other two return values:

| Line | Label today | After §9 |
|---|---|---|
| insights.html:13 | "Clients With Paid Visits (Lifetime)" | a 12-month count |
| insights.html:14 | "Avg. Lifetime Spend / Client" | a 12-month average, refunds subtracted |
| insights.html:91 | caption: POS sales "aren't linked to a client in this system" | no longer true — owner-linked sales now count |

**Both tiles will drop, probably sharply** — all-time to one year, minus
refunds. To anyone who watches them, that looks like a bug. All three strings
are wrong after the change and must be reworded **in both languages** (§10),
and the drop belongs in the CHANGELOG entry (§13) in plain words, not as
"improved client value calculation".

The owner chose to ship this **in the same release as the card**
(2026-09-19), so the tiles and the card move together: if a number looks
wrong afterwards there are two candidate causes, and the CHANGELOG is what
makes that untangleable. Write it properly.

---

## 10. Translation and UI conventions

- Every new user-facing string through `_()`; update both apps' `.po`
  files; `pybabel compile`.
- **Don't guess the Arabic — batch the questions to the clinic owner**, in
  the format from `ARABIC_LOCALIZATION_PLAN.md` §3. Specifically flag:
  **"Member discount" vs "Discount" vs "Clean Up"** — `الخصم` already
  collided once, for Discount and Clean Up (`ARABIC_TRANSLATION_QUESTIONS.md`),
  and a third discount term makes that collision likelier. Also: rewards
  card, member, enroll/unenroll, card number, "on eligible items", and —
  added 2026-09-19 — **expires / expired / renew**, "expires in N days",
  "member since", and the two reworded `/insights` tiles plus their caption
  (§9.1). `ARABIC_TRANSLATION_QUESTIONS.md` #25 is the standing reason to
  ask rather than guess: تهذيب came back where the guess had been تشذيب, one
  letter, invisible to a non-speaker.
- No inline `on*=`; runtime-built markup (the POS customer results) uses
  `data-vz-act` + `VZ.action()`. Inline `style=` stays within the ratchet.
- Any new `<select>` carries its stored constant in `value=`
  (`SEAM_RULES.md` S5, `test_enum_labels.py`). `discount_source` must never
  be derived from displayed text.
- **Digit conversion, both halves of the rule.** The Rewards panel is the
  first place in either app where an identifier and several real numbers sit
  side by side, so stating only half of this is how the wrong half gets
  applied. Card numbers and owner IDs are **never** converted to Eastern
  Arabic digits (`ARABIC_LOCALIZATION_PLAN.md` §7.1). `member_since`,
  `member_expires_on`, "expires in N days" and the discount percentage **are**
  — they are quantities, and they follow whatever every other date and number
  on the page already does. Don't invent a new path for them.
- **The four localization guards already exist — the plan named none of them
  before 2026-09-19.** New strings here land squarely in their territory:
  `test_placeholder_args.py` (every new string with an interpolated value —
  "Member discount — N% on eligible items", "expires in N days"),
  `test_js_localization.py` (the POS live preview is JS and shows a discount
  label), `test_enum_labels.py` (the members-only filter and anything else
  with a stored constant) and `test_arabic_wrapping.py` — see the next point.
- **The badges are an IQ/JO seam, not a shared change.** This feature adds a
  member badge to the owners list and `/insights`, and an "expires soon" badge
  (§5.1). `test_arabic_wrapping.py` exists because a badge with
  `overflow-wrap: anywhere` split the cursive word نجح across two lines as
  نج / ح — and **that test is IQ-only**, because JO's badge is `nowrap`
  (`CLAUDE.md` §62.2 — deliberately not synced). So: reuse the existing badge
  class in both apps and add no new `overflow-wrap: anywhere` rule. If you do
  add one, IQ fails and **JO stays green with the same bug**. Check JO by
  eye; it has no test that will tell you.
- **Keep the audit rows language-neutral.** `auth.log_change()` (`auth.py:492`)
  stores field *values* — `_as_text(old)`/`_as_text(new)` — not prose, so the
  enroll/unenroll/removal rows dodge `COMPARISON.md` §60.1's stored-string
  trap (a string written to a table in one language and read back in another
  is frozen at write time). That is a property to preserve, not a coincidence:
  do not "improve" these into readable sentences at the point of writing.

---

## 11. Tests

Run everything in the isolated environment (`CLAUDE.md` §5). Restart the
test apps by port with `scripts/simulation/restart_test_apps.sh` — a
`pkill` here silently matches nothing and leaves the old code serving.

### 11.1 New seam rules — `tests/test_seam_rules.py`, both apps

Each one discovers its subject live (`app.py` + glob of `routes/*.py`,
plus `logic.py`/`pdf_export.py` where relevant) and asserts a **floor** on
how much it inspected, like Rules 1–4.

| Rule | Asserts | Prevents |
|---|---|---|
| 5 | every `INSERT` into `visit_billing_lines`, `inpatient_billing`, `sale_items` names `discountable` | a new insert site that skips the snapshot (the dropped default also catches this at runtime) |
| 6 | every call to `compute_bill_totals` passes `discountable_subtotal` (walk the AST) | a caller treating everything as discountable |
| 7 | every function that writes `discount_percent` from request input also reads `discount_source` | a staff path that can overwrite a member discount (§7.1) |
| 8 | discount-percentage arithmetic appears only at the allow-listed sites in §2.1 | a new report re-deriving revenue from lines × (1 − d), which is how JO's P&L gap would come back |

### 11.2 One basket through every surface

Fixture: a member owner, rate 10%; item **A** discountable, item **B** not.

- Visit (Automatic), inpatient and POS each charge **10% off A only, B in
  full**. The stored total, the receipt (subtotal − discount − Clean Up =
  total), a refund of A (discounted price) and of B (full price), the P&L,
  `revenue_by_category` and `vet_performance` must all agree with the stored
  total.
- Boarding and a Manual visit: 10% off the whole amount (A4).
- **Controls:** the same basket for a non-member → no discount. A staff
  discount on a non-member bill with only discountable items → **exactly
  the same total as before this change** (the no-op property from §2).
- IQ: rounding and the anti-"looks free" floor applied once, to the total.
  JO: exact to 3 decimals, and the anti-rounding guard still green.

### 11.3 The other guards (each with its control)

- Staff discount on a member bill is refused at all four entry points; the
  same action on a non-member bill succeeds.
- Flip an item's `can_discount` after it's billed → bill total and refund
  price unchanged (A3).
- Enroll an owner after their bill exists → no discount on that bill;
  change the rate → existing bills unchanged (A2).
- A **custom role** without `manage_rewards` cannot enroll (both apps
  support custom roles — `CLAUDE.md` §2 step 5).
- Browser tier: POS customer lookup on a mixed basket → the live preview
  equals the server's total, and the staff-discount input is hidden.

Added with the 2026-09-19 decisions:

- **Expiry boundary, all three days.** A bill created the day *before*
  expiry, **on** the expiry date, and the day *after* → discount, discount,
  none. The middle case is the one that matters and the one an off-by-one
  silently breaks (§5.1.3).
- **Expiry does not disturb existing bills.** A bill created while the card
  was valid keeps its discount after it lapses (§5.1.5), and `is_member`
  stays `TRUE` on a lapsed member (§5.1.2).
- **`member_expires_on IS NULL` never expires**, and the enroll form
  pre-fills `today + member_term_months` — with a control that an edited
  date is honoured rather than overwritten by the setting.
- **The removal action, with its control.** Removing clears the discount and
  leaves an ordinary staff-shaped bill that §7.2's guards then treat
  normally. Control: a non-admin (and a custom role without
  `manage_rewards`) is refused. And the design test — posting a percentage
  to it changes nothing, because it reads none.
- **The role-cap bypass (§6).** A user whose `discount_cap` is **below** the
  member rate can still create a member's bill, and it carries the full rate.
  Control: that same user is still capped on an ordinary staff discount.
  Without this test the feature breaks for every non-admin on day one and
  nothing says so.
- **POS with no customer selected** (the opt-in default) → `owner_id` NULL,
  no discount, sale unaffected. This is the common path, so it needs a test
  rather than an assumption.

### 11.4 Prove every guard (`CLAUDE.md` §7.3)

Reintroduce each bug and watch the suite go red before believing it:

- remove `and discount_source == 'staff'` from the `visit_billing_save` guard
- let `visit_discount_save` accept a member bill
- give `discountable_subtotal` a default of `subtotal`
- revert `refundable_sale_items` to discounting every line
- revert JO's inpatient P&L to the per-line re-derivation
- make the visit UPSERT's `DO UPDATE` overwrite `discount_percent`
- add a `1 − discount/100` computation to a new function (Rule 8)
- change the expiry comparison from `>= today` to `> today` — the boundary
  test in §11.3 must go red, or it is not testing the boundary
- make the §7.3 removal action read a percentage from the request and apply it
- route the member rate at bill creation through `discount_percent_error()`
  (the §6 bug) and confirm the low-cap test fails

---

## 12. Order of work

Do all of it in IQ first, then JO — **tailored to JO's code, not copied**.

1. Schema (§3).
2. Line snapshots and the lookup API (§4).
3. The core calculation, summaries and all seven callers (§2) — **with no
   member logic yet.** **Checkpoint:** the full existing suite must pass
   with zero behavioural change. That's the evidence the no-op property
   actually holds before anything is built on top of it.
4. Membership, permission, Settings rate **and term**, plus the single
   active-member helper (§5, §5.1).
5. Creation-time application — **including the role-cap bypass (§6)** —
   card-only refusals, guard scoping, and the admin removal action
   (§6, §7, §7.3).
6. POS customer link and UI (§4, §5, §7.1).
7. Downstream readers (§8).
8. Ranking (§9).
9. Translations — batch the Arabic questions to the owner (§10).
10. Tests alongside each step; the §11.4 mutation pass at the end.

---

## 13. Release

- `VERSION` + `CHANGELOG.md` in each app, per `RELEASE_WORKFLOW.md`.
- `COMPARISON.md`: a dated section, including the JO per-line revenue
  divergence (§2.1) and how each app fixed it.
- `SEAM_RULES.md`: add Rules 5–8 to the §3 table, and a register entry for
  anything this work turns up.
- `CLAUDE.md` layout block: update the `features/` line.
- **Clinic launch note:** every Price List item defaults to *not*
  discountable. Before handing out cards, mark what's eligible — otherwise
  the card discounts nothing. Use the existing Price List bulk editor (§1);
  it already has the checkbox.
- **CHANGELOG must say the `/insights` tiles changed and why**, in plain
  words — they will drop sharply and it is not a bug (§9.1). "Improved client
  value calculation" is not an acceptable line for this.
- **Also tell the clinic the term is 12 months by default** and where to
  change it, since the first cards all expire on the same date a year out.

---

## 14. Not in scope

- Points, tiers, or stacking with staff discounts (owner's decisions).
- Applying the card to bills that already exist when someone enrolls (A2) —
  and, by the same rule, re-checking expiry on a bill already created (§5.1).
- ~~Removing a member discount from an existing bill (A9).~~ **Now in scope**
  as the admin-only remove-only action — §7.3.
- Automatic enrollment from the ranking (A5), and automatic *renewal* when a
  card lapses — renewal is re-enrolling, by hand (§5.1).
- A revocation reason field, and preserving the original `member_since`
  across a re-enrollment (owner, 2026-09-19: the change log is enough). Note
  the consequence — a returning member's owner page shows the *newer* join
  date.
- Scanning a card's barcode at POS — card numbers are typed or searched in
  v1. POS already has barcode lookup for items, so this is a small
  follow-up if wanted.
- Messaging members (WhatsApp/SMS), or any customer-facing portal.
