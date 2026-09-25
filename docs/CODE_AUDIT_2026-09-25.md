# Code audit — IQ v1.17.2 and JO v1.15.2 — 2026-09-25

> **Status: being fixed in the merged VetClinicSystem.** This audit describes
> the two predecessor apps. Every finding is carried into the one merged
> system and fixed there — `docs/plans/UNIFIED_CODEBASE_PLAN.md` §7 maps each
> ID to where it is fixed, and its §13 progress log records when. Where this
> document says "both apps", read "the merged system, under both money
> settings". File and line references point into the predecessor trees
> (`webapps/`), not this repository.

Scope: bugs in the frontend, backend and database of both apps; parity between
IQ and JO **excluding the deliberate money-model divergence** (float/250-note
IQD vs exact 3-decimal JOD, `COMPARISON.md` §1.1); and design that is more
complicated than it needs to be.

Nothing in either app was changed. Every live check ran in the sanctioned
throwaway environments (`scripts/isolated_test_env.sh`, ports 5091/5092), which
were torn down afterwards.

---

## How this was produced, and what it is worth

1. **Both suites run first, as a baseline**, with `APP_URL` set so the browser
   tier was alive: **IQ 879 passed / 3 skipped, JO 849 passed / 4 skipped**.
   Every finding below that is marked *verified live* was reproduced against
   the same builds those green runs tested. That is the most useful single fact
   in this document: the suites are green through all of it.
2. **Function-by-function diff of the two trees.** A script parsed every
   top-level function in both apps, normalised the currency/branding tokens and
   listed the functions whose bodies differ. That turned a 12,000-line textual
   diff into ~120 functions to read, and is how most parity items were found.
   83.1% of IQ's Python/HTML/JS/CSS lines exist verbatim in JO.
3. **Reading** schema, migrations, `core.py`, `logic.py`, `app.py`, the six
   blueprints, the templates' inline scripts and the static JS.
4. **Live probes** in both apps: hostile date formats on every date filter, a
   POST sweep of all 50 parameterised POST routes with a nonexistent parent id
   (earlier sweeps were GET-only), sub-fils JOD amounts, a manage_settings-only
   and a manage_users_roles-only custom role, concurrent-edit conflicts, the
   P&L summary before/after a payment, and a deactivated item at POS.

Labels used below: **Verified live** (reproduced over HTTP in the throwaway
env), **Confirmed by code** (read, not run), **Inferred** (reasoned, with the
condition that would make it bite).

Prior audits were read first so closed findings are not re-reported
(`FULL_APP_REVIEW_2026-09-10.md`, `SIMULATION_AUDIT_2026-09-11.md` §8,
`SEAM_RULES.md`, `COMPARISON.md` §55–§63).

---

## Index

