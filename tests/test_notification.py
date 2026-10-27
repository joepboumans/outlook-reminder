import time
from datetime import UTC, datetime, timedelta

import pytest

from outlook_reminder.model import Meeting
from outlook_reminder.notification import notification_text
from outlook_reminder.reminders import Reminder

START = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def utc_local_time(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def reminder(location: str = "", all_day: bool = False) -> Reminder:
    m = Meeting(key="k", title="Design review", start=START, end=START + timedelta(minutes=30),
                location=location, all_day=all_day)
    return Reminder(m, START - timedelta(minutes=15))


def test_notification_shows_title_start_time_and_location():
    assert notification_text(reminder("Room 4")) == ("Design review", "Tue 27 Oct 09:00 · Room 4")


def test_notification_without_location_shows_only_the_start_time():
    assert notification_text(reminder())[1] == "Tue 27 Oct 09:00"


def test_all_day_notification_shows_the_day():
    assert notification_text(reminder(all_day=True))[1] == "Tue 27 Oct · All day"
