# VetClinicSystem — ground rules

This repository is **one** application: VetClinicSystem, a clinic management
system for veterinary clinics (patients, visits, inpatient, boarding,
appointments, POS, inventory, consignment, billing, refunds, cash register,
P&L, insights), running on one clinic computer and reached over the clinic
LAN. Repo: `aldbabiomar/vetclinicsystem`. Start sessions with **this folder**
as the working directory.

> **There is no IQ app and no JO app any more.** There is one system with a
> **money setting**: **IQ** (Iraqi dinar — whole dinars, cash rounded to the
> 250-dinar note) or **JO** (Jordanian dinar — three decimals, exact to the
> fils). An admin picks it in Settings before any money is recorded; it locks
> itself after the first money is recorded. The phone format follows it.
> Never write code that is "for IQ" or "for JO" — write it once, and let the
> money setting's values (§3) make the difference.

## 0. Status — the merge is IN PROGRESS

The code started (2026-09-25) as the predecessor **JO** app's tree, renamed.
It is being brought to the design in `docs/plans/UNIFIED_CODEBASE_PLAN.md`,
phase by phase; **that file's progress log is the source of truth for what is
done**, and `docs/CODE_AUDIT_2026-09-25.md` tracks every audit finding to where
it is fixed. Until the merge is complete, some things described below as the
design are not built yet — check the plan's log before assuming.

The project has **never been deployed**. There is no install to keep
compatible with, so a schema or behaviour change needs no migration path —
until the first release (1.0.0) is published, `migrations/0001_baseline.sql`
may be edited in place (then regenerate `tests/schema_snapshot.json` with
`scripts/schema_snapshot.py --write` and read the diff). After 1.0.0, only new
numbered migrations.

Decisions taken by the owner (do not re-ask; the plan records the reasoning):

| Decision | Choice |
|---|---|
| Money setting | Settings dropdown **IQ / JO**; locks after the first money is recorded; also sets phone format |
| Before it is chosen | Money screens stay locked until an admin chooses; phone fields accept only full international numbers |
| Record IDs | Numeric database IDs; staff see generated codes like `V-00123` |
| P&L | Computed live from stored bill totals; no summary table, no Rebuild button |
| Logo | A new neutral SVG mark, tinted by the palette; the dog illustrations stay on error pages |
| Palettes | 15: IQ's Vetzone and ChamPet, JO's crimson/navy, plus 12 new calm palettes, each light + dark, WCAG AA checked |
| Docs | Everything lives in this repo; the IQ/JO-era documents are in `docs/archive/` |
| Repo | Public (the in-app updater downloads releases without credentials) |
| First release | `1.0.0` |
| Also | Inpatient billing refuses the whole submission when a staff discount meets a non-discountable item; status badges do not wrap |

**If something comes up that needs a decision, ask the owner with options.**
They asked for that explicitly.

## 1. Layout

```
VetClinicSystem/                  ← repo root = this folder
├── CLAUDE.md                     ← this file
├── README.md, CHANGELOG.md, VERSION
├── app.py, core.py, logic.py, … the application (flat layout for now; the
├── routes/                         plan's §3.1 describes the target package)
├── templates/, static/, translations/
├── schema.py, migrations/       ← the schema: numbered SQL files, each applied once
│                                   (schema.py has the rules; tests/schema_snapshot.json pins the result)
├── tests/                        ← one suite; run it under BOTH money settings (§5)
├── scripts/
│   ├── isolated_test_env.sh      ← throwaway Postgres + venv + app, per money setting (§4)
│   ├── restore_drill.sh          ← proves a real backup restores
│   └── simulation/               ← drives the app as a real user: repro_*.py per finding,
│                                   hostile sweeps, the localization checkers
├── docs/                         ← see docs/README.md for the index
│   ├── plans/UNIFIED_CODEBASE_PLAN.md   ← the merge plan + progress log
│   ├── CODE_AUDIT_2026-09-25.md          ← findings, tracked to their fixes
│   ├── RELEASE_WORKFLOW.md, SEAM_RULES.md
│   ├── ARABIC_REVIEW.md          ← Arabic written without clinic review; confirm, then delete rows
│   ├── features/                 ← specs of built features (Clean Up, monitoring, rewards card)
│   └── archive/                  ← IQ/JO-era documents, cited by code comments
└── webapps/                      ← NOT tracked. The two predecessor apps' clones, kept as
                                    read-only reference while their features are ported.
                                    Never edit them; removed when the merge is done.
```