| ID | Severity | Apps | Finding | Status |
|---|---|---|---|---|
| **B1** | High | both | Date filters accept ISO-week / basic dates that Postgres rejects → **HTTP 500** on 4 IQ pages and 2 JO pages; silent empty results on 3 more | **Fixed** — `core.strict_date`; `parse_date` renamed `logic.as_date`; `test_dates_strict.py`, seam rule 9 |
| **B2** | High | both | A Clean Up or boarding discount taken with a payment never refreshes the month's P&L summary | **Fixed** — phase 3 (P&L computed on read, `reports.py`); `tests/test_reports_live.py` |
| **B3** | High | JO | JO's P&L and Insights ignore boarding discounts (incl. the rewards card) and Clean Ups; `billed_total` is written and never read | **Fixed** — phase 3 (stored totals apportioned, one query for P&L and Insights); `tests/test_reports_live.py` |
| **S1** | High | both | A `manage_settings`-only role can set `backup_retention=1`, `log_retention_days=90`, `backup_dir`, `backup_time` — fields the UI hides behind `manage_maintenance` | **Fixed** — `SETTING_FIELD_PERMISSION` in `routes/settings.py`, pinned by `test_privileges.py` |
| **S2** | High | both | `manage_users_roles` is full Admin in one click: a holder promotes themselves to the system Admin role (or resets the Admin's password) | **Fixed** — `_beyond_actor` in `routes/admin.py` on all seven routes, pinned by `test_privileges.py` |
| **B4** | Medium | both | The concurrent-edit guard can be defeated by clicking Save twice (JO visit/boarding/inpatient, IQ inpatient) | **Fixed** — `edit_is_stale` + conflict panel; three more holes found and closed; `test_edit_conflicts.py` |
| **B5** | Medium | both | POS sells a deactivated inventory item with **no stock check** | **Fixed** — fails closed in `_priced_cart_lines`; `test_pos_deactivated.py` |
| **B6** | Medium | JO | JOD amounts with >3 decimals are validated unrounded and rounded by Postgres → 500 on a 0.0004 payment, 0.000 bills accepted | **Fixed** — phase 1 (`money.parse`), pinned by `test_money_routes.py::test_b6_*` |
| **B7** | Medium | JO | Cash-register audit calls any discrepancy under **1 JOD** "Perfect" | **Fixed** — phase 1 (`money.audit_status`), pinned by `test_money_routes.py::test_b7_*` |
| **B8** | Medium | IQ | Visit and patient-billing PDFs print the unit price and drop the quantity | **Fixed** — JO's rendering, inherited by the merged tree; now pinned by `test_exports.py` |
| **B9** | Medium | both | Restocked-refund COGS and the consignment restock credit use *current* cost (and current distributor) although `refund_items.sale_item_id` exists | **Partly fixed** — phase 3: the P&L's restock reversal uses the sale line's cost. The consignment restock credit is still open |
| **S3** | Medium | both | Restore runs with the app serving: no request gate, `pg_restore` not single-transaction | Confirmed by code |
| **F1** | Medium | both | ~30 `flash()` messages per app, plus every helper-returned message, are never translated (POS refusals, edit conflicts, date errors, refunds) | Confirmed by code + scan · *partly fixed in phase 1: POS checkout and refund messages* |
| **F2** | Medium | both | All UI text in `static/*.js` is English-only (unsaved-changes dialogs, upload progress, job progress, phone validation), and loading-shell titles | Confirmed by code |
| **B10** | Low–Med | both | Payment method is validated only on refunds; POS, visit/inpatient/boarding payments, distributor payments and settlements store any string | **Fixed** — `core.clean_payment_method` on all eight reads, CHECK constraints, seam rule 10; `test_payment_methods.py` |
| **B11** | Low–Med | both | Three POST routes 500 on a missing parent (one reachable from a stale tab after a delete) | Verified live |
| **B12** | Low | both | After a DB error the 500 page renders on an aborted transaction: English, default clinic name, a second traceback | Verified (logs) |
| **B13** | Low | both | Consignment settlement boundary: seconds-truncated `period_end` vs microsecond `sale_date`, no upper bound | **Partly fixed** — phase 1: microsecond `period_end`, sales and shrinkage bounded by it (pinned by `test_supplier_routes.py::test_control_settling_exactly_what_is_owed_is_recorded`). The restock term is still day-granular until `timestamptz` (phase 2) |
| **B14** | Low | both | "Rebuild Report Data" can erase a sale committed during the rebuild | **Fixed** — phase 3: no summary table, no Rebuild |
| **B15** | Low | both | Two caps checked without the lock that makes them caps (cash payout; retail refund aggregate) | Confirmed by code |
| **B16** | Low | both | Refund and payment dates are free-form: a refund can be booked before its sale or in a future month | Confirmed by code |
| **B17** | Low | JO | A failed appointment booking re-renders the grid for *today*, not the day being booked | Verified live |
| **B18** | Low | both | Audit-derived usage ignores stock recorded through Consignment Receiving | Confirmed by code |
| **B19** | Low | both | Wellness "due" never expires; the two apps sort it in opposite orders | Confirmed by code |
| **S4** | Low | JO | Dev mode runs the Werkzeug debugger on `0.0.0.0` | Confirmed by code |
| **S5** | Low | JO | `/reports/rebuild` redirects to an unvalidated `return_to` | **Fixed** — phase 3: the route was the Rebuild button's, and it is gone |
| **P1–P20** | — | — | Parity gaps, non-money | see §4 |
| **D1–D12** | — | — | Design that could be simplified | see §5 |
| **M1–M10** | — | — | Found while merging, after this audit | see §10 |

---

# 1. Bugs — backend and database

## B1 — Date filters accept formats Postgres rejects → 500s and silent empty pages — **Fixed**

**Severity: High · both apps (IQ worse)**

`logic.parse_date()` (`logic.py:17`, both apps) validates with
`date.fromisoformat()` / `datetime.fromisoformat()`. Since Python 3.11 those
accept the whole ISO 8601 family, not just `YYYY-MM-DD`: `2026-W39-4` (ISO
week), `20260925` (basic), `2026-09-25T10:00`. The routes validate with
`parse_date()` and then pass the **raw string** on to SQL. The installs run
Python 3.14.

Postgres accepts `20260925` but rejects `2026-W39-4`
(`invalid input syntax for type date`). Measured:

| Request | IQ | JO |
|---|---|---|
| `/visits?date=2026-W39-4` | **500** | 200 + warning |
| `/refunds?date=2026-W39-4` | **500** | 200 + warning |
| `/cash-register?date=2026-W39-4` | **500** | **500** |
| `/appointments?day=2026-W39-4` | **500** | **500** |
| `/pos/history?date=20260925` | 200, **silently empty** (LIKE on text timestamp) | 200 + warning |
| `/admin/logs?date=20260925` | 200, **silently empty audit log** | 200 + warning |
| `/consignment/sales?date_from=2026-W39-4` | 200, **silently wrong** (text compare) | 200 + warning |

`/appointments?day=` is `SIMULATION_AUDIT` F4 coming back through a different
input, and `/admin/logs` is `SEAM_RULES` S2 ("an empty audit log with no
warning") coming back. It is also the third time this one function has put a
500 on `/visits` and `/refunds`: IQ v1.10.1 fixed it validating a 10-character
prefix instead of the whole value. JO is mostly immune because its list pages moved to
`core.date_filter_arg()`/`clean_date_filter()` (`strptime("%Y-%m-%d")`), but
its cash register (`routes/sales.py:88`) and appointments
(`routes/clinical.py:2382`) still use `parse_date()`.

Where: IQ `routes/clinical.py:808` (visits), `2422`/`2442` (appointments);
`routes/sales.py:421`, `456`, `772`; `routes/admin.py:386`;
`routes/consignment.py:660`. JO `routes/sales.py:88`,
`routes/clinical.py:2382`.

**Fix.** One strict parser for request input — `datetime.strptime(v,
"%Y-%m-%d")` plus a check that `v == parsed.isoformat()` (strptime alone also
accepts `2026-9-5`) — and route every `?date=`/`?day=`/`?week=`/`?date_from=`
through JO's `date_filter_arg()`, ported to IQ. Keep the lenient
`parse_date()` for reading stored TEXT timestamps only, and rename it so the
two cannot be confused. Extend `test_seam_rules.py` rule 2 with the ISO-week
input; the current tests pass `2026-08-25garbage`, which both parsers reject.

**Fixed (merge).** `core.strict_date()` is the one parser for a date in a
request: exactly `YYYY-MM-DD`, and the value must equal the date's own ISO
spelling. `clean_date`, `clean_date_filter` and `date_filter_arg` go through
it, and so do the cash register and appointments, which had used the lenient
parser. That parser is renamed `logic.as_date()` and reads stored values
only. Seam rule 2 had been counting it as validation; it now counts only the
strict parsers. A new rule 9 keeps `as_date`, `parse_date` and
`fromisoformat` out of `app.py` and `routes/` altogether.

Two more inputs had no date check at all and were fixed at the same time:

- The inventory audit sheet's expiry went raw into a DATE column (garbage in
  gave a 500 and lost the whole sheet).
- The operating-costs month accepted `2026-13` (`core.strict_month`).

`tests/test_dates_strict.py` probes the nine date-filtered pages with three
non-plain spellings each, and has controls. Mutation-checked seven ways,
including making `strict_date` lenient again, which failed 30+ tests.

## B2 — The P&L summary goes stale when a payment carries a Clean Up or a discount — **Verified live**

**Severity: High · both apps**

`monthly_financial_summary` is maintained incrementally: every write that
changes revenue is supposed to call `logic.recompute_month_summary()`. The
three payment routes change revenue and do not:

- `visit_payment_add` (IQ `routes/clinical.py:1328`, JO `:1291`) adds a Clean
  Up and calls `refresh_visit_billing_total()`, which lowers `billing.total` —
  the figure the P&L reads — but never recomputes `date_billed`'s month.
- `inpatient_payment_add` (IQ `:2339`, JO `:2298`) — same, for
  `inpatient_cases.total`.
- `boarding_payment` (IQ `:1839`, JO `:1788`) applies a **staff discount or
  Clean Up** and refreshes `billed_total`, but not the month.

Measured in IQ: a 10% boarding discount given at payment left the month's
revenue at **447,250 IQD** until someone pressed *Rebuild Report Data*, which
brought it to **437,250**. A 250 IQD Clean Up on a visit left the summary
unchanged (it was corrected only because an unrelated later write recomputed
the same month). JO behaves the same for visits and inpatient; for boarding
see B3.

This is a seam bug in the `SEAM_RULES.md` sense: 16 call sites recompute the
summary and 14 refresh a stored total; these three do the second without the
first.

**Fix.** Short term: call `recompute_month_summary()` for the bill's month(s)
wherever `refresh_*_total()` is called — better, make `refresh_*_total()` do
it, so the two can no longer be separated. Long term see D2. Add a
cross-surface test: for every route that can change a stored total, assert
the month summary equals a fresh `_revenue_and_cogs_by_month()`.

## B3 — JO's P&L and Insights ignore boarding discounts and Clean Ups — **Verified live**

**Severity: High · JO only (IQ is correct)**

- JO's `_revenue_and_cogs_by_month()` reads boarding revenue from
  `boarding_sessions.total` (`JO logic.py:1291`) — the **raw pre-discount,
  pre-Clean-Up subtotal** — not `billed_total`. `billed_total` is written by
  `refresh_boarding_total()` and **read nowhere in JO**. A member's rewards-card
  discount on a stay therefore never reaches the P&L. Measured: a stay of
  100.000 JOD with a 10% discount (`billed_total` 90.000) still reported
  100.000 of revenue after a full rebuild.
- JO re-derives inpatient revenue per line (`JO logic.py:1283`) and never
  subtracts the case's `cleanup_amount`.
- JO's Insights `revenue_by_category()` (`JO logic.py:2405`) re-derives every
  category from line items and ignores every Clean Up (visit, POS, inpatient)
  and boarding discounts, while its docstring says it "mirrors the same revenue
  formulas as the Monthly P&L". It does not; the Monthly P&L reads the stored
  `billing.total`/`sales.total` for visits and POS. The two reports disagree.
- An active boarding stay with an auto total is also reported at its stale
  creation-time snapshot in both reports.

Clean Ups are capped at 1 JOD per bill, so that part is small; boarding
discounts are not.

**Fix.** Read `billed_total` for boarding (IQ does), and read or apportion the
stored `inpatient_cases.total` as IQ does rather than re-deriving. Make
Insights read the same stored totals as the P&L, and add a test that the two
reports agree for the same month.

## B4 — The concurrent-edit guard can be defeated by clicking Save twice — **Fixed**

**Severity: Medium · JO visit/boarding/inpatient; IQ inpatient**

`stale_edit_error()` refuses a save whose `expected_updated_at` is stale.
What happens next differs:

- **JO** `visit_edit`, `boarding_edit`, `inpatient_edit` (`routes/clinical.py:
  878`, `1663`, `2038`) and **IQ** `inpatient_edit` (`:2090`) re-render the
  form with `form=request.form` (the user's stale values) and the **freshly
  loaded record**, whose `updated_at` goes into the hidden field. Measured in
  JO: the conflict page showed the stale text, **did not show the other
  person's change**, and carried the new token; submitting it again stored
  the stale value. The guard only delays the lost update by one click.
- **IQ** `visit_edit` and `boarding_edit` redirect instead
  (`routes/clinical.py:892`, `1712`), which is safe but throws away everything
  the person typed.

**Fix.** On conflict, redisplay the user's values **with the old token** (so a
second Save is refused again) and show the other person's current values
alongside, or the changed fields. Make all three routes in both apps behave
the same way.

**Fixed (merge).** One helper for all three forms, `edit_is_stale()` in
`routes/clinical.py`:

- **Refused again.** A redrawn form keeps the token it was loaded with, so a
  second Save is refused again.
- **What changed.** A panel (`templates/_edit_conflict.html`) lists what was
  saved since that token: time, who, field, and old → new, from the audit
  log. `auth.log_change(at=…)` writes the same instant as `updated_at`, so
  "since" is exact.
- **Explicit override.** "Save my version over their changes" works only
  against the version the panel showed. A third save in between makes it
  refuse again.
- **Row lock.** The row is locked (`FOR UPDATE`) between the check and the
  save.

Fixing it turned up three more ways the same lost update happened. All are
closed:

1. **The first edit was unguarded.** `updated_at` was NULL until a record's
   first edit, and NULL meant "nothing to compare", so every record's first
   edit had no guard. It is now `NOT NULL DEFAULT now()`.
2. **Sibling writes.** The follow-up, wellness and grooming status buttons
   and boarding's Dismiss wrote columns the edit forms also write, without
   bumping `updated_at`. A form opened before one of them put the old value
   back on save. A scan in `tests/test_edit_conflicts.py` now holds every
   UPDATE of the three tables to that rule.
3. **One-second tokens.** `updated_at` was stored to the second, so two saves
   within the same second had the same token. It is now stored to the
   microsecond.

`tests/test_edit_conflicts.py` has 29 tests, each run on all three forms.
Mutation-checked six ways, and each mutation fails only its own tests.

## B5 — POS sells a deactivated item with no stock check — **Fixed**

**Severity: Medium · both apps**

`_priced_cart_lines()` (IQ `routes/sales.py:142`, JO `:288`) prices a line
from the active Price List row, then checks stock with
`inventory_status_by_id()` — which only covers **active** inventory items. For
a deactivated item it returns `None`, and `if status and ...` skips both the
"never audited" and the oversell checks. The Price List row and the catalog
item are separate records, so deactivating the item does not deactivate its
price.

Measured in both apps: an active never-audited item is correctly refused;
after deactivating it in the catalog, a checkout of **999 units** went through
and drove its stock to −999. Reachable from a POS cart built before the
deactivation, or a crafted POST (the lookup API does filter `active`).

**Fix.** Treat a missing status as "not sellable" (fail closed), and refuse
lines whose `inventory_list.active` is false inside the locked section.

**Fixed (merge).** In `_priced_cart_lines()`, no status now means refused,
with a message naming the item. The check runs after
`_lock_and_snapshot_cart_items()` has locked the row, so a deactivation
cannot land in between. `tests/test_pos_deactivated.py`: 999 units, and one
unit, of a deactivated item are both refused; the control is the same sale
while the item is active. Failing open again fails both guards.

## B6 — JOD amounts with more than 3 decimals — **Verified live**

**Severity: Medium · JO only**

JO's `parse_money()` (`JO core.py:96`) returns `Decimal(raw)` unrounded.
Validation compares the unrounded value; Postgres then rounds it to
`NUMERIC(12,3)` on insert.

- A distributor payment of `0.0004` passes `amount > 0`, is stored as `0.000`,
  and violates `CHECK (amount > 0)` → **HTTP 500** (CheckViolation).
- A distributor bill of `0.0004` passes "must be greater than zero" and is
  stored as a **0.000 JOD bill**.
- The same shape applies to payments, discounts and Clean Ups: `0.0004` passes
  `> 0` and becomes a zero-value row.

**Fix.** Quantize in `parse_money()` (`val.quantize(Decimal("0.001"),
ROUND_HALF_UP)`) or reject input with more than three decimals, so validation
sees the value that will be stored. Same for `parse_quantity()`.

## B7 — JO's cash-register audit reports up to 0.999 JOD as "Perfect" — **Verified live**

**Severity: Medium · JO only**

`cash_register_audit_new()` (`JO routes/sales.py:175`) keeps IQ's
`if abs(difference) < 1: status = "Perfect"`. In IQD that is sub-note noise;
in JOD it is up to 999 fils. Measured: counted 0.900 against a system figure
of 0 → **Perfect**, stored permanently and shown in Insights' Cash Register
Health. This is the exact failure mode `CLAUDE.md` §2 step 3 warns about, and
the same one fixed for `balance <= 0.5` in `compute_bill_totals()`.

**Fix.** In JO, `difference == 0` (or `< Decimal("0.001")`). Leave IQ as is.

## B8 — IQ's visit and patient-billing PDFs print unit prices without quantity — **Fixed**

**Severity: Medium · IQ only (JO fixed it)**

`pdf_export.py:207` (patient billing) and `:364` (visit export) append
`[l["name"], l["price"]]` per line. `price` is the **unit** price; the
quantity is dropped. A bill for 2 × 5,000 prints a line of 5,000 and a
subtotal of 10,000. JO prints `line_total` with a "× qty" label. These are
the documents handed to clients.

**Fix.** Port JO's line rendering (money formatting stays IQ's).

