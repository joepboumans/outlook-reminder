from datetime import UTC, datetime, timedelta

from outlook_reminder.ics import parse_ics
from outlook_reminder.model import Response

WINDOW = (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC))


def calendar(*events: str) -> str:
    body = "\n".join(f"BEGIN:VEVENT\n{e.strip()}\nEND:VEVENT" for e in events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:test\n{body}\nEND:VCALENDAR\n".replace("\n", "\r\n")


def parse(*events: str):
    return parse_ics(calendar(*events), *WINDOW)


def test_reads_title_times_and_location():
    [m] = parse("""
UID:abc
SUMMARY:Design review
LOCATION:Room 4
DTSTART:20261027T090000Z
DTEND:20261027T093000Z
""")
    assert m.key == "abc"
    assert m.title == "Design review"
    assert m.location == "Room 4"
    assert m.start == datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
    assert m.end == datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
    assert m.reminder_before is None


def test_converts_outlook_windows_timezones():
    [m] = parse("""
UID:abc
SUMMARY:Standup
DTSTART;TZID=W. Europe Standard Time:20261027T100000
DTEND;TZID=W. Europe Standard Time:20261027T101500
""")
    # 27 October 2026 is after the switch to winter time: UTC+1.
    assert m.start == datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def test_reminder_time_comes_from_the_valarm():
    [m] = parse("""
UID:abc
SUMMARY:Standup
DTSTART:20261027T090000Z
DTEND:20261027T091500Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Reminder
TRIGGER;RELATED=START:-PT10M
END:VALARM
""")
    assert m.reminder_before == timedelta(minutes=10)


def test_reminder_time_from_an_absolute_valarm_trigger():
    [m] = parse("""
UID:abc
SUMMARY:Standup
DTSTART:20261027T090000Z
DTEND:20261027T091500Z
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER;VALUE=DATE-TIME:20261027T080000Z
END:VALARM
""")
    assert m.reminder_before == timedelta(hours=1)


def test_each_occurrence_of_a_recurring_meeting_is_its_own_meeting():
    meetings = parse("""
UID:daily
SUMMARY:Standup
DTSTART:20261027T090000Z
DTEND:20261027T091500Z
RRULE:FREQ=DAILY;COUNT=3
""")
    assert [m.start.day for m in meetings] == [27, 28, 29]
    assert len({m.key for m in meetings}) == 3


def test_a_moved_occurrence_keeps_its_key():
    plain = parse("""
UID:daily
SUMMARY:Standup
DTSTART:20261027T090000Z
DTEND:20261027T091500Z
RRULE:FREQ=DAILY;COUNT=2
""")
    moved = parse("""
UID:daily
SUMMARY:Standup
DTSTART:20261027T090000Z
DTEND:20261027T091500Z
RRULE:FREQ=DAILY;COUNT=2
""", """
UID:daily
RECURRENCE-ID:20261028T090000Z
SUMMARY:Standup
DTSTART:20261028T110000Z
DTEND:20261028T111500Z
""")
    assert [m.key for m in moved] == [m.key for m in plain]
    assert moved[1].start == datetime(2026, 10, 28, 11, 0, tzinfo=UTC)


def test_events_outside_the_window_are_left_out():
    assert parse("""
UID:old
SUMMARY:Old
DTSTART:20261001T090000Z
DTEND:20261001T091500Z
""") == []


ALARM = """
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT15M
END:VALARM
"""


def test_without_alarms_in_the_feed_reminders_are_left_on():
    # Many published feeds drop all alarms, so a missing alarm says nothing.
    [m] = parse("UID:a\nSUMMARY:A\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z")
    assert not m.reminder_off


def test_when_the_feed_carries_alarms_a_meeting_without_one_has_its_reminder_off():
    with_alarm, without = parse(
        "UID:a\nSUMMARY:A\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z" + ALARM,
        "UID:b\nSUMMARY:B\nDTSTART:20261027T100000Z\nDTEND:20261027T103000Z",
    )
    assert not with_alarm.reminder_off
    assert without.reminder_off


def test_cancelled_status_and_outlook_canceled_prefix_mean_cancelled():
    by_status, by_prefix, normal = parse(
        "UID:a\nSUMMARY:A\nSTATUS:CANCELLED\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z",
        "UID:b\nSUMMARY:Canceled: B\nDTSTART:20261027T100000Z\nDTEND:20261027T103000Z",
        "UID:c\nSUMMARY:Cancellation policy\nDTSTART:20261027T110000Z\nDTEND:20261027T113000Z",
    )
    assert by_status.cancelled and by_prefix.cancelled
    assert not normal.cancelled


def test_dutch_outlook_geannuleerd_prefix_means_cancelled():
    [m] = parse("UID:a\nSUMMARY:Geannuleerd: Overleg\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z")
    assert m.cancelled


def test_the_users_response_comes_from_their_attendee_entry():
    def response(lines: str, me: str | None = "me@example.com"):
        [m] = parse_ics(calendar(
            "UID:a\nSUMMARY:A\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z\n" + lines
        ), *WINDOW, me=me)
        return m.response

    other = "ATTENDEE;PARTSTAT=ACCEPTED:mailto:other@example.com\n"
    assert response(other + "ATTENDEE;PARTSTAT=DECLINED:mailto:ME@example.com") is Response.DECLINED
    assert response(other + "ATTENDEE;PARTSTAT=TENTATIVE:mailto:me@example.com") is Response.TENTATIVE
    assert response("ATTENDEE;PARTSTAT=ACCEPTED:mailto:me@example.com") is Response.ACCEPTED
    assert response("ORGANIZER:mailto:me@example.com") is Response.ORGANIZER
    assert response(other) is Response.NONE
    assert response("ATTENDEE;PARTSTAT=DECLINED:mailto:me@example.com", me=None) is Response.NONE


def test_outlook_tentative_busy_status_means_tentative():
    [m] = parse("UID:a\nSUMMARY:A\nX-MICROSOFT-CDO-BUSYSTATUS:TENTATIVE\nDTSTART:20261027T090000Z\nDTEND:20261027T093000Z")
    assert m.response is Response.TENTATIVE


def test_all_day_events_are_marked_all_day():
    [m] = parse("UID:a\nSUMMARY:Holiday\nDTSTART;VALUE=DATE:20261028\nDTEND;VALUE=DATE:20261029")
    assert m.all_day
    assert m.end - m.start == timedelta(days=1)
