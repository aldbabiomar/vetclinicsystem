"""
The sidebar highlights the page you are on.

base.html compared request.endpoint with bare names ('visits_list'), but a
blueprint route's endpoint carries its prefix ('clinical.visits_list') — so
since the routes moved into blueprints, every sidebar link to a blueprint
page had lost its highlight, silently; only the handful of pages still in
app.py kept theirs. nav_active() takes full names and refuses unknown ones.
"""
import re

import pytest

from conftest import needs_db

pytestmark = needs_db

# (page, the sidebar link's href) — one per blueprint, plus an app.py page.
PAGES = [
    ("/visits", "/visits"),
    ("/pos", "/pos"),
    ("/inventory-catalog", "/inventory-catalog"),
    ("/consignment/sales", "/consignment/sales"),
    ("/admin/users", "/admin/users"),
    ("/settings", "/settings"),
    ("/reports", "/reports"),
]


def _active_links(html):
    return re.findall(r'<a class="nav-link active[^"]*" href="([^"]+)"', html)


@pytest.mark.parametrize("page,href", PAGES)
def test_the_sidebar_highlights_the_current_page(client, page, href):
    """GUARD."""
    resp = client.get(page)
    assert resp.status_code == 200, page
    assert _active_links(resp.get_data(as_text=True)) == [href]


def test_nav_active_refuses_a_name_that_is_not_an_endpoint(flask_app):
    """GUARD on the guard: a bare name — the original bug — raises instead
    of quietly never matching."""
    import app as app_module
    with flask_app.test_request_context("/visits"):
        with pytest.raises(ValueError):
            app_module.nav_active("visits_list")


def test_control_nav_active_matches_a_full_endpoint(flask_app):
    import app as app_module
    with flask_app.test_request_context("/visits"):   # pushing it matches the URL: request.endpoint is set
        assert app_module.nav_active("clinical.visits_list") == "active"
        assert app_module.nav_active("sales.pos_page") == ""
