"""Shared harness for simulating real use of VetClinicSystem_IQ / _JO."""
import re, html, json, sys, time
import requests

APPS = {
    "iq": dict(base="http://127.0.0.1:5091",
               db="postgresql://postgres:test@localhost:55491/vetclinicsystemiq",
               currency="IQD"),
    "jo": dict(base="http://127.0.0.1:5092",
               db="postgresql://postgres:test@localhost:55492/vetclinicsystemjo",
               currency="JOD"),
}

FLASH_RE = re.compile(r'<div class="flash ([a-z]*)">(.*?)</div>', re.S)
META_CSRF = re.compile(r'<meta name="csrf-token" content="([^"]+)"')
FORM_CSRF = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def flashes(text):
    out = []
    for cat, msg in FLASH_RE.findall(text):
        msg = re.sub(r"<[^>]+>", "", msg)
        out.append((cat, html.unescape(msg).strip()))
    return out


class Client:
    """One logged-in user of one app."""

    def __init__(self, app, label="admin"):
        self.app = app
        self.cfg = APPS[app]
        self.base = self.cfg["base"]
        self.label = label
        self.s = requests.Session()
        self.token = None
        self.events = []      # every request
        self.findings = []    # anomalies

    # ---- plumbing -------------------------------------------------
    def _record(self, method, path, resp, note=""):
        fl = flashes(resp.text) if "text/html" in resp.headers.get("content-type", "") else []
        ev = dict(method=method, path=path, status=resp.status_code,
                  url=resp.url, flashes=fl, note=note)
        self.events.append(ev)
        if resp.status_code >= 500:
            self.finding("HTTP_5XX", f"{method} {path} -> {resp.status_code}", ev)
        return ev

    def finding(self, kind, summary, detail=None):
        f = dict(app=self.app, user=self.label, kind=kind, summary=summary, detail=detail)
        self.findings.append(f)
        print(f"  [!] {self.app.upper()} {kind}: {summary}", flush=True)
        return f

    def csrf(self, path="/"):
        r = self.s.get(self.base + path)
        m = META_CSRF.search(r.text) or FORM_CSRF.search(r.text)
        if m:
            self.token = m.group(1)
        return self.token

    def get(self, path, note="", **kw):
        r = self.s.get(self.base + path, **kw)
        m = META_CSRF.search(r.text) if r.text else None
        if m:
            self.token = m.group(1)
        self._record("GET", path, r, note)
        return r

    def post(self, path, data=None, note="", csrf=True, files=None, **kw):
        data = dict(data or {})
        if csrf:
            if not self.token:
                self.csrf()
            data.setdefault("csrf_token", self.token)
        r = self.s.post(self.base + path, data=data, files=files, **kw)
        m = META_CSRF.search(r.text) if r.text else None
        if m:
            self.token = m.group(1)
        self._record("POST", path, r, note)
        return r

    def post_json(self, path, payload, note=""):
        if not self.token:
            self.csrf()
        r = self.s.post(self.base + path, json=payload,
                        headers={"X-CSRFToken": self.token,
                                 "X-Requested-With": "XMLHttpRequest"})
        self._record("POSTJSON", path, r, note)
        return r

    def login(self, username="admin", password="Admin12345!"):
        self.csrf("/login")
        r = self.post("/login", {"username": username, "password": password}, note="login")
        ok = "/login" not in r.url
        if not ok:
            raise RuntimeError(f"{self.app}: login failed for {username}: {flashes(r.text)}")
        return r

    # ---- assertions used by scenarios -----------------------------
    def ok(self, r, what):
        if r.status_code >= 500:
            return False
        return True

    BENIGN = ("Audit recorded for", "Surplus of", "Deficit of")

    def expect_success(self, r, what):
        """A normal action a real user does — expect no error flash."""
        fl = flashes(r.text)
        errs = [m for c, m in fl if c in ("error", "danger")
                and not any(b in m for b in self.BENIGN)]
        if r.status_code >= 500:
            self.finding("HTTP_5XX", f"{what}: HTTP {r.status_code}")
            return False
        if errs:
            self.finding("UNEXPECTED_REFUSAL", f"{what}: refused with {errs!r}")
            return False
        return True

    def expect_refusal(self, r, what, allow_status=(200, 302, 400, 403)):
        """A bad/hostile input — expect a clean refusal, never a 500 and
        never a silent success."""
        fl = flashes(r.text)
        errs = [m for c, m in fl if c in ("error", "danger")]
        if r.status_code >= 500:
            self.finding("HTTP_5XX_ON_BAD_INPUT", f"{what}: HTTP {r.status_code}")
            return False
        if r.status_code in (400, 403):
            return True
        if not errs:
            self.finding("SILENT_ACCEPT", f"{what}: no error flash — input may have been accepted",
                         dict(status=r.status_code, flashes=fl))
            return False
        return True


def db(app):
    import psycopg
    return psycopg.connect(APPS[app]["db"])


def q(app, sql, params=None):
    with db(app) as c, c.cursor() as cur:
        cur.execute(sql, params or ())
        try:
            return cur.fetchall()
        except Exception:
            return None


def dump(findings, path):
    with open(path, "w") as f:
        json.dump(findings, f, indent=2, default=str)
