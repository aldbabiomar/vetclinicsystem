"""Wrap flash()/error-string literals in _() for gettext — ARABIC_LOCALIZATION_PLAN §5.2.

Locates calls with the AST (precise) and patches the source TEXTUALLY (so
comments, spacing and everything else survive). Deliberately does not use
ast.unparse: this codebase's comments are load-bearing and a reformat would
destroy them.

f-strings become gettext templates with NAMED placeholders, because a
translator has to be able to reorder them:

    flash(f"{name} is required.", "error")
        -> flash(_("%(name)s is required.", name=name), "error")

A format spec is applied before substitution rather than inside the template
(`%(pct).0f` would force every translation to carry the spec), so:

    f"{p:.0f}% discount applied."
        -> _("%(p)s%% discount applied.", p=f"{p:.0f}")

Literal % is doubled, since gettext interpolates with % when kwargs are given.

Run with --check to list what it WOULD do without writing.
"""
import ast
import re
import sys


def _placeholder_name(node, used):
    """A readable, unique kwarg name for an interpolated expression."""
    if isinstance(node, ast.Name):
        base = node.id
    elif isinstance(node, ast.Attribute):
        base = node.attr
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        base = re.sub(r"\W", "_", node.slice.value)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        base = node.func.attr
    else:
        base = "v"
    base = re.sub(r"\W", "_", base).strip("_") or "v"
    if base[0].isdigit():
        base = "v" + base
    name, i = base, 2
    while name in used:
        name, i = f"{base}{i}", i + 1
    used.add(name)
    return name


def convert(node, src):
    """(new_source_text, changed) for one string-ish argument node."""
    seg = ast.get_source_segment(src, node)
    if seg is None:
        return None, False

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # A plain literal. Double any literal % so gettext's own interpolation
        # leaves it alone even when a future translation adds a placeholder.
        if "%" in node.value:
            body = seg[0] + node.value.replace("%", "%%") + seg[0]
            # keep the original quote style, re-escaping is not needed because
            # we only touched '%'
            q = seg[0] if seg[0] in "\"'" else '"'
            body = f"{q}{node.value.replace('%', '%%')}{q}"
            return f"_({body})", True
        return f"_({seg})", True

    if isinstance(node, ast.JoinedStr):
        template, kwargs, used = [], [], set()
        for part in node.values:
            if isinstance(part, ast.Constant):
                template.append(str(part.value).replace("%", "%%"))
            elif isinstance(part, ast.FormattedValue):
                expr_src = ast.get_source_segment(src, part.value)
                if expr_src is None:
                    return None, False
                name = _placeholder_name(part.value, used)
                spec = ""
                if part.format_spec is not None:
                    if not isinstance(part.format_spec, ast.JoinedStr):
                        return None, False
                    bits = []
                    for sp in part.format_spec.values:
                        if isinstance(sp, ast.Constant):
                            bits.append(str(sp.value))
                        else:
                            return None, False   # nested/dynamic spec: skip
                    spec = "".join(bits)
                conv = part.conversion
                if conv not in (-1, None):
                    return None, False           # !r / !s: skip, rare and fiddly
                template.append(f"%({name})s")
                if spec:
                    kwargs.append(f'{name}=f"{{{expr_src}:{spec}}}"')
                else:
                    kwargs.append(f"{name}={expr_src}")
            else:
                return None, False
        text = "".join(template)
        if not kwargs:
            return f'_("{text}")', True
        if '"' in text:
            return None, False                   # quoting gets hairy: skip
        return f'_("{text}", {", ".join(kwargs)})', True

    return None, False


TARGETS = {"flash"}


def rewrite(path, check=False):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    edits, skipped = [], []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in TARGETS and node.args):
            continue
        arg = node.args[0]
        # already wrapped?
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "_":
            continue
        if not isinstance(arg, (ast.Constant, ast.JoinedStr)):
            skipped.append((arg.lineno, ast.get_source_segment(src, arg) or "?"))
            continue
        if isinstance(arg, ast.Constant) and not isinstance(arg.value, str):
            continue
        new, ok = convert(arg, src)
        if not ok:
            skipped.append((arg.lineno, (ast.get_source_segment(src, arg) or "?")[:70]))
            continue
        edits.append((arg.lineno, arg.col_offset, arg.end_lineno, arg.end_col_offset, new))

    if not edits:
        return 0, skipped

    lines = src.splitlines(keepends=True)
    # Character offsets for each line start.
    starts = [0]
    for l in lines:
        starts.append(starts[-1] + len(l))

    def off(lineno, col):
        """AST col_offset is a UTF-8 BYTE offset, not a character offset.

        This codebase is full of em-dashes (3 bytes, 1 character), so slicing
        the source with a raw col_offset overshoots by 2 per dash and eats the
        comma after the argument. Converting through the line's own encoding is
        what makes the replacement land where the AST says it does. The first
        version of this script did not, and only the ast.parse() guard below
        stopped it writing a broken file.
        """
        line = lines[lineno - 1]
        prefix = line.encode("utf-8")[:col].decode("utf-8", errors="ignore")
        return starts[lineno - 1] + len(prefix)

    out = src
    for lineno, col, end_lineno, end_col, new in sorted(
            edits, key=lambda e: (e[0], e[1]), reverse=True):
        a, b = off(lineno, col), off(end_lineno, end_col)
        out = out[:a] + new + out[b:]

    if not check:
        ast.parse(out)          # never write a file that does not parse
        open(path, "w", encoding="utf-8").write(out)
    return len(edits), skipped


if __name__ == "__main__":
    check = "--check" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    total, all_skipped = 0, []
    for p in paths:
        n, sk = rewrite(p, check)
        total += n
        if n or sk:
            print(f"{p}: {n} wrapped, {len(sk)} skipped")
        for lineno, txt in sk:
            all_skipped.append(f"  {p}:{lineno}  {txt}")
    print(f"\nTOTAL {'would wrap' if check else 'wrapped'}: {total}")
    if all_skipped:
        print(f"SKIPPED ({len(all_skipped)}) — handle these by hand:")
        print("\n".join(all_skipped))
