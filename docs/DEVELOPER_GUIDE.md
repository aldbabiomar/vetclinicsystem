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
