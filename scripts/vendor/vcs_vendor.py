#!/usr/bin/env python3
"""
The vendor's tool: make the signing key, sign licenses and Developer Passes,
and inspect a token (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §4.4).

It runs on the vendor's own machine. The app never imports it -- the app can
only verify -- and it never writes a key inside this repository.

    vcs_vendor.py keygen  --out ~/vcs-vendor-keys/signing.pem
    vcs_vendor.py license --key KEY --install-id ID --clinic-name NAME (--days N | --expires YYYY-MM-DD)
                          [--grace-days 14] [--warn-days 14]
    vcs_vendor.py pass    --key KEY --install-id ID --developer NAME [--hours 8]
    vcs_vendor.py inspect TOKEN

Key custody (docs/DEVELOPER_GUIDE.md): keep two encrypted copies offline. A
lost key means no renewal until a release trusts a new one; a leaked key
means anyone can mint licenses until a release stops trusting it.
"""
import argparse
import base64
import getpass
import hashlib
import json
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[2]
PREFIX = "VCS1"
DEFAULT_GRACE_DAYS = DEFAULT_WARN_DAYS = 14      # plan A1, as the owner confirmed
DEFAULT_PASS_HOURS = 8


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _utc(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def public_bytes(private_key):
    return private_key.public_key().public_bytes(serialization.Encoding.Raw,
                                                 serialization.PublicFormat.Raw)


def kid_for(public):
    """A short, stable name for a public key."""
    return "k" + hashlib.sha256(public).hexdigest()[:12]


def sign(private_key, payload):
    """A token over the payload's exact JSON bytes."""
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"{PREFIX}.{_b64(data)}.{_b64(private_key.sign(data))}"


def license_payload(private_key, install_id, clinic_name, expires_at, *, issued_at=None,
                    grace_days=DEFAULT_GRACE_DAYS, warn_days=DEFAULT_WARN_DAYS):
    issued_at = issued_at or datetime.now(timezone.utc)
    return {"v": 1, "kind": "license", "kid": kid_for(public_bytes(private_key)),
            "install_id": install_id, "license_id": "L-" + uuid.uuid4().hex[:12],
            "clinic_name": clinic_name, "issued_at": _utc(issued_at), "expires_at": _utc(expires_at),
            "grace_days": grace_days, "warn_days": warn_days, "entitlements": {}}


def pass_payload(private_key, install_id, developer, *, hours=DEFAULT_PASS_HOURS, issued_at=None):
    issued_at = issued_at or datetime.now(timezone.utc)
    return {"v": 1, "kind": "dev_pass", "kid": kid_for(public_bytes(private_key)),
            "install_id": install_id, "pass_id": "P-" + uuid.uuid4().hex[:12],
            "developer": developer, "issued_at": _utc(issued_at),
            "expires_at": _utc(issued_at + timedelta(hours=hours))}


def refuse_inside_repo(path):
    """A private key never lives in the repository, where one `git add .`
    would publish it."""
    resolved = Path(path).expanduser().resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise SystemExit(f"Refusing to write a key inside the repository ({REPO}). "
                         "Keep it outside, in two encrypted offline copies.")
    return resolved


def keygen(out, passphrase):
    out = refuse_inside_repo(out)
    if out.exists():
        raise SystemExit(f"{out} already exists; not overwriting a signing key.")
    if len(passphrase) < 12:
        raise SystemExit("Use a passphrase of at least 12 characters.")
    key = Ed25519PrivateKey.generate()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode("utf-8"))))
    out.chmod(0o600)
    public = public_bytes(key)
    return kid_for(public), public


# PEM headers, each split in two so the scan for committed keys
# (tests/test_licensing_tokens.py) does not take this file for one.
_ENCRYPTED_PEM = b"-----BEGIN ENCRYPTED PRIVATE" b" KEY-----"
_PLAIN_PEM = b"-----BEGIN PRIVATE" b" KEY-----"


