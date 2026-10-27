"""Reminder logic: which Reminders are due, given a calendar source and a clock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import Clock
from .model import Meeting, Response
from .source import CalendarSource, CalendarUnavailable

log = logging.getLogger(__name__)

DEFAULT_REMINDER_TIME = timedelta(minutes=15)
POLL_INTERVAL = timedelta(minutes=5)
# How far around now the calendar is read: back far enough to keep Reminders of
# Meetings still running, ahead far enough for long Reminder times.
READ_BEHIND = timedelta(days=1)
READ_AHEAD = timedelta(days=14)


def is_silent(m: Meeting) -> bool:
    """A Silent meeting never produces a Reminder."""
    return (
        m.reminder_off
        or m.cancelled
        or m.response is Response.DECLINED
        or (m.all_day and m.reminder_before is None)
    )


@dataclass(frozen=True)
class Reminder:
    meeting: Meeting
    due_at: datetime


class ReminderBoard:
    def __init__(self, source: CalendarSource, clock: Clock) -> None:
        self._source = source
        self._clock = clock
        self._meetings: list[Meeting] = []
        self._due: list[Reminder] = []
        self._dismissed: set[str] = set()
        self._last_read: datetime | None = None

    def refresh(self) -> bool:
        """Read the calendar now. Keeps the last known Meetings if it can't be read.

        Returns whether the read succeeded.
        """
        now = self._clock.now()
        self._last_read = now
        try:
            self._meetings = self._source.meetings(now - READ_BEHIND, now + READ_AHEAD)
        except CalendarUnavailable as e:
            log.warning("Calendar unavailable, keeping last known meetings: %s", e)
            return False
        return True

    def refresh_due(self) -> bool:
        """True when the calendar should be read again."""
        return self._last_read is None or self._clock.now() - self._last_read >= POLL_INTERVAL

    def tick(self, read_calendar: bool = True) -> list[Reminder]:
        """Re-evaluate against the clock; returns the Reminders that just became due.

        Reads the calendar first when a read is due, unless read_calendar is False
        (the app reads it on a worker thread instead).
        """
        if read_calendar and self.refresh_due():
            self.refresh()
        now = self._clock.now()
        before = {r.meeting.key for r in self._due}
        self._due = []
        for reminder in self._reminders():
            if reminder.due_at <= now and reminder.meeting.key not in self._dismissed:
                self._due.append(reminder)
        return [r for r in self._due if r.meeting.key not in before]

    def upcoming(self) -> list[Reminder]:
        """Reminders of the known Meetings that have not started yet, by due time."""
        now = self._clock.now()
        return sorted((r for r in self._reminders() if r.meeting.start > now), key=lambda r: r.due_at)

    def _reminders(self) -> list[Reminder]:
        reminders = []
        for m in sorted(self._meetings, key=lambda m: m.start):
            if is_silent(m):
                continue
            reminders.append(Reminder(m, m.start - (m.reminder_before or DEFAULT_REMINDER_TIME)))
        return reminders

    def now(self) -> datetime:
        return self._clock.now()

    @property
    def due(self) -> list[Reminder]:
        return list(self._due)

    def dismiss(self, key: str) -> None:
        self._dismissed.add(key)
        self._due = [r for r in self._due if r.meeting.key != key]
