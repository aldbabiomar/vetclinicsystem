# Transition notes — for a new Claude account picking up this project

**Rewritten 2026-08-26; §1, §2 and §4 rewritten again 2026-09-10** after the
full-application review and the blueprint split made them wrong in every row.
§3, §5 and §6 are cumulative and still hold — §3 gained six entries on
2026-09-10.

Read this **once**, on your first session in this folder, right after
`CLAUDE.md`. It is a snapshot, not a maintained document — the moment it and
the live repo disagree, **the repo is right**. §7 says how to keep it from
rotting.

If you are here because the user switched Claude accounts: nothing about the
project changed, only who is driving.

---

## 0. Read in this order

1. **`CLAUDE.md`** — ground rules. The apps are siblings, not twins. §7
   covers the test suites; "Where the code lives" covers the module layout.
2. **This file.**
3. **`COMPARISON.md` §1.1** — the money models. Non-negotiable before
   touching anything money-adjacent. There is now an index at the bottom of
   that file.
4. **`RELEASE_WORKFLOW.md`** — before publishing anything.

---

## 1. State as of 2026-09-10 — verify, don't trust

| | IQ | JO |
|---|---|---|
| `VERSION` | **1.12.2** | **1.10.2** |
| Tests, all three tiers | **728** | **709** |
| Skipped | 0 | 0 |
| `test_*.py` files | 39 | 39 |
| Coverage (application code) | 65% | 65% |
| `app.py` | 1,333 lines | 1,277 lines |
| Working tree | clean | clean |
| Branch | `review-fixes-2026-09-10` | `review-fixes-2026-09-10` |
| Remote | `aldbabiomar/vetclinicsystem_iq` | `aldbabiomar/vetclinicsystem_jo` |

**There is unpushed work.** Both apps sit on `review-fixes-2026-09-10`, 29
(IQ) and 30 (JO) commits ahead of `main`, holding the full-application review's fixes and the
blueprint split. Nothing has been pushed or released. `COMPARISON.md` §48 and
§49 are the record of what is in there.

**Check this table before relying on it** — one command:

```bash
for a in iq jo; do d=webapps/vetclinicsystem_${a}-main;
  echo "$a $(cat $d/VERSION) $(git -C $d rev-parse --abbrev-ref HEAD) \
    $(ls $d/tests/test_*.py | wc -l) test files"; done
```

## 2. What has happened, in one place

Do not read this file for detail — read `COMPARISON.md`, which is append-only
and dated. This is only a map of where the detail is.

| What | Where |
|---|---|
| The two money models, and why a fix can never be copied between the apps | `COMPARISON.md` §1.1 |
| Deliberate divergences — read before "fixing" one | §18 |
| Bugs that shipped and how they were found | the ⚠ rows in the index |
| Operational monitoring, all four layers | §29–§34, §37, §39–§41 |
| The full-application review: 37 findings, all shipped | §48 and §51, and `FULL_APP_REVIEW_2026-09-10.md` |
| The blueprint split: where the code lives now | §49, and `CLAUDE.md`'s "Where the code lives" |
| The CSP nonce, and why `on*=` attributes are now a test failure | §51 |
| Why inline `style=` is a ratchet and not a sweep | §51 |

**The review is closed — all 37 findings shipped**, plus R1 and R2. Nothing
from it is outstanding. Two of its findings are deliberately *scoped* rather
than finished, which is not the same as open: M4 stops after `pos_checkout`
because its own prompt says to leave the other five long functions until this
one ships, and M8 converts the two files it names and holds the rest with a
ratchet. Both say so in the report.

## 3. Traps that cost real time — cumulative, newest last

Each of these was hit, diagnosed, and cost 20+ minutes in some session. They
will not be obvious from the code. Items 1–10 are from 2026-08-25/28; 11–16
were added 2026-09-10 by the full-application review and the blueprint split;
17–21 the same day, by the last three findings (`COMPARISON.md` §51).

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
5. **zsh does not word-split unquoted variables.** `set -- $var` silently
   produces one argument. It generated a spurious "MATCH" on a remote-URL
   check that should have aborted.
6. **Backticks inside a double-quoted `git commit -m` are executed by the
   shell.** Two commit messages lost their content this way. Use `-F` with a
   file.
7. **A mutation that does not apply looks identical to a test that cannot
   catch it.** Verify the mutation actually changed the file — several
   "blind test" scares were wrong indentation, a non-unique anchor, or
   editing a *comment* that happened to contain the words `FOR UPDATE`.
8. **`git checkout -- file` discards uncommitted work.** Used to revert a
   mutation, it wiped an unrelated in-progress change. Back the file up
   instead.
