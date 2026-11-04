"""The swappable calendar source interface (ADR 0001)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .model import Meeting


class CalendarSource(Protocol):
    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        """Every Meeting occurrence overlapping [start, end).

        Raises CalendarUnavailable when the calendar can't be read right now,
        and SignInRequired when it can't be read until the user signs in again.
        """
        ...


@runtime_checkable
class SignInSource(Protocol):
    """A calendar source the user signs in to (Microsoft Graph)."""

    def sign_in(self) -> None:
        """Interactive sign-in in the browser. Blocks until done; raises SignInFailed."""
        ...


class CalendarUnavailable(Exception):
    """The calendar could not be read (network down, bad response, ...)."""


class SignInRequired(CalendarUnavailable):
    """The calendar can't be read until the user signs in (again).

    `never_signed_in` is True when there is no sign-in at all yet (first run),
    False when an earlier sign-in expired or was revoked.
    """

    def __init__(self, message: str, never_signed_in: bool = False) -> None:
        super().__init__(message)
        self.never_signed_in = never_signed_in


class SignInFailed(Exception):
    """The interactive sign-in did not complete (cancelled, timed out, refused)."""
