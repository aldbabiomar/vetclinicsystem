# 0013 — One function records a payment; its checks are the point of sale's too

## Context

A visit, an inpatient case and a boarding stay each take payments, and each
had a route carrying its own copy of the same sequence: lock the bill, check
the amount, the Clean Up and the balance, clean the method, write the payment
and its change-log entry, store the bill's new total. The copies drifted
(`plans/PAYMENT_CENTRALIZATION_PLAN.md` §2.2). Boarding checked a payment
against the balance its own discount and Clean Up would leave; the other two
checked it against the balance before the Clean Up, so paying a bill in full
and writing a little off in the same submission was accepted and left the bill
**overpaid by the write-off**, with no route that takes a payment back. An
empty amount was answered two ways, and the cash-note warning fired for card
payments.

Each route had its own tests, and they were green: each tested its route
against its own behaviour (`SEAM_RULES.md` §1).

## Decision

**`payments.record_payment(db, kind, bill_id, …)` is the only writer of
`payments`.** `kind` is `"visit"`, `"inpatient"` or `"boarding"`; what differs
between them is data, in `payments.KINDS` — the row to lock, the column, where
the bill's discount and Clean Up are stored, its summary function and its two
messages. The function does not read the request or the session and does not
commit (0003): a route parses its form, passes what it parsed and who is
signed in, commits once, and shows the answer. A refusal is a `PaymentRefused`
carrying a `messages.Msg`, raised before anything is written.

**The order of steps is fixed, and the same for every kind:**

1. Lock the bill's row. Missing: `BillNotFound`.
2. A repeat? The form's one-time token is already on a payment of this bill:
   answer `Recorded(duplicate=True)` and write nothing. Asked after the lock,
   so of two identical submissions in flight the second waits and then finds
   the first. A unique index stands behind it.
3. The amount is more than zero.
4. Read the bill's summary.
5. Discount, only when the submission sets one (boarding's form): a
   rewards-card bill keeps its card's rate; otherwise within the role's cap.
6. Clean Up, against what is owed after this submission's discount.
7. Payment, against what is owed after its discount **and** its Clean Up.
8. The method is one of the three (the route cleaned it; `None` passes the
   column's CHECK).
9. Cash: what was handed over covers the payment; the change is rounded down
   to the cash unit. Nothing is stored for Card or Transfer.
10. Write: the payment and its change-log entry; the discount and the Clean
    Up, each with its entry, when they changed.
11. `billing.bill_changed()` when the discount or the Clean Up changed (0005).
12. Return `Recorded`: the change, and whether to warn that a **cash** amount
    is not in notes.

**The checks are plain functions, shared with the point of sale**:
`discount_error()`, `cleanup_error()`, `cash_tendered()`. A sale is not a
payment against a bill and keeps its own checkout, but its discount, its Clean
Up and its cash obey the same rules, and a rule with one copy cannot drift.
The two discount routes call `discount_error()` as well. Parsing request text
stays in the request layer (`core.parse_money`, `clean_payment_method`,
`parse_cash_received`).

**The token is stored with its bill** (`kind:id:token`). The boarding list has
one payment form for every stay on the page, so one page's token can arrive
for two stays; a repeat is the same form posted again for the same bill.

**Where a staff discount is taken did not change**: boarding takes it with the
payment, a visit and an inpatient case in their own step, which also refuses a
discount on a non-discountable line. A visit or inpatient payment that posts a
discount ignores it.

## Consequences

A rule about payments is written once, and a new kind of bill is a row in
`KINDS`. The cost is that the SQL names its tables from that row
(`UPDATE {spec.bill_table} …`), which a scan of string constants cannot see:
the scans that used to find this code in the routes — seam rules 1, 7 and 12
and the `updated_at` rule — were taught to read `payments.py` and each now
requires `record_payment` **by name**, so that losing sight of it fails.

When a submission has two faults at once, which one is reported can differ
from before the move: the routes parse the form before the function locks the
bill.

## Held by

- `tests/test_payments_shared.py` — every rule, run against all three kinds
  through the real routes, each guard beside its control; two submissions at
  once, for the lock and for the token.
- Seam rule 17 (`tests/test_seam_rules.py`): `INSERT INTO payments` appears
  once, in `record_payment()`. Rule 18: each check has one copy — the old names
  are gone, nothing else reads the Clean Up cap, works out change or compares
  a Clean Up or cash received, and the callers call the shared checks.
- `tests/test_cleanup_cap.py`; `tests/test_migrations.py` (the token's index
  and the cash checks are in the schema); `tests/test_browser.py` (the Cash
  Received field on the three forms, in English and Arabic, previews the
  change the server stores).
- `scripts/prove_guards.py`, under "one payment function": each of these
  fails when its bug is put back — including the repeat with **both** the
  lookup and the index gone.
