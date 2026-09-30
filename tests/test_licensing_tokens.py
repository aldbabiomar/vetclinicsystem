"""
Licenses and Developer Passes: what the verifier accepts, and who can make
it accept something (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §4, §14.1).

The property everything else rests on: the app can only VERIFY. A token is
accepted only if a trusted key signed its exact bytes, the trusted keys are
constants in the source, and the one way to add a key at run time is called
only by the tests and the test launcher. Every guard is paired with a
control, so "refused for the right reason" is told apart from "refused".

Pure tier.
"""
import ast
import base64
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import source_files
from vcs.licensing import tokens

NOW = datetime.now(timezone.utc)


def _parts(token):
    prefix, payload, signature = token.split(".")
    return prefix, base64.urlsafe_b64decode(payload + "==="), signature


def _with_payload(token, payload_bytes):
    """The same signature over different bytes."""
    prefix, _, signature = token.split(".")
    return f"{prefix}.{base64.urlsafe_b64encode(payload_bytes).rstrip(b'=').decode()}.{signature}"


def _refused(token, kind=tokens.LICENSE, install_id=None, now=NOW, *, vendor):
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(token, kind, install_id or vendor.install_id, now)
    return e.value.code


# ---------------------------------------------------------------------------
# Controls: what must be accepted
# ---------------------------------------------------------------------------

def test_control_a_valid_license_verifies(vendor):
    payload = tokens.verify(vendor.license(), tokens.LICENSE, vendor.install_id, NOW)
    assert payload["clinic_name"] == "Test Clinic" and payload["grace_days"] == 14 == payload["warn_days"]


def test_control_a_valid_pass_verifies(vendor):
    assert tokens.verify(vendor.dev_pass(), tokens.DEV_PASS, vendor.install_id, NOW)["developer"] == "Test Developer"


def test_control_a_key_pasted_with_spaces_and_line_breaks_verifies(vendor):
    """Keys arrive through WhatsApp, wrapped."""
    token = vendor.license()
    mangled = "  " + "\n".join(token[i:i + 30] for i in range(0, len(token), 30)) + " \n"
    assert tokens.verify(mangled, tokens.LICENSE, vendor.install_id, NOW)["kind"] == "license"


def test_control_an_expired_license_still_verifies(vendor):
    """Expiry is a state (warning, grace, read-only), not a forgery."""
    old = vendor.tool.license_payload(vendor.key, vendor.install_id, "Test Clinic", NOW - timedelta(days=90),
                                      issued_at=NOW - timedelta(days=455))
    assert tokens.verify(vendor.tool.sign(vendor.key, old), tokens.LICENSE, vendor.install_id, NOW)


# ---------------------------------------------------------------------------
# Guards: what must be refused, each for its own reason
# ---------------------------------------------------------------------------

def test_a_changed_payload_is_refused(vendor):
    """GUARD. The clinic name, the expiry: any byte changed breaks it."""
    token = vendor.license()
    _, payload, _ = _parts(token)
    later = json.loads(payload)
    later["expires_at"] = (NOW + timedelta(days=3650)).isoformat()
    assert _refused(_with_payload(token, json.dumps(later).encode()), vendor=vendor) == "signature"


def test_a_changed_signature_is_refused(vendor):
    prefix, payload, signature = vendor.license().split(".")
    flipped = ("A" if signature[5] != "A" else "B")
    assert _refused(f"{prefix}.{payload}.{signature[:5]}{flipped}{signature[6:]}", vendor=vendor) == "signature"


def test_a_key_signed_by_an_unknown_key_is_refused(vendor):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    stranger = Ed25519PrivateKey.generate()
    token = vendor.tool.sign(stranger, vendor.tool.license_payload(
        stranger, vendor.install_id, "Test Clinic", NOW + timedelta(days=30)))
    assert _refused(token, vendor=vendor) == "unknown_key"


def test_a_pass_is_not_a_license_and_a_license_is_not_a_pass(vendor):
    assert _refused(vendor.dev_pass(), tokens.LICENSE, vendor=vendor) == "kind"
    assert _refused(vendor.license(), tokens.DEV_PASS, vendor=vendor) == "kind"


def test_a_key_for_another_install_is_refused_and_says_whose_it_is(vendor):
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(vendor.license(install="another-install"), tokens.LICENSE, vendor.install_id, NOW)
    assert e.value.code == "install"
    assert "another-install" in e.value.message and vendor.install_id in e.value.message


