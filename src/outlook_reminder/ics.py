"""Calendar source that reads a published ICS calendar link."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any

import icalendar
import recurring_ical_events

from .model import Meeting, Response
from .source import CalendarUnavailable

FETCH_TIMEOUT_SECONDS = 30


CANCELLED_PREFIXES = ("canceled:", "cancelled:")


def parse_ics(text: str, start: datetime, end: datetime, me: str | None = None) -> list[Meeting]:
    """Every Meeting occurrence in the ICS text overlapping [start, end), sorted by start.

    `me` is the user's email address, used to find their own response.
    """
    try:
        cal = icalendar.Calendar.from_ical(text)
    except ValueError as e:
        raise CalendarUnavailable(f"not a valid ICS calendar: {e}") from e
    recurring = {
        str(e.get("UID", "")) for e in cal.walk("VEVENT")
        if any(p in e for p in ("RRULE", "RDATE", "RECURRENCE-ID"))
    }
    # Feeds that carry alarms at all carry one for every Meeting with its reminder on.
    # Feeds without any alarms tell us nothing, so reminders stay on there.
    alarms_known = any(e.walk("VALARM") for e in cal.walk("VEVENT"))
    meetings = [
        _meeting(e, recurring, alarms_known, me.lower() if me else None)
        for e in recurring_ical_events.of(cal).between(start, end)
    ]
    return sorted(meetings, key=lambda m: m.start)


def _value(component: icalendar.Component, name: str) -> Any:
    """The decoded value of a date, time or duration property."""
    prop: Any = component[name]
    return prop.dt


def _meeting(event: icalendar.Component, recurring: set[str], alarms_known: bool, me: str | None) -> Meeting:
    raw_start = _value(event, "DTSTART")
    all_day = not isinstance(raw_start, datetime)
    start = _aware(raw_start)
    end = _aware(_value(event, "DTEND")) if "DTEND" in event else start + (
        _value(event, "DURATION") if "DURATION" in event else timedelta(days=1 if all_day else 0)
    )
    title = str(event.get("SUMMARY", "")).strip()
    reminder_before = _reminder_before(event, start, end)
    return Meeting(
        key=_key(event, recurring),
        title=title or "(no title)",
        start=start,
        end=end,
        location=str(event.get("LOCATION", "")).strip(),
        reminder_before=reminder_before,
        reminder_off=alarms_known and reminder_before is None,
        response=_response(event, me),
        cancelled=str(event.get("STATUS", "")).upper() == "CANCELLED"
        or title.lower().startswith(CANCELLED_PREFIXES),
        all_day=all_day,
    )


def _response(event: icalendar.Component, me: str | None) -> Response:
    if me is not None:
        if _address(event.get("ORGANIZER")) == me:
            return Response.ORGANIZER
        attendees: Any = event.get("ATTENDEE", [])
        for attendee in attendees if isinstance(attendees, list) else [attendees]:
            if _address(attendee) == me:
                status = str(attendee.params.get("PARTSTAT", "")).upper()
                if status in PARTSTAT_RESPONSES:
                    return PARTSTAT_RESPONSES[status]
    if str(event.get("X-MICROSOFT-CDO-BUSYSTATUS", "")).upper() == "TENTATIVE":
        return Response.TENTATIVE
    return Response.NONE


PARTSTAT_RESPONSES = {
    "ACCEPTED": Response.ACCEPTED,
    "TENTATIVE": Response.TENTATIVE,
    "DECLINED": Response.DECLINED,
}


def _address(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text.removeprefix("mailto:")


def _key(event: icalendar.Component, recurring: set[str]) -> str:
    """Stable per occurrence, also when the occurrence is moved."""
    uid = str(event.get("UID", ""))
    if uid in recurring and "RECURRENCE-ID" in event:
        return f"{uid}#{_aware(_value(event, 'RECURRENCE-ID')).isoformat()}"
    return uid


def _reminder_before(event: icalendar.Component, start: datetime, end: datetime) -> timedelta | None:
    """The Reminder time from the event's earliest alarm, or None when it has no alarm."""
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

    def __init__(self, url: str, me: str | None = None) -> None:
        self._me = me
        self._url = "https://" + url[len("webcal://"):] if url.startswith("webcal://") else url

    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        return parse_ics(self._fetch(), start, end, me=self._me)

    def _fetch(self) -> str:
        request = urllib.request.Request(self._url, headers={"User-Agent": "outlook-reminder"})
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CalendarUnavailable(f"could not fetch the ICS calendar: {e}") from e
