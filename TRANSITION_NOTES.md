# Transition notes — for a new Claude account picking up this project

**Rewritten 2026-08-26.** Supersedes the 2026-08-24 version entirely; that
one was written before ~18 releases, a 370-test suite, and eleven shipped bug
fixes, and most of its specifics had gone stale.

Read this **once**, on your first session in this folder, right after
`CLAUDE.md`. It is a snapshot, not a maintained document — the moment it and
the live repo disagree, **the repo is right**. §7 says how to keep it from
rotting.

If you are here because the user switched Claude accounts: nothing about the
project changed, only who is driving.

---

## 0. Read in this order

1. **`CLAUDE.md`** — ground rules. The apps are siblings, not twins. §7 is
   new and covers the test suites.
2. **This file.**
3. **`COMPARISON.md` §1.1** — the money models. Non-negotiable before
   touching anything money-adjacent. There is now an index at the bottom of
   that file.
8. **`RELEASE_WORKFLOW.md`** — before publishing anything.

---

## 1. State as of 2026-08-26 — verify, don't trust

| | IQ | JO |
|---|---|---|
| `VERSION` | **1.10.9** | **1.8.10** |
| Latest tag | `v1.10.9` | `v1.8.10` |
| Tags total | 42 | 34 |
| Tests collected | 379 † | 361 † |
| Passing with a database | **371** † (8 browser tests skipped) | **353** † (8 skipped) |
| Passing with nothing | 130 (249 skipped) † | 112 (249 skipped) † |
| Coverage | ~68% † | ~67% † |
| Working tree | clean, pushed | clean, pushed |
| Remote | `aldbabiomar/vetclinicsystem_iq` | `aldbabiomar/vetclinicsystem_jo` |

**Versions/tags/tree re-verified 2026-08-26** (the v1.10.9 / v1.8.10 POS fix,
`COMPARISON.md` §27, had shipped after this table was first written).

† **Test counts are as measured at v1.10.8 / v1.8.9 and have not been re-run
since.** §27 added two browser interaction tests per app after that
measurement, so the collected and skipped numbers are each low by two. Neither
app currently has a `venv/` on disk (`isolated_test_env.sh` creates and removes
it), so re-measuring means bringing an environment up. Re-run before quoting
these.

The two apps are versioned **independently** and their numbers are not
expected to match. Always read the live `VERSION` file.

**A bare `pytest tests/ -q` passes 130 and skips 249** — that is correct
behaviour, not a broken suite. The database tier needs `TEST_DATABASE_URL`
and the browser tier needs `APP_URL`; both skip cleanly without them
(`CLAUDE.md` §7.1). **Check the skip count before believing a green run.**

**Check this table is still true before relying on it** — one command:

```bash
for a in iq jo; do d=webapps/vetclinicsystem_${a}-main;
  echo "$a $(cat $d/VERSION) $(git -C $d describe --tags --abbrev=0)"; done
```

---

## 2. What changed in the 2026-08-25/26 sessions

Compressed. Full detail is in `COMPARISON.md` §20–26.

### 2.1 Eleven real bugs found and shipped

Every one was found by writing a test, not by reading code. Ordered by how
much they mattered:

| Bug | Impact | Fixed in |
|---|---|---|
| An index in `schema_postgres.sql` over a migration-added column | **16 of 38 releases could not update at all** — the update aborted and rolled back with no explanation | IQ 1.10.6 / JO 1.8.7 |
| Negative operating costs accepted | **Inflated reported profit** — `net_profit = gross - opex`, so a negative cost *raised* it. A rent of −100,000 moved annual net profit by +200,000 | IQ 1.10.5 / JO 1.8.6 |
| `backup_retention` of 0 | `files[0:]` is every file — **would delete every backup** | IQ 1.10.7 / JO 1.8.8 |
| `parse_date` validated a 10-char prefix | reproducible 500 on `/visits` and `/refunds` | IQ 1.10.1 / JO 1.8.1 |
| JO accepted negative costs and weights on 4 routes | corrupted margin/COGS figures | JO 1.8.4 |
| Consignment settlement with no history | 500 on a `NOT NULL` violation | IQ 1.10.4 / JO 1.8.5 |
| `visit_billing_save` had no existence check | error page instead of a message | IQ 1.10.3 |
| IQ had no upper bound on money input | accepted `1e18` as a price | IQ 1.10.2 |
| `/refunds` overflowed on tablet, `/visits` on phone | horizontal scroll | IQ 1.10.8 / JO 1.8.9 |
| Appointment "+" buttons 20px tall | unusable on a phone | IQ 1.10.8 / JO 1.8.9 |
| A boarding stay could end before it began | nonsense rows in occupancy reports | IQ 1.10.5 / JO 1.8.6 |

