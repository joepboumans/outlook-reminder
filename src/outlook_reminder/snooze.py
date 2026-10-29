"""Outlook's snooze choices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SnoozeChoice:
    """Either a duration from now, or a point relative to the Meeting's start."""

    label: str
    amount: timedelta
    before_start: bool = False

    def until(self, now: datetime, start: datetime) -> datetime:
        return start - self.amount if self.before_start else now + self.amount


SNOOZE_CHOICES: tuple[SnoozeChoice, ...] = (
    SnoozeChoice("5 minutes before start", timedelta(minutes=5), before_start=True),
    SnoozeChoice("0 minutes before start", timedelta(0), before_start=True),
    SnoozeChoice("5 minutes", timedelta(minutes=5)),
    SnoozeChoice("10 minutes", timedelta(minutes=10)),
    SnoozeChoice("15 minutes", timedelta(minutes=15)),
    SnoozeChoice("30 minutes", timedelta(minutes=30)),
    SnoozeChoice("1 hour", timedelta(hours=1)),
    SnoozeChoice("2 hours", timedelta(hours=2)),
    SnoozeChoice("3 hours", timedelta(hours=3)),
    SnoozeChoice("4 hours", timedelta(hours=4)),
)


def choice(label: str) -> SnoozeChoice:
    """The snooze choice with this label."""
    for c in SNOOZE_CHOICES:
        if c.label == label:
            return c
    raise KeyError(label)
