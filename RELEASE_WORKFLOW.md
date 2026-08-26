# Release Workflow — VetClinicSystem IQ & JO (include this in every Claude Code session)

## Why this file exists

Both apps have an in-app updater (`updater.py`) that pulls **specific,
named GitHub Releases** and applies them to a live clinic install. That
mechanism only works if every release Claude Code publishes follows the
*exact same* naming, tagging, and structure every single time — the
updater is dumb on purpose (it doesn't guess, it just trusts the format).
This document is that format. Follow it exactly, every time you're asked
to "push an update," "ship this," "release this," or similar — do not
improvise a different process even if it seems more convenient in the
moment.

This is one shared process used by **both** apps. Each app is versioned,
tagged, and released independently — a release in one doesn't require or
imply a release in the other (see [CLAUDE.md](CLAUDE.md) §3) — but the
mechanics below are identical for each. Where something differs per app,
it's called out explicitly.

If any instruction here conflicts with something faster/looser the user
asks for in the moment, flag the conflict and ask before deviating — a
malformed release can silently break a clinic's update mechanism.

The consumer side of this mechanism (`updater.py`, the `/health` route,
the Settings "Updates" UI) is already built and live in both apps — this
document only covers the *producer* side: what Claude Code must do when
publishing a release so `updater.py` on the clinic's machine can find and
trust it.

---

## 1. Repo identity

| App | Repo | `.env` / `.env.example` `GITHUB_REPO` |
|---|---|---|
| VetClinicSystem IQ | `aldbabiomar/vetclinicsystem_iq` | already set |
| VetClinicSystem JO | `aldbabiomar/vetclinicsystem_jo` | already set |

**Before your first push in any session, confirm the git remote matches
the app you're releasing** (`git remote -v`, from inside
`webapps/vetclinicsystem_iq-main/` or `webapps/vetclinicsystem_jo-main/`
respectively — see [CLAUDE.md](CLAUDE.md) for the folder layout). Never
push to a fork, a personal scratch repo, or a differently-named repo
"just for now" — each app is hardcoded to check its own named repo.

---

## 2. Branching model

Single small team, single environment per app — kept deliberately simple:

- **`main` is always deployable.** Every commit on `main` should be a
  state you'd be comfortable a clinic runs, because a tagged release is
  just "main at this commit, named and published."
- Work directly on `main` for normal changes. Use a short-lived branch
  only for something genuinely risky/experimental you don't want to
  commit to yet — merge and delete it promptly, don't let branches
  linger.
- **Never force-push `main`.** Never rewrite history that's already been
  pushed. If a bad commit landed, fix forward with a new commit — don't
  rebase/force-push it away, since a release may already point at it.

---

## 3. Versioning scheme

