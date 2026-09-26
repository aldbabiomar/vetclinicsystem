# 0009 — A guard test is proven by reintroducing its bug

## Context

Tests in this codebase have repeatedly passed while checking nothing: a
request refused for an unrelated reason before it reached the guard; a
"mutation" edited into a comment; a scan left pointing at a file that had
moved; a check skipping on a misspelt column. Both predecessor suites were
green through every finding in the audit.

## Decision

- After adding a guard, **reintroduce the bug it protects against and see the
  suite fail**, then put the fix back. `scripts/simulation/prove_*.py` do this
  systematically.
- Pair every guard with a **control**: the valid case succeeds. Without it,
  "refused for the right reason" and "refused for any reason" look the same.
- A test that scans source takes its files from `tests/source_files.py` and
  asserts a **floor** on how much it inspected. A scan that finds nothing
  passes hardest when it scanned nothing.
- Run the suite under **both** money settings, with the browser tier alive
  (`APP_URL` set, `pytest tests/test_browser.py --collect-only` shows its
  tests).

## Consequences

A guard costs a few minutes more to write. In return, a green suite means
something about the paths it covers — and `docs/SEAM_RULES.md` is the
checklist for a rule that must hold on paths it does not.

## Held by

`CLAUDE.md` §5.2 and the reviewers who read it. The progress log in
`plans/UNIFIED_CODEBASE_PLAN.md` records the mutation run for each guard.
