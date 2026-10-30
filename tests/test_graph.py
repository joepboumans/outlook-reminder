"""The Graph calendar source, against recorded calendarView responses."""

import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from outlook_reminder.graph import GraphSource, HttpResponse, parse_events
from outlook_reminder.model import Response
from outlook_reminder.reminders import ReminderBoard, is_silent
from outlook_reminder.source import CalendarUnavailable, SignInRequired

from fakes import FakeClock

DATA = Path(__file__).parent / "data" / "graph"
START = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
END = START + timedelta(days=15)


@pytest.fixture(autouse=True)
def amsterdam_local_time(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Amsterdam")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def recorded(name: str) -> bytes:
    return (DATA / name).read_bytes()


def events() -> dict:
    page1 = json.loads(recorded("calendar_view_page1.json"))["value"]
    page2 = json.loads(recorded("calendar_view_page2.json"))["value"]
    return {m.title: m for m in parse_events(page1 + page2)}


class FakeAuth:
    def __init__(self) -> None:
        self.tokens = ["token-1", "token-2", "token-3"]
        self.forced = 0
        self.signed_in = 0

    def token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            self.forced += 1
            self.tokens.pop(0)
        return self.tokens[0]

    def sign_in(self) -> str:
        self.signed_in += 1
        return "joep@example.com"


class FakeHttp:
    """Answers with recorded responses, and remembers every request."""

    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        self.requests.append((url, headers))
        return self.responses.pop(0)


def two_pages() -> FakeHttp:
    return FakeHttp(HttpResponse(200, recorded("calendar_view_page1.json")),
                    HttpResponse(200, recorded("calendar_view_page2.json")))


# Mapping of Graph events into Meetings.

def test_times_are_read_as_utc():
    m = events()["Design review"]
    assert m.start == datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
    assert m.end == datetime(2026, 10, 27, 9, 30, tzinfo=UTC)


def test_reminder_time_comes_from_the_event():
    assert events()["Design review"].reminder_before == timedelta(minutes=10)
    assert events()["Daily standup"].reminder_before == timedelta(minutes=5)


def test_reminder_turned_off_makes_a_silent_meeting():
    m = events()["Focus time"]
    assert m.reminder_off and m.reminder_before is None
    assert is_silent(m)


def test_response_status_is_mapped():
    e = events()
    assert e["Design review"].response is Response.ACCEPTED
    assert e["Daily standup"].response is Response.TENTATIVE
    assert e["Focus time"].response is Response.ORGANIZER
    assert e["Budget sync"].response is Response.DECLINED
    assert e["Customer call"].response is Response.NONE


def test_declined_and_cancelled_meetings_are_silent():
    e = events()
    assert is_silent(e["Budget sync"])
    assert e["Geannuleerd: Retro"].cancelled and is_silent(e["Geannuleerd: Retro"])
    assert not is_silent(e["Daily standup"])


def test_all_day_event_runs_from_local_midnight_and_keeps_its_reminder():
    m = events()["Joep off"]
    assert m.all_day
    assert m.start == datetime(2026, 10, 29, 0, 0).astimezone()
    assert m.end == datetime(2026, 10, 30, 0, 0).astimezone()
    assert m.reminder_before == timedelta(hours=18)
    assert not is_silent(m)


def test_teams_link_comes_from_the_online_meeting():
    assert events()["Design review"].teams_url == (
        "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc%40thread.v2/0?context=%7b%22Tid%22%3a%22t%22%7d"
    )


def test_teams_link_is_also_found_in_the_location():
    assert events()["Customer call"].teams_url == "https://teams.microsoft.com/meet/3456789?p=abcdef"


def test_meetings_without_a_teams_link_have_none():
    assert events()["Daily standup"].teams_url is None


def test_location_and_key():
    m = events()["Daily standup"]
    assert m.location == "Room 4.12"
    assert m.key == "AAMkAGI2TGuLAAB=_occurrence_20261027"


def test_time_in_another_zone_is_converted():
    [m] = parse_events([{
        "id": "x", "subject": "Call", "isAllDay": False,
        "start": {"dateTime": "2026-10-27T10:00:00.0000000", "timeZone": "Europe/Amsterdam"},
        "end": {"dateTime": "2026-10-27T11:00:00.0000000", "timeZone": "Europe/Amsterdam"},
    }])
    assert m.start == datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
    assert m.reminder_before is None and not m.reminder_off


# Reading the calendar view.

def test_reads_every_page_of_the_main_calendar_view():
    http = two_pages()
    meetings = GraphSource(FakeAuth(), http).meetings(START, END)
    assert len(meetings) == 7
    assert [m.start for m in meetings] == sorted(m.start for m in meetings)
    first_url = urlsplit(http.requests[0][0])
    assert first_url.path == "/v1.0/me/calendar/calendarView"
    query = parse_qs(first_url.query)
    assert query["startDateTime"] == ["2026-10-26T08:00:00Z"]
    assert query["endDateTime"] == ["2026-11-10T08:00:00Z"]
    assert "reminderMinutesBeforeStart" in query["$select"][0]
    assert http.requests[1][0].endswith("%24skip=3")


def test_requests_carry_the_token_and_ask_for_utc():
    http = two_pages()
    GraphSource(FakeAuth(), http).meetings(START, END)
    headers = http.requests[0][1]
    assert headers["Authorization"] == "Bearer token-1"
    assert 'outlook.timezone="UTC"' in headers["Prefer"]


def test_meetings_feed_the_reminder_board():
    clock = FakeClock(datetime(2026, 10, 27, 8, 50, tzinfo=UTC))
    board = ReminderBoard(GraphSource(FakeAuth(), two_pages()), clock)
    assert [r.meeting.title for r in board.tick()] == ["Design review"]


def test_a_rejected_token_is_refreshed_once():
    auth = FakeAuth()
    http = FakeHttp(HttpResponse(401, recorded("error_401.json")),
                    HttpResponse(200, recorded("calendar_view_page2.json")))
    assert len(GraphSource(auth, http).meetings(START, END)) == 4
    assert auth.forced == 1
    assert http.requests[1][1]["Authorization"] == "Bearer token-2"


def test_a_token_rejected_twice_needs_sign_in():
    http = FakeHttp(HttpResponse(401, recorded("error_401.json")), HttpResponse(401, recorded("error_401.json")))
    with pytest.raises(SignInRequired):
        GraphSource(FakeAuth(), http).meetings(START, END)


def test_a_server_error_is_unavailable():
    http = FakeHttp(HttpResponse(503, recorded("error_503.json")))
    with pytest.raises(CalendarUnavailable, match="ServiceNotAvailable") as e:
        GraphSource(FakeAuth(), http).meetings(START, END)
    assert not isinstance(e.value, SignInRequired)


def test_invalid_json_is_unavailable():
    with pytest.raises(CalendarUnavailable):
        GraphSource(FakeAuth(), FakeHttp(HttpResponse(200, b"<html>"))).meetings(START, END)


def test_sign_in_goes_to_the_auth():
    auth = FakeAuth()
    GraphSource(auth, FakeHttp()).sign_in()
    assert auth.signed_in == 1
