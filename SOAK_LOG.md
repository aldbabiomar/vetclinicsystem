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

**Host for the multi-day run: UNDECIDED.** The isolated environment lives in
`/tmp` and is removed by `isolated_test_env.sh down`, which makes it a poor
host for something that must survive days and reboots. A more representative
host would be a real install. Needs a decision — see "Open questions".

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

- **Where should Test B run for several days?** The isolated environment is
  throwaway by design. The alternative is a real install — the user's
  `~/Downloads` JO copy is a demo environment they have said is fair game, but
  `CLAUDE.md` §5 says not to touch it without checking, and it would mean
  running unreleased code there. **Ask before using it.**
- **What Period/Grace is the test check actually set to?** Determines whether
  Test A resolves in ten minutes or two and a half days.

---

## Exit criteria

The release goes ahead only when A, B and C have all been observed — not
inferred. Then: MINOR bump, `CHANGELOG.md` entry, one release per app, per
`RELEASE_WORKFLOW.md`.

If the soak finds a fault, fix it and **restart the soak** rather than
counting the days already elapsed — a feature that was noisy on day three and
then patched has not been shown to be quiet on day three.