9. **A stale `.pyc` can outlive a reverted mutation.** If `__pycache__` was
   unwritable when a mutated module was imported (a permission failure, an
   interrupted run), Python keeps loading the *mutated* bytecode after the
   source has been restored — so a correct fix looks broken, and the failure
   points at code that no longer exists. The mirror image of trap #6.
   `rm -rf __pycache__` the moment source and behaviour disagree.
   Cost ~30 minutes on 2026-08-27; see `COMPARISON.md` §32.4.
10. **A dormant test tier can report `1 skipped`, not 13.** IQ's browser
   tier had never run: Playwright was missing from its venv, and
   `pytest.importorskip` at module scope collects **zero** tests, which `-q`
   prints as a single skip. JO reported 13 skips for the same dormant tier
   only because Playwright happened to be installed there. The skip count is
   the documented way to notice this (`CLAUDE.md` §7.1) and it does not work
   — **confirm a tier is alive with `--collect-only`, not by reading
   totals.** It hid a Settings page that scrolled sideways on every phone.
   `COMPARISON.md` §40.3.
11. **When JS post-processes an element, the server's HTML is not evidence.**
   The self-check banner was verified in the rendered markup; `toast.js` then
   converted it to a toast and removed it from the DOM, so the feature never
   existed on screen. Assert against the DOM *after* load — or, better, add a
   static guard on the rule itself plus a control pinning the JS that makes
   the rule necessary. `COMPARISON.md` §40.1.

12. **A green `/health` and a clean page-render sweep both reported healthy
   while every Clean Up and every JO checkout was broken.** The blueprint split
   left `CLEANUP_CAP` and `MAX_QUANTITY` behind in `app.py` while the functions
   reading them moved to `core.py`. Neither is read at import time, so both
   apps started, and 22 sampled pages rendered with no error — the break was
   one level in, on submit. Only the test suite caught it. **A smoke sweep that
   only loads pages cannot see a moved module-level constant.**
