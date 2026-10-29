"""Overdue reminders: Reminders whose time passed while the laptop slept or was off."""

from datetime import UTC, datetime, timedelta

from fakes import FakeClock, FakeSource

from outlook_reminder.model import Meeting
from outlook_reminder.reminders import ReminderBoard
from outlook_reminder.state import JsonStateStore

T0 = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def meeting(key: str, start: datetime = T0, minutes: int = 30) -> Meeting:
    return Meeting(key=key, title=f"Meeting {key}", start=start, end=start + timedelta(minutes=minutes))


def keys(reminders) -> list[str]:
    return [r.meeting.key for r in reminders]


def test_after_resume_reminders_due_during_sleep_appear_once_each():
    clock = FakeClock(T0 - timedelta(hours=1))
    source = FakeSource(meeting("a"), meeting("b", start=T0 + timedelta(minutes=10)), meeting("later", start=T0 + timedelta(hours=3)))
    board = ReminderBoard(source, clock)
    assert board.tick() == []

    clock.advance(minutes=65)  # the laptop slept through both Reminder times
    newly = board.tick()
    assert keys(newly) == ["a", "b"]
    assert board.tick() == []


def test_a_meeting_that_ended_during_sleep_is_skipped():
    clock = FakeClock(T0 - timedelta(hours=1))
    source = FakeSource(meeting("short", minutes=15), meeting("long", minutes=120))
    board = ReminderBoard(source, clock)
    board.tick()

    clock.advance(minutes=80)  # 09:20: "short" ended at 09:15, "long" still runs
    assert keys(board.tick()) == ["long"]


def test_a_meeting_added_or_moved_while_asleep_is_picked_up_by_the_read_after_resume():
    clock = FakeClock(T0 - timedelta(hours=1))
    source = FakeSource()
    board = ReminderBoard(source, clock)
    board.tick()
    clock.advance(minutes=2)
    source.calendar = [meeting("new")]  # added during sleep; next poll is still 3 minutes away
    clock.advance(minutes=52)
    board.read_soon()  # resume
    assert keys(board.tick()) == ["new"]


def test_read_soon_reads_the_calendar_on_the_next_tick():
    clock = FakeClock(T0)
    source = FakeSource()
    board = ReminderBoard(source, clock)
    board.tick()
    clock.advance(minutes=1)
    board.tick()
    assert source.reads == 1

    board.read_soon()  # network change
    board.tick()
    assert source.reads == 2


def test_after_a_cold_start_reminders_due_while_off_appear_unless_dismissed_earlier(tmp_path):
    path = tmp_path / "state.json"
    clock = FakeClock(T0 - timedelta(minutes=10))
    source = FakeSource(meeting("a"), meeting("b"), meeting("c", start=T0 + timedelta(minutes=30)))
    board = ReminderBoard(source, clock, store=JsonStateStore(path))
    board.tick()
    board.dismiss("a")

    clock.advance(minutes=30)  # shut down, and back on at 09:20
    board = ReminderBoard(source, clock, store=JsonStateStore(path))
    assert keys(board.tick()) == ["b", "c"]


def test_after_a_cold_start_reminders_of_ended_meetings_are_not_shown(tmp_path):
    clock = FakeClock(T0 + timedelta(hours=1))
    board = ReminderBoard(FakeSource(meeting("a")), clock, store=JsonStateStore(tmp_path / "state.json"))
    assert board.tick() == []
