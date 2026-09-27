# -*- coding: utf-8 -*-
"""Give every translatable <option> an explicit value= holding the English constant.

An <option> with no value= submits its TEXT CONTENT. Translate that text and
the form starts posting Arabic into columns the rest of the app compares
against English constants — see repro_option_value.py, which walks it from the
rendered page to a false surplus on the cash-register drawer count.

Two shapes, both fixed here:
  <option {{ 'selected' if m=='Cash' }}>{{ _('Cash') }}</option>
      -> value="Cash"                    (the _() argument IS the constant)
  <option {{ 'selected' if x==pm }}>{{ pm }}</option>
      -> value="{{ pm }}" and body {{ pm|tr }}   (loop var: value keeps the
                                                  constant, display translates)
"""
import re, sys, glob

OPT = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.S)


def fix(src):
    out, pos, n_val, n_tr = [], 0, 0, 0
    for m in OPT.finditer(src):
        attrs, body = m.group(1), m.group(2)
        if re.search(r"\bvalue\s*=", attrs):
            continue
        lit = re.fullmatch(r"\s*\{\{\s*_\(\s*(['\"])(.*?)\1\s*\)\s*\}\}\s*", body, re.S)
        var = re.fullmatch(r"\s*\{\{\s*(\w+)\s*\}\}\s*", body)
        if lit:
            value, new_body = lit.group(2), body
        elif var:
            value, new_body = "{{ %s }}" % var.group(1), " {{ %s|tr }} " % var.group(1)
            n_tr += 1
        else:
            continue
        n_val += 1
        out.append(src[pos:m.start()])
        out.append('<option value="%s"%s>%s</option>' % (value, attrs, new_body))
        pos = m.end()
    out.append(src[pos:])
    return "".join(out), n_val, n_tr


def main(app_dir):
    tv = tt = tf = 0
    for f in sorted(glob.glob(f"{app_dir}/templates/**/*.html", recursive=True)):
        src = open(f, encoding="utf-8").read()
        new, nv, nt = fix(src)
        if new != src:
            open(f, "w", encoding="utf-8").write(new)
            print(f"  {f.split('/')[-1]:32s} +{nv} value=  +{nt} |tr")
            tv += nv; tt += nt; tf += 1
    print(f"{app_dir.split('/')[-1]}: {tf} files, {tv} value= added, {tt} |tr added")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
