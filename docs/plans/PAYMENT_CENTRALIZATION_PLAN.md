# Plan — one payment function

**Written 2026-10-02. Status: NOT STARTED.**
The owner's decisions are in §1.1 (taken 2026-10-02). Progress goes in the
log, §12.

Visit, inpatient and boarding payments are three routes that each carry
their own copy of the same sequence. This plan moves that sequence into one
function, makes POS use the same checks, fixes one bug the copies had
drifted into, and adds two things the owner asked for on the way: double-click
protection and cash received / change on bill payments.

This plan is written to be handed to a different Claude session. Read first:

1. `CLAUDE.md` — the money setting (§3), the isolated test environment and
   the predecessor installs you must never touch (§4), tests under **both**
   money settings and proving every guard (§5), localization (§6).
2. `docs/SEAM_RULES.md` — this plan exists because of what that document
   describes. Its §5 checklist applies to every step here.
3. `docs/decisions/0003` (helpers do not commit), `0005` (`bill_changed`),
   `0011` (localization).

Code is cited by **symbol and file**. Line numbers are as of 2026-10-02 and
will drift; grep the symbol.

---

## 0. Preconditions

1. `git status` is clean, or you know whose work is uncommitted. On
   2026-10-02 another session had uncommitted template and stylesheet edits
   and both test environments in use. Do not start on top of that.
2. `git tag` shows no `1.0.0`. While it is unpublished, schema changes go
   into `vcs/db/migrations/0001_baseline.sql` in place (then
   `scripts/schema_snapshot.py --write`, and read the diff). If 1.0.0 has
   been published, §5's schema change becomes a new numbered migration; say
   so in the log.
3. The suite is green under both money settings before you change anything.
   Record the counts in the log; they are your baseline.

---

## 1. Decisions

### 1.1 Taken by the owner, 2026-10-02 — do not re-ask

| # | Question | Decision |
|---|---|---|
| **P-1** | Payment and Clean Up in one submission | **Boarding's rule everywhere**: the payment is checked against the balance *after* this submission's discount and Clean Up. Payment plus Clean Up can never exceed what is owed. This fixes a bug on visits and inpatient (§2.2). |
| **P-2** | Where a staff discount is taken | **Unchanged.** Boarding keeps taking it inside the payment form; visits and inpatient keep their separate Discount step. The shared function accepts an optional discount that only boarding passes. No screen changes for this. |
| **P-3** | Double-click protection | **Add it to all three bill payments**, with the same one-time token POS uses. |
| **P-4** | POS | **Share the checks, not the flow.** Visits, inpatient and boarding call one payment function. POS keeps its own checkout but uses the same shared functions for the method, discount, Clean Up and cash rules. |
| **P-5** | Cash received and change on bill payments | **Add it.** The three payment forms get a Cash Received field and show the change, as POS does. |
| **P-6** | The "not a multiple of the cash note" warning | **Only when the method is Cash.** Card and Transfer payments of an odd amount no longer warn about notes. |

### 1.2 Defaults chosen by the plan's author — override before starting if wrong

| # | Default | Why |
|---|---|---|
| A1 | The function lives in a new `vcs/domain/payments.py`. | The merge plan (§3.1, §5.2) named it; `vcs/domain/` is where rules live. |
| A2 | Parsing request text into numbers stays in the routes (`parse_money`, `parse_percent`, `clean_payment_method`). The function takes `Decimal`s and a cleaned method. | Seam rule 10 already requires every method read from the request to go through `core.clean_payment_method()`; the domain layer does not touch `request`. |
| A3 | An empty amount says "Payment amount must be a valid number." on all three. | Visits and inpatient say that today; boarding says "must be greater than 0". One message. |
| A4 | Cash Received is **optional**, as at POS. Left blank, nothing about cash is stored. | Matches `_cash_payment_for()` today; forcing it would slow the front desk. |
| A5 | A repeated submission (same token) writes nothing and returns the person to the bill with "That payment was already recorded." | POS sends a repeat to the existing receipt; a bill payment has no receipt page. |
| A6 | The cash-register **payout** keeps its warning unchanged. | `core.flash_cash_denomination_warning()` has four callers: the three bill payments and the payout. A payout is always cash, so P-6 does not change it. Refunds and POS do not call it. |
| A7 | PDFs are not changed. | No bill PDF lists individual payments today. |
| A8 | Out of scope: refunds as a shared function, distributor bill payments, consignment settlements. | They pay money *out* or to suppliers, with different rules. `record_refund()` is a sensible later plan. |
| A9 | Each route keeps its own "not found" redirect and its own redisplay. | The three pages are shaped differently (two detail pages, one list with a modal). Only the rules move. |