## 2. Where the code lives (current flat layout)

```
app.py      the Flask app, config, security headers, network allowlist, auth
            gate, error handlers, context processors, dashboard, reports and
            insights, /health, and the launcher.
core.py     the seam shared by app.py and the blueprints: get_db, VERSION,
            form parsing/validation (parse_money, clean_date, normalize_phone,
            the Bad* exceptions, MAX_* bounds), pagination.
routes/     six blueprints: settings, admin, consignment, inventory, sales, clinical.
logic.py    the queries and calculations.
```

1. **A blueprint must never import from `app.py`** — `app.py` registers them,
   so that is circular. Shared pieces go in `core.py`.
2. **`core.py` must be imported after `load_dotenv()`** — it reads the
   environment at import time.
3. **Endpoint names carry the blueprint prefix**: `url_for("settings.settings_page")`.
   A missed one raises `BuildError` at the first page load.

Two conventions enforced by tests:

1. **No inline `on*=` handlers.** `script-src` uses a per-request nonce, which
   does not authorise inline handlers — an `onclick=` is a button that silently
   does nothing. Use `data-vzh` + `VZ.bind()`, or `data-vz-act` + `VZ.action()`
   (`static/behaviors.js`, `tests/test_no_inline_handlers.py`).
2. **Inline `style=` only for server-computed values, or for an element a script
   reveals with `el.style.display = ''`** — clearing an inline style cannot
   unhide an element a *class* hides. `tests/test_inline_styles.py` is a ratchet.

**If you write a test that parses source text, read `routes/*.py` too**, and
assert a floor on how much it inspected — a scan that finds nothing passes
hardest when it scanned nothing.

## 3. The money setting — the one difference that matters

Money is `Decimal` in Python and `NUMERIC` in the database, **always**, under
both settings. Never `float` for money. The IQ and JO rules are the same rules
with different values:

| | IQ | JO |
|---|---|---|
| Currency | IQD, د.ع | JOD, د.أ |
| Decimal places | 0 | 3 |
| Smallest cash unit | 250 | 0.001 |
| Clean Up cap per bill | 1,000 | 1.000 |
| Phone | +964, 10 local digits | +962, 9 local digits |

Rounding a payable total to the cash unit, never letting a real bill round
down to free, giving change and refunds down to the cash unit, and warning
about an amount that cannot be paid in cash are **one** set of functions
parameterised by the cash unit. With JO's unit of 0.001 they change nothing,
which is JO's behaviour. All of it lives in `money.py` (phase 1, done); the
browser previews mirror it in `static/money.js`. Tests default to JO; mark a
test `@pytest.mark.money("IQ")` to run it under IQ.

Threshold constants are where money bugs hide: `balance <= 0.5` or
`abs(diff) < 1` mean "noise" in one currency and "real money" in the other.
Every tolerance goes through the money setting.

## 4. Isolated test environment — the only place to run the app

`scripts/isolated_test_env.sh {up|down|status} {iq|jo}` builds a throwaway
Postgres container (`vcs_test_iq` / `vcs_test_jo`), a venv
(`/tmp/vcs_test_venv_<m>`) and a running app (**5091** for iq, **5092** for jo;
DB ports 55491 / 55492) with admin `admin` / `Admin12345!` and one Retail item
`INV301`/`PL301`. The second argument is the **money setting** of the
throwaway clinic — same code, different setting, and both can run at once.
`down` refuses while the app's PID is alive or anything holds its port.

- **Kill by PORT, never by command pattern.** The app is launched with `exec`,
  so `pkill -f ".../python3 app.py"` matches nothing and leaves an old process
  serving code that predates your change — indistinguishable from a real pass.
  `scripts/isolated_test_env.sh restart iq|jo` kills by port and asserts the
  pid changed — use it after any code or catalogue change.
- **A loading shell is not the page.** `/insights`, `/retention` and the
  consignment overview answer with a placeholder that polls a job and then
  navigates. Wait for `.vz-progress-shell` to disappear before asserting.
- **Tear it down when done**: stop the app (by port), then `down`.

### This machine also runs the two predecessor apps — never touch them

The predecessor IQ and JO apps are **installed and in use on this machine**
(IQ: app 5050, Postgres container `vetclinicsystemiq_postgres` on 5432, data
`~/Downloads/vetclinicsystemiq-data`; JO: app 5051, `vetclinicsystemjo_postgres`
on 5433, `~/Downloads/vetclinicsystemjo-data`). They are not this project, and
nothing here may read-write them. Their databases run in the same Docker
Desktop as the test containers:

