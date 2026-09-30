# Developer guide — licenses, Developer Passes and the signing key

For the vendor: the person who installs VetClinicSystem at a clinic, issues its
license and, when needed, signs in to its Developer area. The design is
`plans/DEVELOPER_AND_LICENSING_PLAN.md`; this guide is how to run it. Sections
are added as the plan's phases land.

## What the app can and cannot do

A clinic's install can only **verify** a license or a Developer Pass: it holds
public keys, never the private one, so nothing on the clinic's computer can make
a key it would accept. The trusted public keys are constants in
`vcs/licensing/trusted_keys.py` — no setting, environment variable or file can
add one.

Whoever controls the clinic's computer can still edit its code, its database or
its clock. The license cannot be forged, an edited license fails its signature,
and a clock wound back is noticed; but nothing pretends that a machine's owner
cannot change the machine. Stopping a clinic's **updates** is real: revoke its
GitHub token.

## The signing key

One Ed25519 key signs both licenses and Developer Passes. Make it once, on your
own computer, **outside this repository** (the tool refuses a path inside it):

```bash
python3 scripts/vendor/vcs_vendor.py keygen --out ~/vcs-vendor-keys/signing.pem
```

It asks for a passphrase (at least 12 characters), writes the key encrypted with
it, and prints two lines to add to `TRUSTED_KEYS` in
`vcs/licensing/trusted_keys.py`. A release carrying that change is what makes
installs trust your licenses.

**Custody.**
- Keep **two encrypted copies offline** (say, two USB drives kept apart). The
  passphrase goes somewhere other than the drives.
- **Lost** key: no renewal can be issued until a release trusts a new key, and
  every clinic updates to it.
- **Leaked** key: anyone holding it can mint licenses until a release stops
  trusting it. Rotate at once.

**Rotation.** Make the new key; add its line to `TRUSTED_KEYS` in one release,
next to the old one, so every install trusts both. Issue new licenses with the
new key. Remove the old line only in a later release, once every clinic has
updated.

## Issuing a license

