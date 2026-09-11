# -*- coding: utf-8 -*-
"""Wrap the `Label ({{ currency_label() }})` column headers.

Roughly a quarter of the English left on the pages after the main pass was
this one shape — "Total (IQD)", "Amount (JOD)", "Outstanding (IQD)". The
mixed-node pass skipped every one of them because the currency is spliced into
the middle, and the currency word is itself translated (IQD/د.ع), so the
header has to be one msgid with the currency as a named argument.
"""
import re, sys, glob

PAT = re.compile(r"([A-Z][A-Za-z ]*?)\s*\(\s*\{\{\s*currency_label\(\)\s*\}\}\s*\)")


def repl(m):
    label = m.group(1).strip()
    return ("{{ _('%s (%%(currency_label)s)', currency_label=currency_label()) }}"
            % label)


for app_dir in sys.argv[1:]:
    tot = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        new, n = PAT.subn(repl, src)
        if n:
            open(f, "w", encoding="utf-8").write(new)
            tot += n
    print(f"{app_dir.split('/')[-1]}: {tot} currency headers wrapped")
