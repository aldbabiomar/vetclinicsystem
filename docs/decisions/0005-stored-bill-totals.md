# 0005 — Bills store their total; `bill_changed()` keeps it right; reports read it

## Context

Each bill's payable total — after its discount, the cash-unit rounding and
Clean Up — is computed by one function (`billing.compute_bill_totals()`). The
predecessor apps also kept a monthly summary table, refreshed by hand at about
thirty call sites; three forgot (audit B2), JO's Insights re-derived revenue
from lines instead (B3), and a Rebuild button could erase a concurrent sale
(B14).

## Decision

- **No summary table** (owner decision D-3). The P&L and Insights compute on
  read from the stored bill totals (`vcs/domain/reports.py`): one query for
  every revenue line, which every report sums, so two reports cannot
  disagree about a month.
- **Each bill stores its total**: `billing.total`, `inpatient_cases.total`,
  `boarding_sessions.billed_total`. Reports read those, never re-derive them.
- **One entry point keeps them right**: `billing.bill_changed(db, kind, id)`,
  called in the same transaction as any change to a bill's lines, manual
  amount, discount or Clean Up (audit D2). Payments change what is owed,
  never the total.

## Consequences

A new way to change a bill has one thing to remember, and a test that
reminds it.

## Held by

Seam rule 12 (`tests/test_seam_rules.py`): every function in the blueprints
or the domain that writes a bill's inputs calls `bill_changed()`.
`tests/test_reports_live.py` checks the reports against the stored totals.