**Strict [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`**

- **PATCH** (`1.5.0` → `1.5.1`): bug fixes, no schema changes, no
  behavior changes a user would notice as "new."
- **MINOR** (`1.5.1` → `1.6.0`): new features, additive schema changes
  (new columns/tables — never destructive), backward-compatible.
> **Precedent set 2026-08-25 — adding `NOT NULL` to an existing column.**
> §6.2 and §7 forbid "type-narrowing in place" outside a MAJOR release, and
> adding a `NOT NULL` constraint trips that rule's letter. The user's call
> was that a **backfill plus a constraint, with no data loss and no manual
> admin step, counts as additive → MINOR**, with the tightening spelled out
> in the CHANGELOG so the admin sees it before clicking Update Now. Shipped
> that way as IQ v1.10.0. Use that precedent rather than re-asking — but do
> still flag the conflict, and still verify the migration converges on a
> simulated old install first.

- **MAJOR** (`1.6.0` → `2.0.0`): breaking changes — should be very rare
  for either app given each is a single self-hosted instance with no
  external API consumers; mainly reserved for "this requires the admin
  to do something manually before/after updating" (e.g. a one-time data
  migration too risky to run silently).

The version lives in **exactly one place per app**: a `VERSION` file at
that app's repo root, containing nothing but the number, no `v` prefix,
no newline issues:

```
1.5.0
```

Every release **must** bump this file in the same commit as the
corresponding `CHANGELOG.md` entry (§4). The app reads this file at boot
(`app.py`, `VERSION = open(...).read().strip()`); it must match the
release tag exactly (tag `v1.5.0` ↔ `VERSION` contents `1.5.0`) or the
updater's validation step will refuse the release.

As of this writing: IQ is at `1.5.0`, JO is at `1.1.0` — check the live
`VERSION` file in the app you're releasing, don't assume it's still this
number.

---

## 4. CHANGELOG.md

Keep `CHANGELOG.md` at each app's repo root in
[Keep a Changelog](https://keepachangelog.com) style. Add a new entry at
the top **in the same commit** as the `VERSION` bump:

```markdown
## [1.5.1] - 2026-08-24

### Fixed
- Consignment settlement carry-forward no longer drifts on rounding.
```

Use `### Added` / `### Changed` / `### Fixed` / `### Removed` as needed;
skip sections that don't apply. Keep entries short and user-facing — this
text is what gets shown to the admin in the Settings "Check for Updates"
changelog view, not a commit log dump. Don't describe internal refactors
here unless they change behavior a clinic user would notice.

---

## 5. Commit messages

Lightweight [Conventional Commits](https://www.conventionalcommits.org)
prefixes — not enforced by tooling, just consistency, since it makes
`git log` and changelog-writing faster:

```
feat: add cash tendered / change due to POS checkout
fix: round refund amounts to nearest 250 IQD
chore: bump VERSION to 1.5.1
docs: update CHANGELOG for 1.5.1
```

One logical change per commit where reasonable. Don't bundle an unrelated
fix into a feature commit.

---

## 6. The release checklist — run this every time, in order

Do not skip steps or reorder them. Do not tag/release anything that
hasn't gone through 1–5. Run this from inside the specific app's folder
(`webapps/vetclinicsystem_iq-main/` or `webapps/vetclinicsystem_jo-main/`).

1. **Confirm `main` is in a runnable state.** As of 2026-08-26 both apps
   have real test suites (370+ / 350+ tests, `CLAUDE.md` §7) and **the full
   suite must pass, including the database tier**, not just the fast one:

   ```bash
   scripts/isolated_test_env.sh up iq
   TEST_DATABASE_URL=postgresql://postgres:test@localhost:55491/vetclinicsystemiq \
     venv/bin/python -m pytest tests/ -q
   ```

   A bare `pytest tests/ -q` **skips** every database-backed test and passes
   in under a second — which looks identical to a real run. Check the skip
   count. `python3 -c "import app"` succeeding is no longer sufficient. For a real
   behavioral fix, verify live first in that app's isolated test
   environment (`scripts/isolated_test_env.sh` — see
   [CLAUDE.md](CLAUDE.md) §5), not just by inspection.
2. **Confirm schema changes are additive-only.** If this release touches
   `schema_postgres.sql`, every change must be something `setup.py`'s
   idempotent sync can apply to a live DB without data loss (new column
   with default, new table — never a drop/rename/type-narrowing in
   place).

   **Additive is not sufficient on its own — check the ORDER too.**
   `apply_schema()` runs the whole schema file *before*
   `apply_incremental_migrations()`. Anything in `schema_postgres.sql` that
   references a column only a migration adds works on a fresh install (the
   `CREATE TABLE` carries it) and **raises on every upgrade**, aborting the
   schema apply so every statement below it never runs — and because
   `_run_schema_sync()` uses `check=True`, that becomes a failed,
   rolled-back update.

   This shipped: a `CREATE UNIQUE INDEX` over `sales(idempotency_key)` in
   the schema file meant **16 of 38 tagged releases could not update at
   all**, with no indication why. Fixed in IQ v1.10.6 / JO v1.8.7. An index
   over a migration-added column belongs in
   `INCREMENTAL_SCHEMA_STATEMENTS`, beside the `ALTER TABLE` that adds it.

   `tests/test_migrations.py` guards this. It builds a database from an old
   tag's schema, runs the real upgrade, and asserts convergence — plus a
   static check needing no database. **If it fails, do not ship.** If a genuinely destructive change is unavoidable, that's a
   MAJOR version and needs an explicit manual migration note in the
   changelog, not a silent auto-applied one.
3. **Bump `VERSION`** to the new number per §3.
4. **Add the `CHANGELOG.md` entry** per §4, dated today.
5. **Commit both together**: `chore: release v1.5.1` (bumps VERSION +
   CHANGELOG in one commit — never split across two, since the updater
   should never see a state where they disagree).
6. **Push `main`**: `git push origin main`.
7. **Tag the release**, annotated, exactly `v` + the `VERSION` file
   contents — no other format, ever:
   ```bash
   git tag -a v1.5.1 -m "v1.5.1"
   git push origin v1.5.1
   ```
8. **Publish a GitHub Release from that tag**, with the release body set
   to the CHANGELOG entry for that version (not the raw commit list —
   GitHub's auto-generated notes are not what gets shown to the clinic
   admin). Using the `gh` CLI:
   ```bash
   gh release create v1.5.1 \
     --repo aldbabiomar/vetclinicsystem_iq \
     --title "v1.5.1" \
     --notes-file <(sed -n '/## \[1.5.1\]/,/## \[/p' CHANGELOG.md | sed '$d')
   ```
   (swap `--repo` for `aldbabiomar/vetclinicsystem_jo` when releasing
   JO). If `gh` isn't available/authenticated, use the GitHub API
   (`POST /repos/{OWNER}/{REPO}/releases`) with the same tag name and
   notes — never publish a release through the web UI with a
   differently-formatted tag "just this once."
9. **Verify the release is what the updater expects**: fetch
   `GET /repos/{OWNER}/{REPO}/releases/latest` and confirm `tag_name` is
   exactly `v1.5.1` and a source tarball is attached (GitHub attaches
   this automatically for any tagged release — no extra step needed
   unless the release needs bundled binaries/assets, which neither app
   does).

---

## 7. Hard rules — never do these

- Never publish a release without bumping `VERSION` in the same commit.
- Never tag a commit that hasn't been pushed to `main` first.
- Never reuse or move a tag once published (no `git tag -f`) — if a
  release was bad, publish a new PATCH version with the fix; don't
  overwrite history a running clinic instance may have already checked
  against.
- Never publish a pre-release/draft as if it were the latest stable — the
  updater always asks for `/releases/latest`, which GitHub defines as the
  most recent *non-prerelease, non-draft* release. Mark anything not
  ready for a clinic as a draft or prerelease explicitly.
- Never include destructive schema changes in a MINOR or PATCH release.
- Never skip the CHANGELOG entry, even for a "tiny" fix — it's the only
  thing the admin sees before clicking "Update Now."
- Never ship a test-only change as a release. Commit and push it to `main`
  — a clinic should not get an "update available" prompt for tests it
  cannot see. §7 of this file requires a VERSION bump when *publishing a
  release*, not on every commit, and `main` stays deployable either way.
  Several test-only commits were shipped this way on 2026-08-25/26.
- Never assume the updater compares versions by ordering. `updater.py`'s
  `is_update_available()` uses `!=`, not `>`. That is why IQ's jump to a
  double-digit minor (`1.10.0`) was safe where a lexical `<` would have
  hidden the update from every clinic. Do not "fix" this into an ordering
  comparison without thinking it through.
- Never release into the wrong app's repo — double-check `git remote -v`
  and the `.env`/`.env.example` `GITHUB_REPO` value match (§1) before
  pushing or tagging, since IQ and JO are versioned independently and a
  tag pushed to the wrong repo can't be un-published cleanly (§ above).

---

## 8. Hotfix flow (something's actively broken in production)

Same checklist, just faster and smaller in scope:

1. Fix on `main` directly (skip a branch for genuine emergencies).
2. PATCH bump only (`1.5.0` → `1.5.1`).
3. One-line `CHANGELOG.md` entry under `### Fixed`.
4. Steps 5–9 above, unchanged — **do not skip the health-check-backed
   release process even under time pressure**; a broken hotfix pushed
   without going through the normal tag/release path can't be picked up
   by the updater's rollback safety net, since that safety net only
   protects the version *it* installed, not something applied outside
   the mechanism.

---

## 9. How the consumer side works (reference, not something you build)

This mechanism is already implemented in both apps — the notes below are
so a release you publish actually gets picked up correctly, not a spec to
implement from scratch.

**It was verified end to end on 2026-08-26** against a scratch GitHub repo
(`aldbabiomar/scratchup`), not mocked: a normal update applied and the new
files were confirmed live; rollback reverted; a release whose `VERSION` file
disagreed with its tag was refused at validation; and a release that
installed but raised at import was refused at the health probe, never
becoming the running version. Both failure paths left the install exactly as
it was. See `COMPARISON.md` §25 for the method and its limits — it exercised
the mechanism on macOS, and says nothing about Windows, a proxy, a truncated
download, or losing power mid-switch.

- **On-disk layout at each clinic** (outside any versioned code folder,
  so an update never deletes/orphans it):
  ```
  vetclinicsystem{iq,jo}-data/       # never touched by updates
    .env
    logs/
    active_release.txt              # pointer, e.g. "app_v1.5.0"

  vetclinicsystem{iq,jo}-releases/
    app_v1.4.0/                     # old, kept for rollback
    app_v1.5.0/                     # current
  ```
  Env vars: `VETCLINICSYSTEMIQ_DATA_DIR` / `VETCLINICSYSTEMIQ_RELEASES_DIR`
  for IQ, `VETCLINICSYSTEMJO_DATA_DIR` / `VETCLINICSYSTEMJO_RELEASES_DIR`
  for JO. Set up by `setup.py --enable-updates` on the clinic's machine.
- **`updater.py`** (per app, at the repo root): checks
  `GET /repos/{GITHUB_REPO}/releases/latest`, backs up the DB
  (`backup.py`), downloads the tagged tarball into a new release folder,
  validates it (`VERSION` matches the tag, `app.py` imports cleanly),
  runs the additive schema sync, flips `active_release.txt`, restarts,
  and health-checks `/health`. On a failed health check it automatically
  flips the pointer back and restarts the previous version — the backup
  taken in step one is there so nothing is lost even then.
- **`/health`** (`app.py`): `{"status": "ok", "version": VERSION}` on
  success, checks a live DB query, not just process liveness.
- **Settings → Updates UI**: admin-triggered only, never automatic/silent
  during clinic hours. Shows the GitHub Release body (i.e. your
  `CHANGELOG.md` entry) before the admin confirms.
- Only the **last 2 releases** are kept on disk after a successful
  update; older ones are pruned automatically. The release currently
  pointed to by `active_release.txt` is never deleted.

If you're asked to change *this* mechanism itself (not just publish a
release through it), read `updater.py`, `setup.py`, and the `/health`
route in the specific app first — don't assume IQ's and JO's
implementations are identical without checking, per
[CLAUDE.md](CLAUDE.md) §1.

---

## 10. Quick reference

| Thing | Format | Example |
|---|---|---|
| `VERSION` file contents | `MAJOR.MINOR.PATCH`, no `v`, no newline noise | `1.5.1` |
| Git tag | `v` + VERSION contents | `v1.5.1` |
| Release title | same as tag | `v1.5.1` |
| Release notes | that version's `CHANGELOG.md` section | see §4 |
| Release commit message | `chore: release vX.Y.Z` | `chore: release v1.5.1` |
| Branch | `main` only, always deployable | — |
| IQ repo | `aldbabiomar/vetclinicsystem_iq` | — |
| JO repo | `aldbabiomar/vetclinicsystem_jo` | — |
