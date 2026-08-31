# Working with VetClinicSystem_IQ and VetClinicSystem_JO together

This folder is the shared workspace for both apps. It exists so the ground
rules below are visible to **any** Claude Code session working here,
regardless of which account started it — read this file before touching
either app's code.

## Layout

```
VetClinicSystem/
├── CLAUDE.md              ← this file
├── COMPARISON.md          ← dated, structured diff between the two apps — re-read before porting anything
├── RELEASE_WORKFLOW.md    ← the release process, see §3
├── TRANSITION_NOTES.md    ← read once on a first session: what's in flight, what's stale
├── features/              ← feature plans: CLEANUP (built), MONITORING (unbuilt)
├── audits/                ← three standing audits, see below
├── scripts/
│   ├── isolated_test_env.sh   ← throwaway Postgres + venv for either app, see §5
│   └── restore_drill.sh       ← proves a real backup restores, see §6
└── webapps/
    ├── vetclinicsystem_iq-main/   ← git clone, aldbabiomar/vetclinicsystem_iq
    └── vetclinicsystem_jo-main/   ← git clone, aldbabiomar/vetclinicsystem_jo
```

Start sessions with **this folder** (`VetClinicSystem/`) as the working
directory, not directly inside `webapps/vetclinicsystem_iq-main/` or
`webapps/vetclinicsystem_jo-main/` — that's what guarantees this file and
`COMPARISON.md` actually load.

## 0. The `audits/` folder

Three long-lived audit documents live in `audits/`. Nothing else in this
folder pointed to them until 2026-08-26, so a fresh session had no way to
find them except by listing the directory:

| File | What it is | Status |
|---|---|---|
| `ERROR_500_AUDIT.md` (1,036 lines) | every action that could raise an unhandled exception | findings applied to both apps, 2026-08-24 |
| `ORPHANED_RECORDS_AUDIT.md` (1,414 lines) | every way a row could be left with no reachable parent | findings applied to both apps, 2026-08-24 |
| `IQ_JO_DIVERGENCE_AUDIT.md` (551 lines) | phased line-by-line diff of the two trees | **all closed** — 7.6, the last one, closed 2026-08-26 (`COMPARISON.md` §28) |

They are the reasoning behind a lot of existing defensive code — a guard that
looks unnecessary is usually one of these findings. Search them before
removing anything that looks redundant.

**One caveat worth carrying:** the divergence audit **missed a reproducible
500** that a five-minute test run later caught (`COMPARISON.md` §21). Reading
code is not the same as running it. Treat these as maps of where to look, not
as proof that an area is sound.

## 1. These are siblings, not twins

VetClinicSystem_IQ (Iraq) and VetClinicSystem_JO (Jordan) share a common
origin — JO was forked from IQ — but they've diverged on purpose in real,
load-bearing ways: different currency model (`float`/IQD-whole-numbers vs.
`Decimal`/JOD-3-decimal), different phone-number format, different frontend
conventions (IQ has a small JS framework — toasts, styled dialogs, a
background-job progress UI; JO uses native browser `confirm()`/`alert()`
and renders everything synchronously), and JO is missing several features
IQ has (custom role creation, backup restore, folder browser, multi-palette
theming). IQ is the more tested, more refined baseline; JO is not just "IQ
with a different clinic name."

**Both apps will keep changing concurrently from now on** — features added
or bugs fixed in one don't automatically apply to the other, and a fix that
looks identical on the surface can be structurally wrong once it crosses
into the other app's actual code (a `float` op that's safe in IQ can be a
`TypeError` or a silent precision bug in JO; a UI pattern from one has no
equivalent JS framework in the other). The goal every time is **a fix or
feature tailored to each app's own code**, not one implementation
copy-pasted into both.

## 2. Before porting anything — the checklist

Run through this every time a fix or feature might apply to both apps
(porting from one into the other, or building something new that touches
an area §1 calls out as diverged):

1. **Re-read `COMPARISON.md` first.** Don't assume it's still accurate —
   it's a snapshot, dated at the top. If either app has changed since that
   date in the relevant area, treat the doc as a starting point, not the
   final word, and update it once you're done (see §4).
2. **Diff the target function/route directly in the other app's actual
   current code.** Never assume "the surrounding code looks the same, so
   this must apply the same way" — verify by reading, the same discipline
   `PORTING_CHECKLIST.md`/`IQ_AUDIT_APPLICABILITY_REVIEW.md` used to apply
   (removed from JO's repo as stale planning docs, superseded by
   `COMPARISON.md`, which is what actually gets kept current now).
