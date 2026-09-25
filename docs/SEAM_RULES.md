# Seam rules — rules that must hold on every sibling surface, not just one

**Written 2026-09-11** for the two predecessor apps (IQ and JO); **carried into
the merged VetClinicSystem**, where it applies unchanged: the siblings it talks
about (the four payment surfaces, the date filters, the discount routes) are
all still here, now in one codebase and under two money settings. Where it
says "each app" or "both apps", read "this codebase, under both money
settings". Its document citations resolve under `docs/archive/`.

This file exists because of a pattern, not a bug.

Of the six defects in `SIMULATION_AUDIT_2026-09-11.md`, **five had the same
shape**: a rule written into one code path and missing from the equivalent one
beside it. Nobody was careless — each surface was written correctly in
isolation, reviewed in isolation, and tested in isolation. The rule simply did
not propagate, and **a suite of 728/709 tests was green through every one of
them**, because the tests were organised the same way the code was: per
surface.

A follow-up audit the same day, looking specifically for this shape, found
three more. They are listed in §2.

> **The short version, if you read nothing else:** when you add or change a
> validation, locking, rounding or formatting rule, the question is never "is
> this route correct?" It is **"which other routes do the same job, and do they
> all now agree?"** `scripts/simulation/seam_audit.py` will list the siblings
> for you. `tests/test_seam_rules.py` enforces the eight rules whose
> absence has actually cost something (1-4) or would (5-8, the rewards card).

---

## 1. Why a green suite does not help here

This is the part worth internalising, because it is counter-intuitive.

A per-surface test suite tests each path against **its own** expectations.
If `pos_checkout` was written without the anti-"looks free" floor, its tests
were written to match — asserting the behaviour it has, not the behaviour its
sibling has. The suite is green and stays green. Coverage does not help
either: every one of these lines was covered. The line ran; it just ran the
wrong rule.

What actually catches this:

1. **Asking, when writing a rule, where else it applies.** The cheapest and
   most effective step, and the one this document exists to prompt.
2. **A cross-surface test** — one that walks *all* siblings and asserts the
   rule on each, rather than one test per surface. §3.
3. **Driving the app** (`scripts/simulation/`). Five of the six were found by
   use, not by reading. `COMPARISON.md` §21 made the same point in 2026-08.

---

## 2. The register — every seam bug found so far

| # | The rule | Where it lived | Where it was missing | Cost |
|---|---|---|---|---|
| F1 | anti-"looks free" floor on a payable total | `logic.compute_bill_totals` | `pos_checkout` | a sale under 125 IQD rang up **free**, and the till returned every dinar tendered |
| F2/F5 | `parse_money()` rejects non-finite/negative input | every other numeric entry point | `_save_audit_lines` | a `nan` stock count **disabled the oversell guard** (IQ) / **500'd the till** (JO) |
| F3 | a refund is never settled at zero | (neither retail nor service handled it) | both | goods returned, customer paid nothing |
| F6 | a stay cannot end before it begins | `boarding_edit` | `inpatient_edit` | negative-length stays in length-of-stay reporting |
| S1 | a bill mutation takes the parent row's lock | `visit_billing_save` | `visit_discount_save`, `inpatient_discount_save`, `inpatient_billing_add` | discounted bills carrying non-discountable lines, **plus 46 deadlock 500s** |
| S2 | a read-side date filter is validated | `/visits`, `/pos/history`, `/refunds`, `/cash-register` | `/admin/logs` | an **empty audit log** with no warning — reads as "nobody did anything" |
| S3 | (the same rule) | as above | `/consignment/sales` | a sales report silently narrowed to nothing |
| S4 | the served address is **derived**, never a literal | JO's `BIND_PORT`, a module-level constant exposed to templates | IQ read the port only inside `main()`; its dashboard and Settings hard-coded `:5050` | IQ told staff the wrong address on any other port — and the two installs collide on the defaults, which is why JO already runs on 5051 |
| S5 | an `<option>` carries the stored constant in `value=` | IQ's refunds, settlements and distributor payments | JO's same three forms, and 18 options in both apps whose translated text *was* the submitted value | in Arabic a visit payment stored `method='نقدًا'`; the cash register bucketed it as "other", so the **drawer count reported a surplus that was not real** |
| S6 | a long job reports through the shared progress component | JO's Backup and Restore, and IQ's Update | **JO's Update and Rollback** — they polled `job-status` by hand and wrote plain text | the LONGEST job in the app showed no bar, no fraction and no elapsed time while the app restarted under the admin watching it |
| S7 | "is this item discountable?" is answered from the price_list row the PRICE came from | `item_sale_price()` filters `active=true` | `non_discountable_line_names_for_items()` does not | latent only: an inactive linked row with a different `can_discount` would answer for a price it did not set. Found while building the rewards card (2026-09-19); `discountable_by_item_ids()` was written to match `item_sale_price()`, and the older function was deliberately LEFT as-is rather than changed underneath the staff-discount guard that depends on it. Written down here because a hole that is a decision is fine and a hole nobody looked at is not (§4). |