def test_a_pass_longer_than_twelve_hours_is_refused(vendor):
    """GUARD (A2), whatever the pass says."""
    assert _refused(vendor.dev_pass(hours=12.5), tokens.DEV_PASS, vendor=vendor) == "too_long"


def test_control_a_twelve_hour_pass_is_allowed(vendor):
    assert tokens.verify(vendor.dev_pass(hours=12), tokens.DEV_PASS, vendor.install_id, NOW)


def test_a_pass_from_the_future_is_refused(vendor):
    """Issued more than ten minutes after the clinic clock's now."""
    later = vendor.tool.pass_payload(vendor.key, vendor.install_id, "Dev", issued_at=NOW + timedelta(minutes=30))
    assert _refused(vendor.tool.sign(vendor.key, later), tokens.DEV_PASS, vendor=vendor) == "future"


def test_an_expired_pass_is_refused(vendor):
    old = vendor.tool.pass_payload(vendor.key, vendor.install_id, "Dev", hours=2, issued_at=NOW - timedelta(hours=3))
    assert _refused(vendor.tool.sign(vendor.key, old), tokens.DEV_PASS, vendor=vendor) == "expired"


@pytest.mark.parametrize("field, value", [
    ("license_id", None), ("grace_days", "14"), ("grace_days", True), ("entitlements", []),
    ("expires_at", "next year"), ("expires_at", "2030-01-01T00:00:00"), ("v", 2)])
def test_a_signed_key_missing_what_it_needs_is_refused(vendor, field, value):
    """Signed, but not a v1 license: a missing field, a wrong type, a time
    with no offset, a version this app does not know."""
    payload = vendor.tool.license_payload(vendor.key, vendor.install_id, "Test Clinic", NOW + timedelta(days=30))
    payload[field] = value
    assert _refused(vendor.tool.sign(vendor.key, payload), vendor=vendor) in ("fields", "version")


@pytest.mark.parametrize("garbage", ["", "hello", "VCS1..", "VCS1.!!!.???", "VCS2.abc.def",
                                     "VCS1.bm90IGpzb24.c2lnbmF0dXJl", None, "a.b.c.d"])
def test_garbage_is_refused_never_raised_past(vendor, garbage):
    assert _refused(garbage, vendor=vendor) in ("malformed", "version", "signature", "unknown_key")


def test_every_refusal_has_a_message_for_a_person(vendor):
    """Shown in the clinic's language (a messages.Msg), and never the key."""
    token = vendor.license(install="another-install")
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(token, tokens.LICENSE, vendor.install_id, NOW)
    assert hasattr(e.value.message, "msgid") and token.split(".")[2] not in e.value.message


# ---------------------------------------------------------------------------
# Trust: nothing at run time can add a key, and the app never signs
# ---------------------------------------------------------------------------

def _production_sources():
    """Everything a clinic's install runs: the package, the launcher, setup,
    and the launchers setup writes (they are strings inside setup.py)."""
    return [*source_files.all_python(), source_files.ROOT / "setup.py",
            source_files.ROOT / "Start VetClinicSystem.command", source_files.ROOT / "Start VetClinicSystem.bat"]


def test_no_production_entry_point_trusts_a_key_at_run_time():
    """GUARD. trust_for_tests is defined in tokens.py and called only by the
    tests and scripts/test_launcher.py."""
    files = _production_sources()
    assert len(files) >= 60
    callers = [str(p.relative_to(source_files.ROOT)) for p in files if _calls_trust(p)]
    assert callers == [], f"a production entry point trusts a key at run time: {callers}"
    assert _calls_trust(source_files.ROOT / "scripts" / "test_launcher.py"), "the check cannot see a call"


def _calls_trust(path):
    """A call to trust_for_tests -- in Python, a real call (a docstring may
    name it); in a shell or batch launcher, the name at all."""
    src = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return "trust_for_tests" in src
    return any(isinstance(n, ast.Call) and "trust_for_tests" in ast.unparse(n.func)
               for n in ast.walk(ast.parse(src)))


def test_the_trusted_keys_are_constants_in_the_source():
    """GUARD. trusted_keys.py is a docstring and one literal dict: no import,
    no call, so no environment variable, setting or file can reach it."""
    tree = ast.parse(source_files.module("trusted_keys").read_text(encoding="utf-8"))
    body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    assert len(body) == 1 and isinstance(body[0], ast.Assign) and isinstance(body[0].value, ast.Dict)
    for value in body[0].value.values:
        assert isinstance(value, ast.Call) and ast.unparse(value.func) == "bytes.fromhex" \
            and all(isinstance(a, ast.Constant) for a in value.args), ast.unparse(value)


