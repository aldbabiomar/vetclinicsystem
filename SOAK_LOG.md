# Monitoring pre-release soak — running log

**Started 2026-08-26.** This is the last gate before the monitoring feature is
released (`features/MONITORING_FEATURE_PLAN.md` §6.1, `COMPARISON.md` §29–§31).
All four layers are built, tested and pushed to `main` in both apps, and
**deliberately unreleased** until this log says the soak passed.

It exists as a file rather than a conversation because the soak spans days and
outlives any one session. **Append observations with dates; do not rewrite.**

---

## Why the soak cannot be skipped or simulated

The plan ships all four layers in one release, so there is no second release
to catch a feature that cries wolf in its first week. And a monitoring feature
that produces one false alarm gets switched off and never switched back on —
at which point it is worse than not having built it, because everyone believes
they are covered.

Two of the three things below can be proven in minutes. The third cannot be
rushed, inferred, or replaced by a passing test suite.

---

## What is being tested

| # | Property | How | Status |
|---|---|---|---|
| A | The receiver alerts when pings STOP | stop the app, wait for the alert | **running — see below** |
| B | A healthy install reports `ok` on several CONSECUTIVE days | leave it running, check daily | not started |
| C | A real fault surfaces: banner, then modal on the 3rd failing day | rename the backup folder | not started |

C's mechanism is already covered by tests and was verified live on 2026-08-26
(`COMPARISON.md` §29.3). It is repeated here against a long-running install
because the tests seed day-rows rather than living through three real days.

---

## Test A — absence detection

The only test of the property the whole feature exists for: everything else
requires the app to be running in order to report anything.

**Setup (IQ, isolated environment, install id `06FDC1AE`):**

- real backup taken through the app's own `run_backup()`
- restore verification ran and **passed** (7 checks)
- self-check: **`ok`, zero findings** — a genuinely healthy baseline, which
  matters because an alert from an unhealthy install would prove nothing
- heartbeat sent, HTTP 200 (ping #3 on the test check)

**Last ping: 2026-08-26 06:17 +03 (03:17 UTC).**
**App stopped: 2026-08-26 06:17:34 +03.** No further pings are possible.

**Expected**, depending on the test check's Period/Grace:

| Check settings | Alert due |
|---|---|
| 5 min / 5 min (recommended for a test check) | ~06:27 +03, same morning |
| 1 day / 36 hours (the production values) | ~2026-08-28 18:17 +03 |

**Result: _pending — record the time the alert actually arrived._**

> Note the production values are what §31.4 settled on, and they mean the
> alert fires at **~60 hours**, not the 48 the plan's §6.1 text says. A test
> check at 5/5 exercises the identical mechanism in ten minutes.

---

## Test B — no false alarms on a healthy install

Not started. Needs the app restarted and left running across several days,
confirming each day that the self-check still reports `ok` with zero findings
and that no banner appears.

**The specific thing being watched for:** a check that is quiet on day one and
noisy on day three. `backup_stale` (2 days) and `restore_unverified` (45 days,
re-verified every 30) are the two with time-dependent thresholds, and are the
most likely sources of a day-three surprise.

One such bug was already found and fixed on 2026-08-26 *before* the soak
started, by asking what a fresh install looks like on day two: a brand-new
install warned `restore_unverified` every day until the 1st of the month,
because the verification ran on a monthly cron. Fixed to a daily due-check.
That is the class of thing this test exists to catch.

**Host: the `~/Downloads` JO install** — authorised by the user 2026-08-26 as
a demo environment. This is far more representative than the throwaway: real
demo data (12 owners, 14 patients, 14 visits, 13 bills), real backups, the
real versioned-release layout, the real nightly schedule.

### How it was set up, 2026-08-26

1. **Pre-soak backup taken first**, through the app's own `run_backup()` —
   `~/Desktop/backups/vetclinicsystemjo_backup_20260826_062445.dump`.
2. **That backup was proven restorable** with `scripts/restore_drill.sh`
   before anything was modified: DRILL PASSED, 99 rows, 5 accounts, no
   orphans, `numeric` money intact. It is a real rollback point, not a hope.
3. New release folder `app_v1.8.11-soak` built by copying `app_v1.8.10`
   (to inherit its working venv) and rsyncing current `main` over it.
4. `active_release.txt` flipped; the supervisor loop restarted into it.
5. Schema sync run the way `updater._run_schema_sync()` runs it.
6. App restarted so a clean startup self-check ran.

**Nothing was deleted.** `app_v1.8.9` and `app_v1.8.10` are both still in
place.

### Schema change against a real populated database — PASSED

Worth its own line, because this is the failure mode that stopped 16 of 38
releases from updating (`RELEASE_WORKFLOW.md` §6.2):

- `self_check_log` created, `idx_selfcheck_ran` created
- `migration_failures` empty
- real data untouched: owners=12, patients=14, visits=14, billing=13

### Current state

| | |
|---|---|
| Running | `app_v1.8.11-soak`, `/health` ok, port 5050 |
| `backup_time` | 02:00 → self-check 02:20, verify-if-due 02:45 |
| Startup self-check | `warn`, one finding: `restore_unverified` |
| Verification due | yes — will run tonight 02:45 and should clear it |
| Successful backups on file | 17 |
| `heartbeat_url` | **deliberately UNSET** — see below |

**The heartbeat is off on this install on purpose.** Test A is currently
running against the one test check, and pinging it from here would reset its
timer and destroy that test. Set the URL only after Test A has resolved.

**Expected in the demo app meanwhile:** a Dashboard warning saying no backup
has been verified as restorable. That is truthful — this install has 17
backups and has never test-restored one — and it should disappear after
02:45 tonight. **If it is still there on the 27th, that is a Test B failure
and worth reporting.**

### How to revert, if wanted at any point

```bash
echo "app_v1.8.10" > ~/Downloads/vetclinicsystemjo-data/active_release.txt
kill $(lsof -nP -iTCP:5050 -sTCP:LISTEN -t)
```

The supervisor restarts into the old release within seconds. The only
database changes are additive — one new table and a few settings rows — so
the old release runs against it unchanged, ignoring what it does not know
about.

---

## Test C — a real fault surfaces

Not started. Rename the backup folder, then confirm:

1. the Dashboard banner appears with the real finding
2. no modal on day one
3. the modal appears on the third consecutive failing day, for
   `manage_settings` holders only
4. restoring the folder clears it

---

## Open questions

- ~~Where should Test B run?~~ **Settled 2026-08-26: the `~/Downloads` JO
  install**, with the user's explicit authorisation.
- **What Period/Grace is the test check actually set to?** Determines whether
  Test A resolves in ten minutes or two and a half days.
- **A latent fragility worth a look later, not a bug today.**
  `setup.load_dotenv_now()` loads `.env` from the *release* folder, but on the
  versioned-release layout `.env` lives in the *data* dir. `app.py` handles
  that distinction correctly; `setup.py` does not. It works in practice only
  because `updater._run_schema_sync()` inherits the running app's environment,
  which already has `DATABASE_URL` in it from `app.py`'s own `load_dotenv`.
  Any future caller of `apply_schema()` that does not happen to inherit that
  environment gets `RuntimeError: DATABASE_URL is not set`. Found by hitting
  it while doing the schema sync by hand.

---

## Exit criteria

The release goes ahead only when A, B and C have all been observed — not
inferred. Then: MINOR bump, `CHANGELOG.md` entry, one release per app, per
`RELEASE_WORKFLOW.md`.

If the soak finds a fault, fix it and **restart the soak** rather than
counting the days already elapsed — a feature that was noisy on day three and
then patched has not been shown to be quiet on day three.