**S6 is the cheapest one to have avoided.** Nothing was missing: `progress.js`
ships in both apps, and JO already called `VZProgress.poll`/`render` for two of
its four long jobs — in the same file, a hundred lines from the code that did
not. The update path simply predated the component and was never brought
across, and nothing failed because each path was individually correct. It took
a user watching an update to notice, because a progress bar is only missing at
the one moment nobody is running tests.

**S5 is the one that shows what a seam is.** Nothing about it is a
localization bug in the usual sense — the translation was correct, the page
looked right, and the money was wrong. HTML's rule is that an `<option>`
without `value=` submits its own text; the app's rule is that `method` is one
of three English constants. Neither rule is written down anywhere the other
can see, and the two had never disagreed before because the text *was* the
constant. Translating the text broke a coupling nobody had named. The two
apps had drifted in opposite directions on the same seam — IQ had explicit
values where JO did not on three forms, and JO had them where IQ did not on
others — which is the signature of a rule applied by hand each time rather
than once. `tests/test_enum_labels.py` now refuses any `<option>` whose
translated text is its submitted value, and
`scripts/simulation/repro_option_value.py` walks it from the rendered page to
the wrong total.

**S1 is the one to study.** `visit_billing_save` took the visit row
`FOR UPDATE` and its comment said the lock was there *"so a concurrent discount
save on the same visit serialises behind this one."* That sentence was true
about its own side and false about the system: **a lock only serialises if both
sides take it**, and the discount route never did. Two guards written to
protect the same invariant were each validating against a snapshot the other
had already invalidated. Reproduced at 2/25 trials, alongside 46
`DeadlockDetected` 500s caused by the two paths taking locks in different
orders. JO had locked all four routes from the start and was clean at 0/25.

---

## 3. What is enforced automatically

`tests/test_seam_rules.py`, in **both** apps. **Eight** rules, each one derived
from a defect above rather than invented:

| Rule | Asserts | From |
|---|---|---|
| 1 | every function writing to `billing` / `visit_billing_lines` / `inpatient_billing`, or setting `discount_percent`, takes `FOR UPDATE` on its parent row | S1 |
| 2 | every route reading `?date=`/`?day=`/`?week=`/`?date_from=`/`?date_to=` validates it before use | F4, S2, S3 |
| 3 | no `float()` is applied to a value derived from `request.form`/`request.args` | F2/F5 |
| 4 | date arguments use `request.args.get(k) or default`, never `get(k, default)` | F4 |
| 5 | every `INSERT` into `visit_billing_lines` / `inpatient_billing` / `sale_items` names `discountable` | rewards card |
| 6 | every call to `compute_bill_totals()` passes `discountable_subtotal` (AST walk) | rewards card |
| 7 | every function writing a request-supplied `discount_percent` also reads `discount_source` | rewards card |
| 8 | discount-percentage arithmetic appears only at the allow-listed sites | rewards card |

**Rules 5-8 were added with the rewards card (2026-09-19), which is a seam
feature by construction: one new rule on four payment paths that were already
shaped differently from each other.** All four were verified by reintroducing
their bug — `scripts/simulation/prove_rewards_guards.py {iq|jo}` does this on
demand, and reported 9/9 in both apps.

**Rule 8 is worth reading as a lesson about scanning guards.** Its first draft
scanned line by line and its own floor assertion reported finding only 2 of
the 4 real sites — the P&L weighting reads the rate on one line and divides on
another, which no line-scoped regex can see. The floor is the only reason that
was caught rather than shipping as a guard that passed while checking half its
subject. It now scans per function, with comments stripped.

