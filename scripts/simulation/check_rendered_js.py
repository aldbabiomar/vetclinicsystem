# -*- coding: utf-8 -*-
"""Render every page in BOTH languages and check what the browser would get.

Two things, both of which produce a page that looks fine until you read it:

1. Every inline <script> must PARSE. A template that parses proves nothing
   about the JavaScript it emits: a mis-escaped quote gives a page that renders
   perfectly and whose buttons silently do nothing — the same failure mode as a
   reintroduced inline on* handler. Node is the syntax oracle.

2b. A page that renders a LOADING SHELL is not the page. Several heavy
   reports return a placeholder and navigate to the real URL once a background
   job finishes; checking the shell checks nothing, and a deliberately broken
   /retention passed clean twice for this reason. The shell is followed
   through to the content before anything is checked.

2. No markup may arrive ESCAPED. Emphasis inside a translated sentence is
   passed as a placeholder, and the wrong Jinja idiom — `('<b>' ~ _('x') ~
   '</b>')|safe`, which reads as though it works — escapes the tags before
   `|safe` sees them, printing `&lt;b&gt;` in the middle of the sentence.

Both are invisible to a status-code sweep: the pages are 200.
"""
import json
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "/Users/omaraldbabi/Desktop/VetClinicSystem/scripts/simulation")
from vzsim import Client, set_language  # noqa: E402

SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S)

ROOT = "/Users/omaraldbabi/Desktop/VetClinicSystem/webapps"
VENV = "/private/tmp/vz_%s_test_venv/bin/python3"

# A hand-written page list goes stale silently, and a page it forgets is a page
# these checks cannot fail on: a deliberately broken /retention passed this
# script clean, because /retention was simply not in the list. Discovered from
# the app's own url_map instead, the way tests/test_permissions.py does.
def pages(app):
    code = (
        "import app as m, json;"
        "print(json.dumps(sorted({r.rule for r in m.app.url_map.iter_rules()"
        " if 'GET' in r.methods and not r.arguments"
        " and not r.rule.startswith('/static')})))"
    )
    env = {
        "iq": ("55491", "vetclinicsystemiq"),
        "jo": ("55492", "vetclinicsystemjo"),
    }[app]
    out = subprocess.run(
        [VENV % app, "-c", code],
        cwd=f"{ROOT}/vetclinicsystem_{app}-main", capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "SECRET_KEY": "x",
             "DATABASE_URL": f"postgresql://postgres:test@localhost:{env[0]}/{env[1]}"},
    )
    if out.returncode != 0:
        raise SystemExit(f"could not enumerate {app} routes:\n{out.stderr[-800:]}")
    return [r for r in json.loads(out.stdout)
            if r not in ("/logout", "/health")]



SHELL = re.compile(r"VZProgress\.poll\((\"[^\"]+\"),")
RELOAD = re.compile(r"window\.location = (\"[^\"]+\")")


def _follow_loading_shell(c, r, tries=60):
    """Heavy pages return `_loading_shell.html` and navigate once a job ends.

    Without this the checker reads a placeholder for /retention, /insights and
    friends — every string on the real page unseen, and every guard here
    silently unable to fail on them."""
    if "vz-progress-shell" not in r.text:
        return r
    job = SHELL.search(r.text)
    dest = RELOAD.search(r.text)
    if not job or not dest:
        return r
    job_id = json.loads(job.group(1))
    url = c.base + json.loads(dest.group(1))
    for _ in range(tries):
        st = c.s.get(f"{c.base}/jobs/status", params={"job_id": job_id})
        try:
            status = st.json().get("status")
        except ValueError:
            break
        if status in ("done", "error"):
            break
        time.sleep(0.5)
    follow = c.s.get(url)
    # the destination can itself be a shell the first time through
    if "vz-progress-shell" in follow.text and tries > 1:
        return _follow_loading_shell(c, follow, tries=1)
    return follow


def check(app):
    c = Client(app)
    c.login()
    bad = []
    page_list = pages(app)
    for lang in ("en", "ar"):
        set_language(app, lang)
        for page in page_list:
            r = _follow_loading_shell(c, c.s.get(c.base + page))
            if r.status_code >= 500:
                bad.append(f"{lang} {page}: HTTP {r.status_code}")
                continue
            if r.status_code != 200:
                continue
            for ent in ("&lt;strong&gt;", "&lt;em&gt;", "&lt;code&gt;",
                        "&lt;b&gt;", "&lt;i&gt;"):
                if ent in r.text:
                    bad.append(f"{lang} {page}: escaped markup {ent} on the page")

            for i, m in enumerate(SCRIPT.finditer(r.text)):
                attrs, body = m.group(1), m.group(2)
                if "src=" in attrs or "json" in attrs:
                    continue
                if not body.strip():
                    continue
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                                 encoding="utf-8") as fh:
                    fh.write(body)
                    path = fh.name
                p = subprocess.run(["node", "--check", path],
                                   capture_output=True, text=True)
                if p.returncode != 0:
                    first = p.stderr.strip().splitlines()
                    detail = next((l for l in first if "SyntaxError" in l), first[0] if first else "")
                    bad.append(f"{lang} {page} script#{i}: {detail}")
    set_language(app, "en")
    return bad


if __name__ == "__main__":
    total = 0
    for app in sys.argv[1:] or ["iq", "jo"]:
        bad = check(app)
        total += len(bad)
        print(f"=== {app}: {len(pages(app))} pages x2 languages, {len(bad)} problem(s) ===")
        for b in bad[:25]:
            print("   ", b)
    print("CLEAN" if not total else f"{total} PROBLEMS")
    sys.exit(1 if total else 0)