### 2.2 What now exists that didn't

- **Test suites**: 16 files per app, three tiers (pure / database / browser).
  `CLAUDE.md` §7 is the reference.
- **`scripts/restore_drill.sh`**: proves a real backup restores. **Both apps
  now pass**; IQ had never passed before 2026-08-26 because no IQ backup
  existed. Run monthly.
- **`features/MONITORING_FEATURE_PLAN.md`**: a precise, unbuilt 3-layer plan
  for operational monitoring. Ready to hand to an implementer.
- **An IQ backup** at `~/Downloads/vetclinicsystemiq-data/backups/`, and a
  seeded IQ dataset in the isolated environment.

### 2.2b Folders that are easy to miss

`features/` and `audits/` hold ~3,700 lines of design and audit work between
them and were, until 2026-08-26, referenced by none of the standing docs.
`CLAUDE.md` §0 now covers `audits/`. In `features/`:

- `CLEANUP_FEATURE_PLAN.md` — **built and shipped** (`COMPARISON.md` §6).
  Retained as a design record; do not re-implement it.
- `MONITORING_FEATURE_PLAN.md` — **not built.** See §4.1.

### 2.3 Verified, so you don't have to re-derive it

- **The permission system works.** 28 permissions, 140 routes, all proven to
  deny. It had never been tested before.
- **The updater works** — end to end against a real GitHub repo, including
  rollback and both failure paths. `COMPARISON.md` §25.
- **The concurrency guards work** — the oversell, double-submit and
  overpayment races were actually run. `test_concurrency.py`.
- **The user's real JO data is clean** — 16 damage checks, all zero. But it
  is demo data seeded 2026-08-25, so that says little about a database with
  real history. `COMPARISON.md` §24.

---

## 3. Traps that cost real time this session

Each of these was hit, diagnosed, and cost 20+ minutes. They will not be
obvious from the code.

1. **`TESTING=True` bypasses every error handler.** It turns on
   `PROPAGATE_EXCEPTIONS`, so routes that degrade gracefully in production
   look like raw 500s under the test client. `conftest.py` forces it off. A
   "bug" that only reproduces in tests is probably this.
2. **A passing test may be testing nothing.** Repeatedly: shrinkage tests
   refused for a missing audit rather than the guard they named; bulk-editor
   payloads rejected for a missing `name` before the value under test was
   read; a payout test that could not reach its guard because the drawer was
   empty. **Always pair a guard test with a control asserting the valid case
   succeeds.**
3. **A green test suite says nothing about whether a button works.** POS
   "Complete Sale" did nothing at all for 25/29 releases while 371 tests
   passed — route tests POST directly and never click; browser tests loaded
   the page and never interacted. `COMPARISON.md` §27. **When a user reports
   something "might be broken", drive the real UI before trusting any test
   result.**
4. **`760px` is not a tablet.** A standard tablet is 768px. This
   off-by-one-breakpoint mistake was made twice — once with tables (fixed at
   1120px) and again with `.panel-grid`, which shipped. **A third instance
   (the Settings form grid) turned up on 2026-08-28, and the sweep that
   followed found the 760px query was the app's entire mobile switch: an iPad
   in portrait got no 44px touch targets and 14px form fields, so iOS Safari
   zoomed on every field and never zoomed back. Swept out in favour of
   `(pointer: coarse)` — see `COMPARISON.md` §36. If you find yourself
   picking a pixel number for a device class, that is the smell.**
4. **zsh does not word-split unquoted variables.** `set -- $var` silently
   produces one argument. It generated a spurious "MATCH" on a remote-URL
   check that should have aborted.
5. **Backticks inside a double-quoted `git commit -m` are executed by the
   shell.** Two commit messages lost their content this way. Use `-F` with a
   file.
6. **A mutation that does not apply looks identical to a test that cannot
   catch it.** Verify the mutation actually changed the file — several
   "blind test" scares were wrong indentation, a non-unique anchor, or
   editing a *comment* that happened to contain the words `FOR UPDATE`.
7. **`git checkout -- file` discards uncommitted work.** Used to revert a
   mutation, it wiped an unrelated in-progress change. Back the file up
   instead.
