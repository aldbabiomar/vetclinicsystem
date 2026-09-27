# Predecessor-era simulation scripts (archived)

These drove, fixed or checked the two predecessor apps, VetClinicSystem IQ and
VetClinicSystem JO, before the merge. They are kept for the record, because
the audit documents and some test docstrings cite them. None of them runs
against this codebase:

- **`ar_batch*.py`, `wrap_*.py`, `fix_*.py`, `unfix_option_data.py` and
  `rename_throwaway_underscore.py`** were one-off codemods. They wrapped the
  predecessor apps' templates for translation and repaired their `<option>`
  values. The work they did is in the templates now.
- **`repro_*.py` and `verify_fixes.py`** each reproduced one finding of the
  2026-09-11 simulation audit against the predecessor apps' text ids
  (`INV301`, `OW…`). Every one of those findings has a pytest guard now.
- **`prove_guards.py` and `prove_rewards_guards.py`** re-proved guards by
  editing the predecessor clones. `scripts/prove_guards.py` does that for
  this codebase, from a registry of mutations.
- **`restart_test_apps.sh`** is `scripts/isolated_test_env.sh restart`, older.

The live tools are in `scripts/simulation/`: the day in the clinic, the hostile
sweeps, the browser walks, the localisation checkers and the seam audit.