3. **Check for money/currency-type divergence before touching anything
   money-adjacent** — rounding, denomination logic, `float`/`Decimal`
   mixing, comparison thresholds (`balance <= 0.5`-style constants are the
   specific failure mode that's already bitten this codebase once, see
   `COMPARISON.md` §1.1).
4. **Replicate the bug live, in that app's own isolated test environment**
   (§5), before assuming it reproduces — don't fix from inspection alone
   just because it's "the same bug" in the other app.
5. **After fixing, re-verify live**, including a no-regression pass against
   each app's actual role/permission model (JO has only 3 fixed roles with
   broad defaults; IQ supports arbitrary custom roles — a fix that's safe
   for JO's roles isn't automatically safe for an IQ custom role with a
   narrower permission set).
6. **Tear down the test environment** when done (§5) — never leave a
   throwaway container/venv running, and never touch either app's real dev
   database while testing.

## 3. Release process

Both apps follow the same tag/release checklist, in `RELEASE_WORKFLOW.md`
in this folder — read it before publishing anything. It supersedes the
original source docs (`CLAUDE_CODE_RELEASE_WORKFLOW.md`,
`UPDATE_MECHANISM_PLAN.md`) that used to live at `/Users/omaraldbabi/Desktop/
Updater - Include in Claude Code Session/`; those were IQ-only drafts
written before the update mechanism was actually built — both apps now
have it live (`updater.py`, `/health`, a real `VERSION`/`CHANGELOG.md`),
so `RELEASE_WORKFLOW.md` is the current, app-agnostic version of record.
Don't skip its checklist for a plain `git commit`+`push` — the in-app
updater in both apps depends on the exact tag/CHANGELOG format it defines.

Each app keeps its own `VERSION`/`CHANGELOG.md` and is versioned
independently — a fix landing in both isn't required to bump both to the
same number. Confirm `git remote -v` matches the right repo
(`aldbabiomar/vetclinicsystem_iq` / `aldbabiomar/vetclinicsystem_jo`)
before the first push of a session in either.

## 4. Keeping `COMPARISON.md` current

It's a snapshot, not a living rulebook — it will drift the moment either
app changes in a way that touches a module it describes. When you finish
work that changes how the two apps compare in some area (a feature added
to only one, a fix that closes a gap `COMPARISON.md` names, a new
divergence introduced on purpose), **append a dated note to the relevant
section** rather than leaving the doc silently stale. Don't rewrite
history in it — add to it, the same way each app's own `CHANGELOG.md`
only ever gets new entries at the top.

## 5. Isolated test environment

**Both apps now have real test suites — run them before and after any
change.** See §7. `scripts/isolated_test_env.sh {up|down|status} {iq|jo}` spins up a
throwaway Postgres container + Python venv for whichever app you name —
schema applied, an admin user (`admin` / `Admin12345!`) and one Retail test
item (`INV301`/`PL301`) seeded, app running on a fixed port (5091 for IQ,
5092 for JO — both can run at once without colliding). Never points at
either app's real dev database or Docker container. `up` prints the PID to
kill when you're done testing; `down` won't proceed while that process is
still running, and removes the container/venv/data dir together. This is
the only sanctioned way to replicate a bug or verify a fix live — never
test against a real install.

## 6. Restore drill — run it monthly

`scripts/restore_drill.sh {iq|jo} [path/to/file.dump]` takes a **real**
backup, restores it into a throwaway Postgres container, and checks what
came back: schema and foreign keys present, core tables actually
populated, at least one user account, no orphaned parent/child rows, the
money column restored as the right type (`numeric` for JO, `double
precision` for IQ, with IQ additionally checking every non-zero bill is a
whole multiple of 250), and the app able to connect and query it. Exits 0
on pass, 1 on fail, and always removes the container — including on
Ctrl-C. It only ever *reads* the backup file and never touches either
app's real database.

With no path it picks the newest `.dump` it can find for that app —
`~/Downloads/vetclinicsystem{iq,jo}-data/backups/` and `~/Desktop/backups/`.
Both apps have a real backup there and both currently pass.

**Why it exists:** both apps back up diligently — nightly, before every
in-app update, on shutdown — and none of that is worth anything until a
backup has actually been restored. A truncated or empty dump looks
exactly like a good one on disk: same name, plausible size, listed
happily in Settings.

The drill was validated against deliberately broken backups: a truncated
file, a correctly-sized file of random bytes, and — the important one — a
*structurally perfect* archive containing no rows, which restores
cleanly, keeps all 78 foreign keys and lets the app boot. All three fail
the drill. A check that silently skips is treated as a failure for the
same reason.

Run it **once a month**, and any time backup behaviour changes. Record
the result; a passing drill is only evidence about the backup it read.

