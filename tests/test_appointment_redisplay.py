"""
A booking that fails validation re-opens on the day it was for (audit B17).

The grid read its day from ?day=/?week=, which a POST to /appointments/new
does not carry: a refused booking for next week re-rendered this week's
grid with the booking modal open over it.
"""
import re
from datetime import timedelta

from vcs import clock
from conftest import needs_db

pytestmark = needs_db


def _selected_day(page):
    """The day the grid shows: its day tab marked active."""
    m = re.search(r'<a class="active" href="[^"]*day=(\d{4}-\d{2}-\d{2})"', page)
    return m.group(1) if m else None


def test_a_refused_booking_reopens_on_its_own_day(client):
    """GUARD. No time slot, so the booking is refused — on its own day."""
    day = (clock.today() + timedelta(days=10)).isoformat()
    resp = client.post("/appointments/new", data={"appt_date": day, "slot_label": ""})
    assert resp.status_code == 200
    assert _selected_day(resp.get_data(as_text=True)) == day


def test_control_the_grid_shows_the_day_asked_for(client):
    day = (clock.today() + timedelta(days=10)).isoformat()
    assert _selected_day(client.get(f"/appointments?week={day}&day={day}").get_data(as_text=True)) == day


def test_control_a_refused_booking_with_no_valid_date_shows_today(client):
    resp = client.post("/appointments/new", data={"appt_date": "not-a-date", "slot_label": ""})
    assert _selected_day(resp.get_data(as_text=True)) == clock.today().isoformat()