Each install prints its **installation ID** during setup (it is also in the
install's `.env` as `VETCLINICSYSTEM_INSTALL_ID`, and on its License page). A
license is signed for that one ID and works nowhere else.

```bash
python3 scripts/vendor/vcs_vendor.py license --key ~/vcs-vendor-keys/signing.pem \
    --install-id <ID> --clinic-name "Clinic name" --days 365
```

`--expires YYYY-MM-DD` instead of `--days`. The warning period before expiry and
the grace period after it are in the license: 14 days each unless you pass
`--warn-days` / `--grace-days`. Send the printed key to the clinic however you
like; spaces and line breaks added on the way (WhatsApp wraps it) are ignored.

## A Developer Pass

Signed for one install, for a few hours (8 by default, 12 at most whatever it
says):

```bash
python3 scripts/vendor/vcs_vendor.py pass --key ~/vcs-vendor-keys/signing.pem \
    --install-id <ID> --developer "Your name" --hours 4
```

Nothing secret is stored at the clinic. The pass's name is what the clinic sees
in the record of what the developer did there.

## Checking a key

```bash
python3 scripts/vendor/vcs_vendor.py inspect '<key>'
```

prints what the key says and whether this checkout's trusted keys accept its
signature.

## A clinic without Docker

`docs/NATIVE_POSTGRESQL.md`: create the role (owner of the database, with
CREATEDB, nothing more) and run setup with `--db-mode native --database-url …`.
Backups, restores and the restore check then use the PostgreSQL client tools on
the machine, never Docker; Developer → System shows which ones.

## Setup needs a license

`setup.py` does not finish without a license key that verifies for the
installation it is setting up (there is no trial). It prints the installation
ID, then takes the key from `--license-key` or asks for it. **So the release a
clinic installs must already trust your key** (`TRUSTED_KEYS`): until it does,
every key is "signed by a key this version does not know", and no install can
finish.

## The license's states

| State | When | What the clinic sees |
|---|---|---|
| Active | more than the warning period left | nothing |
| Expiring soon | within the warning period | a banner, to those who can enter a key |
| Grace | expired, within the grace period | a banner to everyone, with the date it becomes read-only |
| Read-only | past the grace period | a red banner; anything that saves is refused with a page saying why |
| Not valid / No license key / Clock wrong | the key fails, is missing, or the computer's clock was wound back more than a day | treated as read-only, with its own message |

Read-only begins at a **sign-in**: someone already working keeps working until
they sign out (12 hours at most). What still saves while read-only: signing in,
one's own password, the license key, backups, restore, updates, user
administration, and notes and owner calls on animals already admitted.
Payments do not. Entering a new key unlocks every session at once.

The clinic enters a key on **Settings → License**; you can do the same in the
Developer area. Every key entered, accepted or refused, is in the Developer
Audit, which the clinic can read and nothing deletes.

## What only you set: Configuration, Monitoring, Updates

Three things are yours, not the clinic's. The clinic's Settings page shows them
without a way to change them, and its POST refuses them from anyone, the
clinic's system Admin included (`vcs/web/vendor_settings.py`). You set them in
the Developer area, and each change is in the Developer Audit:

- **Configuration** — the **money setting** (IQ or JO) and the **color
  palette**. The money setting can be changed only until the first price or
  amount is recorded; after that it is locked for you too, because every stored
  amount is in its currency. Until it is chosen, the clinic's billing,
  payments, point of sale and price list stay locked and staff are told the
  vendor has to finish setup. `setup.py --money-setting IQ|JO` chooses it at
  install time, so a new clinic is ready in one step.
- **Monitoring** — the daily status ping's URL (https only). It is a
  credential: anyone who has it can send a fake ping and silence the alert
  that fires when the clinic's machine goes dark. So neither the clinic's
  change log nor the Developer Audit records it, only that it was set or
  cleared, and the page shows it masked. Use a different URL for each clinic.
- **Updates** — the clinic's **GitHub access token**, and the same
  check / update / roll back controls the clinic has on Settings → Updates.

## The update token, one per clinic

The repository is private, so each install needs a token to download a
release. Give every clinic **its own** token; then stopping one clinic's
updates is revoking one token, and nothing else changes.

1. On GitHub: *Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token*. Resource owner: the account that
   owns `aldbabiomar/vetclinicsystem`; *Only select repositories*: that one
   repository; permissions: **Contents: Read-only** and nothing else. Name it
   after the clinic. Pick an expiry you will remember to renew — or none, if
   you would rather revoke it by hand.
2. In the clinic's Developer area: **Updates → Replace the access token**,
   paste, **Save token**, then **Test connection**. It should say
   *Connected: the latest release is v…*.

The token is kept in the data folder, in a file only the app's user can read
(`github_token`, mode 0600), read at every call — a replaced token works at
once, with no restart. It is never in `.env`, a log, an error message, a job
result or the audit; the page shows its last four characters.

**Revoking.** Delete the clinic's token on GitHub (same page as step 1). The
clinic keeps running the version it has; only updates stop.

**What the clinic sees when its token stops working:**

| Cause | Message on Updates |
|---|---|
| No token set (or you removed it) | "No access token is set for updates on this install, so updates are off. Your vendor sets one in the Developer area." |
| Token revoked or expired | "GitHub rejected the access token for this install — it may have expired or been revoked." |
| Token cannot see the repository | "GitHub answered “not found or no access”: …" — GitHub answers 404, not 403, for a private repository a token cannot see |

## Your tools at a clinic

- **System** shows what the app already knows about itself: version and
  uptime, the database (reachable, its PostgreSQL version, how it runs, where
  `pg_dump` and `pg_restore` were found), the latest daily self-check with its
  findings and the free space it read, the last backup, restore and restore
  check, the database changes applied and any missing, and the last lines of
  the error log with secrets, contact details and quoted values removed. **Run
  the self-check now** runs and records the same check the scheduler does.
- **Support → Download a support bundle** gives you a ZIP to diagnose from
  without a remote session: the facts above, the clinic's non-sensitive
  settings (a fixed list — a setting added later is left out until someone
  adds it to `support_bundle.ALLOWED_SETTINGS`), the license's state, and the
  last 500 lines of the error and update logs, redacted. No clinic records,
  no secrets; its README says so and says the clinic may read it first.
- **Support → Restore administrator access** is for when nobody at the clinic
  can sign in as an administrator. It gives one active system administrator a
  temporary password, shown to you once and stored nowhere: they must choose
  their own at their next sign-in, any session they have ends, and their
  sign-in lockout is cleared. The clinic's change log records it under your
  name, and so does the Developer Audit.
- **Vendor Message** puts a short plain-text message at the top of every page,
  labelled "Message from your vendor": information or warning, with an
  optional last day. Turning it off keeps the text; clearing removes it.
- **Data Export** makes the clinic's full export — every table as CSV, every
  attachment, the schema and a manifest — exactly as Settings → Data Export
  does for the clinic's own administrators, also while read-only. The three
  newest are kept in `<data dir>/exports/`.

Everything here is recorded in the Developer Audit, which the clinic can read.
