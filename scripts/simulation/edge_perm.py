"""Phase 2e — a real custom role with a narrow permission set, then every
route tried as that user. Checks nothing is reachable that shouldn't be."""
import sys, re, json, random
import os
SIM = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM)
from vzsim import Client, q, flashes
from vzform import selects

SAFE_GET_FOR_ALL = {"/", "/health", "/logout", "/change-password", "/favicon.ico",
                    "/login", "/jobs/status"}


def routes_of(app):
    """Every GET rule with no path parameters, from the live url_map."""
    path = f"{SIM}/../routes_{app}.txt"
    out = []
    for line in open(path).read().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        rule, methods, endpoint = parts[0], parts[1], parts[2]
        if "<" in rule or not rule.startswith("/"):
            continue
        if "GET" in methods:
            out.append((rule, endpoint))
    return out


def run(app):
    admin = Client(app, "admin"); admin.login()
    F = admin.finding
    print(f"\n=== {app.upper()}: narrow custom role ===", flush=True)

    # 1. a role that may only look at patients
    rolename = f"Kennel Assistant {random.randint(100,999)}"
    r = admin.post("/admin/roles/new", {
        "name": rolename, "description": "May only view patients",
        "discount_cap": "0", "is_vet_role": "N", "permissions": ["manage_patients"],
    }, note="create narrow role")
    admin.expect_success(r, "create narrow role")
    row = q(app, "select id from roles where name=%s", (rolename,))
    if not row:
        F("ROLE_CREATE_FAILED", f"could not create narrow role {rolename}")
        return admin
    role_id = row[0][0]
    perms = q(app, "select permission_id from role_permissions where role_id=%s", (role_id,))
    print(f"  role {role_id} has {len(perms)} permission(s): {[p[0] for p in perms]}")

    # 2. a user in it
    uname = f"kennel{random.randint(1000,9999)}"
    r = admin.post("/admin/users/new", {
        "username": uname, "full_name": "Kennel Assistant", "password": "Str0ngPass!23",
        "role_id": role_id, "capmode": "role",
    }, note="create narrow user")
    admin.expect_success(r, "create narrow user")

    # 3. that user signs in and tries everything
    u = Client(app, uname)
    try:
        u.login(uname, "Str0ngPass!23")
    except RuntimeError as e:
        print(f"  (login note: {e})")
        return admin
    # a first login is forced through a password change before anything else
    NEWPW = "Kennel!Pass99"
    u.get("/change-password")
    u.post("/change-password", {"current_password": "Str0ngPass!23",
                                "new_password": NEWPW, "confirm_password": NEWPW},
           note="forced password change")
    probe = u.get("/patients", note="post-change probe")
    if "/change-password" in probe.url:
        F("PASSWORD_CHANGE_STUCK", "forced password change did not clear; cannot test permissions")
        return admin
    reachable, denied = [], []
    for rule, endpoint in routes_of(app):
        if rule in SAFE_GET_FOR_ALL:
            continue
        r = u.get(rule, note=f"as {uname}")
        if r.status_code >= 500:
            F("HTTP_5XX_AS_LIMITED_USER", f"GET {rule} as narrow role -> {r.status_code}")
            continue
        fl = [m for c_, m in flashes(r.text)]
        blocked = (r.status_code in (401, 403)
                   or "/login" in r.url
                   or any("permission" in m.lower() or "not allowed" in m.lower()
                          or "access" in m.lower() for m in fl)
                   or r.url.rstrip("/").endswith(u.base))          # bounced to dashboard
        (denied if blocked else reachable).append(rule)
    print(f"  reachable: {len(reachable)}   denied: {len(denied)}")
    allowed_by_design = {"/patients", "/change-password"}
    leaked = [x for x in reachable if x not in allowed_by_design]
    if leaked:
        F("PERMISSION_LEAK",
          f"a role holding only manage_patients could still load {len(leaked)} page(s)",
          dict(pages=leaked[:40]))

    # 4. and the write routes it must never reach
    writes = [
        ("/pos/checkout", {"item_id": "INV301", "quantity": "1", "payment_method": "Cash",
                           "idempotency_key": f"perm-{random.randint(1,10**9)}"}),
        ("/owners/new", {"name": "Should Not Exist", "phone": "07701234567"}),
        ("/price-list/new", {"name": "Nope", "category": "Retail", "sale_price": "1"}),
        ("/inventory-catalog/new", {"name": "Nope", "category": "Retail", "unit": "Each"}),
        ("/admin/users/new", {"username": f"x{random.randint(1,10**6)}", "full_name": "X",
                              "password": "Str0ngPass!23", "role_id": role_id}),
        ("/admin/roles/new", {"name": f"Escalated {random.randint(1,10**6)}",
                              "permissions": ["manage_users_roles"], "discount_cap": "100"}),
        ("/cash-register/payout", {"day": "2026-09-11", "amount": "1", "reason": "x"}),
        ("/reports/opex", {"month": "2026-09", "rent": "1"}),
        ("/settings", {"theme_palette": "vetzone"}),
    ]
    for path, payload in writes:
        before = q(app, "select count(*) from audit_log")[0][0]
        r = u.post(path, payload, note=f"write as {uname}")
        after = q(app, "select count(*) from audit_log")[0][0]
        if r.status_code >= 500:
            F("HTTP_5XX_AS_LIMITED_USER", f"POST {path} as narrow role -> {r.status_code}")
        elif after > before:
            F("PERMISSION_WRITE_LEAK",
              f"a role holding only manage_patients performed a write via POST {path}")

    # 5. privilege escalation: can it change its own role?
    me = q(app, "select id from users where username=%s", (uname,))
    if me:
        admin_role = q(app, "select id from roles where name='Admin'")[0][0]
        r = u.post(f"/admin/users/{me[0][0]}/role", {"role_id": admin_role},
                   note="self-promote to Admin")
        now = q(app, "select role_id from users where username=%s", (uname,))[0][0]
        if now == admin_role:
            F("PRIVILEGE_ESCALATION",
              "a narrow-role user promoted itself to Admin via /admin/users/<id>/role")

    print(f"  -- {app}: {len(admin.findings)} findings")
    return admin


if __name__ == "__main__":
    allf = []
    for app in ("iq", "jo"):
        allf += run(app).findings
    json.dump(allf, open(f"{SIM}/../findings_perm.json", "w"), indent=2, default=str)
    print(f"\nTOTAL: {len(allf)}")
