# 0006 — The `vcs/` package: a factory, blueprints, domain modules

## Context

The merge started from a flat tree: `app.py` (the app, its config, its hooks,
its error handlers and a dozen routes), `routes/`, and a 2,800-line
`logic.py`. The owner chose a full restructure (decision D-15).

## Decision

- **No module-level app.** `vcs.create_app()` builds it
  (`vcs/web/factory.py`); `run.py` is the launcher. Importing the package
  loads `.env` first (`vcs/config.py`), so any module may read the environment
  at import time.
- **The request layer** is `vcs/web/`: `hooks.py`, `errors.py`,
  `templating.py`, and `core.py` (what the blueprints share). A blueprint
  never imports the factory that registers it.
- **The domain** is `vcs/domain/`, one module per area of the clinic. It
  imports nothing from Flask beyond flask_babel.
- **Module names are also good local names** — `billing`, `search`,
  `settings`, `refunds`. A function that assigns `billing = …` and calls
  `billing.…` raises UnboundLocalError on that path only. So a file never
  rebinds a domain module it imports. The Dashboard's and Insights' modules
  are `alerts` and `analytics` because `dashboard` and `insights` are view
  functions.
- **Tests find source through one helper**, `tests/source_files.py`, which
  asserts what it returns exists: a scan left pointing at a moved file passes
  having read nothing.

## Consequences

A move is one edit to `source_files.py`. Endpoint names carry the blueprint
prefix (`main.dashboard`, `reports.monthly`); a stale one raises `BuildError`
at the first render, not at the first click.

## Held by

`tests/test_domain_imports.py` (no rebinding; no Flask in the domain);
`tests/test_routes_smoke.py` (every page renders); `tests/source_files.py`'s
own assertions.