8. **A stale `.pyc` can outlive a reverted mutation.** If `__pycache__` was
   unwritable when a mutated module was imported (a permission failure, an
   interrupted run), Python keeps loading the *mutated* bytecode after the
   source has been restored — so a correct fix looks broken, and the failure
   points at code that no longer exists. The mirror image of trap #6.
   `rm -rf __pycache__` the moment source and behaviour disagree.
   Cost ~30 minutes on 2026-08-27; see `COMPARISON.md` §32.4.
9. **A dormant test tier can report `1 skipped`, not 13.** IQ's browser
   tier had never run: Playwright was missing from its venv, and
   `pytest.importorskip` at module scope collects **zero** tests, which `-q`
   prints as a single skip. JO reported 13 skips for the same dormant tier
   only because Playwright happened to be installed there. The skip count is
   the documented way to notice this (`CLAUDE.md` §7.1) and it does not work
   — **confirm a tier is alive with `--collect-only`, not by reading
   totals.** It hid a Settings page that scrolled sideways on every phone.
   `COMPARISON.md` §40.3.
10. **When JS post-processes an element, the server's HTML is not evidence.**
   The self-check banner was verified in the rendered markup; `toast.js` then
   converted it to a toast and removed it from the DOM, so the feature never
   existed on screen. Assert against the DOM *after* load — or, better, add a
   static guard on the rule itself plus a control pinning the JS that makes
   the rule necessary. `COMPARISON.md` §40.1.

---

## 4. Open work, in priority order

Nothing here is broken; these are decisions or unbuilt work.

