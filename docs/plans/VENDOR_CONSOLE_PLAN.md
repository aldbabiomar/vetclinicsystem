# Vendor Console and setup codes

**Status:** done 2026-10-01 (the log below). Owner's decisions taken 2026-10-01. Follows
`DEVELOPER_AND_LICENSING_PLAN.md` (done), whose trust model this keeps.

## 1. Why

Issuing licenses worked from the command line: one command per license,
Developer Pass and check, an installation ID sent from the clinic to the
vendor before a new clinic could finish setup, and a spreadsheet of who holds
what. The owner asked for it to be frictionless.

## 2. Decisions

| # | Decision |
|---|---|
| **V-1** | **A Vendor Console**: a small web app that runs **only on the vendor's own computer** (`127.0.0.1`), never at a clinic. It holds the signing key while unlocked and replaces the commands and the spreadsheet: a list of clinics with each license's state, new clinics, renewals with the date prefilled, Developer Passes, first-time key creation. |
| **V-2** | **One setup code per new clinic.** The console chooses the clinic's installation ID and signs its license before the install; setup takes the one code (`--setup-code`, or asked for on a new install) and needs nothing sent back. |
| **V-3** | **The setup code carries the clinic's secrets too**: the GitHub update token and, when used, the monitoring ping URL, so one paste finishes the install. The code is therefore a secret: shown once, never stored by the console, carried on a USB stick or sent privately. |
| **V-4** | **Signing never moves into the clinic's app** — not its setup, not its Developer area. A clinic's computer holds only public keys (licensing plan §2, §4.3); the one-time edit of `trusted_keys.py` stays a code change. |

Chosen by the plan, not asked (conventional): the console lives beside the key
tool (`scripts/vendor/`), keeps its ledger in a SQLite file next to the key
(`~/vcs-vendor-keys/console.sqlite3`), and reuses `vcs_vendor.py` for every
key operation, so the command line and the console cannot drift.

## 3. Design

**The setup code** is `VCSSETUP1.<base64url JSON>.<checksum>`: the signed
license (which already names the installation ID and the clinic), the money
setting, the palette, and the optional token and ping URL. The checksum
catches a damaged paste before anything is written. It is not signed: whoever
runs setup controls that computer anyway, and the license inside is signed.
It is made and read by functions in `setup.py`, which the console imports, so
there is one definition.

**Setup** reads the code before writing `.env`, puts the code's installation
ID there (refusing a code for another ID on an existing install), and after the
schema applies the money setting, the license, the palette, the clinic's name
(if none is set), the ping URL and the token. `--enable-updates` moves the
token file into the data folder, as it does the license.

**The console's guards**, because a signing service on `127.0.0.1` is reachable
by any web page the vendor has open:

- it listens on the loopback address only;
- it refuses a request whose `Host` is not `127.0.0.1` or `localhost` (DNS
  rebinding);
- every form carries a CSRF token;
- the key is unlocked with its passphrase, held in memory only, and locked
  after 30 idle minutes or on **Lock**;
- the token and the ping URL are never written to the ledger; a setup code,
  a Developer Pass and a secret are sent with `Cache-Control: no-store`.

## 4. Done means

1. A new clinic is installed with one pasted code, nothing sent back.
2. Renewals and passes come from the console with no command line.
3. Each guard above has a test that fails with the guard removed
   (`scripts/prove_guards.py`).
4. `DEVELOPER_GUIDE.md`, `README.md` and the vendor manuals describe the
   console as the way to work, the commands as the fallback.

## 5. Progress log

- **2026-10-01 — built.**
  - `scripts/vendor/console.py` with `console_templates/` and `console_static/`:
    first-run key (or an existing one) and the line for `trusted_keys.py`;
    unlock / lock; the clinic list with each license's state today; *New
    clinic* (installation ID chosen, license signed, one setup code shown
    once); *Clinic already installed*; renewal prefilled a year past the
    current end (or today, if that has passed); Developer Passes (1-12 hours);
    a setup code again for a clinic made here. A banner on every page while
    the key is not yet in `TRUSTED_KEYS`. Records: SQLite, mode 0600, beside
    the key; refuses a folder inside the code.
  - `setup.py`: `make_setup_code` / `parse_setup_code` (one definition, the
    console imports it), `read_setup_code` (`--setup-code`, or asked for on a
    new install), the code's installation ID written to `.env`,
    `ensure_setup_code_matches`, `apply_setup_code` (palette, the clinic's name
    when none is set, ping URL, token; a secret reported, never printed),
    `move_secrets_into` (license and token into the data folder).
  - **Tests:** `tests/test_vendor_console.py` (22) and `tests/test_setup_code.py`
    (12). Nine mutations, all proven: the loopback-only answer, CSRF, nothing
    signed while locked, the idle lock, no secret in the ledger, a damaged code
    refused, a code for another installation refused, the token moved with the
    license, no secret printed. The console was also run for real and walked in
    a browser (first key, unlock, a new clinic, its page), and
    `scripts/simulation/native_install.py` now installs from a setup code, from
    the working tree, with Docker off PATH: the code's ID, palette, name, ping
    URL and an owner-only token file all arrived, and nothing secret was
    printed.
  - **Docs:** `DEVELOPER_GUIDE.md` (the console; the install walkthrough by
    setup code), `README.md` (current status; installing by setup code; the
    vendor's tools; Arabic, the rewards card, Clean Up and monitoring, which it
    had not mentioned), `NATIVE_POSTGRESQL.md`, `CLAUDE.md`'s layout, the docs
    index; the two vendor manuals point to the console.

  **Suite:** IQ **1828 passed, 0 skipped**; JO **1828 passed, 0 skipped**; no
  database 811 passed.
