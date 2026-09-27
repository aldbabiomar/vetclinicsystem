# -*- coding: utf-8 -*-
"""Take |tr back off options whose text is DATA, not an enum constant.

The test is the option's own value=. When it is the same bare variable as the
body (value="{{ s }}">{{ s }}) the text IS the stored constant and belongs in
the catalogue. When value= is an id or another field (value="{{ v.id }}">
{{ v.full_name }}) the text is a row a user typed — a distributor named "Cash"
would otherwise come back translated.

One exception the rule cannot see: `visits.doctor` stores the vet's full NAME,
so value= and text are the same variable and it reads as a constant. It is a
staff name. Reverted by hand; if another column ever stores a user-typed value
as its own key, it needs the same treatment.
"""
import re, sys, glob

OPT = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.S)


def fix(src):
    out, pos, n = [], 0, 0
    for m in OPT.finditer(src):
        attrs, body = m.group(1), m.group(2)
        b = re.fullmatch(r"\s*\{\{\s*([\w.]+)\|tr\s*\}\}\s*", body)
        if not b:
            continue
        v = re.search(r'value="\{\{\s*([\w.]+)\s*\}\}"', attrs)
        if v and v.group(1) == b.group(1):
            continue                       # value IS the text: a real constant
        n += 1
        out.append(src[pos:m.start()])
        out.append("<option%s>{{ %s }}</option>" % (attrs, b.group(1)))
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
            print(f"  {f.split('/')[-1]:34s} -{n}")
            tot += n
    print(f"{app_dir.split('/')[-1]}: {tot} data options reverted")
