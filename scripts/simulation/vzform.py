"""Form-reading helpers — pick values the way a user picks from a dropdown."""
import re, html

def selects(text):
    """{select_name: [(value,label),...]} for every <select> on the page."""
    out = {}
    for m in re.finditer(r'<select\b([^>]*)>(.*?)</select>', text, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        nm = re.search(r'name="([^"]+)"', attrs)
        if not nm:
            continue
        opts = []
        for om in re.finditer(r'<option\b([^>]*)>(.*?)</option>', body, re.S | re.I):
            v = re.search(r'value="([^"]*)"', om.group(1))
            label = re.sub(r"<[^>]+>", "", om.group(2)).strip()
            opts.append(((v.group(1) if v else label), html.unescape(label)))
        out[nm.group(1)] = opts
    return out

def pick(text, name, avoid_blank=True, contains=None):
    """First usable option value for a select."""
    opts = selects(text).get(name, [])
    for v, lab in opts:
        if avoid_blank and not v.strip():
            continue
        if contains and contains.lower() not in lab.lower():
            continue
        return v
    return None

def inputs(text):
    """{input_name: value} for text/hidden/number inputs."""
    out = {}
    for m in re.finditer(r'<input\b([^>]*)>', text, re.I):
        a = m.group(1)
        nm = re.search(r'name="([^"]+)"', a)
        if not nm: continue
        val = re.search(r'value="([^"]*)"', a)
        out[nm.group(1)] = val.group(1) if val else ""
    return out

def radios(text, name):
    vals = []
    for m in re.finditer(r'<input\b([^>]*)>', text, re.I):
        a = m.group(1)
        if f'name="{name}"' in a and 'type="radio"' in a:
            v = re.search(r'value="([^"]*)"', a)
            if v: vals.append(v.group(1))
    return vals
