# Decisions

Why the code is the way it is, one decision per file. A comment in the code
states what must stay true; the reasoning, the history and the alternatives
that were turned down live here (audit D12). When a comment starts telling a
story — "this used to…", a finding number, a date — the story belongs in one
of these files and the comment can shrink to the rule and a pointer.

The owner's product decisions (the money setting, record codes, palettes,
the logo, the time zone setting, …) are in
[`plans/UNIFIED_CODEBASE_PLAN.md` §10](../plans/UNIFIED_CODEBASE_PLAN.md) and
the table in `CLAUDE.md`. These are the engineering ones.

Each record says what was decided, why, what it costs, and **which test holds
it** — a decision nothing checks is a decision the next change undoes.

| # | Decision | Held by |
|---|---|---|
| [0001](0001-money-is-one-policy.md) | Money is `Decimal`, and one policy parameterised by the money setting | `test_money*.py`, seam rules 5–8 |
| [0002](0002-clinic-clock.md) | One clock, in the clinic's zone; the database session shares it | `test_clock.py` |
| [0003](0003-one-transaction-per-request.md) | A request is one transaction; helpers do not commit | `test_no_hidden_commits.py`, `test_crud_routes.py`, `test_error_pages.py` |
| [0004](0004-native-placeholders.md) | SQL uses psycopg's own `%s` | `test_sql_placeholders.py` |
| [0005](0005-stored-bill-totals.md) | Bills store their total; `bill_changed()` keeps it right; reports read it | seam rule 12, `test_reports_live.py` |
| [0006](0006-package-layout.md) | The `vcs/` package: a factory, blueprints, domain modules | `test_domain_imports.py`, `tests/source_files.py` |
| [0007](0007-read-only-what-you-show.md) | What runs on every page reads only what it shows | `test_dashboard_snapshot_bounds.py`, `test_inventory_latest_state.py` |
| [0008](0008-scripts-under-a-nonce.md) | Scripts run under a CSP nonce: no inline handlers | `test_no_inline_handlers.py`, `test_inline_styles.py` |
| [0009](0009-a-guard-is-proven.md) | A guard test is proven by reintroducing its bug | `CLAUDE.md` §5.2, `scripts/simulation/prove_*.py` |

New record: the next number, a short imperative title, and the four
headings the others use.
