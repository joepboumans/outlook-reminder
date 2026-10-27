"""Fake clock and fake calendar source for testing the reminder logic."""

from __future__ import annotations

from datetime import datetime, timedelta

from outlook_reminder.model import Meeting
from outlook_reminder.source import CalendarUnavailable


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


class FakeSource:
    def __init__(self, *meetings: Meeting) -> None:
        self.calendar: list[Meeting] = list(meetings)
        self.unavailable = False
        self.reads = 0

    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        self.reads += 1
        if self.unavailable:
            raise CalendarUnavailable("offline")
        return [m for m in self.calendar if m.end > start and m.start < end]