---

## 2. What exists today (read 2026-10-02)

### 2.1 Three copies of one sequence

`visit_payment_add`, `inpatient_payment_add` and `boarding_payment` in
`vcs/web/blueprints/clinical.py` (70, 70 and 107 lines). Each one:

1. locks the bill's row (`FOR UPDATE`);
2. parses the amount and refuses zero or less;
3. reads the bill's summary;
4. checks the Clean Up (`core.cleanup_amount_error`);
5. refuses more than the balance;
6. cleans the payment method (`core.clean_payment_method`);
7. inserts into `payments` and writes the change log;
8. adds the Clean Up to the bill, logs it, and calls
   `billing.bill_changed()`;
9. commits, flashes, warns about cash notes.

Boarding also takes a staff discount in the same submission, with the
rewards-card rule (a member's rate cannot be changed) and the role's
discount cap.

POS (`pos_checkout` in `vcs/web/blueprints/sales.py`) does the method,
discount, member, Clean Up and cash steps for a sale, plus its own
`_cash_payment_for()` and an idempotency token.

### 2.2 Where the copies disagree

| # | Difference | Visits / inpatient | Boarding | Decision |
|---|---|---|---|---|
| 1 | **Payment checked against which balance?** | the balance **before** this submission's Clean Up | the balance **after** its discount and Clean Up | P-1: boarding's |
| 2 | Empty amount | "must be a valid number" | "must be greater than 0" | A3 |
| 3 | Staff discount at payment | no (separate step) | yes | P-2: keep |
| 4 | Who is recorded as the user | `session["user_id"]` | `session.get("user_id")` | one way: the caller passes it |
| 5 | Double-submit protection | none | none (POS has it) | P-3 |
| 6 | Cash received and change | not recorded | not recorded (POS records them) | P-5 |
| 7 | Cash-note warning | fires for every method | fires for every method | P-6 |

**Difference 1 is a bug.** Replayed on 2026-10-02 with the app's own
`billing.compute_bill_totals()` and the routes' own checks, under IQ: a bill
of 10,000, a payment of 10,000 and a Clean Up of 1,000 in one submission.
The visit/inpatient checks accept it (the payment is within the old balance,
the Clean Up is within the cap and the old balance). The bill then stands at
9,000 with 10,000 paid: **overpaid by 1,000**, and there is no route to
delete a payment. Boarding's checks refuse the same submission. It was
replayed through the functions, not through HTTP; reproduce it through the
route in phase 1 before fixing it.

---

## 3. The design

### 3.1 `vcs/domain/payments.py`

```python
class PaymentRefused(Exception):
    """Carries a messages.Msg the route shows with core.flash()."""

class BillNotFound(PaymentRefused): ...

@dataclass(frozen=True)
class Recorded:
    payment_id: int
    duplicate: bool            # True: this token was already recorded; nothing was written
    change_given: Decimal | None
    warn_cash_note: bool       # P-6: Cash, and not payable exactly in notes

def record_payment(db, kind, bill_id, *, amount, method, user_id,
                   cleanup_amount=Decimal(0), notes=None,
                   cash_received=None, idempotency_key=None,
                   staff_discount=None, discount_cap=None) -> Recorded: ...
```

- `kind` is `"visit"`, `"inpatient"` or `"boarding"`. Everything that
  differs per kind is **data in one table** inside this module: the bill's
  table, the `payments` column that points at it, its summary function
  (`billing.visit_billing_summary` and its two siblings), its "not found"
  message and its "more than the remaining balance on this visit / case /
  stay" message. No `if kind ==` scattered through the function.
- `staff_discount` is passed **only by boarding** (P-2). `None` means "this
  submission does not touch the discount".
- It **does not commit** (`docs/decisions/0003`,
  `tests/test_no_hidden_commits.py`). The route commits once.
- It does not import Flask and does not read `request` or `session`: the
  route passes `user_id` and the role's `discount_cap`. It may call
  `auth.log_change()`, as other domain modules already do.
- Errors are `messages.Msg` values (English plus msgid and arguments), so
  the route shows them in the clinic's language with `core.flash()`.

### 3.2 The order of steps — fixed, and the same for every kind

1. **Lock** the bill's row `FOR UPDATE`. Missing: `BillNotFound`.
2. **Repeat?** If `idempotency_key` is set and a payment with it exists,
   return `Recorded(duplicate=True)` and write nothing. This runs *after*
   the lock, so two identical submissions queue behind each other and the
   second one sees the first. The unique index (§5) is the guarantee behind
   it.
3. **Amount** must be greater than zero.
4. **Summary** of the bill.
5. **Discount** (only when `staff_discount` is not `None`): on a
   rewards-card bill the rate cannot be changed; otherwise it must be within
   `discount_cap`. Uses the shared `discount_error()` (§3.3).
6. **Clean Up**, checked against the balance as this submission's discount
   would leave it (`cleanup_error()`, §3.3).
7. **Payment**, checked against the balance as this submission's discount
   **and Clean Up** would leave it (P-1).
8. **Method** must be one of the payment constants (the route already
   cleaned it; assert it here so a future caller cannot skip that).
9. **Cash** (`cash_tendered()`, §3.3): for Cash with an amount received,
   the received amount must cover the payment, and the change is
   `money.change_due(received, amount)`. Otherwise both stay `NULL`.
10. **Write**: the payment row and its change-log entry; the discount, if
    it changed, with its entry; the Clean Up, if any, with its entry.
11. **`billing.bill_changed(db, kind, bill_id)`** when the discount or the
    Clean Up changed (seam rule 12).
12. Return `Recorded`, with `warn_cash_note` set only for Cash (P-6).

### 3.3 The shared checks — one implementation each, used by POS too (P-4)

Move these out of the request layer into `vcs/domain/payments.py`, each
returning a `Msg` or `None`. POS and `record_payment()` both call them.

| Today | Becomes | Callers after this plan |
|---|---|---|
| `core.cleanup_amount_error()` | `payments.cleanup_error(new, existing, balance)` | `record_payment`, `pos_checkout` |
| `core.discount_percent_error()` | `payments.discount_error(percent, cap)` | `record_payment`, `pos_checkout`, `visit_discount_save`, `inpatient_discount_save` |
| `sales._cash_payment_for()` | `payments.cash_tendered(method, received, due)` | `record_payment`, `pos_checkout` |
| `core.flash_cash_denomination_warning(amount)` | stays in `core` (it flashes); the three payment routes call it only when `Recorded.warn_cash_note` is set (P-6) | the three payment routes, the cash-register payout (unchanged, A6) |

Delete the old functions rather than leaving wrappers behind: a wrapper is a
second place for a rule to live. The "cash received is less than the total"
message is worded for a sale today ("before completing the sale"); give it
wording that fits both a sale and a payment, or two msgids chosen by the
caller. That is a new Arabic string (§7).

### 3.4 The routes afterwards

Each route keeps only what is about its page:

```python
def visit_payment_add(visit_id):
    f = request.form
    try:
        amount = parse_money(f.get("amount"), required=True)
        cleanup = parse_money(f.get("cleanup_amount")) or 0
        received = parse_money(f.get("cash_received"))
        method = clean_payment_method(f.get("method"))
    except (BadNumber, BadPaymentMethod) as e:
        ...flash the field's message, redisplay
    try:
        done = payments.record_payment(
            db, "visit", visit_id, amount=amount, method=method,
            user_id=session["user_id"], cleanup_amount=cleanup,
            notes=f.get("notes"), cash_received=received,
            idempotency_key=f.get("idempotency_key") or None)
    except payments.BillNotFound as e: ...flash, redirect to the list
    except payments.PaymentRefused as e: ...flash, redisplay
    db.commit()
    ...flash "Payment recorded." (or A5's message when done.duplicate),
       the change when there is some, the cash-note warning when set
```

Keep each field's own parse message ("Payment amount…", "Clean Up amount…",
"Cash Received…"); do not collapse them into one.

