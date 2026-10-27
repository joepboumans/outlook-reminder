"""Wording shown to the user."""

from __future__ import annotations

from datetime import datetime


def _amount(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        text = f"{hours} hour{'s' if hours != 1 else ''}"
        return text if not rest else f"{text} {rest} min"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def describe_start(start: datetime, now: datetime) -> str:
    """'Starts in 10 minutes', 'Starting now' or 'Started 5 minutes ago' (Outlook's 'Overdue')."""
    seconds = (start - now).total_seconds()
    if -60 < seconds < 60:
        return "Starting now"
    minutes = round(abs(seconds) / 60)
    return f"Starts in {_amount(minutes)}" if seconds > 0 else f"Started {_amount(minutes)} ago"


def start_time(start: datetime, all_day: bool = False) -> str:
    """Local start time, e.g. 'Tue 27 Oct 10:00'."""
    local = start.astimezone()
    return local.strftime("%a %d %b") + ("" if all_day else local.strftime(" %H:%M"))
