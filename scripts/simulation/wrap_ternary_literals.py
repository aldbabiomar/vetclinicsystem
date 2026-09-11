# -*- coding: utf-8 -*-
"""Wrap `{{ 'A' if cond else 'B' }}` where A and B are display text.

Only the two literals are wrapped, never the condition — the condition
compares against a STORED value ("Confirmed", "Consignment") and translating
that side would compare Arabic to English and always take the false branch.
That asymmetry is the whole point: `{{ 'Confirmed' if s.status=='Confirmed'
else 'Saved' }}` must become `_('Confirmed') if s.status=='Confirmed' else
_('Saved')`, with the comparison untouched.
"""
import re, sys, glob

# {{ 'A' if <cond> else 'B' }} — A and B start with a capital, cond kept verbatim
PAT = re.compile(
    r"\{\{\s*'([A-Z][^']*)'\s+if\s+(.+?)\s+else\s+'([A-Z][^']*)'\s*\}\}")


def repl(m):
    return "{{ _('%s') if %s else _('%s') }}" % (m.group(1), m.group(2), m.group(3))


for app_dir in sys.argv[1:]:
    tot = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        new, n = PAT.subn(repl, src)
        if n:
            open(f, "w", encoding="utf-8").write(new)
            tot += n
    print(f"{app_dir.split('/')[-1]}: {tot} ternary literals wrapped")
