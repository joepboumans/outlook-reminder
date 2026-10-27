from datetime import UTC, datetime, timedelta

from outlook_reminder.ics import parse_ics

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