13. **A static guard that reads `app.py` goes vacuous, not red, when the code
   moves.** `test_no_raw_form_dates.py` caught this on itself only because its
   floor is written as a count ("the scanner found 0 date form reads across 21
   modules … fix the detector rather than lowering this floor"). Guards that
   assert "no matches" pass hardest when they are scanning nothing. **Write a
   static guard's floor as a positive count of what it inspected.**
14. **A word-boundary `\b` in a regex over HTML matches inside hyphenated
   attributes.** A duplicate-`id` guard written as `\bid="` reported three
   false duplicates on `/admin/users`, because `-` is a word boundary and so
   `data-role-id="` matched. `(?<![-\w])id="` is the fix. The guard had the
   exact bug it was written to catch.
15. **Adding a key to `auth.PERMISSIONS` grants it to nobody on an existing
   install.** `seed_default_roles_and_permissions()` skips roles it has already
   created, and `admin_role_edit()` refuses to edit a system role — so a new
   permission ships switched off for Admin too, and the feature it gates
   disappears on upgrade. A `CROSS JOIN … ON CONFLICT DO NOTHING` backfill for
   `is_system` roles is now in `auth.py`; found by a control test failing live,
   not by reading. `COMPARISON.md` §48.
16. **A test that rewrites shared state fails five unrelated tests later.**
   Three separate instances: an upgrade test that stripped a grant from the
   session database, a password test that reset the seeded admin's password
   under a mutation, and a search test whose full-name query pinned its row
   either way. Use a throwaway fixture, or restore in `finally` — and when a
   clean run reports errors "somewhere else", suspect the test you just added.
17. **`el.style.display = ''` cannot unhide an element that a CLASS hides.**
   It clears the *inline* style and nothing else. Moving a script-toggled
   `display:none` into CSS — the obvious tidy-up, and what a mechanical
   inline-style sweep does first — makes the Settings Updates panel disappear
   permanently, with no error and nothing in any log. `COMPARISON.md` §51.
18. **A single utility class loses to `.field label`.** Specificity 0,0,1,0
   against 0,0,1,1, so the inline style being replaced was the only thing
   winning, and labels silently shift weight. The fix used here is to double
   the class name in the selector (`.u-strong.u-strong`). Any "move this
   inline style into CSS" edit needs the computed value checked, not the
   rendered page eyeballed.
19. **A CSP violation does not fire `pageerror`.** The browser refuses the
   script and writes a console error; the page renders normally. A policy that
   blocks every script on every page is invisible to a Playwright test that
   only listens for page errors.
20. **A permissive policy produces no violations, which is what a violation
   guard checks for.** The CSP guard passed perfectly with `'unsafe-inline'`
   put back. Every "assert nothing bad happened" test needs a control that
   makes the bad thing happen.
21. **A guard whose subject is *discovered* rather than fixed can find
   nothing and pass.** Four instances this cycle: a dormant browser tier
   (§40.3), a static scanner whose code moved out of `app.py` (§49), a POS
   selector matching an attribute that no longer exists (§51), and a CSS
   parser that swallowed the comment above each rule and therefore never saw
   the class it was looking for (§51). **Whenever a guard scans, parses or
   selects to find its subject, add a floor asserting how much it found.**

---

## 4. Open work, in priority order

Nothing here is broken; these are decisions or unbuilt work.

1. **The review branch is unpushed and unreleased.** 33 (IQ) / 34 (JO)
   commits on `review-fixes-2026-09-10`, including two schema migrations (the
   `manage_maintenance` permission and `refunds.boarding_id`). Merging and
   releasing it is the next real decision. `RELEASE_WORKFLOW.md` applies.

2. **The five remaining long functions**, which M4 deliberately deferred:
   `refund_retail_save` (137/134) and `refund_service_save` (125/126) are now
   the longest in `routes/sales.py`. M4's own prompt says to do these only
   once `pos_checkout` has shipped cleanly, so they are waiting on the release
   in item 1, not on a decision.

3. **No HTTPS by default.** `BEHIND_TLS_PROXY` exists and is off. Plain HTTP
   over the clinic LAN. `HOSTING_MIGRATION_PLAN.md` and
   `CLINIC_PC_TUNNEL_PLAN.md` are both DRAFTS and neither has been executed.

4. **`updater.py` is at 36% coverage** — its first unit tests landed with the
   review (release ordering and the update check). The apply/rollback path is
   still verified end-to-end on macOS only.

5. **No automated contrast check.** Deliberately removed after two attempts
   produced 117 then 142 false positives; the reasoning is in
   `tests/test_browser.py`. A future attempt should sample rendered pixels,
   not parse stylesheets.

6. **The workspace has git history but NO REMOTE.** `CLAUDE.md`,
   `COMPARISON.md` (now ~3,900 lines), `RELEASE_WORKFLOW.md`, this file, the
   audits, the features and `scripts/` are version-controlled here and exist on
   this one disk and nowhere else. A `git init` is not a backup.

7. **The restore drill: IQ passes, JO cannot run.** Last run 2026-09-11. IQ
   passed all eight checks against a real pre-update backup. **JO has no
   install on this machine at all any more** — see §5. Next run ~2026-10-11.
   `scripts/restore_drill.sh {iq|jo}`, `CLAUDE.md` §6, `COMPARISON.md` §52.

## 5. Things not to do without asking

- **`~/Downloads/vetclinicsystemjo-data` no longer exists** (checked
  2026-09-11). Nor does a JO releases directory, a JO `.app`, or the
  `vetclinicsystemjo_postgres` container. JO's install is gone from this
  machine; only the dev clone under `webapps/` remains, which is source, not
  an install. **Whether that was deliberate is not recorded anywhere** — if it
  was not, the data is unrecoverable, because JO also has no backup here. The
  old standing rule was "do not touch it beyond reading"; there is now nothing
  to touch. Ask before recreating it.
- **`~/Downloads/vetclinicsystemiq-data` is the user's real IQ install.** Read
  it; do not write to it. It holds exactly one backup, taken automatically
  before the 2026-09-10 update, and that backup restores cleanly.
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
- Port 5432 is taken by the user's real **IQ** Postgres container
  (`vetclinicsystemiq_postgres`, up and healthy, bound to 127.0.0.1).
  **Corrected 2026-09-11 — this used to say JO's container, which no longer
  exists.** Throwaway environments use 55491/55492, the restore drill 55499.
- `pg_dump` / `pg_restore` 16.15 are on PATH.
- `docker exec` needs `-i` to accept a heredoc on stdin.
- The scratch repo `aldbabiomar/scratchup` is public and usable.

---

## 7. Keeping this file honest

This document goes stale the moment anything ships — the previous version
lasted two days.

When you finish a substantial piece of work: append the dated detail to
`COMPARISON.md` (that is the permanent record, per `CLAUDE.md` §4), and only
then correct **§1, §2 and §4 here** (and append to §3 if it cost you time) if they are now wrong. If a whole section
has become misleading, rewrite it rather than patching it — a half-true
handoff doc is worse than an obviously old one, because the reader cannot
tell which half to trust.
