"""
Licenses and Developer Passes (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md).

Both are Ed25519-signed tokens made by the vendor's tool
(scripts/vendor/vcs_vendor.py) and checked here. This package can only
VERIFY: it holds public keys, never a private one, so nothing an install
contains can make a token it would accept. The trusted public keys are
constants in trusted_keys.py; nothing read at run time -- no environment
variable, setting, file or request -- can add one.
"""
