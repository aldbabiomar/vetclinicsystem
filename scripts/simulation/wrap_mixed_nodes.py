"""Convert text nodes that MIX prose with Jinja expressions into a single
gettext call with named placeholders.

    Page {{ page }} of {{ total_pages }}
        -> {{ _('Page %(page)s of %(total_pages)s', page=page,
                total_pages=total_pages) }}

This is the remainder wrap_templates.py deliberately skips: it only handles
text nodes with no Jinja at all, because a sentence split across expressions
cannot be wrapped by substitution alone — the translator has to be able to
move the placeholders, which means the whole sentence must become one msgid.

Only nodes whose Jinja is entirely `{{ ... }}` expressions are converted.
A node containing `{% if %}`/`{% for %}` is left alone: the branches are
separate sentences and merging them would produce a msgid that cannot be
translated coherently. Those are reported so they can be done by hand.

Run with --check to see what it would do.
"""
import re
import sys

EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)
STATEMENT = re.compile(r"\{%|\{#")
SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def _name_for(expr, used):
    """A readable placeholder name for a Jinja expression."""
    base = re.sub(r"\(.*?\)", "", expr).strip()
    base = re.split(r"[|\.\[]", base)[0].strip()
    base = re.sub(r"\W", "_", base).strip("_")
    if not base or base[0].isdigit():
        base = "v"
    name, i = base, 2
    while name in used:
        name, i = f"{base}{i}", i + 1
    used.add(name)
    return name


def convert_node(text):
    """(replacement, True) or (None, False) if this node should be left alone."""
    if STATEMENT.search(text):
        return None, False
    exprs = EXPR.findall(text)
    if not exprs:
        return None, False
    # needs real prose around the expressions to be worth a msgid
    prose = EXPR.sub(" ", text)
    if len(re.findall(r"[A-Za-z]{2,}", prose)) < 2:
        return None, False
    if "'" in text or '"' in prose:
        return None, False          # quoting inside a msgid: skip, do by hand

    used, kwargs = set(), []
    def sub(m):
        expr = m.group(1).strip()
        name = _name_for(expr, used)
        kwargs.append(f"{name}={expr}")
        return f"%({name})s"

    template = EXPR.sub(sub, text).strip()
    template = template.replace("%", "%%").replace("%%(", "%(")
    # the escape above also doubled the placeholders' own %; undo for those
    for kw in kwargs:
        n = kw.split("=")[0]
        template = template.replace(f"%%({n})s", f"%({n})s")
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f"{lead}{{{{ _('{template}', {', '.join(kwargs)}) }}}}{trail}", True


def wrap(path, check=False):
    src = open(path, encoding="utf-8").read()
    masked = SCRIPT_OR_STYLE.sub(lambda m: "\x00" * len(m.group(0)), src)
    edits, skipped = [], 0
    for m in re.finditer(r">([^<>]*\{\{[^<>]*)<", masked):
        text = m.group(1)
        if "\x00" in text or "_(" in text:
            continue
        new, ok = convert_node(text)
        if not ok:
            skipped += 1
            continue
        edits.append((m.start(1), m.end(1), new))
    if not edits:
        return 0, skipped
    out = src
    for a, b, new in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:a] + new + out[b:]
    if not check:
        open(path, "w", encoding="utf-8").write(out)
    return len(edits), skipped


if __name__ == "__main__":
    check = "--check" in sys.argv
    total = skip = 0
    for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
        n, s = wrap(p, check)
        total += n
        skip += s
        if n:
            print(f"  {p.split('/')[-1]}: {n}")
    print(f"TOTAL {'would convert' if check else 'converted'}: {total}; "
          f"left for hand treatment: {skip}")
