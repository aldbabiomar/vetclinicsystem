#!/usr/bin/env python3
"""
Starts the app exactly as run.py does, after trusting the test environment's
ephemeral vendor key (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §14.4), so the
throwaway clinic has a license and the browser tests a Developer Pass.

scripts/isolated_test_env.sh runs this; nothing else may. The production
launchers run run.py, which never trusts a key at run time
(tests/test_licensing_tokens.py holds that).

    test_launcher.py <trusted.key>      # the file holds "<kid> <public key hex>"
"""
import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

kid, public_hex = Path(sys.argv[1]).read_text().split()
from vcs.licensing import tokens  # noqa: E402

tokens.trust_for_tests(kid, bytes.fromhex(public_hex))
os.chdir(REPO)
sys.argv = [str(REPO / "run.py")]
runpy.run_path(str(REPO / "run.py"), run_name="__main__")
