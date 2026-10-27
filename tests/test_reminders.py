from datetime import UTC, datetime, timedelta

from fakes import FakeClock, FakeSource

from outlook_reminder.model import Meeting
from outlook_reminder.reminders import ReminderBoard

T0 = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def meeting(key: str = "m1", start: datetime = T0, minutes: int = 30, **kw) -> Meeting:
    return Meeting(key=key, title=kw.pop("title", f"Meeting {key}"), start=start,
                   end=start + timedelta(minutes=minutes), **kw)


def board_at(now: datetime, *meetings: Meeting) -> tuple[ReminderBoard, FakeClock, FakeSource]:
    clock = FakeClock(now)
    source = FakeSource(*meetings)
    board = ReminderBoard(source, clock)
    board.refresh()
    return board, clock, source


def due_keys(board: ReminderBoard) -> list[str]:
    return [r.meeting.key for r in board.due]


def test_reminder_without_own_setting_is_due_15_minutes_before_start():
    board, clock, _ = board_at(T0 - timedelta(minutes=16), meeting())
    board.tick()
    assert due_keys(board) == []

    clock.advance(minutes=1)
    board.tick()
    assert due_keys(board) == ["m1"]


def test_reminder_uses_the_meetings_own_reminder_time():
    board, clock, _ = board_at(T0 - timedelta(minutes=31), meeting(reminder_before=timedelta(minutes=30)))
    board.tick()
    assert due_keys(board) == []

    clock.advance(minutes=1)
    board.tick()
    assert due_keys(board) == ["m1"]


def test_dismiss_removes_the_reminder_and_it_stays_gone():
    board, clock, _ = board_at(T0 - timedelta(minutes=10), meeting("a"), meeting("b"))
    board.tick()
    board.dismiss("a")
    assert due_keys(board) == ["b"]

    clock.advance(minutes=1)
    board.refresh()
    board.tick()
    assert due_keys(board) == ["b"]


def test_tick_reports_each_reminder_once_when_it_becomes_due():
    board, clock, _ = board_at(T0 - timedelta(minutes=16), meeting("a"), meeting("b", start=T0 + timedelta(minutes=5)))
    assert board.tick() == []

    clock.advance(minutes=1)
    assert [r.meeting.key for r in board.tick()] == ["a"]
    assert board.tick() == []

    clock.advance(minutes=5)
    board.refresh()
    assert [r.meeting.key for r in board.tick()] == ["b"]
    assert due_keys(board) == ["a", "b"]


def test_calendar_is_reread_every_5_minutes():
    board, clock, source = board_at(T0 - timedelta(hours=1))
    assert source.reads == 1
    clock.advance(minutes=4)
    board.tick()
    assert source.reads == 1
    clock.advance(minutes=1)
    board.tick()
    assert source.reads == 2


def test_a_meeting_added_to_the_calendar_is_picked_up_on_the_next_read():
    board, clock, source = board_at(T0 - timedelta(minutes=20))
    source.calendar.append(meeting())
    clock.advance(minutes=5)
    assert [r.meeting.key for r in board.tick()] == ["m1"]


def test_a_meeting_removed_from_the_calendar_loses_its_reminder():
    board, clock, source = board_at(T0 - timedelta(minutes=10), meeting())
    board.tick()
    source.calendar.clear()
    clock.advance(minutes=5)
    board.tick()
    assert due_keys(board) == []


def test_when_the_calendar_cannot_be_read_the_last_known_meetings_are_kept():
    board, clock, source = board_at(T0 - timedelta(minutes=20), meeting())
    source.unavailable = True
    clock.advance(minutes=5)
    assert [r.meeting.key for r in board.tick()] == ["m1"]
