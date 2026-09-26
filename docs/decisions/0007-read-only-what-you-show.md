# 0007 — What runs on every page reads only what it shows

## Context

The sidebar's Dashboard badge is computed on every page. It came from the
Dashboard's snapshot, which fetched every visit ever recorded to count the
active ones in Python, every pending follow-up, every wellness reminder ever
set, and every confirmed audit line of every item (audit D3). The cost grew
with the clinic's history on every click. The POS and the audit confirm
recomputed the whole catalogue's stock to answer for a few items (D4).

## Decision

The database narrows; the Python that decides stays the one definition.

- Counts are `COUNT(*)`.
- Lists are limited to the rows that can matter: today's and tomorrow's
  follow-ups; the wellness doses in a window one day wider than "due", so it
  can only let through more, and Python still decides what is due.
- An item's stock reads its **latest** confirmed audit, with the
  carried-forward threshold and usage rate worked out in SQL
  (`inventory.latest_audit_state()`), instead of replaying its whole history.
  `inventory_status(db, item_ids)` answers for the items asked about.

A second copy of a rule (a SQL count of "due" beside the Python one) was
turned down: the badge and the Dashboard would disagree the day they drift.

## Consequences

The per-page cost follows the clinic's current state, not its age.
`confirmed_audit_rows_by_item()` still walks the full history for the Audit
History page and the Ordering Sheet, and serves as the reference the SQL is
tested against.

## Held by

`tests/test_dashboard_snapshot_bounds.py` (the snapshot equals the unbounded
reads, across every date boundary); `tests/test_inventory_latest_state.py`
(the SQL equals the full-history walk: carried thresholds, backdated audits,
same-day audits, unstamped confirmations — and on the whole test database).
