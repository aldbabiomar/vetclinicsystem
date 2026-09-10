# Working with VetClinicSystem_IQ and VetClinicSystem_JO together

This folder is the shared workspace for both apps. It exists so the ground
rules below are visible to **any** Claude Code session working here,
regardless of which account started it — read this file before touching
either app's code.

> **Last audited against the actual trees: 2026-09-01.** That audit found ten
> stale claims. Four were in §1, asserting divergences that had not existed
> since 2026-08-23 (with §2 step 5 repeating one of them). The other six: the
> layout block omitted `SOAK_LOG.md` — the gate on the next release — and two
> other root files; it called the monitoring feature "unbuilt" when all four
> layers were built; the audits table had a wrong line count; §7's test
> numbers and file count were badly understated; §7.1's tier table was
> missing six test files; and §6 said the restore drill "currently" passes
> without saying when it last ran. This file loads automatically every session,
> which makes a wrong statement here more expensive than one anywhere else —
> and nothing re-checks it on its own. **Where this file and `COMPARISON.md`
> disagree, `COMPARISON.md` wins**, and where either disagrees with the code,
> the code wins. Re-derive counts, versions and file lists rather than
> quoting them.
>
> **Re-checked 2026-09-09:** the §1 divergence table, the §7 test-file count
> and the audits table still match the trees. The layout block had drifted
> again in the same way — `HOSTING_MIGRATION_PLAN.md` and
> `CLINIC_PC_TUNNEL_PLAN.md` sit in the root and were not listed. Both are
> now in. That is twice this block has gone stale by omission; when you add a
> file to this folder, add its line here in the same commit.
>
> **Re-checked 2026-09-10**, after the full-application review and the
> blueprint split. §7's test counts, file count, coverage figure and tier table
> were all re-measured rather than adjusted, and a "Where the code lives"
> section was added because `app.py` is no longer where most of the code is.
> The §7.1 tier table has now gone stale by omission twice; it says so in
> place, and the fix is `ls tests/`, not trusting the list.

## Layout

```
VetClinicSystem/
├── CLAUDE.md              ← this file
├── COMPARISON.md          ← dated, structured diff between the two apps — re-read before porting anything
├── RELEASE_WORKFLOW.md    ← the release process, see §3
├── TRANSITION_NOTES.md    ← read once on a first session: what's in flight, what's stale
├── SOAK_LOG.md            ← the monitoring soak — CLOSED, passed 2026-09-02; read it for how a soak is run
├── CODE_REVIEW_MONITORING_2026-08-27.md  ← the monitoring code review, 9 findings
├── FULL_APP_REVIEW_2026-09-10.md  ← whole-app review of BOTH apps: 37 findings (security, logic, QoL, dead code). **CLOSED — all 37 shipped** on branch `review-fixes-2026-09-10` (local, unpushed) — see COMPARISON.md §48, §49 and §51
├── HOSTING_MIGRATION_PLAN.md      ← DRAFT, written 2026-08-24, NOT executed: moving each app off the clinic PC onto its own VPS
├── CLINIC_PC_TUNNEL_PLAN.md       ← DRAFT, written 2026-08-24, NOT executed: the Cloudflare-tunnel alternative to the above; read the VPS plan first
├── features/              ← feature plans: CLEANUP and MONITORING, both built and SHIPPED (IQ 1.11.0 / JO 1.9.0)
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


## Where the code lives (both apps, since 2026-09-10)

`app.py` used to be ~7,200 lines holding every route. It was split into
blueprints; see `COMPARISON.md` §49. Both apps now have the same shape:

```
app.py      ~1,300   the Flask app and its config, security headers, the
                     network allowlist, the auth gate, error handlers, the
                     context processor, dashboard, reports/insights, /health,
                     and the launcher. 13 routes.
core.py     ~400     the seam. get_db, VERSION, form parsing and validation
                     (parse_money, clean_date, normalize_phone, the Bad*
                     exceptions, the MAX_* bounds), pagination, and the
                     money-validation helpers.
routes/              six blueprints: settings, admin, consignment, inventory,
                     sales, clinical.
