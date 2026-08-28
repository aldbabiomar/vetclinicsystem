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
| A | The receiver alerts when pings STOP | stop the app, wait for the alert | **PASSED 2026-08-26** |
| B | A healthy install reports `ok` on several CONSECUTIVE days | leave it running, check daily | **restarted 2026-08-27** — see below |
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

**Check settings confirmed 2026-08-26: Period 5 minutes, Grace 5 minutes.**
Notification method: email, ON.

**Result — detection: PASSED.** Observed on the receiver at 06:33 +03:

- *"This check is down. Last ping was 16 minutes ago"* — 16 minutes before
  06:33 is 06:17, exactly when the app was stopped.
- *1 downtime, 3 min 52 sec total, 99.99% uptime* for August — the first
  downtime the check has ever recorded, i.e. caused by this test.
- Down transition therefore at roughly 06:29, against a theoretical
  06:27 (last ping + period + grace). The ~2 minute lag is the receiver's own
  polling granularity, not anything on the app side: the app's last ping is
  the 06:17 the page itself reports.

**This is the property the whole feature exists for**, and it is the one that
no test suite can establish: the app was not merely reporting a problem, it
was *gone*, and something else noticed.

**Result — notification: PASSED.** The user confirmed the alert email arrived.
(It was not there at 06:27 when first checked, which is consistent: the down
transition happened at ~06:29, not 06:27.)

### TEST A: PASSED — 2026-08-26

Both halves. The app was stopped, the receiver noticed the absence, and a
human was told. Nothing else in this feature can do that: every other layer
needs the app to be running in order to report anything, and a machine that
never came back cannot report that it never came back.

**Scope of what this proves, honestly.** It exercised the mechanism on one
machine, on a 5-minute check, over about twelve minutes. It says nothing about
a receiver outage, a clinic behind a captive portal or proxy, or a laptop that
sleeps rather than shuts down. Those are not covered and should not be claimed.

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

~~**The heartbeat is off on this install on purpose.** Test A is currently
running against the one test check, and pinging it from here would reset its
timer and destroy that test. Set the URL only after Test A has resolved.~~
— **Test A passed, so the heartbeat was enabled here 2026-08-26.** Install id
`22335E2F`. Setting the URL does not itself ping; the first ping is the daily
self-check at 02:20.

> **The check's schedule must move to the production values before that
> ping**, or Test B generates days of alert spam. The soak install pings
> **once a day**; the check is currently Period 5 min / Grace 5 min, so it
> would go DOWN roughly ten minutes after every single daily ping and mail an
> alert each time. Period **1 day** / Grace **36 hours** matches the real ping
> cadence — and running the soak at the production values is better evidence
> than running it at test values anyway.

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

### Night 2 (2026-08-27→28): INVALIDATED, and it found the SAME bug one layer down

The backup again did not run, and the check went yellow. This time the app
had been alive the whole time and the night-1 fix was already deployed.

Cause: on macOS `time.monotonic()` does not advance during sleep (93.64h wall
since boot vs 48.08h monotonic), so APScheduler's countdown to a job 22 hours
out simply freezes. The job never becomes due, so misfire grace has nothing
to act on. Full writeup in `COMPARISON.md` §33.

Fixed by a 5-minute tick that runs whatever the WALL CLOCK says is overdue,
and verified live on this install: with the self-check made overdue, the tick
ran it and pinged (rows 5 → 6) while correctly leaving the not-overdue backup
alone (rows 23 → 23).

**Night 2 is not counted either.** Two nights, two real bugs, both in the
same area and both invisible to a green test suite. This is the soak doing
exactly the job it exists for — and it is also the reason not to shorten it.

### Night 1 (2026-08-26→27): INVALIDATED, and it found a real bug

The soak paid for itself here. The nightly backup did not run and no
heartbeat was sent — because the Mac slept from 01:01 to 03:10, straight
through the 02:00 backup and the 02:20 self-check, and APScheduler discards a
job whose time passed by more than `misfire_grace_time` (**default: one
second**). Full writeup in `COMPARISON.md` §32.

Fixed in both apps and pushed before restarting the soak:
`misfire_grace_time=None` + `coalesce=True` on every recurring job, plus a
startup catch-up for the case where the machine was OFF rather than asleep.

**The night is not counted.** Per this file's own exit criteria, a fault means
the soak restarts rather than resuming the count.

### Soak install now on `app_v1.8.11-soak4` (2026-08-28, later the same day)

Redeployed after the code review (`COMPARISON.md` §34) changed `app.py`,
`heartbeat.py`, `autostart.py`, `selfverify.py` and `scheduler.py`. Same day,
so Test B's day 1 is still 2026-08-28.

Confirmed on the real install after the redeploy:

- startup catch-up ran, `ok`, heartbeat sent
- **`install_id` stayed `22335E2F` across four redeploys** — the property
  finding 5 was about; a changing id would make the receiver report a healthy
  clinic as dead every night
- **no `heartbeat_url` value anywhere in `audit_log`** — finding 1

### Test B restarted AGAIN 2026-08-28 (day 1 = 2026-08-28), on `app_v1.8.11-soak3`

The 2026-08-27 restart below is superseded; its night failed for the reason
above. Kept because what it demonstrated about Layer 4 still stands.

### Test B restarted 2026-08-27, on the fixed code

Soak install rebuilt from `main` at `343f11f` as `app_v1.8.11-soak2`,
pre-soak backup taken first, schema sync run, restarted. Day 1 = 2026-08-27.

**What the restart itself demonstrated on the real install**, none of it
simulated:

| Observation | Meaning |
|---|---|
| 03:34 self-check → `warn` (`restore_unverified`), heartbeat sent | the daily job runs and pings |
| **03:59 verification ran and PASSED — "7 checks passed"** | Layer 4 test-restored a real backup of real demo data into a throwaway database and verified it |
| 03:59 self-check → `ok` | the warning cleared the same day |
| `last_verified_restore` = `{"at": "2026-08-27T03:59:00", "result": "pass"}` | recorded where the self-check and payload read it |
| `selfverify_%` databases remaining: **0** | the throwaway was dropped |
| Startup catch-up took **no** backup | today's 03:14 nightly already succeeded — the control working in production, no redundant backup per boot |
| Current self-check: `ok`, findings `[]` | healthy baseline for day 1 |

That 03:34 → 03:59 sequence is also the first real-world confirmation of the
earlier fix (`COMPARISON.md` §31): under the original monthly cron this
install would have warned every day until the 1st of the month.

**Note the machine still sleeps.** That is now *desirable* — if tonight's
backup happens on wake rather than not at all, the sleep fix is proven in the
field rather than only in tests.

**Check schedule confirmed 2026-08-27: Period 1 day, Grace 36 hours** — the
production values, so the soak now runs at the settings a real clinic will.

### What "normal" looks like from here, so a non-event is not mistaken for a pass

- Last ping 2026-08-27 05:11. The soak install's next scheduled ping is the
  daily self-check at **03:34** (backup_time 03:14 + 20 min), ~22h later —
  inside the 24-hour period, so the check stays green.
- **If the Mac sleeps through 03:34**, the misfire fix means the job runs on
  wake instead. A ping at, say, 10:00 is ~29h after the last one: past the
  24-hour period, comfortably inside the 36-hour grace. healthchecks.io shows
  the check as *late*, **not** down, and sends nothing.

That second case is worth stating explicitly because it is the interesting
one: the 36-hour grace exists precisely to absorb a machine that pings late
rather than never. A "late" check that recovers on its own is the system
working, not a fault — and only a genuinely absent ping (no wake at all for
36+ hours) should ever produce an email.

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
