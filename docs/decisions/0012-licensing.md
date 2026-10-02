# 0012 — Licensing: signed keys, one trust rule, read-only at a sign-in

## Context

Each clinic runs VetClinicSystem on its own computer, and pays the vendor for
it. The vendor needed three things: a license that ends, a way to look after a
clinic's install that the clinic's own administrator does not have, and a way
to stop updates reaching a clinic that stops paying — without an online check,
and without ever hiding a clinic's records from it
(`plans/DEVELOPER_AND_LICENSING_PLAN.md`, owner decisions L-1 to L-10).

## Decision

**A license key and a Developer Pass are signed tokens.** `VCS1.<payload>.<signature>`,
base64url, Ed25519 (`vcs/licensing/tokens.py`). The payload names its kind
(`license` or `dev_pass`), the one install it is for (`install_id`, a UUID
setup writes into `.env`), who and when; the signature is checked before a
byte of the payload is trusted. One vendor signing key signs both; `kind`
keeps them apart. A pass lasts 12 hours at most, whatever it says.

**Trust is a constant in the source, and nothing else.** The public keys the
app accepts are `TRUSTED_KEYS` in `vcs/licensing/trusted_keys.py`. No
environment variable, setting, file or request can add one — a configurable
trust list would be a documented free-license switch. Tests trust an
ephemeral key through `trust_for_tests()`, which only `tests/conftest.py` and
`scripts/test_launcher.py` call. The app can only verify; the vendor tool
(`scripts/vendor/vcs_vendor.py`) signs, with a key that never enters the
repository (`DEVELOPER_GUIDE.md`).

**The license's states** are worked out from the key, the install ID and the
clock: active; expiring (within the warning window); grace (expired, within
the grace window); read-only; and three that are read-only too — invalid,
missing, and clock wrong (the clock more than a day behind the latest moment
the app has seen). Both windows are in the signed license (14 days each by
default), so the vendor can give one clinic longer without a code change.

**Read-only begins at a sign-in, never mid-task.** A session keeps the state it
signed in under; one hook (`vcs/web/readonly.py`) refuses writes only for a
session that signed in under a read-only state while the state is still
read-only. Someone halfway through a visit finishes it; the next sign-in is
read-only; a new key ends read-only for every session at once. What still
works is one allowlist: every page, search, print and export, backups and
restore, updates, user administration, one's own password, the license key,
the full data export, and notes on animals already admitted. Payments do not
(A7): that is the reason to renew.

**What only the vendor does** is in the Developer area, reached with a
Developer Pass for this install — never a password, a role or a permission,
so the clinic's system Admin, who holds every permission, cannot reach it.
The money setting, the palette, the monitoring ping and the vendor's message
are gated `developer` in the settings registry, so `POST /settings` refuses
them from everyone. Every vendor action is in `developer_audit`, which the
clinic can read and nothing prunes or deletes.

**Updates need a token per clinic.** The repository is private; each clinic's
read-only GitHub token is a file in its data folder, read at every call.
Revoking one stops that clinic's updates and nothing else.

## The honest limit

The app runs on the clinic's computer, with its database, its Python source and
its clock. **Whoever controls that machine can edit the code, the database or
the clock.** Nothing here changes that, and nothing pretends to. What holds:

- There is **no supported way** around the license or into the Developer area:
  no password in the source, no setting, no environment variable, no role or
  permission. Getting around it takes deliberate editing of code or files.
- A license cannot be **forged**: the app can only verify, never sign.
- Tampering is **detectable**: an edited key fails its signature, and a clock
  wound back is noticed.
- Stopping a clinic's **updates** is real: revoke its token.

## Costs

- The vendor's signing key is the whole scheme: lost, no new key verifies;
  leaked, anyone can sign. Its custody and rotation are in
  `DEVELOPER_GUIDE.md`; a release must trust a key before any install can use
  it, and setup does not finish without a license.
- Read-only refuses payments on existing bills. A clinic taking cash it cannot
  record is the price of the lever; moving the payment routes onto the
  allowlist is one line in one registry.
- A clock wound back more than a day makes the install read-only until it is
  corrected — a real clock fault reads the same as a deliberate one. So does
  a clock that was *ahead* for a while and has been corrected, and there the
  clinic's clock is already right: a license key newer than the one held and
  signed within the last two days vouches for the clock and ends it
  (`state.enter_key`; decided 2026-10-02, held by
  `test_a_new_key_ends_a_lockout_from_a_clock_that_was_ahead` and
  `test_a_key_that_does_not_vouch_for_the_clock_leaves_the_lockout`). Only
  the vendor can make such a key.

## Held by

| Rule | Test |
|---|---|
| a token is verified before it is read; tampering, other installs, wrong kinds and long passes are refused | `test_licensing_tokens.py` |
| no production entry point trusts a key at run time; no `PRIVATE KEY` in the repository | `test_licensing_tokens.py` |
| no role or permission reaches the Developer area; the Admin is refused on every page | `test_developer_access.py` |
| each state, the clock rollback, renewal unlocking at once, read-only at a sign-in | `test_license.py` |
| every writing endpoint is allowed or refused in read-only (seam rule 13) | `test_license.py` |
| the vendor's settings are refused by `POST /settings` (seam rule 14) | `test_vendor_settings.py` |
| no secret appears in any output (seam rule 15) | `test_secrets.py` |
| every guard above is proven by putting its bug back | `scripts/prove_guards.py --all` |
