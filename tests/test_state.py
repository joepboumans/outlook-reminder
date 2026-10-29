"""Snooze and Dismiss survive an app restart (a new ReminderBoard on the same saved state)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fakes import FakeClock, FakeSource

from outlook_reminder.model import Meeting
from outlook_reminder.reminders import ReminderBoard
from outlook_reminder.snooze import choice
from outlook_reminder.state import JsonStateStore

T0 = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def meeting(key: str = "m1", start: datetime = T0, minutes: int = 30) -> Meeting:
    return Meeting(key=key, title=f"Meeting {key}", start=start, end=start + timedelta(minutes=minutes))


def start_app(path: Path, clock: FakeClock, source: FakeSource) -> ReminderBoard:
    board = ReminderBoard(source, clock, store=JsonStateStore(path))
    board.refresh()
    board.tick()
    return board


def due_keys(board: ReminderBoard) -> list[str]:
    return [r.meeting.key for r in board.due]


def test_a_dismissed_reminder_stays_dismissed_after_a_restart(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting("a"), meeting("b"))
    board = start_app(path, clock, source)
    board.dismiss("a")

    clock.advance(minutes=1)
    board = start_app(path, clock, source)
    assert due_keys(board) == ["b"]


def test_dismiss_all_is_saved_too(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting("a"), meeting("b"))
    start_app(path, clock, source).dismiss_all()

    assert due_keys(start_app(path, clock, source)) == []


def test_a_snoozed_reminder_stays_snoozed_until_the_same_moment_after_a_restart(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=15)), FakeSource(meeting())
    start_app(path, clock, source).snooze(["m1"], choice("10 minutes"))

    clock.advance(minutes=9, seconds=59)
    board = start_app(path, clock, source)
    assert due_keys(board) == []

    clock.advance(seconds=1)
    assert [r.meeting.key for r in board.tick()] == ["m1"]


def test_moving_a_meeting_while_the_app_was_off_discards_its_saved_dismiss(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting())
    start_app(path, clock, source).dismiss("m1")

    source.calendar = [meeting(start=T0 + timedelta(minutes=5))]
    assert due_keys(start_app(path, clock, source)) == ["m1"]


def test_moving_a_meeting_while_the_app_was_off_discards_its_saved_snooze(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting())
    start_app(path, clock, source).snooze(["m1"], choice("4 hours"))

    source.calendar = [meeting(start=T0 + timedelta(minutes=5))]
    assert due_keys(start_app(path, clock, source)) == ["m1"]


def test_each_occurrence_of_a_recurring_meeting_has_its_own_state(tmp_path):
    path = tmp_path / "state.json"
    today = meeting("daily#2026-10-27T09:00:00+00:00")
    tomorrow = meeting("daily#2026-10-28T09:00:00+00:00", start=T0 + timedelta(days=1))
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(today, tomorrow)
    start_app(path, clock, source).dismiss(today.key)

    clock.set(tomorrow.start - timedelta(minutes=10))
    assert due_keys(start_app(path, clock, source)) == [tomorrow.key]


def test_state_of_ended_meetings_is_cleaned_up(tmp_path):
    path = tmp_path / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting("a"), meeting("b"))
    board = start_app(path, clock, source)
    board.dismiss("a")
    board.snooze(["b"], choice("5 minutes"))
    assert set(JsonStateStore(path).load().dismissed) == {"a"}

    clock.advance(hours=1)
    board.tick()  # the snooze of b ended, so b is due again
    board.dismiss("b")
    clock.advance(minutes=1)
    board.tick()
    saved = JsonStateStore(path).load()
    assert saved.dismissed == {} and saved.snoozed == {}


def test_a_missing_or_damaged_state_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    assert JsonStateStore(path).load().dismissed == {}
    path.write_text("{not json")
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting())
    assert due_keys(start_app(path, clock, source)) == ["m1"]


def test_the_state_file_and_its_folder_are_created_on_first_save(tmp_path):
    path = tmp_path / "deeper" / "state.json"
    clock, source = FakeClock(T0 - timedelta(minutes=10)), FakeSource(meeting())
    start_app(path, clock, source).dismiss("m1")
    assert path.exists()
