# -*- coding: utf-8 -*-
"""Translate the display text of options that already carry an explicit value=.

The sibling of fix_option_values.py. Where value= is present the submitted
constant is safe, so the body is free to be translated — it just never was.
IQ had this shape where JO had the missing-value one, which is why the two
apps' counts differed; see SEAM_RULES.md.
"""
import re, sys, glob

OPT = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.S)


def fix(src):
    out, pos, n = [], 0, 0
    for m in OPT.finditer(src):
        attrs, body = m.group(1), m.group(2)
        if not re.search(r"\bvalue\s*=", attrs):
            continue
        var = re.fullmatch(r"\s*\{\{\s*(\w+(?:\.\w+)?)\s*\}\}\s*", body)
        if not var:
            continue
        n += 1
        out.append(src[pos:m.start()])
        out.append("<option%s> {{ %s|tr }} </option>" % (attrs, var.group(1)))
        pos = m.end()
    out.append(src[pos:])
    return "".join(out), n


for app_dir in sys.argv[1:]:
    tot = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        new, n = fix(src)
        if new != src:
            open(f, "w", encoding="utf-8").write(new)
            print(f"  {f.split('/')[-1]:34s} +{n}")
            tot += n
    print(f"{app_dir.split('/')[-1]}: {tot} option bodies translated")