def load_key(path, passphrase):
    """The signing key at `path`, or a plain message saying why it will not
    open -- never a Python traceback for a mistyped passphrase. Which message
    is decided by what the file is, not by the wording of the library's
    errors."""
    path = Path(path).expanduser()
    try:
        data = path.read_bytes()
    except OSError as e:
        raise SystemExit(f"No signing key could be read at {path} ({e.strerror}). Check the --key path.")
    if _ENCRYPTED_PEM not in data:
        if _PLAIN_PEM in data:
            raise SystemExit(f"The key at {path} is not encrypted, so keygen did not make it. "
                             "Use the signing key keygen wrote.")
        raise SystemExit(f"{path} is not a signing key. Check the --key path.")
    try:
        key = serialization.load_pem_private_key(data, password=passphrase.encode("utf-8") or None)
    except (ValueError, TypeError):
        raise SystemExit(f"That passphrase does not open the signing key at {path}. "
                         "Run the command again and type it carefully; nothing shows while you type.")
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit(f"The key at {path} is not an Ed25519 signing key, so keygen did not make it.")
    return key


def inspect(token):
    """The payload, and whether this checkout's trusted keys accept its signature."""
    sys.path.insert(0, str(REPO))
    from vcs.licensing import tokens
    text = "".join(token.split())
    try:
        payload = json.loads(base64.urlsafe_b64decode(text.split(".")[1] + "==="))
    except (IndexError, ValueError):
        return None, "not a token"
    try:
        tokens._signed_payload(text)
        verdict = "signature: valid, from a trusted key"
    except tokens.TokenError as e:
        verdict = f"signature: NOT accepted ({e.code})"
    return payload, verdict


def _expiry(args):
    if args.expires:
        day = date.fromisoformat(args.expires)
        return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
    return datetime.now(timezone.utc) + timedelta(days=args.days)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", required=True)
    lic = sub.add_parser("license")
    lic.add_argument("--key", required=True)
    lic.add_argument("--install-id", required=True)
    lic.add_argument("--clinic-name", required=True)
    when = lic.add_mutually_exclusive_group(required=True)
    when.add_argument("--days", type=int)
    when.add_argument("--expires")
    lic.add_argument("--grace-days", type=int, default=DEFAULT_GRACE_DAYS)
    lic.add_argument("--warn-days", type=int, default=DEFAULT_WARN_DAYS)
    ps = sub.add_parser("pass")
    ps.add_argument("--key", required=True)
    ps.add_argument("--install-id", required=True)
    ps.add_argument("--developer", required=True)
    ps.add_argument("--hours", type=float, default=DEFAULT_PASS_HOURS)
    ins = sub.add_parser("inspect")
    ins.add_argument("token")
    args = ap.parse_args(argv)

    if args.cmd == "keygen":
        passphrase = getpass.getpass("New passphrase for the signing key: ")
        if passphrase != getpass.getpass("Again: "):
            raise SystemExit("The two passphrases differ.")
        kid, public = keygen(args.out, passphrase)
        print(f"Signing key written to {Path(args.out).expanduser()} (encrypted).")
        print("Add this to vcs/licensing/trusted_keys.py, in TRUSTED_KEYS:")
        print(f'    "{kid}": bytes.fromhex("{public.hex()}"),')
    elif args.cmd == "inspect":
        payload, verdict = inspect(args.token)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if payload else "not a token")
        print(verdict)
    else:
        key = load_key(args.key, getpass.getpass("Passphrase for the signing key: "))
        if args.cmd == "license":
            payload = license_payload(key, args.install_id, args.clinic_name, _expiry(args),
                                      grace_days=args.grace_days, warn_days=args.warn_days)
        else:
            payload = pass_payload(key, args.install_id, args.developer, hours=args.hours)
        print(sign(key, payload))


if __name__ == "__main__":
    main()
