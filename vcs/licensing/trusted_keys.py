"""
The public keys whose signatures this app accepts: {kid: 32 raw Ed25519
public-key bytes}.

Constants in the source, by design (plan §4.3). A trust list that a setting,
an environment variable or a file could extend would be a documented way to
mint free licenses, so there is none: the only other entry point is
tokens.trust_for_tests(), which only the test suite and the test launcher
call (tests/test_licensing_tokens.py holds that).

Empty until the vendor generates the signing key:
    python3 scripts/vendor/vcs_vendor.py keygen --out <outside the repo>
prints the kid and the public key to add here. To rotate, add the new key in
one release and remove the old one in a later one, so every install trusts
both during the changeover (docs/DEVELOPER_GUIDE.md).
"""

TRUSTED_KEYS = {}
