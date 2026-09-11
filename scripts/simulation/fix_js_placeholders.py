# -*- coding: utf-8 -*-
"""A placeholder JavaScript substitutes cannot be written `%(name)s`.

Jinja's gettext ALWAYS runs `rv % variables` on the translated string, even
when no keyword arguments were passed. So `_('Only %(stock)s in stock.')`,
which deliberately leaves the placeholder for a later JS `.replace()`, raises
`KeyError: 'stock'` while rendering the page — six pages per app returned 500
in both languages, English included.

Placeholders Jinja fills stay `%(name)s` (currency_label, and every ordinary
template message). Placeholders JavaScript fills become `{name}`, which
carries no `%` and therefore passes through `rv % variables` untouched.
Both kinds can sit in the same string: `_('Cash received is {amount}
%(currency_label)s short of the total.', currency_label=currency_label())`.
"""
import re
import sys
import glob

CALL = re.compile(r"\.replace\('%\(([a-z_]+)\)s'")
SPAN = re.compile(r"\{\{\s*_\(.*?\}\}((?:\.replace\((?:[^()]|\([^()]*\))*\))+)", re.S)


def fix(src):
    """Find each `{{ _(...) }}` followed by a chain of .replace() calls, and
    convert only the placeholders that chain names."""
    n = 0

    def repl(m):
        nonlocal n
        whole = m.group(0)
        names = CALL.findall(m.group(1))
        if not names:
            return whole
        for name in names:
            whole = whole.replace("%%(%s)s" % name, "{%s}" % name)
        n += 1
        return whole

    return SPAN.sub(repl, src), n


for app_dir in sys.argv[1:]:
    tot = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        s = open(f, encoding="utf-8").read()
        new_s, n = fix(s)
        if n:
            open(f, "w", encoding="utf-8").write(new_s)
            print(f"  {f.split('/')[-1]:26s} {n}")
            tot += n
    print(f"{app_dir.split('/')[-1]}: {tot} call sites converted")
