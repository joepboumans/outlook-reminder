from datetime import UTC, datetime, timedelta

from fakes import FakeClock, FakeSource

from outlook_reminder.model import Meeting, Response
from outlook_reminder.reminders import ReminderBoard
from outlook_reminder.snooze import choice

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


def test_a_meeting_with_its_reminder_turned_off_gives_no_reminder():
    board, _, _ = board_at(T0, meeting(reminder_off=True))
    board.tick()
    assert due_keys(board) == []


def test_a_declined_meeting_gives_no_reminder():
    board, _, _ = board_at(T0, meeting(response=Response.DECLINED))
    board.tick()
    assert due_keys(board) == []


def test_a_cancelled_meeting_gives_no_reminder():
    board, _, _ = board_at(T0, meeting(cancelled=True))
    board.tick()
    assert due_keys(board) == []


def test_a_tentative_meeting_gives_a_reminder():
    board, _, _ = board_at(T0, meeting(response=Response.TENTATIVE))
    board.tick()
    assert due_keys(board) == ["m1"]


def test_an_all_day_event_gives_a_reminder_only_when_it_has_one_set():
    day = datetime(2026, 10, 28, tzinfo=UTC)
    board, _, _ = board_at(
        day + timedelta(hours=1),
        meeting("plain", start=day, minutes=24 * 60, all_day=True),
        meeting("set", start=day, minutes=24 * 60, all_day=True, reminder_before=timedelta(hours=18)),
    )
    board.tick()
    assert due_keys(board) == ["set"]


def labels(choices) -> list[str]:
    return [c.label for c in choices]


def test_snoozed_reminder_leaves_and_comes_back_when_the_snooze_ends():
    board, clock, _ = board_at(T0 - timedelta(minutes=15), meeting())
    board.tick()
    board.snooze(["m1"], choice("5 minutes"))
    assert due_keys(board) == []

    clock.advance(minutes=4)
    assert board.tick() == []
    clock.advance(minutes=1)
    assert [r.meeting.key for r in board.tick()] == ["m1"]


def test_snooze_relative_to_start():
    board, clock, _ = board_at(T0 - timedelta(minutes=15), meeting())
    board.tick()
    board.snooze(["m1"], choice("5 minutes before start"))
    clock.set(T0 - timedelta(minutes=5, seconds=1))
    assert board.tick() == []
    clock.set(T0 - timedelta(minutes=5))
    assert [r.meeting.key for r in board.tick()] == ["m1"]


def test_all_choices_are_offered_well_before_start():
    board, _, _ = board_at(T0 - timedelta(minutes=15), meeting())
    board.tick()
    assert labels(board.snooze_choices(["m1"])) == [
        "5 minutes before start", "0 minutes before start",
        "5 minutes", "10 minutes", "15 minutes", "30 minutes",
        "1 hour", "2 hours", "3 hours", "4 hours",
    ]


def test_choices_that_would_land_in_the_past_are_not_offered():
    board, _, _ = board_at(T0 - timedelta(minutes=3), meeting())
    board.tick()
    assert "5 minutes before start" not in labels(board.snooze_choices(["m1"]))
    assert "0 minutes before start" in labels(board.snooze_choices(["m1"]))

    board, _, _ = board_at(T0 + timedelta(minutes=1), meeting())
    board.tick()
    assert labels(board.snooze_choices(["m1"]))[0] == "5 minutes"


def test_default_snooze_is_5_minutes_before_start_until_the_meeting_starts_then_5_minutes():
    def default_at(now: datetime) -> str:
        board, _, _ = board_at(now, meeting())
        board.tick()
        return board.default_snooze(["m1"]).label

    assert default_at(T0 - timedelta(minutes=15)) == "5 minutes before start"
    assert default_at(T0 - timedelta(minutes=3)) == "0 minutes before start"
    assert default_at(T0) == "5 minutes"
    assert default_at(T0 + timedelta(minutes=10)) == "5 minutes"


def test_choices_for_several_reminders_are_those_that_suit_all_of_them():
    board, _, _ = board_at(T0 - timedelta(minutes=4), meeting("soon"), meeting("later", start=T0 + timedelta(minutes=10)))
    board.tick()
    assert labels(board.snooze_choices(["soon", "later"]))[0] == "0 minutes before start"
    assert board.default_snooze(["soon", "later"]).label == "0 minutes before start"


def test_snooze_all_selected_and_dismiss_all():
    board, clock, _ = board_at(T0 - timedelta(minutes=10), meeting("a"), meeting("b"), meeting("c"))
    board.tick()
    board.snooze(["a", "b"], choice("10 minutes"))
    assert due_keys(board) == ["c"]

    clock.advance(minutes=10)
    board.tick()
    assert sorted(due_keys(board)) == ["a", "b", "c"]
    board.dismiss_all()
    clock.advance(minutes=30)
    board.tick()
    assert due_keys(board) == []
