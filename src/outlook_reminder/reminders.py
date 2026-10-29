"""Reminder logic: which Reminders are due, given a calendar source and a clock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import Clock
from .model import Meeting, Response
from .snooze import SNOOZE_CHOICES, SnoozeChoice, choice
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
        # Snooze and Dismiss are kept per Meeting key together with the start they
        # were made for, so moving the Meeting discards them.
        self._dismissed: dict[str, datetime] = {}
        self._snoozed: dict[str, tuple[datetime, datetime]] = {}  # key -> (start, until)
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

    def calendar_read_due(self) -> bool:
        """True when the calendar should be read again."""
        return self._last_read is None or self._clock.now() - self._last_read >= POLL_INTERVAL

    def tick(self, read_calendar: bool = True) -> list[Reminder]:
        """Re-evaluate against the clock; returns the Reminders that just became due.

        Reads the calendar first when a read is due, unless read_calendar is False
        (the app reads it on a worker thread instead).
        """
        if read_calendar and self.calendar_read_due():
            self.refresh()
        now = self._clock.now()
        shown = {(r.meeting.key, r.meeting.start) for r in self._due}
        self._due = []
        newly_due: list[Reminder] = []
        for reminder in self._reminders():
            m = reminder.meeting
            if reminder.due_at > now or self._dismissed.get(m.key) == m.start:
                continue
            already_shown = (m.key, m.start) in shown
            snooze = self._snoozed.get(m.key)
            if snooze is not None and snooze[0] == m.start:
                if snooze[1] > now:
                    continue
                # The snooze ended: the Reminder is due again, even if the Meeting has ended.
                del self._snoozed[m.key]
            elif not already_shown and m.end <= now:
                # A Reminder not shown yet is only shown while its Meeting has not ended.
                continue
            self._due.append(reminder)
            if not already_shown:
                newly_due.append(reminder)
        return newly_due

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
        for r in self._due:
            if r.meeting.key == key:
                self._dismissed[key] = r.meeting.start
        self._due = [r for r in self._due if r.meeting.key != key]

    def snooze(self, keys: list[str], choice: SnoozeChoice) -> None:
        now = self._clock.now()
        for r in self._due:
            if r.meeting.key in keys:
                self._snoozed[r.meeting.key] = (r.meeting.start, choice.until(now, r.meeting.start))
        self._due = [r for r in self._due if r.meeting.key not in keys]

    def snooze_choices(self, keys: list[str]) -> list[SnoozeChoice]:
        """The snooze choices that land in the future for every one of these Reminders."""
        now = self._clock.now()
        starts = [r.meeting.start for r in self._due if r.meeting.key in keys]
        return [c for c in SNOOZE_CHOICES if all(c.until(now, start) > now for start in starts)]

    def default_snooze(self, keys: list[str]) -> SnoozeChoice:
        """'5 minutes before start' until the Meeting starts (or 0 minutes when that is past), then 5 minutes."""
        offered = self.snooze_choices(keys)
        for label in ("5 minutes before start", "0 minutes before start"):
            if choice(label) in offered:
                return choice(label)
        return choice("5 minutes")

    def dismiss_all(self) -> None:
        for r in self._due:
            self._dismissed[r.meeting.key] = r.meeting.start
        self._due = []