**Fixed (merge).** The merged tree is JO's, so both documents already print
the line total with "× quantity", and money formatting follows the money
setting. Nothing pinned it, so
`test_exports.py::test_an_itemised_line_prints_its_quantity_and_line_total`
now captures the tables each PDF is built from and checks the line for
2 × 12: "× 2" and 24. Reintroducing IQ's rendering fails it, in each
document separately.

## B9 — Restock reversals use current cost and current distributor — **Confirmed by code**

**Severity: Medium · both apps**

- `_revenue_and_cogs_by_month()` (IQ `logic.py:1377`, JO `:1321`) reverses
  the COGS of a restocked retail refund at the item's **current**
  `cost_price`.
- `consignment_balance()` (IQ `logic.py:2688`, JO `:1975`) credits a restocked
  refund at current cost **and against the item's current distributor**, while
  the sale itself was attributed through the snapshotted
  `COALESCE(si.distributor_id, i.distributor_id)`. Re-pointing an item moves
  refund credits from distributor A to B. Its day-granular `refund_date >
  period_start::date` also drops any restock refunded on the same day as the
  previous settlement, permanently.

Both functions' comments say this is unavoidable because "refund_items doesn't
link back to the specific sale_items row". It does now:
`refund_items.sale_item_id` exists and is written by `refund_retail_save()`.
The comments are stale and the limitation is gone.

