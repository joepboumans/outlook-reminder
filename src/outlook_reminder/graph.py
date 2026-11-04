"""Calendar source that reads the main Microsoft 365 calendar through Microsoft Graph (ADR 0001).

Read-only: only GET requests to the calendar view of the user's main calendar.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, time, timedelta
from typing import Any, NamedTuple, Protocol
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .model import Meeting, Response
from .source import CalendarUnavailable, SignInRequired
from .teams import find_teams_url

GRAPH = "https://graph.microsoft.com/v1.0"
FETCH_TIMEOUT_SECONDS = 30
# Everything the reminder rules need, and nothing more.
SELECT = ",".join([
    "id", "subject", "start", "end", "isAllDay", "location", "isReminderOn",
    "reminderMinutesBeforeStart", "responseStatus", "isCancelled", "isOnlineMeeting",
    "onlineMeetingProvider", "onlineMeeting", "onlineMeetingUrl", "body",
])
HEADERS = {
    # Times come back in UTC, bodies as plain text, 100 events per page.
    "Prefer": 'outlook.timezone="UTC", outlook.body-content-type="text", odata.maxpagesize=100',
    "Accept": "application/json",
}

RESPONSES = {
    "none": Response.NONE,
    "notResponded": Response.NONE,
    "organizer": Response.ORGANIZER,
    "accepted": Response.ACCEPTED,
    "tentativelyAccepted": Response.TENTATIVE,
    "declined": Response.DECLINED,
}


def parse_events(events: list[dict[str, Any]]) -> list[Meeting]:
    """Meetings from the `value` items of a Graph calendarView response, sorted by start."""
    return sorted((_meeting(e) for e in events), key=lambda m: m.start)


def _meeting(event: dict[str, Any]) -> Meeting:
    all_day = bool(event.get("isAllDay"))
    start = _time(event["start"], all_day)
    end = _time(event["end"], all_day)
    reminder_on = event.get("isReminderOn", True)
    minutes = event.get("reminderMinutesBeforeStart")
    title = str(event.get("subject") or "").strip()
    return Meeting(
        # An occurrence of a recurring Meeting has its own id, which stays the same when it is moved.
        key=str(event["id"]),
        title=title or "(no title)",
        start=start,
        end=end,
        location=str((event.get("location") or {}).get("displayName") or "").strip(),
        reminder_before=timedelta(minutes=minutes) if reminder_on and minutes is not None else None,
        reminder_off=not reminder_on,
        response=RESPONSES.get(str((event.get("responseStatus") or {}).get("response")), Response.NONE),
        cancelled=bool(event.get("isCancelled")),
        all_day=all_day,
        teams_url=_teams_url(event),
    )


def _time(value: dict[str, Any], all_day: bool) -> datetime:
    """A Graph dateTimeTimeZone as an aware datetime. All-day dates are local midnight, as in Outlook."""
    t = datetime.fromisoformat(str(value["dateTime"]))
    if all_day:
        return datetime.combine(t.date(), time()).astimezone()
    if t.tzinfo is None:
        t = t.replace(tzinfo=_zone(str(value.get("timeZone") or "UTC")))
    return t


def _zone(name: str) -> Any:
    if name.upper() in ("UTC", "Z", "ETC/UTC"):
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # We ask Graph for UTC, so this only happens with an unexpected Windows zone name.
        return UTC


def _teams_url(event: dict[str, Any]) -> str | None:
    """The Teams join link: Graph's own field first, then any join link in the location or body."""
    online = event.get("onlineMeeting") or {}
    join_url = str(online.get("joinUrl") or "")
    found = find_teams_url(
        join_url,
        str(event.get("onlineMeetingUrl") or ""),
        str((event.get("location") or {}).get("displayName") or ""),
        str((event.get("body") or {}).get("content") or ""),
    )
    if found is None and join_url and event.get("onlineMeetingProvider") == "teamsForBusiness":
        return join_url
    return found


class HttpResponse(NamedTuple):
    status: int
    body: bytes


Http = Callable[[str, Mapping[str, str]], HttpResponse]


def urllib_get(url: str, headers: Mapping[str, str]) -> HttpResponse:
    request = urllib.request.Request(url, headers={"User-Agent": "outlook-reminder", **headers})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return HttpResponse(response.status, response.read())
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CalendarUnavailable(f"could not reach Microsoft Graph: {e}") from e


class TokenProvider(Protocol):
    def token(self, force_refresh: bool = False) -> str: ...
    def sign_in(self) -> str: ...


def calendar_view_url(start: datetime, end: datetime) -> str:
    query = urlencode({
        "startDateTime": _iso(start),
        "endDateTime": _iso(end),
        "$select": SELECT,
        "$orderby": "start/dateTime",
    })
    return f"{GRAPH}/me/calendar/calendarView?{query}"


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GraphSource:
    """Reads the main calendar's calendar view. Never writes anything back to Outlook."""

    def __init__(self, auth: TokenProvider, http: Http = urllib_get) -> None:
        self._auth = auth
        self._http = http

    def meetings(self, start: datetime, end: datetime) -> list[Meeting]:
        events: list[dict[str, Any]] = []
        url: str | None = calendar_view_url(start, end)
        while url:
            page = self._get(url)
            events.extend(page.get("value", []))
            url = page.get("@odata.nextLink")
        try:
            return parse_events(events)
        except (KeyError, TypeError, ValueError) as e:
            raise CalendarUnavailable(f"unexpected event in the Graph response: {e}") from e

    def sign_in(self) -> None:
        self._auth.sign_in()

    def _get(self, url: str) -> dict[str, Any]:
        response = self._http(url, {**HEADERS, "Authorization": f"Bearer {self._auth.token()}"})
        if response.status == 401:
            # The access token may have been revoked before it expired: get a fresh one once.
            fresh = self._auth.token(force_refresh=True)
            response = self._http(url, {**HEADERS, "Authorization": f"Bearer {fresh}"})
            if response.status == 401:
                raise SignInRequired("Microsoft Graph no longer accepts the sign-in")
        if response.status != 200:
            raise CalendarUnavailable(f"Microsoft Graph answered {response.status}: {_error(response.body)}")
        try:
            page = json.loads(response.body)
        except ValueError as e:
            raise CalendarUnavailable(f"Microsoft Graph sent invalid JSON: {e}") from e
        if not isinstance(page, dict):
            raise CalendarUnavailable("Microsoft Graph sent an unexpected response")
        return page


def _error(body: bytes) -> str:
    try:
        error = json.loads(body)["error"]
        return f"{error.get('code')}: {error.get('message')}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return body[:200].decode("utf-8", errors="replace")


