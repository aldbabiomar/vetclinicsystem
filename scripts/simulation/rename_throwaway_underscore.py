"""Rename throwaway `_` variables so they stop shadowing gettext's `_`.

`_` is both the gettext convention and Python's conventional throwaway. Once a
function assigns to `_` ANYWHERE, Python makes `_` local for the whole
function, so an earlier `_("...")` in that same function raises

    UnboundLocalError: cannot access local variable '_'

...at request time, not import time — which is why a green import and a clean
GET sweep both said nothing was wrong, and only a POST that actually reached
the flash surfaced it.

Targets Name nodes in a STORE context only, so a `_(...)` call is never
touched. Offsets go through the same UTF-8 conversion as wrap_flashes.py:
ast col_offset is a byte offset and this codebase is full of em-dashes.
"""
import ast
import sys

NEW_NAME = "_unused"


def rewrite(path, check=False):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    # only bother if this module actually uses _() for gettext
    uses_gettext = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
        for n in ast.walk(tree))
    if not uses_gettext:
        return 0

    targets = [n for n in ast.walk(tree)
               if isinstance(n, ast.Name) and n.id == "_"
               and isinstance(n.ctx, (ast.Store, ast.Del))]
    if not targets:
        return 0

    lines = src.splitlines(keepends=True)
    starts = [0]
    for l in lines:
        starts.append(starts[-1] + len(l))

    def off(lineno, col):
        line = lines[lineno - 1]
        return starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", "ignore"))

    out = src
    for n in sorted(targets, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        a = off(n.lineno, n.col_offset)
        b = off(n.end_lineno, n.end_col_offset)
        assert out[a:b] == "_", f"{path}:{n.lineno} expected '_', found {out[a:b]!r}"
        out = out[:a] + NEW_NAME + out[b:]

    if not check:
        ast.parse(out)
        open(path, "w", encoding="utf-8").write(out)
    return len(targets)


if __name__ == "__main__":
    check = "--check" in sys.argv
    total = 0
    for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
        n = rewrite(p, check)
        if n:
            print(f"  {p}: {n} throwaway `_` renamed to {NEW_NAME}")
            total += n
    print(f"TOTAL: {total}")