def test_the_verifier_reads_nothing_from_outside():
    """GUARD. No environment, setting, file or database in the licensing
    package's trust path."""
    for name in ("tokens", "trusted_keys"):
        src = source_files.module(name).read_text(encoding="utf-8")
        for reach in ("os.environ", "getenv", "open(", "settings", "execute(", "Path("):
            assert reach not in src, f"{name}.py reaches outside with {reach}"


def test_the_app_can_only_verify():
    """GUARD. No private key and no signing anywhere the app runs."""
    for p in _production_sources():
        if p.suffix != ".py":
            continue
        src = p.read_text(encoding="utf-8")
        assert "Ed25519PrivateKey" not in src and ".sign(" not in src, p


def test_no_private_key_is_tracked():
    """GUARD. A vendor key committed by accident would let anyone mint
    licenses. A key is a PEM block; prose that names one is not."""
    import re
    pem = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE" rb" KEY-----")
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=source_files.ROOT, capture_output=True,
                             check=True).stdout.decode().split("\0")
    assert len(tracked) > 300
    hits = [f for f in tracked if f and (source_files.ROOT / f).is_file()
            and pem.search((source_files.ROOT / f).read_bytes())]
    assert hits == []


def test_control_the_key_scan_sees_a_pem_block(vendor):
    import re
    from cryptography.hazmat.primitives import serialization
    block = vendor.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
    assert re.search(rb"-----BEGIN [A-Z ]*PRIVATE" rb" KEY-----", block)


def test_git_ignores_key_files():
    ignore = (source_files.ROOT / ".gitignore").read_text()
    assert "*.pem" in ignore and "vendor-keys/" in ignore


# ---------------------------------------------------------------------------
# The vendor tool
# ---------------------------------------------------------------------------

def test_the_vendor_tool_refuses_to_write_a_key_inside_the_repository(vendor, tmp_path, monkeypatch):
    """Against a stand-in repository, so a broken guard writes its key there
    and not into this checkout."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    monkeypatch.setattr(vendor.tool, "REPO", repo)
    with pytest.raises(SystemExit):
        vendor.tool.keygen(repo / "vendor-keys" / "signing.pem", "a long passphrase here")
    assert not (repo / "vendor-keys").exists()


def test_control_the_vendor_tool_writes_an_encrypted_key_outside_it(vendor, tmp_path):
    kid, public = vendor.tool.keygen(tmp_path / "signing.pem", "a long passphrase here")
    pem = (tmp_path / "signing.pem").read_text()
    assert "ENCRYPTED" in pem and kid == vendor.tool.kid_for(public)
    loaded = vendor.tool.load_key(tmp_path / "signing.pem", "a long passphrase here")
    assert vendor.tool.public_bytes(loaded) == public


@pytest.mark.parametrize("passphrase", ["not the passphrase", ""])
def test_a_wrong_passphrase_is_a_plain_message(vendor, tmp_path, passphrase):
    """A mistyped passphrase (or just Return) ends in one sentence, not a
    traceback ending in `ValueError: Incorrect password`."""
    vendor.tool.keygen(tmp_path / "signing.pem", "a long passphrase here")
    with pytest.raises(SystemExit) as refused:
        vendor.tool.load_key(tmp_path / "signing.pem", passphrase)
    assert str(refused.value).startswith("That passphrase does not open the signing key at")


def test_a_key_file_that_will_not_open_says_why(vendor, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    (tmp_path / "plain.pem").write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (tmp_path / "notes.txt").write_text("not a key at all")
    for path, words in ((tmp_path / "missing.pem", "No signing key could be read at"),
                        (tmp_path, "No signing key could be read at"),
                        (tmp_path / "plain.pem", "is not encrypted"),
                        (tmp_path / "notes.txt", "is not a signing key")):
        with pytest.raises(SystemExit) as refused:
            vendor.tool.load_key(path, "a long passphrase here")
        assert words in str(refused.value), (path, str(refused.value))


def test_the_vendor_tool_inspects_a_token(vendor):
    payload, verdict = vendor.tool.inspect(vendor.license())
    assert payload["kind"] == "license" and verdict.startswith("signature: valid")
