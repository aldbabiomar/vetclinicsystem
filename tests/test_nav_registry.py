"""
The sidebar offers exactly the pages a person can open (audit P1).

It used to draw every clinical, inventory and POS link for everyone: a role
holding only `manage_settings` saw 20 links, 16 of them leading to "access
denied". nav.py now decides each link by the permission of the page it
opens, read from the route itself.
"""
import re

import pytest

from vcs.web import nav
from conftest import needs_db
from test_privileges import admin_restored, as_role  # noqa: F401

pytestmark = needs_db

ACCOUNT = {"/", "/change-password", "/logout"}     # always there: dashboard and the account links


def _sidebar(client):
    page = client.get("/").get_data(as_text=True)
    side = page[page.index('<nav class="sidebar">'):page.index("</nav>")]
    return [h for h in re.findall(r'<a class="nav-link[^"]*" href="([^"]+)"', side) if h not in ACCOUNT]


def test_a_settings_only_role_is_offered_only_settings(as_role):
    """GUARD. The audit's measurement."""
    assert _sidebar(as_role({"manage_settings"})["client"]) == ["/settings"]


def test_control_the_admin_is_offered_every_link(client, flask_app):
    with flask_app.test_request_context():
        every = [link.opens for group in nav.NAV for link in group.links]
    assert len(_sidebar(client)) == len(every) >= 30


def test_every_link_opens_for_someone_holding_just_what_it_requires(flask_app, as_role):
    """GUARD. Each link, followed by a person the sidebar would offer it to
    — holding only the permissions it requires — opens its page. A link
    whose visibility and its page's gate disagree fails here."""
    with flask_app.test_request_context():
        needs = {}
        for group in nav.NAV:
            for link in group.links:
                any_of, all_of = nav.required(link)
                assert any_of, f"{link.opens} has no permission_required() — the sidebar cannot gate it"
                needs.setdefault(frozenset({any_of[0], *all_of}), []).append(link)
                hrefs = {id(link): __import__("flask").url_for(link.opens) for group in nav.NAV for link in group.links}
    refused = []
    for perms, links in needs.items():
        user = as_role(set(perms))
        offered = _sidebar(user["client"])
        for link in links:
            href = hrefs[id(link)]
            if href not in offered:
                refused.append(f"{link.label}: not offered to a role holding {sorted(perms)}")
                continue
            status = user["client"].get(href).status_code
            if status != 200:
                refused.append(f"{link.label} ({href}): {status} for a role holding {sorted(perms)}")
    assert not refused, "\n  ".join(["sidebar and page disagree:"] + refused)


def test_settlements_needs_both_the_overview_and_the_right_to_settle(as_role):
    """The Settlements link opens the Consignment Overview (settling starts
    there), so settling alone is not enough to be offered it."""
    assert "/consignment" not in [h for h in _sidebar(as_role({"manage_consignment_settlements"})["client"])]
    both = _sidebar(as_role({"manage_consignment_settlements", "view_consignment"})["client"])
    assert both.count("/consignment") == 2    # Overview and Settlements
    viewing_only = _sidebar(as_role({"view_consignment"})["client"])
    assert viewing_only.count("/consignment") == 1, "offered Settlements without the right to settle"
