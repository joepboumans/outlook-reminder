"""Reminder logic: which Reminders are due, given a calendar source and a clock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import Clock
from .model import Meeting, Response
from .snooze import SNOOZE_CHOICES, SnoozeChoice, choice
from .source import CalendarSource, CalendarUnavailable, SignInFailed, SignInRequired, SignInSource
from .state import Dismissed, MemoryStateStore, Snoozed, StateStore

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
    def __init__(self, source: CalendarSource, clock: Clock, store: StateStore | None = None) -> None:
        self._source = source
        self._clock = clock
        self._store = store or MemoryStateStore()
        self._meetings: list[Meeting] = []
        self._due: list[Reminder] = []
        # Snooze and Dismiss are kept per Meeting key together with the start they
        # were made for, so moving the Meeting discards them.
        self._state = self._store.load()
        self._last_read: datetime | None = None
        # Set while the calendar can't be read until the user signs in again.
        self._sign_in: SignInRequired | None = None
        self._sign_in_announced = False

    def refresh(self) -> bool:
        """Read the calendar now. Keeps the last known Meetings if it can't be read.

        Returns whether the read succeeded.
        """
        now = self._clock.now()
        self._last_read = now
        try:
            self._meetings = self._source.meetings(now - READ_BEHIND, now + READ_AHEAD)
        except SignInRequired as e:
            log.warning("Sign-in needed, keeping last known meetings: %s", e)
            self._sign_in = e
            return False
        except CalendarUnavailable as e:
            log.warning("Calendar unavailable, keeping last known meetings: %s", e)
            return False
        self._signed_in()
        return True

    # Sign-in (Graph only): an expired sign-in shows as an entry in the Reminders window.
    @property
    def needs_sign_in(self) -> bool:
        """The calendar can't be read until the user signs in (again)."""
        return self._sign_in is not None

    @property
    def never_signed_in(self) -> bool:
        """Sign-in is needed because there has never been one (first run)."""
        return self._sign_in is not None and self._sign_in.never_signed_in

    def take_sign_in_notice(self) -> bool:
        """True exactly once each time sign-in becomes needed, for its one notification."""
        if self._sign_in is None or self._sign_in_announced:
            return False
        self._sign_in_announced = True
        return True

    def sign_in(self) -> bool:
        """Run the source's browser sign-in (blocks). Returns whether it worked.

        After a successful sign-in the entry goes away and the next tick reads the calendar.
        """
        if not isinstance(self._source, SignInSource):
            return False
        try:
            self._source.sign_in()
        except SignInFailed as e:
            log.warning("Sign-in failed: %s", e)
            return False
        self._signed_in()
        self.read_soon()
        return True

    def _signed_in(self) -> None:
        self._sign_in = None
        self._sign_in_announced = False

    def calendar_read_due(self) -> bool:
        """True when the calendar should be read again."""
        return self._last_read is None or self._clock.now() - self._last_read >= POLL_INTERVAL

    def read_soon(self) -> None:
        """Make the next tick read the calendar, without waiting for the 5-minute poll."""
        self._last_read = None

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
        dismissed, snoozed = self._state.dismissed, self._state.snoozed
        changed = False
        for reminder in self._reminders():
            m = reminder.meeting
            dismiss = dismissed.get(m.key)
            if reminder.due_at > now or (dismiss is not None and dismiss.start == m.start):
                continue
            already_shown = (m.key, m.start) in shown
            snooze = snoozed.get(m.key)
            if snooze is not None and snooze.start == m.start:
                if snooze.until > now:
                    continue
                # The snooze ended: the Reminder is due again, even if the Meeting has ended.
                del snoozed[m.key]
                changed = True
            elif not already_shown and m.end <= now:
                # A Reminder not shown yet is only shown while its Meeting has not ended.
                continue
            self._due.append(reminder)
            if not already_shown:
                newly_due.append(reminder)
        if self._clean_up(now) or changed:
            self._save()
        return newly_due

    def _clean_up(self, now: datetime) -> bool:
        """Forget Snoozes and Dismisses that can no longer matter. Returns whether anything went."""
        st = self._state
        old_dismissed = [k for k, d in st.dismissed.items() if d.end <= now]
        old_snoozed = [k for k, s in st.snoozed.items() if s.end <= now and s.until <= now]
        for k in old_dismissed:
            del st.dismissed[k]
        for k in old_snoozed:
            del st.snoozed[k]
        return bool(old_dismissed or old_snoozed)

    def _save(self) -> None:
        self._store.save(self._state)

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
        self._dismiss([r for r in self._due if r.meeting.key == key])

    def snooze(self, keys: list[str], choice: SnoozeChoice) -> None:
        now = self._clock.now()
        for r in self._due:
            m = r.meeting
            if m.key in keys:
                self._state.snoozed[m.key] = Snoozed(m.start, m.end, choice.until(now, m.start))
        self._due = [r for r in self._due if r.meeting.key not in keys]
        self._save()

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
        self._dismiss(list(self._due))

    def _dismiss(self, reminders: list[Reminder]) -> None:
        for r in reminders:
            self._state.dismissed[r.meeting.key] = Dismissed(r.meeting.start, r.meeting.end)
            self._state.snoozed.pop(r.meeting.key, None)
        self._due = [r for r in self._due if r not in reminders]
        self._save()