**Rule 4 is subtle enough to restate:** `request.args.get("day", today)` applies
the default only when the parameter is **absent**. A present-but-empty `?day=`
keeps the empty string — and `parse_date("")` *returns None rather than
raising*, so the route's own `except ValueError` never fired either. Two
independent near-misses in one line, which is how F4 shipped.

### Three things about these tests worth keeping

- **They discover their subject live** — `app.py` plus a glob over `routes/*.py`
  — and every one asserts a **floor** on how much it inspected. A "no matches"
  assertion passes hardest when it is scanning nothing, which is how four
  guards in this codebase came to pass while checking nothing
  (`COMPARISON.md` §51).
- **Rule 3 walks the AST, not the text, and the text version was proven
  blind.** F2 was written as `stock = request.form.get(...)` on one line and
  `float(stock)` a few lines later; a regex for `float(f.get(` sees nothing
  there. The first draft of Rule 3 was exactly that regex — it passed while
  F2 was reintroduced. It now tracks which locals came from the request and
  flags `float()` on any of them. **Caught by the guard's own mutation run**,
  which is the only reason it is not still blind.
- **Rule 3 deliberately excludes `int()`.** `int("nan")` raises, so `int()` is
  not the hazard `float()` is, and the four `int(f.get(...))` sites here are
  each wrapped in `try/except ValueError`. A rule that flagged them would cry
  wolf, and a guard nobody trusts gets deleted.

All four were verified by reintroducing their bug and watching the suite go
red — `CLAUDE.md` §7.3.

---

## 4. The exploratory tool, and its honest limits

`scripts/simulation/seam_audit.py` prints a matrix of **parallel surfaces ×
shared guards** and lists the holes. Run it when you add a rule, or when you
are about to touch one of the groups it knows about:

```bash
python3 scripts/simulation/seam_audit.py
```

It is a **candidate generator, not an oracle**, and it is worth knowing why it
cannot be one:

- Matching a guard by name in a function's text **under-reports**, because a
  guard delegated to a helper (as `pos_checkout`'s row lock is, after the M4
  extraction) looks absent.
- Inlining called helpers to fix that **over-reports the other way**: context
  builders drag in half the module's vocabulary, and almost every cell turns
  to "yes".

So it currently inlines one level and you should read its output as *"these
pairs are worth five minutes"*, never as a pass/fail. Its most useful column is
the split at the bottom: a hole present in **both** apps is usually a shared
design decision, while a hole in **one** app is far more often a genuine
divergence. S1 surfaced exactly that way — thirteen IQ-only holes, one of which
was real.

**If a hole is deliberate, write down why** — in the route, as a comment. The
value of this whole exercise is turning every hole into a decision someone
looked at.

---

## 5. The checklist, for when you are adding a rule

1. **Name the siblings.** Which other routes do the same job? The groups in
   `seam_audit.py` are a starting list, not a complete one — add to it.
2. **Decide for each sibling**, and write the decision down. "Not applicable
   because this form has no date field" is a fine answer; silence is not.
3. **Ask whether it belongs in one function instead.** F1's fix was
   `money.payable_total()` — one function both paths call — not a patched
   line. A rule that lives in exactly one place cannot drift.
4. **If it is a rule that has bitten before, add it to
   `tests/test_seam_rules.py`** as a cross-surface assertion.
5. **Tailor per app.** Identical code is not the goal, identical *rules* are —
   IQ's audit counts use `parse_money`, JO's use `parse_quantity`, because
   that is what each app's own cart parser uses. `CLAUDE.md` §1.
6. **Mutate it.** Reintroduce the bug and watch the suite go red before you
   believe the guard. Rule 3 above was blind on its first draft and only its
   mutation run said so.

---

## 6. Where the boundary is

Not every difference between two similar routes is a seam bug. Deliberate
divergence is documented in `COMPARISON.md` §18, and the money models in §1.1
mean some rules **must not** cross: IQ's 250-note rounding has no JO
equivalent, and JO's test suite carries a guard that fails twenty tests if it
is ever ported across. The question is not "is this code the same?" but **"is
this *rule* the same, and should it be?"**
