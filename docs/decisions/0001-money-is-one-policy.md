# 0001 — Money is `Decimal`, and one policy parameterised by the money setting

## Context

The two predecessor apps handled money differently: IQ rounded payable totals
to the 250-dinar note with floats in places; JO kept three decimals exactly.
Most of the bugs the audit found in money were not in either rule but in the
copies of them — a tolerance written as `balance <= 0.5` is noise in dinars
and real money in fils, and it had been copied between the two.

## Decision

- Money is `Decimal` in Python and `NUMERIC` in the database, under both
  settings. Never `float`; JSON is the one place a `Decimal` becomes a float,
  on its way out to the browser for display (`vcs/web/factory.py`).
- Every money rule lives in `vcs/money.py` as **one** function parameterised
  by the active setting's cash unit: rounding a payable total
  (`payable()`, never rounding a real bill down to free), change and refunds
  (`change_due()`, `refund_payout()`), what counts as settled (`is_settled()`),
  and whether an amount can be paid in cash. With JO's unit of 0.001 they
  change nothing, which is JO's behaviour.
- A tolerance is never a literal; it comes from the setting.
- The payable total is rounded once, on the whole bill, never per line.
  Clean Up is applied after that rounding and capped by the setting.
- The browser's live previews mirror the same functions (`static/money.js`),
  so what the cashier sees is what the server stores.

## Consequences

Adding a currency is a new setting's values, not new code. The price is
discipline at every boundary: `core.parse_money()` is the only way a form
value becomes money, and a new money column needs a `NUMERIC` type and a CHECK
that refuses NaN.

## Held by

`tests/test_money.py` (JO) and `tests/test_money_iq.py` (IQ);
`test_cleanup_cap.py`; seam rules 5–8 (the discount paths,
`tests/test_seam_rules.py`); `test_quantities.py::test_every_numeric_column_refuses_nan`.
Run the suite under both settings (`CLAUDE.md` §5).
