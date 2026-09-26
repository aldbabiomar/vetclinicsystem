# 0002 — One clock, in the clinic's zone; the database session shares it

## Context

Event times were `TEXT` ISO strings compared lexically, "today" came from the
computer's clock, and SQL cast timestamps to dates in the server's zone. On a
machine whose zone differed from the clinic's, a sale near midnight landed on
the wrong day in one report and the right day in another.

## Decision

- Every "now" and "today" comes from `vcs/clock.py`: the Time Zone setting,
  else the money setting's zone, else the computer's. Nothing calls
  `datetime.now()` or `date.today()`.
- Event times are `timestamptz`.
- Each request puts its pooled database connection in the same zone
  (`clock.apply_to()`, from `vcs/web/hooks.py`), so a `::date` in SQL and
  `clock.today()` in Python name the same day.
- The clock, like the money setting, is a context variable copied into
  background jobs and scheduler runs.

## Consequences

A report's month and a list's day agree however the machine is configured.
A new query that needs "today" either takes it from `clock.today()` as a
parameter or relies on the session zone — never on `now()` in a zone nobody
chose.

## Held by

`tests/test_clock.py`, which also scans the whole package for
`datetime.now(` and `date.today(`.
