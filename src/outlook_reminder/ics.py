"""Calendar source that reads a published ICS calendar link."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any

import icalendar
import recurring_ical_events

from .model import Meeting
from .source import CalendarUnavailable

FETCH_TIMEOUT_SECONDS = 30


def parse_ics(text: str, start: datetime, end: datetime) -> list[Meeting]:
    """Every Meeting occurrence in the ICS text overlapping [start, end), sorted by start."""
    try:
        cal = icalendar.Calendar.from_ical(text)
    except ValueError as e:
        raise CalendarUnavailable(f"not a valid ICS calendar: {e}") from e
    recurring = {
        str(e.get("UID", "")) for e in cal.walk("VEVENT")
        if any(p in e for p in ("RRULE", "RDATE", "RECURRENCE-ID"))
    }
    meetings = [_meeting(e, recurring) for e in recurring_ical_events.of(cal).between(start, end)]
    return sorted(meetings, key=lambda m: m.start)


def _value(component: icalendar.Component, name: str) -> Any:
    """The decoded value of a date, time or duration property."""
    prop: Any = component[name]
    return prop.dt


def _meeting(event: icalendar.Component, recurring: set[str]) -> Meeting:
    raw_start = _value(event, "DTSTART")
    all_day = not isinstance(raw_start, datetime)
    start = _aware(raw_start)
    end = _aware(_value(event, "DTEND")) if "DTEND" in event else start + (
        _value(event, "DURATION") if "DURATION" in event else timedelta(days=1 if all_day else 0)
    )
    return Meeting(
        key=_key(event, recurring),
        title=str(event.get("SUMMARY", "")).strip() or "(no title)",
        start=start,
        end=end,
        location=str(event.get("LOCATION", "")).strip(),
        reminder_before=_reminder_before(event, start, end),
        all_day=all_day,
    )


def _key(event: icalendar.Component, recurring: set[str]) -> str:
    """Stable per occurrence, also when the occurrence is moved."""
    uid = str(event.get("UID", ""))
    if uid in recurring and "RECURRENCE-ID" in event:
        return f"{uid}#{_aware(_value(event, 'RECURRENCE-ID')).isoformat()}"
    return uid


def _reminder_before(event: icalendar.Component, start: datetime, end: datetime) -> timedelta | None:
    """The longest lead time of the event's alarms, or None when it has none."""
    leads: list[timedelta] = []
    for alarm in event.walk("VALARM"):
        trigger: Any = alarm.get("TRIGGER")
        if trigger is None:
            continue
        if isinstance(trigger.dt, timedelta):
            anchor = end if trigger.params.get("RELATED") == "END" else start
            leads.append(start - (anchor + trigger.dt))
        else:
            leads.append(start - _aware(trigger.dt))
    return max(leads) if leads else None


def _aware(value: date | datetime) -> datetime:
    """Timezone-aware datetime; dates and floating times are taken as local time."""
    if not isinstance(value, datetime):
        value = datetime.combine(value, time())
    if value.tzinfo is None:
        value = value.astimezone()
    return value


class IcsSource:
    """Reads a published ICS link (https:// or webcal://)."""

    def __init__(self, url: str) -> None:
        self._url = "https://" + url[len("webcal://"):] if url.startswith("webcal://") else url

    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        return parse_ics(self._fetch(), start, end)

    def _fetch(self) -> str:
        request = urllib.request.Request(self._url, headers={"User-Agent": "outlook-reminder"})
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CalendarUnavailable(f"could not fetch the ICS calendar: {e}") from e