1. **Operational monitoring** — `features/MONITORING_FEATURE_PLAN.md`.
   **ALL FOUR LAYERS ARE BUILT** in both apps as of 2026-08-26 and committed
   to `main`, and deliberately **NOT RELEASED**: the plan ships all four in
   one release per app, and **the §6.1 soak is the only remaining gate**.
   - Layer 1, the local self-check — `COMPARISON.md` §29 (plus two claims in
     the plan's §0.2 that turned out to be wrong).
   - Layer 4, the self-verifying backup — §30, including a real JO-only bug
     where a wrong money type reported "could not run" instead of "failed".
   - Layers 2 & 3, the heartbeat and payload — §31. Verified against a real
     healthchecks.io check: both apps pinged 200 with distinct install ids.

   **What the soak needs, and it is calendar time, not work:** several
   consecutive daily self-check runs reporting `ok` on a healthy install, and
   leaving the app stopped until the receiver alerts. Note §31.4 — with the
   agreed period/grace (1 day / 36 hours) that alert arrives at **~60 hours**,
   not the 48 the plan's §6.1 says. Budget two and a half days.
   Only after that: MINOR bump and one release per app.
   ~~four open questions in its §7~~ — **wrong, corrected 2026-08-26.** The
   plan's §7 is titled "Nothing is open" and says every question it raised was
   answered and folded into §0.4; build it as written without checking back.
   (The §7 heading is easy to miss — it sits on the same line as a `---` rule,
   so a `grep '^## 7'` finds nothing and the section looks absent.)
2. **Bound the backup retry — FIRST thing after the release.** Decided
   2026-09-01: found by Test C on the last day of the soak, deferred rather
   than fixed, because it only bites an install whose backup destination is
   already broken and loudly reported (`SOAK_LOG.md`, 2026-09-01).

   `scheduler._backup_catchup_due()` asks whether a backup **succeeded**
   since today's scheduled time. A permanently broken destination never
   satisfies that, so the 5-minute tick retries forever — Test C logged 13
   attempts in one day against Test B's 1. `_self_check_due()` asks whether
   one **ran**, which is why the self-check does not do this; the asymmetry
   looks unintended.

   Two parts: bound the retry (at most one attempt per hour reads best — it
   still recovers a transient fault quickly, and caps the day at ~24), and
   give `backup_log` row retention, which it has none of today
   (`_apply_retention` prunes backup *files* on disk, not rows).

   **Test it on the failing path, and mutation-check on BOTH paths.** A guard
   written only against a healthy install passes whatever the retry logic
   does, because a healthy install backs up once regardless — this is exactly
   the §7.3 trap, and it is why the bug survived until an install that fails
   every time existed to show it.

3. **Port IQ's `consecutive_fail_days()` into JO — AFTER the soak.**
   Agreed 2026-08-31. The two versions have differed since the feature
   landed, despite JO's docstring claiming the file was identical to IQ's
   (`COMPARISON.md` §40.6). IQ keys each day's verdict by `ran_at`; JO keys
   by insert order, relying on `ORDER BY id DESC` agreeing with `ran_at`
   order. A robustness gap, not a live bug — which is why it waits: this
   function decides when the Dashboard modal escalates, and that is exactly
   what the soak's Test C measures.

   **The part that is easy to get wrong.** The two versions agree in every
   ordinary case, so a test written the obvious way passes against BOTH and
   proves nothing — the §7.3 failure mode this project keeps hitting. The
   port is only verified by a case where **id order and `ran_at` order
   disagree**: insert a row with a LOWER id but a LATER `ran_at` for the same
   day (e.g. write yesterday's 'fail' row after today's 'ok' row, or set
   `ran_at` explicitly on two rows inserted in the opposite order), then
   assert the day's verdict follows the timestamp, not the id. Mutation-check
   it by reverting JO to `setdefault` and confirming that test — and only
   that test — fails.

   Also fix JO's `consecutive_fail_days` docstring, which says "ending today"
   while the code ends at the most recent *recorded* day, and restore the
   module docstring's parity claim once the two files genuinely match.

4. **No HTTPS by default.** `BEHIND_TLS_PROXY` exists and is off. Plain HTTP
   over the clinic LAN.
5. **`updater.py` has no unit coverage** — verified end-to-end on macOS only.
6. **`app.py` is ~4,000 statements in one file**, ~1,340 uncovered. Splitting
   it is worth doing only now that tests exist to catch what a split breaks.
7. **No automated contrast check.** Deliberately removed after two attempts
   produced 117 then 142 false positives; the reasoning is recorded in
   `tests/test_browser.py`. A future attempt should sample rendered pixels,
   not parse stylesheets.
8. **`features/CLEANUP_FEATURE_PLAN.md` is now BUILT** (shipped, see
   `COMPARISON.md` §6) — the plan is retained as a design record. Do not
   re-implement it.
9. **The workspace has git history but NO REMOTE.** Corrected 2026-08-31 —
   the first half of this item was done on 2026-08-26: `CLAUDE.md`,
   `COMPARISON.md`, `RELEASE_WORKFLOW.md`, this file and `scripts/` are now
   version-controlled (`webapps/` is excluded via `.gitignore`). What is
   still outstanding is a **remote**: every one of these documents, now
   ~3,000 lines in `COMPARISON.md` alone, exists on this one disk and
   nowhere else. A `git init` is not a backup.

---

## 5. Things not to do without asking

- **Do not touch `~/Downloads/vetclinicsystemjo-data`** beyond reading,
  without checking. It is the user's real install — they have said it is a
  test/demo environment and fair game, but it holds the seeded demo data used
  for showing the app.
- **Do not publish test releases to the real repos.** `aldbabiomar/scratchup`
  is the scratch repo for that, and currently holds `v9.0.0`–`v9.0.3` from
  updater testing. They are inert.
- **Do not add dependencies to `requirements.txt` for tests.** Playwright is
  test-only on purpose — the apps have no build step and no browser
  dependency, and that is worth protecting.
- **Do not port a money fix between the apps without re-deriving it.**
  `CLAUDE.md` §2 is not a formality; a `float` operation safe in IQ is a
  `TypeError` or a silent precision bug in JO.
- **Do not run the restore drill or tests against a real database.** Both
  take a throwaway; `TEST_DATABASE_URL` is deliberately separate from
  `DATABASE_URL` for this reason.

---

## 6. Environment facts specific to this machine

- Homebrew Python 3.14 at `/opt/homebrew/bin/python3`, PEP 668 — system pip
  is blocked, everything needs a venv.
- A pytest venv needs `--system-site-packages` **or** the app's own
  `requirements.txt` installed, because the tests `import app`.
- Port 5432 is taken by the user's real JO Postgres container
  (`vetclinicsystemjo_postgres`). Throwaway environments use 55491/55492, the
  restore drill 55499.
- `pg_dump` / `pg_restore` 16.15 are on PATH.
- `docker exec` needs `-i` to accept a heredoc on stdin.
- The scratch repo `aldbabiomar/scratchup` is public and usable.

---

## 7. Keeping this file honest

This document goes stale the moment anything ships — the previous version
lasted two days.

When you finish a substantial piece of work: append the dated detail to
`COMPARISON.md` (that is the permanent record, per `CLAUDE.md` §4), and only
then correct **§1, §2 and §4 here** if they are now wrong. If a whole section
has become misleading, rewrite it rather than patching it — a half-true
handoff doc is worse than an obviously old one, because the reader cannot
tell which half to trust.