**Fix.** Join `refund_items.sale_item_id → sale_items` and use its
`unit_cost` and `distributor_id` (falling back to current values only for rows
with a NULL link). Compare refunds at timestamp precision (`created_at`).

## B10 — Payment method is validated only on refunds — **Fixed**

**Severity: Low–Medium · both apps**

`refund_retail_save`/`refund_service_save` reject a method outside
`PAYMENT_METHODS`. `pos_checkout` (`payment_method=f.get(...)`),
`visit_payment_add`, `inpatient_payment_add`, `boarding_payment`,
`distributor_payment_new` and `consignment_settlement_new` store whatever is
posted, including nothing. Anything outside Cash/Card/Transfer lands in the
Cash Register's "other" bucket, so the drawer total is wrong for that day.
This is `SEAM_RULES` S5's rule applied on one surface and not its siblings.

**Fix.** One `clean_payment_method()` in `core.py`, called by all seven, and
a seam-rule test that every `INSERT INTO payments/sales/...` path calls it.

**Fixed (merge).** `core.clean_payment_method()` is the one check. It is
required on the clinic's own payments (POS, visit, boarding, inpatient,
refunds) and optional on the two supplier payments, whose forms offer a blank
"not recorded" — optional, but never anything outside the three. The
database refuses any other value too: a CHECK on each of the five method
columns. Seam rule 10 (`test_seam_rules.py`) walks the AST and requires
every read of a method field in `app.py` and `routes/` to be the argument of
`clean_payment_method()`; there are eight, and a floor asserts it sees them.

`tests/test_payment_methods.py` covers all seven routes with bad values
(unknown, wrong case, blank, missing) and has controls. Mutation-checked:
with the check accepting anything, 25 tests fail; with one route bypassing
it, that route's tests and the seam rule fail; making the settlement's method
required fails its control.

## B11 — POST routes that 500 on a missing parent — **Verified live**

**Severity: Low–Medium · both apps**

A sweep of all 50 parameterised POST routes with a nonexistent id found three
that raise a ForeignKeyViolation instead of a message, identically in both
apps:

| Route | Reachable in practice? |
|---|---|
| `POST /distributors/<id>/bills/new` | **Yes** — distributors can be deleted, so a bill form left open in another tab 500s on submit |
| `POST /inpatient/<id>/update` | Crafted URL only (cases cannot be deleted) |
| `POST /inpatient/<id>/contact` | Crafted URL only |

JO additionally 500s on the *invalid-amount* path of `distributor_bill_new`
for a deleted distributor: its redisplay does `ctx =
_distributor_detail_context(dist_id); ctx["form"] = f` with no `None` check
(IQ aborts 404). Also, `inpatient_update_add`/`inpatient_contact_add` log the
**case id** as the audit record id, not the new row's id.

**Fix.** Existence check (ideally `FOR UPDATE`) before insert in all three;
`None` check in JO's redisplays.

## B12 — The error page after a DB error — **Verified (error log)**

**Severity: Low · both apps**

When a request fails inside Postgres (every 500 in B1 and B11), the
transaction is aborted. `handle_unexpected_error()` (IQ `app.py:914`, JO
`:891`) then renders `error_500.html` on the same connection, so
`_select_locale()` and `inject_globals()` both hit `InFailedSqlTransaction`
and fall back: an **Arabic-configured clinic gets an English error page with
the default clinic name**, and a second traceback is logged for every error.

**Fix.** `g.db.rollback()` (guarded) at the top of the handler, before
rendering.

## B13 — Consignment settlement period boundary — **Confirmed by code**

**Severity: Low · both apps**

`consignment_balance()` sets `period_end = datetime.now().isoformat(
timespec="seconds")` (IQ `logic.py:2657`, JO `:1944`) but counts sales with
`s.sale_date > period_start` and **no upper bound**, and `sale_date` carries
microseconds. A sale in the same wall-clock second as a settlement (before it)
is counted in that settlement and, because `'…T10:00:00.3' > '…T10:00:00'`,
again in the next. A sale timestamped before `period_end` but committed after
the balance read is counted in neither.

**Fix.** Use microsecond precision for `period_end` and bound the queries with
`<= period_end`.

## B14 — "Rebuild Report Data" can erase a concurrent sale from the P&L — **Inferred**

**Severity: Low · both apps**

`recompute_full_summary()` (IQ `logic.py:1411`, JO `:1355`) scans all history,
then `DELETE FROM monthly_financial_summary` and re-inserts. A sale that
commits (and upserts its month) between the scan and the DELETE is dropped
from the summary until something else recomputes that month. In IQ the
rebuild runs in a background thread for seconds to minutes on a large
database, which widens the window.

**Fix.** `LOCK TABLE monthly_financial_summary IN EXCLUSIVE MODE` at the start
of the rebuild (the incremental upsert then waits), or recompute per month
inside the lock.

## B15 — Two caps checked without their lock — **Confirmed by code**

**Severity: Low · both apps**

- `cash_register_payout_new` checks `amount <= drawer cash` with no lock; two
  simultaneous payouts can each pass and together exceed the drawer.
- `refund_retail_save` locks the `sale_items` rows being refunded, not the
  `sales` row, but checks the **sale-level** aggregate cap
  (`already_refunded_total + rounded_total <= sale.total`). Two concurrent
  refunds of *different* lines of one sale both read the same aggregate.

Every other cap in the app takes a row lock first; these two are the
exceptions.

## B16 — Refund and payment dates are free-form — **Confirmed by code**

**Severity: Low · both apps**

`refund_date` accepts any valid date: before the sale or visit it reverses,
or in the future. The P&L books the negative revenue in that month (possibly
a closed one — the opposite of what the schema comment promises) and the Cash
Register shows the money leaving on that day. `visit_payment_add` and
`inpatient_payment_add` also accept an undocumented `date` field that no form
sends; `boarding_payment` always uses today. Clamp both to `[origin date,
today]`, and make the three payment routes agree.

## B17 — JO's appointment booking error jumps back to today — **Verified live**

**Severity: Low · JO only**

JO's `_appointments_page_context()` reads `week`/`day` from `request.args`
(`routes/clinical.py:2382`), which a POST to `/appointments/new` does not
carry. A validation failure while booking for 4 Oct re-rendered the grid for
**25 Sep** with the modal open. IQ passes the submitted date explicitly and
keeps the day.

## B18 — Audit usage ignores Consignment Receiving — **Confirmed by code**

**Severity: Low · both apps**

`confirmed_audit_rows_by_item()` computes usage as `prior count +
received_since_prior − count`, where `received_since_prior` is typed by hand
on the audit sheet. Stock recorded through *Consignment → Receiving* is
already in `inventory_transactions` but is not offered or added there, so
unless staff type it twice, the item's daily usage comes out understated or
negative and the Ordering Sheet's suggestion is wrong. Pre-fill the column
from `consignment_receipt` transactions since the prior audit.