logic.py    ~2,500   the queries and calculations. Unchanged by the split.
```

**Three things to know before editing:**

1. **A blueprint must never import from `app.py`** — `app.py` registers them,
   so that is circular. Shared pieces go in `core.py`.
2. **`core.py` must be imported after `load_dotenv()`**, because it reads
   `DB_REQUEST_TIMEOUT_SECONDS` from the environment at import time. `app.py`
   keeps its own early `_data_dir` read for the same class of reason.
3. **Endpoint names carry the blueprint prefix**:
   `url_for("settings.settings_page")`, not `url_for("settings_page")`. A
   missed one raises `BuildError` while the page renders, so it fails at the
   first page load rather than the first click.

### Two conventions that are enforced by tests, not by habit

1. **No inline `on*=` handlers.** `script-src` carries a per-request nonce
   instead of `'unsafe-inline'`, and a nonce does not authorise inline event
   handlers — a reintroduced `onclick=` is a button that silently does
   nothing. Use `data-vzh` + `VZ.bind()`, or `data-vz-act` + `VZ.action()` for
   markup a script builds at runtime. `static/behaviors.js`, guarded by
   `tests/test_no_inline_handlers.py`.
2. **Inline `style=` only for values the server computes, or for an element a
   script reveals with `el.style.display = ''`.** That second one is not
   pedantry: clearing the inline style cannot unhide an element a *class*
   hides, so moving such a `display:none` into CSS makes the panel disappear
   for good with no error. Everything else belongs in `style.css`.
   `tests/test_inline_styles.py` is a ratchet, not a demand.

**If you write a test that parses source text, read `routes/*.py` too.** Six
tests do this, and after the split every one of them would have passed while
checking a fraction of the surface. `test_permissions.py` pins its discovery
against Flask's live `url_map` for exactly this reason — copy that approach
rather than a magic number.

## 0. The `audits/` folder

Three long-lived audit documents live in `audits/`. Nothing else in this
folder pointed to them until 2026-08-26, so a fresh session had no way to
find them except by listing the directory:

| File | What it is | Status |
|---|---|---|
| `ERROR_500_AUDIT.md` (1,036 lines) | every action that could raise an unhandled exception | findings applied to both apps, 2026-08-24 |
| `ORPHANED_RECORDS_AUDIT.md` (1,414 lines) | every way a row could be left with no reachable parent | findings applied to both apps, 2026-08-24 |
| `IQ_JO_DIVERGENCE_AUDIT.md` (563 lines) | phased line-by-line diff of the two trees | **all closed** — 7.6, the last one, closed 2026-08-26 (`COMPARISON.md` §28) |

They are the reasoning behind a lot of existing defensive code — a guard that
looks unnecessary is usually one of these findings. Search them before
removing anything that looks redundant.

**One caveat worth carrying:** the divergence audit **missed a reproducible
500** that a five-minute test run later caught (`COMPARISON.md` §21). Reading
code is not the same as running it. Treat these as maps of where to look, not
as proof that an area is sound.

## 1. These are siblings, not twins

VetClinicSystem_IQ (Iraq) and VetClinicSystem_JO (Jordan) share a common
origin — JO was forked from IQ — and they have diverged on purpose in some
real, load-bearing ways. **The list below was re-verified against both trees
on 2026-09-01; the previous version of this section had drifted badly and was
asserting four things that are no longer true.**

### What actually differs

| | IQ | JO |
|---|---|---|
| **Money** | `DOUBLE PRECISION` / `float`, whole IQD, 250-note rounding, in a dedicated `money.py` | `NUMERIC(12,3)` / `Decimal`, 3-decimal JOD, **no `money.py` — there is nothing to round** |
| **Phone** | country code `964`, 10 local digits | `962`, 9 local digits — same algorithm, different constants |
| **Theming** | multiple palettes (~19 references in `app.py`) | one palette, no palette switching |

**The money divergence is the one that matters most.** IQ has no `Decimal`
import anywhere; JO uses it in four modules. A `float` op that is safe in IQ
is a `TypeError` or a silent precision bug in JO, and vice versa. Read
`COMPARISON.md` §1.1 before touching anything money-adjacent.

### What this section used to claim, and is WRONG (corrected 2026-09-01)

Each of these was stated here as settled fact and is not:

- ~~"JO uses native browser `confirm()`/`alert()` and renders everything
  synchronously; IQ has a small JS framework"~~ — **both apps ship
  `toast.js`, `progress.js` and `ui.js`**, with identical numbers of
  styled-dialog calls and identical numbers of native `confirm(`/`alert(`
  uses in templates. A UI pattern from one app usually *does* have an
  equivalent in the other; check rather than assuming it does not.
- ~~"JO is missing custom role creation"~~ — **both** have
  `/admin/roles/new`, `/edit` and `/delete` behind `manage_users_roles`,
  reachable from `admin_users.html`. Both support arbitrary custom roles.
- ~~"JO is missing backup restore"~~ — **both** have restore routes and a
  "Restore From Backup" card in Settings.
- ~~"JO is missing the folder browser"~~ — **both** have it.

IQ is still the more tested baseline, and JO is still not "IQ with a
different clinic name" — but the gap is much narrower than this file claimed.

**How this went wrong is worth knowing, because it will happen again.**
`COMPARISON.md` §3 had all four corrections recorded on **2026-08-23** — the
JS framework, custom roles, restore and the folder browser all crossed into
JO that day, and §3 says so. This file went on asserting the opposite for
over a week. §2 step 1 tells you to re-read `COMPARISON.md` first; that advice
was right, and the file it points at was right. **When this file and
`COMPARISON.md` disagree, `COMPARISON.md` wins** — it gets appended to as work
lands, and this one only changes when someone remembers to change it. Treat
the table above as evidence with a date on it, not a standing truth.

**Both apps will keep changing concurrently** — a feature added or a bug
fixed in one does not automatically apply to the other, and a fix that looks
identical on the surface can still be structurally wrong once it crosses into
the other app's actual code (money types above being the clearest case). The
goal every time is **a fix or feature tailored to each app's own code**, not
one implementation copy-pasted into both — but "tailored" now means checking
the target code, not assuming a divergence this file once listed.

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
   each app's actual role/permission model. **Corrected 2026-09-01: this
   step used to say JO had only 3 fixed roles while IQ supported custom
   ones. Both support arbitrary custom roles** (§1), so the warning applies
   equally in both directions — a fix that is safe for the seeded roles is
   not automatically safe for a custom role with a narrower permission set,
   in *either* app.
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
kill when you're done testing; `down` won't proceed while that PID is alive
**or while anything still holds the app port**, and removes the
container/venv/data dir together.

**Both guards exist because the PID one alone was unable to fail.** Until
2026-09-09 the PID `up` printed was not the app's — off by two, measured in
both apps — so killing it left the app serving, and `down` tore the container
out from under it while reporting success. Fixed and verified by a real
up/kill/down cycle in both apps (`COMPARISON.md` §44). The lesson generalises
past this script: **a guard you have never watched refuse is not yet known to
be a guard** — §7.3, in tooling rather than in a test. This is
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
`~/Downloads/vetclinicsystem{iq,jo}-data/backups/` and `~/Desktop/backups/`
(it recurses, so a `pre_update/` backup counts).

**Last run 2026-09-11. IQ passed all eight checks. JO could not run: there is
no JO install on this machine any more** — no data directory, no releases
directory, no `.app`, and no `vetclinicsystemjo_postgres` container. Only the
dev clone under `webapps/` remains, and that is source, not an install. The
drill reports that as a failure, correctly: "this app has no reachable backup"
is a true statement about JO on this machine. It is not evidence that JO's
backup *code* is broken. `COMPARISON.md` §52.

"Currently pass" is not a property a file can keep — **next run due
~2026-10-11.**

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
the result *with its date*; a passing drill is only evidence about the backup
it read, on the day it read it.

## 7. The test suites — run these, and trust them only as far as §7.3

Both apps went from 5-6 tests to real suites on 2026-08-25/26, and have kept
growing since. **Measured 2026-09-10, after the full-application review, the
blueprint split and the last three findings, all three tiers alive: IQ 728,
JO 709, zero skips, 39 `test_*.py` files each** (`COMPARISON.md` §48, §49 and
§51). They have found well over a dozen real bugs, several of which had
shipped — four more during the blueprint split, two of which a green `/health`
and a clean page-render sweep both reported as fine, and four more during the
CSP work, including one that would have made every POS quantity button target
a line id that does not exist.

**Two things gate "zero skips", and both look like a problem when they are
not:**

1. **`APP_URL` must be exported**, or the 13 browser tests skip and the totals
   read 712 / 693.
2. **Do not judge a run started between 00:00 and ~01:05.**
   `test_scheduler_catchup.py` carries two wall-clock gates: nine tests skip
   before 01:00 ("today's 00:30 slot has not passed yet"), and one more skips
   until roughly 01:05, because it needs `now - (BACKUP_RETRY_MIN_MINUTES + 5)`
   to still fall on today's date. Both are legitimate — the behaviour under
   test genuinely cannot be arranged at that hour — but a midnight run reports
   `9 skipped` or `1 skipped` and looks like a dormant tier. Found 2026-09-10
   by running the suite at 00:32; re-running the same file at 01:05 passed all
   22 with no skips.

**Coverage, re-measured 2026-09-10 after all 37 findings shipped** (the 61%
figure it replaces was measured 2026-09-01, before the review's ~200 new
tests). It has not moved off 65% through the blueprint split or the last three
findings, which is what relocation-plus-new-guards should look like:

| | IQ | JO |
|---|---|---|
| **Application code** — the honest number | **65%** | **65%** |

Re-measured 2026-09-10 with the review's tests in place (61% on 2026-09-01).
`scripts/isolated_test_env.sh` now installs `pytest-cov`, so the command below
actually runs — until that day it did not, which is exactly why this table kept
being quoted rather than re-measured.

Quote the first row. The second counts the tests measuring themselves, which
is how a suite flatters its own coverage.

Three modules sit at **0%** and drag the total by roughly five points:
`setup.py`, `import_seed.py` and `reconcile_attachments.py`. They are
entry-point scripts that no in-process test imports — the number is honest,
but "0% covered" and "untested" are not the same claim for these three.

Where the real gaps are, **re-measured 2026-09-10 after the blueprint split**
(so these are per-module figures for the layout that actually exists):
`barcode.py` 18%, `attachments.py` 27%, **`updater.py` 36%** — its first unit
tests landed with the review, and it is still verified end-to-end on macOS only
(`TRANSITION_NOTES.md` §4) — `backup.py` 42-43%, `desktop_shortcut.py` 57%,
`pdf_export.py` 61% and `autostart.py` 61%.

Among the six blueprints the spread is wide and worth knowing before you go
looking for an untested path: `routes/admin.py` 54-55% and
`routes/inventory.py` 55-56% at the bottom, `routes/settings.py` 64%, then
`routes/clinical.py` and `routes/consignment.py` both 70%, and
`routes/sales.py` 86-87% at the top. What is left in `app.py` — config, the
scheduler wiring and thirteen cross-cutting routes — is 72% (IQ) / 74% (JO),
and the new `core.py` seam is 88% / 85%.

Best covered: `money.py` 100% (IQ only — **JO has no `money.py` at all**,
because exact `Decimal` JOD needs no denomination rounding), `auth.py` 89%,
`selfcheck.py` 88%, `routes/sales.py` 86-87%, `selfverify.py` 83%,
`logic.py` 81%, `scheduler.py` 81%.

**Re-measure rather than quoting these** — every previous figure in this file
was stale within days:

```bash
TEST_DATABASE_URL=... venv/bin/python -m pytest tests/ -q --cov=. --cov-report=
venv/bin/python -m coverage report --omit="tests/*,venv/*" --sort=cover
```

### 7.1 Three tiers, by what they need

| Tier | Files | Needs | Runtime |
|---|---|---|---|
| **Pure** | 13 files: `test_money`, `test_frontend`, `test_updater`, `test_updater_releases`, `test_cleanup_cap`, `test_scheduler_logging`, `test_sql_placeholders`, `test_no_raw_form_dates`, `test_desktop_shortcut_target`, `test_autostart_windows`, `test_launcher_preflight`, `test_no_inline_handlers`, `test_inline_styles` | nothing | < 4s |
| **Database** | 25 files — every `*_routes`, plus `test_permissions`, `test_maintenance_permission`, `test_money_routes`, `test_backup`, `test_migrations`, `test_concurrency`, `test_selfcheck`, `test_selfverify`, `test_heartbeat`, `test_scheduler_catchup`, `test_login_lockout`, `test_login_log_ip`, `test_password_policy`, `test_session_and_csrf_lifetime`, `test_search_wildcards`, `test_log_retention`, `test_health_endpoint`, `test_refund_boarding`, `test_exports` | a throwaway Postgres | ~20s |
| **Browser** | `test_browser.py` (16 tests — 13, plus the CSP violation guard, its control, and a nonce-freshness check) | Playwright + a running app | ~2min |

**Do not hand-maintain this table** — `ls tests/` and check for `needs_db` /
`pytest.importorskip`. It has gone stale twice by omission.

*(The six monitoring-era files were added on 2026-08-26/27 and were missing
from this table until 2026-09-01 — another reason to trust `ls tests/` over
this list.)*

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
  /tmp/vz_iq_test_venv/bin/python -m pytest tests/ -q
```

(55492 / `vetclinicsystemjo` / `/tmp/vz_jo_test_venv` for JO.)
`TEST_DATABASE_URL` is deliberately a separate variable from `DATABASE_URL` —
these tests write and delete rows, and must never be pointed at a real install
by an exported shell variable.

**Corrected 2026-09-09: this block used to say `venv/bin/python`, which does
not exist.** That is the path in each app's README, where it means the venv a
real *install* builds in the repo directory; **the dev clones under
`webapps/` have no `venv/` at all**, so the documented command failed outright
until the throwaway venv the script actually builds was named here.

Browser tier: **set `APP_URL` to the app the script started**, or all 13
tests skip at runtime — a skip that looks nothing like the dormant-tier skip
described above, and is just as easy to read past:

```bash
APP_URL=http://127.0.0.1:5091 \
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystemiq \
  /tmp/vz_iq_test_venv/bin/python -m pytest tests/ -q
```

(5092 for JO.) Also see each app's README. Playwright is **test-only and not in
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
