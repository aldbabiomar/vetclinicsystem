# -*- coding: utf-8 -*-
"""The language is a saved clinic setting, not a per-browser toggle.

Drives it the way a user would: open Settings, pick العربية in the dropdown,
press Save, and check that the whole app came back in Arabic — for a DIFFERENT
session too, since the point of moving it out of a cookie is that it is a
property of the clinic rather than of one browser.
"""
import re
import sys

sys.path.insert(0, "/Users/omaraldbabi/Desktop/VetClinicSystem/scripts/simulation")
import vzform
from vzsim import Client, q


def settings_form(page):
    """Every field of the Clinic Settings form, so Save does not blank the rest."""
    data = dict(vzform.inputs(page))
    for name, opts in vzform.selects(page).items():
        chosen = next((v for v, lab in opts if "selected" in lab), None)
        data[name] = chosen if chosen is not None else (opts[0][0] if opts else "")
    return data


def save_language(c, lang):
    page = c.s.get(c.base + "/settings").text
    form = settings_form(page)
    form["csrf_token"] = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    form["language"] = lang
    # only the Clinic Settings form's own fields
    keep = {"clinic_name", "clinic_location", "opening_date", "theme_palette",
            "language", "audit_overdue_days", "expiry_soon_days", "appt_start_time",
            "appt_end_time", "appt_slot_minutes", "backup_dir", "backup_time",
            "backup_retention", "selfcheck_backup_max_age_days", "heartbeat_url",
            "log_retention_days", "csrf_token"}
    return c.s.post(c.base + "/settings", data={k: v for k, v in form.items() if k in keep})


def run(app):
    c = Client(app); c.login()
    print(f"[{app}] header toggle present on the page: "
          f"{'lang-toggle' in c.s.get(c.base + '/').text}")

    for lang, probe in (("ar", "لوحة"), ("en", "Dashboard")):
        r = save_language(c, lang)
        stored = q(app, "select value from settings where key='language'")
        page = c.s.get(c.base + "/").text
        tag = re.search(r'<html[^>]*lang="([^"]+)"[^>]*dir="([^"]+)"', page)
        # a SECOND, cookie-less session must see the same language
        fresh = Client(app); fresh.login()
        fresh_page = fresh.s.get(fresh.base + "/").text
        print(f"[{app}] saved {lang!r}: stored={stored} "
              f"html={tag.groups() if tag else None} "
              f"dashboard-in-{lang}={probe in page} fresh-session-agrees={probe in fresh_page}")


if __name__ == "__main__":
    for a in sys.argv[1:] or ["iq", "jo"]:
        run(a)