## B19 — Wellness "due" never expires — **Confirmed by code**

**Severity: Low · both apps**

`_annotate_wellness()` marks a reminder `due` from 5 days before the dose
**forever** until someone ticks "contacted". Every uncontacted reminder since
the clinic opened stays in the Dashboard's *Wellness Reminders Due* list and
in the sidebar alert badge. The two apps also sort it oppositely (IQ newest
first, JO oldest first — `wellness_reminders()`), so the dashboard's top six
are different lists in the two apps. Bound "due" to the missed window, and let
a later wellness entry for the same patient and type supersede the old one.

## B20 — Smaller items

- `get_or_create_draft_session()` has a check-then-insert race (two drafts for
  one date) and **commits** from inside a helper (see D11).
- `stale_edit_error()`'s message is an English f-string (also F1).
- `_login_rate_limit_check()` mutates a module dict from 8 Waitress threads
  without a lock; its cleanup loop can raise `KeyError` under contention once
  more than 1,000 IPs are tracked.

---

# 2. Bugs — frontend and localization

## F1 — Flash messages that are never translated — **Confirmed by code**

**Severity: Medium · both apps**

`base.html` renders flashes as `{{ message }}` — no translation at render. So
any message not wrapped in `_()` at the call site shows in English in an
Arabic-configured clinic. An AST scan found **31 (IQ) / 30 (JO)** direct
literal `flash()`/`refuse()` calls, including:

- **POS checkout**: "Cart is empty.", "Nothing to sell.", "Discount must be a
  valid number.", the rewards-card refusal, "Can't apply a discount — the cart
  includes…", "Clean Up amount must be a valid number."
- **Refunds**: the success message "Refund of X IQD/JOD recorded…" and "Pick
  how this refund was actually paid out…"
- every "X must be one of: …" validation, role create/save/delete messages,
  the orphaned-appointment warnings, "Item reactivated./deactivated."

and, indirectly, every message built by a helper and flashed later:
`_priced_cart_lines()`/`_cash_payment_for()`/`_merged_cart_quantities()`
(stock-blocked, not-audited, cash-short), `stale_edit_error()`, `clean_date()`
(`BadDate`), `record_consignment_shrinkage()`/`_return()`, IQ's
`flash_cash_denomination_warning()` (observed live), and "Weight and BCS must
be valid numbers."

**Fix.** Wrap each in `_()` with named placeholders (as the rest of the app
does), and have helpers return `(msgid, args)` like `selfcheck` findings.
Extend `test_localization.py` with the AST scan used here: no `flash()` whose
first argument is a string literal, f-string or concatenation.

## F2 — UI text in static JavaScript is English-only — **Confirmed by code**

**Severity: Medium · both apps**

Localization reaches inline `<script>` blocks in templates only
(`test_js_localization.py`). The external files are never translated:

- `unsaved-changes.js` / `unsaved-changes-form.js` — the whole "Unsaved
  Changes / Keep Editing / Discard Changes / Save & Continue / Saving…" dialog
- `upload-progress.js` — "Max file size", "Selected:", "Uploading…", "Upload
  failed…"
- `progress.js` — "Working / Done / Failed", "Lost track of this job…",
  "Could not reach the server."
- `phone-validate.js` — the validation message
- `toast.js` — the "Dismiss" label; IQ `rebuild.js` — every string
- inline template JS literals not wrapped: "Owner:", "Chip:", "each",
  "stock:" (`boarding.html`, `inpatient_new.html`, `pos.html`,
  `inpatient_detail.html`)
- loading-shell `page_title`/`page_note` for Insights, Retention and
  Consignment Overview (`app.py`, `routes/consignment.py`), and IQ's rebuild
  job labels/messages (`app.py:1218`)

**Fix.** Emit one `window.VZ_I18N = {{ strings|tojson }}` block from
`base.html` and have the static scripts read from it.

---

# 3. Security and permissions

## S1 — `manage_settings` can write the maintenance-only settings — **Fixed**

**Severity: High · both apps**

After `FULL_APP_REVIEW` S1, `settings.html` hides the backup fields behind
`has_permission("manage_maintenance")` (IQ lines 53–67, JO 47–61) and every
maintenance route requires it. But `settings_page()`'s POST (IQ
`routes/settings.py:163`, save loop at `:289`; JO `:280`) is gated only by
`manage_settings`, and saves `backup_dir`, `backup_time`, `backup_retention`
and `log_retention_days` whenever they are present in the form.

Measured with a custom role holding **only** `manage_settings`: the fields are
not rendered and `/settings/backup-now` returns 403, yet posting them to
`/settings` saved `backup_retention=1`, `log_retention_days=90`,
`backup_dir=/tmp/…` and `backup_time=03:33` in both apps ("Settings saved.").
`backup_retention=1` makes the next backup delete every older dump
(`backup._apply_retention`); `log_retention_days=90` prunes the audit trail
back to 90 days on the next scheduled prune. It is the S1 pattern — gate in the
template only — for four fields.

**Fix.** In `settings_page()`, only accept those four keys when the user holds
`manage_maintenance`; add them to the S1 guard tests with a control.

**Fixed (merge).** `routes/settings.py` keeps one table,
`SETTING_FIELD_PERMISSION`, of the permission each field needs. The POST
refuses the whole submission ("Nothing was saved: …") if it carries a field
the user cannot change, before anything is validated or stored. The template
draws the Backups section via `setting_editable()`, which reads the same table,
so what is drawn and what is accepted cannot drift apart again.
`tests/test_privileges.py` posts each of the four fields as a
`manage_settings`-only role (all four refused), with controls: the same role
saves a field it holds, and the Admin sees the fields. Mutation-checked: with
the refusal disabled all four guard tests fail, and with the template gate
reverted the drawing test fails.

## S2 — `manage_users_roles` is a one-click route to full Admin — **Fixed**

**Severity: High · both apps**

`admin_user_role()` (`routes/admin.py:171`) lets any `manage_users_roles`
holder move **any user, including themselves**, into the system Admin role;
`admin_user_reset_password()` (IQ `:207`, JO `:362`) lets them reset the
system Admin's password; `admin_role_new()` lets them create a role with every
permission. Measured: a user whose role held only `manage_users_roles`
promoted themselves to Admin and immediately passed the `manage_maintenance`
gate (403 → authorised) in both apps.

That makes the new `manage_maintenance` separation, and every permission in
the checklist, only as strong as the list of people holding this one box —
while the UI presents it as one permission among many.

**Fix.** Only a system-role user may assign the system role, reset a system
user's password, or grant permissions they do not themselves hold. At minimum,
say on the checkbox that it is equivalent to Admin.