---

## 4. Build order

Do it in this order. Each phase ends with the suite green under **both**
money settings and an entry in §12. The point of the order is that the move
(phase 2) changes **no behaviour**, so if a test fails there, the move is
wrong.

| Phase | Work |
|---|---|
| **1. Pin what exists** | A table-driven test file (§6.1) that runs every rule against all three kinds through the real routes. Where the kinds disagree today (§2.2), the test records today's behaviour and is marked as about to change. Reproduce §2.2's overpayment through the visit and inpatient routes and record it in the log. |
| **2. Move** | `vcs/domain/payments.py` with `record_payment()` and the shared checks; the three routes call it; behaviour **identical** to today, including the bug (keep the per-kind balance order behind one clearly named flag for this phase only). Phase 1's tests must pass untouched. |
| **3. Decide once** | Remove the flag: P-1 (one balance rule), A3 (one empty-amount message), P-6 (cash-only warning). Each is its own commit with its guard, its control and its mutation. Flip phase 1's "about to change" rows. |
| **4. POS shares the checks** | `pos_checkout` calls `payments.discount_error`, `cleanup_error`, `cash_tendered`; the two discount routes call `discount_error`; the old `core` and `sales` functions are deleted. |
| **5. Double-click protection** | §5's `idempotency_key`; the token in the three forms; step 2 of §3.2. |
| **6. Cash received and change** | §5's two columns; the form field, the live change preview and the payments list (§7). |
| **7. Rules and docs** | §8. |
| **8. Verification** | §9. |