## 7. The test suites — run these, and trust them only as far as §7.3

Both apps went from 5-6 tests to **370+ (IQ) / 350+ (JO)** on 2026-08-25/26,
covering roughly 68% of the code. Sixteen test files each. They found eleven
real bugs, several of which had shipped.

### 7.1 Three tiers, by what they need

| Tier | Files | Needs | Runtime |
|---|---|---|---|
| **Pure** | `test_money.py`, `test_frontend.py`, `test_desktop_shortcut_target.py`, `test_migrations.py`'s static guard | nothing | < 1s |
| **Database** | `test_money_routes.py`, `test_crud_routes.py`, `test_workflow_routes.py`, `test_admin_routes.py`, `test_supplier_routes.py`, `test_edit_routes.py`, `test_exports.py`, `test_permissions.py`, `test_routes_smoke.py`, `test_backup.py`, `test_migrations.py`, `test_concurrency.py` | a throwaway Postgres | ~12s |
| **Browser** | `test_browser.py` | Playwright + a running app | ~2min |

Every tier **skips cleanly** when its requirement is absent, so
`venv/bin/python -m pytest tests/ -q` always works and never fails for
environmental reasons.

**But the skip count does not tell you a tier is dormant.** `test_browser.py`
gates on `pytest.importorskip` at module scope: with Playwright missing it
collects **zero** tests and reports as **`1 skipped`**, not 13. IQ's browser
tier had never run for exactly this reason, and the single innocuous skip hid
it — while JO reported 13 skips for the identical dormant tier, because
Playwright happened to be installed there. **Confirm a tier is alive by
collecting it (`pytest tests/test_browser.py --collect-only`), not by reading
totals.** `scripts/isolated_test_env.sh up` now installs pytest and Playwright
into the throwaway venv so both tiers run; see `COMPARISON.md` §40.3.

To run the database tier:

```bash
scripts/isolated_test_env.sh up iq
cd webapps/vetclinicsystem_iq-main
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystemiq \
  venv/bin/python -m pytest tests/ -q
```

(55492 / `vetclinicsystemjo` for JO.) `TEST_DATABASE_URL` is deliberately a
separate variable from `DATABASE_URL` — these tests write and delete rows, and
must never be pointed at a real install by an exported shell variable.

Browser tier: see each app's README. Playwright is **test-only and not in
`requirements.txt`** — the apps have no build step and no browser dependency,
and that property is worth more than making these run by default.

### 7.2 The two apps' test files are NOT copies

`test_money.py` and `test_money_routes.py` assert deliberately **opposite**
things, per `COMPARISON.md` §1.1. IQ asserts a 100-unit subtotal becomes 250
(the anti-"looks free" floor); JO asserts 0.100 stays 0.100. JO carries a
guard that fails 20 tests if IQ's 250-rounding is ever ported across. Adapt,
never copy.

### 7.3 A test that passes has not yet been shown to catch anything

This is the single most useful lesson from writing them, and it is not
optional discipline here. **After adding any guard, reintroduce the bug it
protects against and confirm the suite fails.** During this work, tests that
passed while checking nothing were caught repeatedly:

- shrinkage tests refused for an unrelated reason (a missing audit), never
  reaching the guard they named
- bulk-editor tests whose payload was rejected for a missing `name` before
  the value under test was read
- a payout test that could not reach its guard because the drawer was empty
- a "blind" mutation that was really a mutation edited into a **comment**
  containing the words `FOR UPDATE` rather than the SQL below it
- the drill's own money check silently skipping on a wrong column name and
  still reporting a pass

Always pair a guard test with a **control** asserting the valid case
succeeds. Without it, "refused for the right reason" and "refused for any
reason" are indistinguishable.

### 7.4 Harness facts worth knowing before debugging a strange failure

- `TESTING=True` turns on `PROPAGATE_EXCEPTIONS`, which **bypasses every
  `@app.errorhandler`** — routes that degrade gracefully in production then
  look like raw 500s. `conftest.py` forces it back off. A "finding" that only
  reproduces under the test client is probably this.
- pytest tears fixtures down in **reverse setup order**, so a price-list
  fixture runs before the case that billed against it — clear child rows
  first or the delete trips a foreign key, aborts the transaction, and every
  later teardown on that connection fails too.
- `inpatient_cases` is referenced by **six** tables.
- Some guards are **defence in depth**: `owners.phone` has a unique index
  behind the app's duplicate check, `appointments.resource_type` has a CHECK
  constraint, and POS idempotency has both a fast-path lookup and a unique
  index. Disabling one layer alone still yields correct behaviour — that is
  the design working, not a blind test. Disable both to prove the test.