- **Never quit or restart Docker Desktop, and never run a Docker-wide command**
  (`docker stop $(docker ps -q)`, `docker system prune`, …). Only ever touch
  `vcs_test_*` containers. On 2026-09-25 quitting Docker after testing took the
  in-use JO install's database down for ten minutes.
- Before anything that could affect them, check
  `lsof -iTCP:5050 -iTCP:5051 -sTCP:LISTEN` and ask.

## 5. Tests — run under BOTH money settings, and trust them only as far as §5.2

```bash
scripts/isolated_test_env.sh up iq     # and/or: up jo
APP_URL=http://127.0.0.1:5091 \
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystem \
  /tmp/vcs_test_venv_iq/bin/python -m pytest tests/ -q
```

(5092 / 55492 / `/tmp/vcs_test_venv_jo` for jo.) A change is verified only
when the suite is green under **both**. `TEST_DATABASE_URL` is deliberately not
`DATABASE_URL`: the tests write and delete rows.

Baseline at the start of the merge (JO tree, renamed, jo setting):
**844 passed, 4 skipped**; the plan's progress log records each phase's run. The 4 skips are data- or feature-dependent (no
barcode seeded, no visit to export, no dated row, JO CSS not driving modal
opacity) and are tracked for removal in the plan. Re-measure; do not quote.

### 5.1 What gates "zero skips"

- `APP_URL` must be exported, or the browser tests skip.
- Don't judge a run started between 00:00 and ~01:05 — `test_scheduler_catchup.py`
  legitimately skips until today's 00:30 slot has passed.
- A tier can be dormant while reporting one innocuous skip: confirm the browser
  tier is alive with `pytest tests/test_browser.py --collect-only`.

### 5.2 A test that passes has not yet been shown to catch anything

**After adding any guard, reintroduce the bug it protects against and confirm
the suite fails** — then put the fix back. Pair every guard test with a
**control** asserting the valid case succeeds, or "refused for the right
reason" and "refused for any reason" look identical. Tests in this codebase
have repeatedly passed while checking nothing: refused for an unrelated
reason before reaching the guard, a payload rejected for a missing field
before the value under test was read, a "mutation" edited into a comment, a
check silently skipping on a wrong column name. `scripts/simulation/prove_*.py`
do this systematically.

And a green suite is evidence about the paths it covers, not about rules that
are supposed to hold across sibling paths: the suites of both predecessor apps
were green through every finding in `docs/CODE_AUDIT_2026-09-25.md`.
`docs/SEAM_RULES.md` is the checklist for a rule that must hold on several
surfaces.

### 5.3 Harness facts

- `TESTING=True` turns on `PROPAGATE_EXCEPTIONS`, which bypasses every
  `@app.errorhandler`; `conftest.py` forces it back off.
- pytest tears fixtures down in reverse setup order — clear child rows first
  or a foreign key aborts the transaction and every later teardown fails.
- Some guards are defence in depth (a unique index behind an app check); to
  prove the test, disable both layers.

## 6. Localization

English and Arabic; the language is a clinic setting. Before touching a
template, an `<option>` or the catalogue, read `docs/archive/COMPARISON.md`
§57–§62:

- An `<option>` must carry the stored constant in `value=`; translated text as
  the submitted value once stored `method='نقدًا'` and broke the cash register.
- Translated text inside `<script>` goes through `|tojson`.
- A message stored by a background job is stored as English + msgid + args and
  translated at render (§60.1).
- **Never accept `pybabel update` fuzzy matches** — they produced Arabic that
  looked reviewed and was nonsense. Flag uncertain translations to the owner;
  do not guess (`docs/archive/arabic/`).
- After editing `translations/ar/LC_MESSAGES/messages.po`, run
  `pybabel compile -d translations` — a test fails if the `.mo` is older.
- **Rewording an English string changes its msgid**, so it silently renders
  English under Arabic. `tests/test_catalogue.py` extracts every msgid the code
  uses and fails until each has Arabic; it also refuses a translation that is
  one sentence repeated, a dropped placeholder and any fuzzy entry. Arabic you
  write yourself goes into `docs/ARABIC_REVIEW.md` for the clinic to confirm.
- PDFs stay English with the Latin currency code, permanently.

## 7. Releases

`docs/RELEASE_WORKFLOW.md`. The in-app updater depends on its exact
tag/VERSION/CHANGELOG format. Nothing is released until the merge is complete
and verified under both money settings.