---

## 5. Schema

In `payments` (baseline in place while 1.0.0 is unpublished, §0):

```sql
cash_received NUMERIC(15,3),
change_given  NUMERIC(15,3),
idempotency_key TEXT,
CHECK (cash_received IS NULL OR (cash_received >= 0 AND cash_received <> 'NaN')),
CHECK (change_given  IS NULL OR (change_given  >= 0 AND change_given  <> 'NaN')),
CHECK (cash_received IS NULL OR method = 'Cash'),
CHECK (cash_received IS NULL OR cash_received >= amount),

CREATE UNIQUE INDEX idx_payments_idempotency_key ON payments(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
```

These mirror `sales` (same types, same checks, same partial unique index).
The structural test that every `NUMERIC` column refuses NaN will fail until
the checks are there; that is the test doing its job. Regenerate
`tests/schema_snapshot.json` and read the diff.

---

## 6. Tests

Run everything in the isolated environment under both money settings
(`CLAUDE.md` §4–§5). Unmarked tests run under the run's money setting; mark
a test `@pytest.mark.money(...)` only when it asserts one setting's numbers
(the change rounded down to the 250-dinar note under IQ, exact under JO).

### 6.1 One table, every kind

`tests/test_payments_shared.py`, parametrised over `visit`, `inpatient`,
`boarding`, through the real routes. Each row is a guard with its control:

| Rule | Guard | Control |
|---|---|---|
| Missing bill | refused with the kind's own message; nothing written | — |
| Amount | zero, negative, empty, not a number: refused | a valid amount is recorded |
| Balance | more than is owed: refused | exactly what is owed: recorded, bill settled |
| **P-1** | pay in full **plus** a Clean Up: refused, nothing written | payment + Clean Up equal to the balance: recorded, balance zero |
| Clean Up cap | cumulative cap across two submissions: second refused | at the cap exactly: recorded |
| Method | anything outside the constants: refused | each constant recorded |
| **P-3** | same token twice: **one** payment row, second answers A5's message | a new token records a second payment |
| **P-5** | cash received below the payment: refused; received with Card: refused | received and change stored; blank received stores `NULL`s |
| **P-6** | Card or Transfer of an odd amount: no note warning | Cash of an odd amount: warning (IQ only; JO never warns) |
| Stored total | after a Clean Up, the stored total equals a fresh computation | — |
| Change log | a row for the payment, and one for each of discount and Clean Up when they changed | — |
| Boarding only (P-2) | discount above the role's cap refused; a member's rate cannot be changed | a discount within the cap is applied with the payment |

Also keep, and extend to all three kinds:
`tests/test_concurrency.py::test_two_simultaneous_payments_cannot_overpay_one_visit`,
and add "two simultaneous submissions with the same token record one
payment".

The seven test files that already post to these routes
(`test_concurrency`, `test_exports`, `test_license`, `test_money_routes`,
`test_money_routes_iq`, `test_reports_live`, `test_payment_methods`) must
pass in phase 2 **without edits**. If one needs editing in phase 3, it is
because it asserted a behaviour the owner changed; say which, in the log.

### 6.2 Seam rules

Add to `docs/SEAM_RULES.md` §3 and `tests/test_seam_rules.py`, taking files
from `tests/source_files.py` and asserting a floor on what was inspected:

- **Rule 17 — one writer of payments.** `INSERT INTO payments` appears only
  in `vcs/domain/payments.py`.
- **Rule 18 — one copy of each check.** No function outside
  `vcs/domain/payments.py` compares a Clean Up against a cap or a balance,
  or cash received against an amount due. (Assert the old names are gone
  and that `pos_checkout` calls the shared ones.)

Check that rules **1** (lock), **7** (discount source), **10** (payment
method) and **12** (`bill_changed`) still *find* the code after it moves
into `vcs/domain/`. A scan that no longer sees the function it was written
for passes. Their floors should rise or stay, never fall.

### 6.3 Prove every guard (`CLAUDE.md` §5.2)

Register each in `scripts/prove_guards.py` and run `--all` at the end (some
existing anchors will have moved with the code; re-anchor them, do not
delete them):

- check the payment against the balance *before* the Clean Up (P-1);
- drop the repeat lookup **and** the unique index (defence in depth: prove
  the test with both gone);
- warn about notes for every method (P-6);
- let Cash Received be less than the payment (P-5);
- add an `INSERT INTO payments` to a route (rule 17);
- give `pos_checkout` its own Clean Up check again (rule 18);
- remove `bill_changed()` from `record_payment()`.

### 6.4 Browser tier

The three payment forms, in both languages: the Cash Received field shows
for Cash and hides for Card and Transfer; the change preview matches what
the server stores; no console errors, no CSP violations.

---

## 7. Screens and words

- **Forms** (`visit_detail.html`, `inpatient_detail.html`, the payment modal
  in `boarding.html`): a hidden `idempotency_key`, generated per page render
  in the page's context builder and **kept** on a redisplay after an error,
  as `pos_checkout`'s `redisplay()` does; a Cash Received field shown only
  when the method is Cash; a live change preview.
- **No inline handlers**: `data-vzh` + `VZ.bind()`. An element a script
  shows or hides keeps its `display` inline, not in a class (`CLAUDE.md` §2).
- **The change preview** uses `VZMoney.changeDue` in `vcs/static/money.js`.
  Do not write a second rounding rule in a template.
- **Payments list** on the visit and inpatient pages: add "received … ·
  change …" when they were recorded.
