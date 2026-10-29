"""The calendar model shared by every calendar source and the reminder logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Response(Enum):
    """The user's own response to a Meeting."""

    NONE = "none"
    ORGANIZER = "organizer"
    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"


@dataclass(frozen=True)
class Meeting:
    """One occurrence of an event on the user's calendar.

    `key` identifies the occurrence and stays the same when the Meeting is moved.
    `reminder_before` is the Meeting's own Reminder time, or None when the
    calendar gives none. `reminder_off` is True when the user turned the
    reminder off in Outlook.
    """

    key: str
    title: str
    start: datetime
    end: datetime
    location: str = ""
    reminder_before: timedelta | None = None
    reminder_off: bool = False
    response: Response = Response.NONE
    cancelled: bool = False
    all_day: bool = False
    teams_url: str | None = None
