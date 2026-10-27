"""The swappable calendar source interface (ADR 0001)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .model import Meeting


class CalendarSource(Protocol):
    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        """Every Meeting occurrence overlapping [start, end).

        Raises CalendarUnavailable when the calendar can't be read right now.
        """
        ...


class CalendarUnavailable(Exception):
    """The calendar could not be read (network down, bad response, ...)."""
