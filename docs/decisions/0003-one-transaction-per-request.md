# 0003 — A request is one transaction; helpers do not commit

## Context

A route that failed half-way used to leave half its writes behind: the
catch-all error handler swallowed the exception before teardown could see it,
so teardown committed (audit ORPHANED_RECORDS F-01). And some helpers
committed on their own (audit D11), splitting a request into two transactions
without the route knowing — the first half survived a failure that rolled back
the rest.

## Decision

- `close_db()` (`vcs/web/hooks.py`) commits once, at the end of a request that
  succeeded, and rolls back otherwise.
- An error handler calls `errors.mark_transaction_failed()` first. It marks
  the request failed and rolls back **now**, so the error page reads the
  clinic's language and name from a working connection (audit B12).
- Helpers in `vcs/domain` and the shared modules do not commit. The few that
  must say so in their docstring and are listed, with the reason, in
  `tests/test_no_hidden_commits.py`: batched log pruning, an attachment whose
  file and row stand or fall together, a sign-in attempt that must stay on
  record for the lockout, and install-time seeding.

## Consequences

A route can call any helper and still fail cleanly. A helper that needs its
own transaction has to be deliberate about it, and visible.

## Held by

`tests/test_no_hidden_commits.py`. A request refused after it had written
leaves nothing behind: `test_crud_routes.py::test_a_duplicate_microchip_is_refused_and_leaves_nothing_behind`
(the owner written before the refused patient is rolled back with it),
`test_money_routes.py::test_a_refused_checkout_leaves_stock_untouched`. The
error page after a database error is the clinic's own:
`test_error_pages.py::test_the_error_page_after_a_database_error_is_the_clinics_own`.
