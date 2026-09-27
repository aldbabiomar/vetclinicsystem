# -*- coding: utf-8 -*-
"""Wrap the English inside `{% block title %}` — the browser tab and window title.

The mixed-node pass skipped these: a title block is one literal run with
`{{ clinic_name }}` spliced in, which reads as a mixed node and got left
alone. It is the page name, so on /pos the tab still said "Point of Sale"
with every visible word on the page in Arabic.

Wraps each literal run of words and leaves the em-dash separators and the
interpolations outside, so the msgid is just "Dashboard" — which the nav has
already translated — rather than a whole title that could never be reused.
"""
import re, sys, glob

BLOCK = re.compile(r"(\{%\s*block title\s*%\})(.*?)(\{%\s*endblock\s*%\})", re.S)
PLACEHOLDER = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)
# leading/trailing separators stay outside the call
SPLIT = re.compile(r"^([\s—–|-]*)(.*?)([\s—–|-]*)$", re.S)


def wrap_body(body):
    out, n = [], 0
    for part in PLACEHOLDER.split(body):
        if not part or PLACEHOLDER.fullmatch(part) or "_(" in part:
            out.append(part); continue
        pre, core, post = SPLIT.match(part).groups()
        if not re.search(r"[A-Za-z]", core):
            out.append(part); continue
        q = '"' if "'" in core else "'"
        out.append(f"{pre}{{{{ _({q}{core}{q}) }}}}{post}")
        n += 1
    return "".join(out), n


for app_dir in sys.argv[1:]:
    tot = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        changed = 0

        def repl(m):
            global changed
            new, n = wrap_body(m.group(2))
            changed += n
            return m.group(1) + new + m.group(3)

        new_src = BLOCK.sub(repl, src)
        if changed:
            open(f, "w", encoding="utf-8").write(new_src)
            tot += changed
    print(f"{app_dir.split('/')[-1]}: {tot} title strings wrapped")