**Fixed (merge).** One rule, `_beyond_actor()` in `routes/admin.py`: someone
not in the system role may only act within the permissions they hold, read
from the database rather than the session. It applies to creating a user (the
role given), enabling or disabling a user, changing a user's role (both the
new role and the one being left, so an Admin cannot be demoted either),
creating or editing a role (the permissions given and, for an edit, the ones
the role already has), deleting a role (the role and the one its staff move
to) and resetting a password (the target's role). `tests/test_privileges.py`
covers each route with a guard and a control. Mutation-checked seven ways (the
rule switched off, then each of the six route-specific checks removed); each
mutation fails exactly the tests for its route. The guard tests for disabling
or demoting an Admin keep a second active Admin present, so the "last active
Admin" rule cannot be what refuses them.

## S3 — Restore runs with the app still serving — **Confirmed by code**

**Severity: Medium · both apps**

`settings_restore_now()` closes the pool and starts `pg_restore --clean
--if-exists` in a thread; `maintenance_lock` only stops a second
backup/restore. Every other workstation keeps working — the pool reopens on
the next request — against tables being dropped and reloaded, and `pg_restore`
is not run with `--single-transaction`. A POS sale during that window either
500s or writes a row that then collides with the COPY, leaving the restore
"partially restored". Add a `before_request` that answers 503 ("restore in
progress") while a restore holds the lock, and consider
`--single-transaction`.

## S4 — JO dev mode exposes the Werkzeug debugger on the LAN — **Confirmed by code**

**Severity: Low · JO only**

JO `app.py:1467`: `app.run(debug=True, host=bind_host, …)` with `bind_host`
defaulting to `0.0.0.0`. IQ pins dev mode to `127.0.0.1` with a comment
explaining why (the debugger console is PIN-protected but otherwise
unauthenticated). Port IQ's line. (IQ's dev mode, conversely, hard-codes port
5050 and ignores `BIND_PORT` — `app.py:1522`.)

## S5 — JO `/reports/rebuild` redirects to an unvalidated `return_to` — **Confirmed by code**

**Severity: Low · JO only**

`redirect(request.form.get("return_to") or url_for("reports"))`
(`JO app.py:1167`). CSRF-protected, so not exploitable cross-site, but it is
the only redirect in the app that skips `is_safe_local_path()`.

## Also

`/api/browse-folder` checks `os.path.isdir(path)` **before** the root
confinement, so its two error messages distinguish "doesn't exist" from
"outside the allowed roots" for any path on the host — a small existence
oracle, for `manage_maintenance` holders only.

---

# 4. Parity — IQ vs JO, excluding the money model

Deliberately **not** listed: float vs Decimal, 250-note rounding, `money.py`,
step sizes and currency formatting, IQ's two palettes and branded images,
country phone constants, IQ-only `test_arabic_wrapping.py` (`COMPARISON.md`
§62.2). B3, B6 and B7 above are JO bugs, not parity items.

| # | Area | IQ | JO | Suggested direction |
|---|---|---|---|---|
| P1 | **Sidebar gating** | every link wrapped in `has_permission` | every clinical/inventory/POS link shown to everyone — a `manage_settings`-only user saw **20** links vs IQ's 4, all but 4 leading to 403 (**verified**) | port IQ |
| P2 | **Inpatient billing** | search API, Service **and Medicine** | server-rendered checkbox list of `category='Service'` only — **Medicine cannot be billed to an inpatient case from the UI**; the whole service catalogue is rendered into every case page (`_inpatient_detail_context`) | port IQ |
| P3 | Inpatient tabs | tab kept in the URL hash across submits; ARIA tab roles | every submit lands back on "Info"; no ARIA | port IQ |
| P4 | Patient history | `patient_outpatient_visits()` drops the "Inpatient" admitting visit already represented by the case | shows the same encounter twice | port IQ |
| P5 | Back link | `_back_link.html` on 16 detail pages | none (the `ui.js` code that drives it is dead in JO) | port IQ |
| P6 | Row navigation | `data-row-href` (ui.js): 10px drag threshold, press feedback, aria-label | `data-vz-href` (behaviors.js): plain click — a touch scroll that starts on a row opens it; inline `cursor` style | pick one mechanism for both (D8) |
| P7 | Audit confirm | warns when a consignment item is counted below expected and suggests logging shrinkage | no warning | port IQ |
| P8 | `inpatient_billing_add` with a staff discount and a non-discountable item | refuses the whole submission | adds the rest and skips the blocked ones | decide once |
| P9 | `inpatient_new` | audit-logs exam findings, admitted items, vets | logs only the create | port IQ |
| P10 | Edit conflicts (B4) | visit/boarding redirect; inpatient redisplays | all three redisplay | one behaviour, fixed per B4 |
| P11 | Date filters (B1) | inline `parse_date()` ×7 | `date_filter_arg()` helper (strict), except cash register/appointments | port JO's helper, then fix both |
| P12 | Report rebuild | background job + progress bar (`rebuild.js`) | synchronous POST, unvalidated `return_to` | port IQ |
| P13 | POS name search | `inventory_status_by_id()` per result — up to 10 full catalogue recomputes per keystroke | computed once | port JO |
| P14 | Signed out after a password change | no message, keeps `next` | flashes why, drops `next` | combine: message **and** `next` |
| P15 | Wellness sort (B19) | newest first | oldest first | decide once |
| P16 | Appointment booking error (B17) | keeps the booked day | jumps to today | port IQ |
| P17 | Distributor bill/payment redisplay for a deleted distributor | 404 | 500 (B11) | port IQ |
| P18 | Migrations (`INCREMENTAL_SCHEMA_STATEMENTS`) | bumps `permissions_version` on **every launch**; lacks `backup_log.triggered_by` and `barcode_source` ALTERs | lacks the `manage_cash_register` retro-grant and the `consignment_since`/`refund_method` ALTERs and "Bank Transfer" normalisation | legacy-upgrade paths only; converge the list |
| P19 | Vet lookup | one `logic.vet_users()` | the same query inlined 3× (`day_grid`, `orphaned_appointments`, routes) | port IQ |
| P20 | Small UI | attachment delete "×" with aria-label and a fuller confirm; `aria-expanded` on toggles | plain "Delete"; per-item "print" barcode link in the catalogue that IQ lacks | converge |

Also: seven indexes have different names in the two schemas
(`idx_consreceipts_dist` vs `idx_consreceipts_distributor`, …) — harmless, but
the restore drill and any hand-written maintenance SQL must know both; JO's
`list_audit_sessions()` returns a tuple or a list depending on its arguments;
JO's `boarding_payment` still carries the Clean Up checks that
`cleanup_amount_error()` now performs (`FULL_APP_REVIEW` M5 remnant); JO's
schema comment on `inventory_transactions.reason` lists two of the six reasons.

---

# 5. Design that could be simplified

## D1 — Two forks that are 83% the same file

83.1% of IQ's Python/HTML/JS/CSS lines exist verbatim in JO. The real
differences are a money module, two phone constants, a palette, branding, a
port and a data-dir name. Everything else — including every bug marked "both"
above — is maintained twice by hand, and `COMPARISON.md` (5,400 lines),
`SEAM_RULES.md` and a function-diff discipline exist to keep the copies
honest. Most of §4 is simply drift.

One codebase with a per-country profile (`currency`: precision, rounding
strategy, tolerance, `Decimal` vs float; `phone`; `branding`; defaults) would
delete the parity problem rather than manage it. The money divergence can live
behind one small interface (`parse`, `payable_total`, `round_change`,
`format`, `is_settled`) with two implementations — which is roughly what IQ's
`money.py` already is. Keep two repos for release/update if needed, but
generate them from one source.

## D2 — Denormalised totals kept in sync by hand at ~30 call sites

`billing.total`, `inpatient_cases.total`, `boarding_sessions.billed_total` and
`monthly_financial_summary` are caches. They are refreshed by explicit calls:
14 `refresh_*_total()` sites and 16 `recompute_month_summary()` sites in IQ
alone. B2 is three sites that did one without the other; B3 is JO reading the
uncached column instead. The P&L is 12 rows per year and a clinic's bill
volume is small: computing the monthly figures on read (one grouped query per
source over indexed date columns) would remove the summary table, its rebuild
button, B2 and B14. If the caches stay, give them **one** entry point —
`bill_changed(db, kind, id)` — that refreshes the stored total and every
affected month together.

## D3 — The whole dashboard is computed on every page

`inject_globals()` (IQ `app.py:718`) calls `dashboard_snapshot()` on every
rendered page for the sidebar badge. That function fetches **every visit row**
to count active cases in Python (`SELECT case_status FROM visits`,
`logic.py:1178`), every pending follow-up, every wellness row ever recorded
(B19), the grooming queue, and the full `inventory_status()` (all items and
all confirmed audit lines). It grows with history on every click. Use
`COUNT(*)` queries for the badge, or cache it for a minute.

## D4 — `inventory_status_by_id()` recomputes the catalogue to answer for one item

It runs `inventory_status()` (every active item, every confirmed audit line,
one transaction aggregate) and scans the result. POS checkout calls it once
per cart line **while holding the row locks**; shrinkage and returns call it
under a lock; IQ's POS search calls it per result (P13). Add
`inventory_status_for(db, item_ids)` that scopes the three queries.

## D5 — Migrations re-run in full on every launch

> **Fixed — phase 2a.** `schema.py` + `migrations/`: each file runs once, in its own transaction; a failure stops the install or update instead of being recorded and started past. P18's IQ/JO list differences are moot — there is one baseline, and IQ's schema was checked against it (identical apart from index names).

`INCREMENTAL_SCHEMA_STATEMENTS` (107 IQ / 99 JO statements) runs on every
start, including ~30 `DROP CONSTRAINT`/`ADD CONSTRAINT` pairs that each
re-validate a whole table under an ACCESS EXCLUSIVE lock, full-table `UPDATE`
normalisations, and in IQ an unconditional `permissions_version` increment
(not idempotent, despite the list's contract). Startup time grows with the
data. A `schema_migrations(id, applied_at)` table and numbered migrations
would run each once, and would also make the IQ/JO differences in P18 visible
as missing numbers.

## D6 — Three date validators and TEXT timestamps

> **TEXT timestamps: fixed — phase 2c.** 39 event-time columns are `timestamptz`, `sales.sale_date` is `sold_at`, and "now"/"today" come from one clock in the clinic's zone (`clock.py`, the Time Zone setting). The three date validators remain — that is B1's fix.

`parse_date()` (lenient), `clean_date()` (strict, raises), `clean_date_filter()`
(strict, JO only) — and B1 is what the lenient one costs. Separately, most
event times are `TEXT` ISO strings compared lexically and filtered with
`LIKE 'YYYY-MM-DD%'` (`sales.sale_date`, `audit_log.timestamp`,
`inventory_transactions.timestamp`, consignment periods). They work only while
every writer uses the same `isoformat()` shape; `timestamptz`/`date` columns
would make range filters indexable and B13 impossible.

## D7 — A SQLite-era placeholder translator

`db.Connection.execute()` rewrites every `?` to `%s` with a regex that is not
quote-aware (its own comment says so). psycopg supports `%s` natively; a
one-time rewrite of the SQL strings would delete the translator and the class
of bug it documents.

## D8 — Two ways to do the same thing, in the same app

- Row navigation: `ui.js` (`data-row-href`) **and** `behaviors.js`
  (`data-vz-href`) ship in both apps; each app uses one, the other is dead
  code (P6).
- Context builders: IQ passes `db`, dates and page explicitly; JO's builders
  read `request.args` themselves, which is why a POST redisplay loses the day
  (B17). Pick the explicit style.
- Date filters (P11), vet lookup (P19), conflict handling (P10).

## D9 — Missing indexes for the filters the app actually runs

> **Fixed — phases 2b and 2c**: every index listed (plus refunds by visit / case / stay), and the `substr(timestamp,1,10)=?` / `LIKE 'YYYY-MM%'` filters are now indexed ranges over `timestamptz`.

No index on `sales(sale_date)`, `payments(date)`, `refund_items(sale_item_id)`,
`sale_items(item_id)`, `login_log(username, timestamp)` (read on every login
attempt), `visits(followup_date)`, `visits(wellness_next_dose_date)`,
`inpatient_cases(visit_id)`, or `(item_id, timestamp)` on
`inventory_transactions`; `audit_log`/`login_log` are filtered with
`substr(timestamp,1,10)=?`, which cannot use the existing index. Small today;
each is a full scan that grows with years of data.

## D10 — Inconsistent constraints on money

> **Fixed — phase 2b.** Every NUMERIC column has a CHECK — its sign as the routes already enforce it, percentages 0–100, and never NaN (which passes `>= 0` in Postgres) — pinned for future columns by `tests/test_quantities.py::test_every_numeric_column_refuses_nan`. Quantization before validation was phase 1 (B6).

Only `distributor_bill_payments.amount` has `CHECK (amount > 0)`; `payments`,
`refunds`, `cash_register_payouts`, `consignment_*` quantities and
`discount_percent` (0–100) have none, so the database backs up the app on one
table and not the others. In JO, NUMERIC scale and Python validation disagree
(B6). Add the CHECKs, and make JO quantize before validating.

## D11 — Helpers that commit

`get_or_create_draft_session()` and `_ensure_summary_populated()` call
`db.commit()` from inside `logic.py`, whose own convention (and
`close_db()`'s design) is that the request commits once. A helper commit
splits a request into two transactions without its caller knowing.

## D12 — Comment volume, and comments that are now wrong

Comments and docstrings are **29%** of non-blank Python lines in both apps.
Much of that is history ("this used to…", finding numbers, dates) that belongs
in `COMPARISON.md`/`CHANGELOG.md`; it makes the code slower to read and it
rots. Examples that are now false:

- "refund_items doesn't link back to the specific sale_items row" — it does
  (B9), in `_revenue_and_cogs_by_month()` and `consignment_balance()`.
- `app.py`'s language block still describes a cookie toggle and a page reload;
  since §58 it is a clinic setting.
- JO's `revenue_by_category()` "mirrors the same revenue formulas as the
  Monthly P&L" — it does not (B3).
- JO schema: `inventory_transactions.reason` lists 2 of 6 reasons.

---

# 6. Test-suite observations

- **Green through everything above.** Both suites passed in full while 6
  pages returned 500 (B1), the P&L went stale (B2), JO reported undiscounted
  boarding revenue (B3) and a settings-only role rewrote backup retention
  (S1). Same lesson as `SEAM_RULES.md` §1: the gaps sit between surfaces.
- **Worth adding:** a POST sweep with nonexistent parents (the GET sweep
  exists; this one found B11 in minutes); a cross-report consistency test
  (month summary == fresh recompute == Insights for the same month) run after
  *every* money-writing route; the ISO-week date on rule 2; the AST
  `flash()`-literal scan from F1.
- `test_browser.py:507` (barcode rendering) **skips in the sanctioned
  environment** — "no inventory item has a barcode in this database" — because
  `isolated_test_env.sh` seeds `INV301` without one. It is a dormant test in
  exactly the setup `CLAUDE.md` tells you to use. Seed a barcode.

---

# 7. Checked and found sound

- CSRF on every POST, including the JSON endpoints; login rate limit and
  per-username escalating lockout; inactive users are rejected on their next
  request; sessions invalidated on password change.
- Every `|safe` in templates wraps a static string; dynamic `innerHTML` in
  POS, boarding, inpatient and customer search passes names through
  `escapeHtml()`.
- Update tarballs are extracted with `filter="data"`.
- Folder browser confinement uses `realpath` + `commonpath` (not
  `startswith`).
- POS idempotency (fast path + unique index), fixed-order row locking in POS
  checkout, `FOR UPDATE` on bill mutations (`SEAM_RULES` rule 1).
- Structurally, the two schemas are identical apart from money types and seven
  index names (a normalising comparison of every table, column and
  constraint).

---

# 8. Suggested order of work

1. **S1, S2** — permission holes, small fixes.
2. **B1** — one strict parser, ported helper; it is F4 and S2 reappearing.
3. **B2, B3** — the P&L; then the cross-report test in §6.
4. **B5, B6, B7, B4** — POS stock hole, JO precision, JO tolerance, the
   conflict guard.
5. **B8, B9, B10, B11** — client PDFs, cost basis, payment method, 500s.
6. **F1, F2** — the Arabic residue.
7. §4 parity items, with P1–P4 first (JO users see them daily).
8. D2–D4 before the data grows; D1 is the decision that makes most of §4 go
   away.

---

# 9. Reproducing

Bring up `scripts/isolated_test_env.sh up iq` / `up jo`, then with
`scripts/simulation/vzsim.py`'s `Client` logged in as `admin`:

- **B1** — `GET /visits?date=2026-W39-4` (IQ 500), `GET
  /cash-register?date=2026-W39-4` (both 500), `GET /admin/logs?date=20260925`
  (IQ: empty, no warning).
- **B2** — bill a visit (Manual), note `monthly_financial_summary.revenue` for
  the month, pay with `cleanup_amount` > 0; the row does not change. For
  boarding: create a stay with a typed total, pay with `discount_percent=10`;
  compare the row before and after `POST /reports/rebuild`.
- **B3** — as B2's boarding case in JO: after the rebuild the month still
  carries the undiscounted total.
- **S1** — create a role with only `manage_settings`, a user in it, and `POST
  /settings` with `backup_retention=1&log_retention_days=90`.
- **S2** — create a role with only `manage_users_roles`; as that user `POST
  /admin/users/<self>/role` with the system role id.
- **B4** — open `/visits/<id>/edit` (token T0); save once with T0; save again
  with T0 (conflict page); save the conflict page's form (JO: overwrites).
- **B5** — `UPDATE inventory_list SET active=false WHERE id='INV301'`, then
  `POST /pos/checkout` with `item_id=INV301&quantity=999`.
- **B6** — JO: distributor → bill of 10 → payment of `0.0004` (500).
- **B7** — JO: `POST /cash-register/audit` with `day=2020-01-01&
  counted_cash=0.9` → Perfect.
- **B11** — `POST /distributors/NOPE/bills/new` with `total_amount=5`.

---

# 10. Found while merging

Bugs the merge turned up that this audit missed. Each was in a predecessor
app as released; each is fixed in the merged system. IDs are `M` so they do
not collide with the sections above.

| ID | Apps | Finding | Fixed |
|---|---|---|---|
| **M1** | JO | **The rewards card could not be switched on.** Settings validated `member_discount_percent` and `member_term_months` but its save loop never listed them (IQ's did), so saving the form discarded both; the programme stayed at 0% whatever an admin entered. | phase 1, `routes/settings.py` save loop |
| **M2** | IQ | **A service refund could pay out nothing, or more than was paid.** It was checked against what was refundable and *then* rounded to the *nearest* 250-dinar note: under 125 IQD it was recorded as a refund of 0 (no CHECK on `refunds.amount` stopped it), and 1,200 refundable / 1,200 refunded was stored as 1,250. The retail path already rounded down and never to zero; this sibling did not (a seam, `SEAM_RULES.md`). | phase 1, `money.refund_payout()` on both refund paths; `test_money_routes_iq.py::test_m2_*` |
| **M3** | both | **A consignment settlement was checked at one amount and stored at another** — the "more than owed" check ran before rounding. In IQ the rounding was to the *nearest* 250-dinar note, so 1,200 owed and 1,200 paid was stored as 1,250 with a carry-forward of −50. Same shape as B6. | phase 1, stored as entered (`money.parse()` at the door); `test_supplier_routes.py::test_m3_*` |
| **M4** | both | **Six Arabic translations were one sentence written two or three times over** (JO: "Password reset…", "Revenue from billing…", the Clean Up cap, the three "more than what's left refundable…"; IQ had two). They rendered as one run-on line and passed the "is it Arabic" test, because they were. The existing catalogue check also only saw entries that fit on one line. | phase 1; `tests/test_catalogue.py` now checks every entry, parsed |
| **M5** | both | **Four dashboard warnings disappeared after a few seconds** — flashed as toasts, which auto-dismiss, though each describes a standing condition (overdue audit, expiring stock, …). | phase 1, persistent notice banners |
| **M6** | both | **The pure test tier errored without a database** — `test_localization.py`'s autouse fixture wrote to the database on teardown, so a bare `pytest` reported 6 errors instead of skipping, contrary to the documented "every tier skips cleanly". | phase 1 |
| **M7** | both | **The browser tier never ran the IQ money rules.** Every browser test ran under JO, whose cash unit changes nothing, so the till's 250-note rounding and change-rounds-down had never been exercised in a real browser. | phase 1, IQ-marked POS tests in `test_browser.py`, mutation-checked |
| **M8** | both | **A distributor could be owed money that could never be settled.** An item already on the shelf can be flagged Consignment with no delivery logged; its sales then count as owed (from `consignment_since`), but `consignment_balance()` took the first period's start only from receipts, shrinkage and returns — so it stayed `None`, and the settlement route refused every attempt as "There's nothing to settle for this distributor yet" beside the amount owed. The suite's own "cannot pay more than is owed" test had been hitting exactly this refusal: it logged a delivery and sold nothing, so it never reached the check it was named for. | phase 1, `consignment_since` counts as activity; the test now sells through the POS and asserts the refusal's reason, with a control |
| **M9** | both | **Quantities printed four different ways, two of them wrong.** The POS receipt and inpatient billing printed the raw column (`Item × 1.000`), the refunds list printed `|int` — a 2.5-unit refund showed as 2 — and consignment pages printed `|round(2)` (`5.0`). | phase 2b, one formatter (`logic.format_quantity`, the `|qty` filter) on every count and weight |
| **M10** | both | **A visit's saved bill showed as an empty list.** The visit page draws its billed-items list at load, and drawing a saved line called `escapeHtml()` — defined at the END of `base.html`, after the page's own script ran. The script threw and the list stayed empty, so staff saw a billed visit as unbilled. Invisible to the JS-error sweep, which only opens visits without a bill. | phase 2d, `escapeHtml` moved into `<head>`; `test_browser.py::test_a_saved_bill_line_counts_up_as_a_number` |
| **M11** | both | **The sidebar highlighted almost no page.** `base.html` compared `request.endpoint` with bare names (`'visits_list'`), but a blueprint route's endpoint carries its prefix (`'clinical.visits_list'`), so since the routes moved into blueprints only the few pages left in `app.py` were ever highlighted. | `nav_active()` takes full endpoint names and raises on an unknown one, so a missing prefix fails every page render in the tests; `tests/test_nav_active.py` |

