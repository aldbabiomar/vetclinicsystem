"""
A helper does not commit behind its caller's back (audit D11).

A request commits once, at the end (close_db() in vcs/web/hooks.py); an error
page rolls the whole of it back. A helper that commits part-way splits that
request into two transactions without its caller knowing: what it wrote
survives a failure that rolls back everything around it.

A few commit on purpose, and say so in their docstrings. Anything else in the
domain or the shared helpers that calls commit() fails here.
"""
import ast

import source_files

# qualified name -> why it commits
COMMITS_ON_PURPOSE = {
    "logs.prune_old_logs": "batched, so a first prune of years of history never holds one long transaction",
    "attachments.save_attachment": "the file and its row stand or fall together: a failed commit removes the file",
    "auth.log_login": "a sign-in attempt is on record even if the request fails after it; the lockout counts them",
    "auth.seed_default_roles_and_permissions": "runs at install and update (migrate.apply), never in a request",
}


def _helper_modules():
    return [*source_files.domain_modules(),
            *(source_files.module(m) for m in ("auth", "money", "clock", "messages", "core", "nav"))]


def _committing_functions(tree, prefix):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            commits = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "commit"
                          for c in ast.walk(node))
            if commits:
                out[f"{prefix}.{node.name}"] = ast.get_docstring(node) or ""
    return out


def _all_committing():
    found = {}
    for path in _helper_modules():
        found.update(_committing_functions(ast.parse(path.read_text(encoding="utf-8")), path.stem))
    return found


def test_no_helper_commits_except_on_purpose():
    """GUARD."""
    found = _all_committing()
    unexpected = sorted(set(found) - set(COMMITS_ON_PURPOSE))
    assert not unexpected, (
        "these helpers commit inside their caller's transaction; let the caller "
        "commit, or add them to COMMITS_ON_PURPOSE with the reason:\n  " + "\n  ".join(unexpected))
    stale = sorted(set(COMMITS_ON_PURPOSE) - set(found))
    assert not stale, f"no longer commit — drop them from COMMITS_ON_PURPOSE: {stale}"


def test_a_helper_that_commits_says_so():
    """GUARD. Its caller reads the docstring, not this file."""
    found = _all_committing()
    silent = [name for name in COMMITS_ON_PURPOSE if "commit" not in found.get(name, "").lower()]
    assert not silent, f"these commit without their docstring saying so: {silent}"


def test_control_a_commit_is_found():
    src = '''
def quiet(db):
    db.execute("UPDATE t SET a=1")
    db.commit()

def fine(db):
    db.execute("UPDATE t SET a=1")
'''
    assert list(_committing_functions(ast.parse(src), "m")) == ["m.quiet"]