- **Words**: reuse POS's existing msgids for "Cash Received" and "Change".
  New strings (the repeat message, the reworded "cash received is less
  than…") go through `_()`, get Arabic, and are listed in
  `docs/ARABIC_REVIEW.md` for the clinic. Never accept a fuzzy match;
  recompile the catalogue (`CLAUDE.md` §6).

One thing to know, not to change: under IQ the change is rounded **down** to
the 250-dinar note, as at POS. A cash payment of an amount that is not a
multiple of 250 therefore leaves the drawer slightly over. That is what the
cash-note warning tells staff, and why it stays for Cash.

---

## 8. Documentation

| File | What |
|---|---|
| `docs/decisions/0013-one-payment-function.md` (new) | the rule, the fixed order of steps (§3.2), why the checks are shared with POS, and the tests that hold it |
| `docs/SEAM_RULES.md` | rules 17 and 18; a register entry for §2.2's overpayment (a rule on boarding and not its siblings) |
| `docs/CODE_AUDIT_2026-09-25.md` §10 | the overpayment as a finding found after the audit, with where it was fixed |
| `CLAUDE.md` §2 conventions | "a payment is recorded only by `payments.record_payment()`" |
| `docs/README.md` | this plan's status |
| `docs/ARABIC_REVIEW.md` | the new strings |
| `CHANGELOG.md` | under 1.0.0 |

---

## 9. Verification and "done"

1. The suite is green under both money settings, with no unexplained skips
   and the browser tier alive.
2. `scripts/prove_guards.py --all` proves every guard, old and new.
3. `scripts/simulation/day.py` (a day in the clinic) passes under both
   settings, and `scripts/simulation/audit_repro.py` still refuses
   everything it refused before.
4. `grep -rn "INSERT INTO payments" vcs/` finds one place.
5. §2.2's overpayment is refused through the visit and the inpatient route.
6. The three routes in `clinical.py` are short: parse, call, show.

Report to the owner: what changed, the schema change, which existing tests
had to change and why, the suite counts under each setting, and anything in
§1.2 you would now choose differently.

---

## 10. What this plan does not do

- Refunds, distributor payments and consignment settlements (A8).
- A way to delete or edit a recorded payment.
- Any change to how discounts are taken (P-2), to PDFs (A7), or to what
  read-only mode allows (payment routes stay refused, and keep their
  endpoint names so the allowlist is untouched).

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| The move changes a behaviour nobody decided to change | phase 2 changes nothing and the existing tests must pass unedited (§6.1) |
| A seam-rule scan stops seeing the moved code and passes on nothing | check each rule's floor after the move (§6.2) |
| The shared function grows a flag per kind | per-kind differences are a data table (§3.1); the only optional input is boarding's discount |
| IQ and JO diverge | no money code outside `money.py`; the table runs under both settings |
| Guard anchors go stale as code moves | `prove_guards.py --all` at the end; re-anchor, never delete |

---

## 12. Progress log

Newest last. Each entry: what landed, how it was verified, the suite result
under each money setting.

### 2026-10-02 — preconditions and baseline

`git status` held only this plan and its line in `docs/README.md`; no
`1.0.0` tag; both test environments were down, so nobody else was using
them. Work is on the branch `payment-centralization`, not pushed.

Baseline, before any change: **1849 passed, 0 skipped** under IQ and under
JO (the browser tier ran in both).

### 2026-10-02 — phase 1: pin what exists

`tests/test_payments_shared.py`: every rule in §6.1 that exists today, run
against `visit`, `inpatient` and `boarding` through the real routes, each
guard beside its control. 135 tests, green under both settings against the
code as it stood.

Where the kinds disagree, the file records today's behaviour in three
constants headed ABOUT TO CHANGE: the empty-amount message (A3), whether a
payment of the whole balance plus a Clean Up is refused (P-1), and which
methods warn about notes (P-6).

**§2.2's overpayment, reproduced through the routes.**
`test_a_payment_plus_a_clean_up_cannot_exceed_what_is_owed[visit]` and
`[inpatient]` post a payment of the whole bill and a Clean Up at the cap in
one submission. Both routes answer "Payment recorded." Under IQ the bill
then stands at 99,000 with 100,000 paid; under JO at 99.000 with 100.000
paid. `[boarding]` refuses the same submission and writes nothing.

Two things the tests found that §2 does not list, both left as they are
for phase 2:

- A visit or inpatient payment that posts a `discount_percent` ignores it
  (pinned: `test_a_visit_or_inpatient_payment_takes_no_discount`). That is
  P-2, and the shared function must keep it.
- All three write the payment's `date` as today whatever the form says
  (audit B16), pinned for all three.

### 2026-10-02 — phase 2: the move

`vcs/domain/payments.py`: `record_payment()`, the table `KINDS`, and the
checks `discount_error()` and `cleanup_error()`. The three routes in
`clinical.py` parse, call it and show the answer (39, 39 and 49 lines, from
70, 70 and 107). The per-kind balance order is kept behind
`Kind.payment_checked_before_cleanup` — true for a visit and an inpatient
case, phase 3 removes it — so the overpayment is still there, on purpose.

**Phase 1's 135 tests pass unedited**, and so do the seven files §6.1 names.
Suite, on freshly reset databases: **1986 passed, 0 skipped** under IQ and
under JO (1849 + phase 1's 135 + seam rule 17 and its control).

What moved with it, and why:

- **The discount and Clean Up half of phase 4 was done here.**
  `core.discount_percent_error()` and `core.cleanup_amount_error()` are
  deleted; `pos_checkout` and the two discount routes call
  `payments.discount_error()` / `payments.cleanup_error()`. Leaving them
  for phase 4 would have meant two copies of each rule for two phases, and
  `test_cleanup_cap.py`'s "one copy, used by every surface" test fails the
  moment three of its call sites move. Phase 4 is left with
  `cash_tendered()` and rule 18.
- **A message a domain function returns is a `messages.Msg`**, so
  `messages` gained `Amount` and `Currency`: arguments the page formats as
  it formats every other amount (the money setting's format, the reader's
  digits, د.ع / د.أ under Arabic). `core.shown()` renders them. The msgids
  are the ones the routes used, so the catalogue did not change.
- **`billing.total_and_balance()`**, taken out of `compute_bill_totals()`:
  the last step of every bill (Clean Up off the payable total, then what is
  owed). `record_payment()` asks it what a Clean Up arriving with a payment
  would leave owed, using the bill's own `pre_cleanup_total`, so there is
  no second copy of the arithmetic and no re-rounding of an inpatient
  subtotal.
- **`core.PAYMENT_METHODS` is `payments.METHODS`**: the function refuses a
  method the route did not clean (`None` passes the column's CHECK).

Scans that had to be taught where the code went (§6.2) — each would
otherwise have passed by no longer seeing it:

- **Rule 1** (lock) reads `payments.py` too, knows `{spec.table}` and
  `{spec.bill_table}`, requires `record_payment` among the mutators by
  name, and checks `KINDS` locks `visits` / `inpatient_cases` /
  `boarding_sessions`. It had never covered boarding.
- **Rule 7** (discount source) counts `staff_discount` as a
  request-supplied discount and requires `record_payment` by name; its
  floor rose from 3 to 5.
- **Rule 12** (`bill_changed`) knows `{spec.bill_table}` and
  `cleanup_amount`. Its count floor went from 12 to 10 — three writers
  became one — and it now requires `record_payment` by name, which is the
  stricter floor.
- **Rule 10** (payment method) was unaffected: still 8 reads, one per route.
- **`test_edit_conflicts.py`'s `updated_at` rule** is not in §6.2's list,
  and its own floor caught the move (11 UPDATEs found, 12 required). It now
  reads `record_payment()`'s UPDATEs once per kind's table
  (`_payment_updates()`, with a floor of its own).
- **Rule 17** added: `INSERT INTO payments` appears once, in
  `record_payment()`.

Tests edited, and why: `test_cleanup_cap.py` and `test_money_iq.py` import
the check from its new home (assertions unchanged; the wiring test now
asserts `record_payment()` and `pos_checkout` call it and the message
exists once). Nothing else.

Behaviour that is not identical, all of it reachable only with a crafted
request or a submission with two faults at once:

- The routes parse the form before the function locks the bill, so when a
  submission has two faults, the one reported can differ (a bad method is
  now reported before an amount over the balance, for example). A missing
  bill is still reported as missing whatever else is wrong.
- Boarding, a stay that is **not** a member's, discount field **omitted**
  from the request: the stay's discount is left alone. It used to be read
  as 0 and so removed an existing discount. The form always sends the
  field (prefilled), so staff cannot reach this; it follows §3.1's
  "`None` means this submission does not touch the discount". A blank
  field is still 0, as before.

Proven by putting each bug back (`scripts/prove_guards.py`, 13 of 13): a
route with its own INSERT; the lock gone (rule 1, and the two-at-once tests
on every kind); `bill_changed()` gone (rule 12, and the stored totals and
reports); a member's rate changed; the role's cap unchecked; a visit
payment given a discount; the Clean Up unchecked; the cap not cumulative;
an uncleaned method; a payment dated otherwise; the `updated_at` scan blind
to the function.

### 2026-10-02 — phase 3: decide once

Three commits, each with its guard, its control and its mutation; the
three ABOUT TO CHANGE constants in `test_payments_shared.py` are gone.

- **P-1** — `Kind.payment_checked_before_cleanup` is removed. The Clean Up
  is checked against what is owed after the submission's discount, the
  payment against what is owed after its discount **and** its Clean Up.
  §2.2's submission (the whole bill plus a Clean Up at the cap) is now
  refused through the visit and the inpatient route, with "That's more than
  the remaining balance of 99,000 IQD on this visit", and nothing is
  written. Putting the old check back fails the test on all three kinds.
- **A3** — boarding's route parses the amount as required: an empty amount
  says "Payment amount must be a valid number." everywhere.
- **P-6** — `Recorded.warn_cash_note` is set only for Cash. The payout's
  warning is untouched (A6).

No existing test needed editing for any of the three: every test that paid
with a Clean Up paid the balance less the Clean Up, none posted an empty
boarding amount, and none asserted the warning.

Suite on reset databases: 1990 passed and 1 failed under each setting. The
failure was mine and in a test file — `test_domain_imports.py` refuses a
file that imports the domain module `payments` and also defines something
of that name, and `test_payments_shared.py`'s `Bill.payments()` did. The
module is imported there as `rules`. Both files re-run green under both
settings; the next full run is phase 4's.

### 2026-10-02 — phase 4: the point of sale shares the checks

`sales._cash_payment_for()` is `payments.cash_tendered(method, received,
due)`; `pos_checkout` calls it, as it has called `discount_error()` and
`cleanup_error()` since phase 2. The old function is deleted. Parsing the
typed figure stays in the request layer (A2): `core.parse_cash_received()`
reads the field only when the method is Cash, which is what the sale always
did, and is what the bill payments will use in phase 6. The message keeps
its sale wording until then.

**Seam rule 18**: the three old names appear nowhere; nothing outside
`money.py`, `payments.py` and `templating.py` reads the Clean Up cap or
calls `change_due()`; no comparison anywhere else names a Clean Up or cash
received; and `record_payment()`, `pos_checkout` and the two discount
routes call the shared checks. Its control shows the detector finds a
second copy written four ways and ignores five things that are not one.

Proven: `pos_checkout` given its own Clean Up check again (rule 18 and
`test_cleanup_cap.py` both fail); cash allowed to be less than what is due
(both POS underpayment tests fail).

Suite on reset databases: **1993 passed, 0 skipped** under IQ and under JO.

