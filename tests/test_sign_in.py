"""An expired sign-in shows as an entry in the Reminders window (issue #12)."""

from datetime import UTC, datetime, timedelta

from outlook_reminder.model import Meeting
from outlook_reminder.reminders import ReminderBoard
from outlook_reminder.source import SignInFailed, SignInRequired

from fakes import FakeClock, FakeSource

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


def meeting(key: str, minutes: int) -> Meeting:
    start = NOW + timedelta(minutes=minutes)
    return Meeting(key=key, title=key, start=start, end=start + timedelta(minutes=30))


class FakeSignInSource(FakeSource):
    """A Graph-like source whose sign-in can expire."""

    def __init__(self, *meetings: Meeting) -> None:
        super().__init__(*meetings)
        self.expired = False
        self.never_signed_in = False
        self.sign_in_works = True
        self.sign_ins = 0

    def meetings(self, start, end):
        if self.expired:
            self.reads += 1
            raise SignInRequired("expired", never_signed_in=self.never_signed_in)
        return super().meetings(start, end)

    def sign_in(self) -> None:
        self.sign_ins += 1
        if not self.sign_in_works:
            raise SignInFailed("cancelled")
        self.expired = False


def setup(*meetings: Meeting):
    source = FakeSignInSource(*meetings)
    clock = FakeClock(NOW)
    return source, clock, ReminderBoard(source, clock)


def test_no_sign_in_entry_while_signed_in():
    _, _, board = setup()
    board.tick()
    assert not board.needs_sign_in
    assert not board.take_sign_in_notice()


def test_expired_sign_in_shows_the_entry():
    source, _, board = setup()
    source.expired = True
    board.tick()
    assert board.needs_sign_in
    assert not board.never_signed_in


def test_first_run_is_told_apart():
    source, _, board = setup()
    source.expired = source.never_signed_in = True
    board.tick()
    assert board.never_signed_in


def test_notice_is_sent_once():
    source, clock, board = setup()
    source.expired = True
    board.tick()
    assert board.take_sign_in_notice()
    assert not board.take_sign_in_notice()
    clock.advance(minutes=5)
    board.tick()
    assert board.needs_sign_in
    assert not board.take_sign_in_notice()


def test_polling_continues_while_signed_out():
    source, clock, board = setup()
    source.expired = True
    board.tick()
    clock.advance(minutes=5)
    board.tick()
    assert source.reads == 2


def test_known_reminders_keep_coming_while_signed_out():
    source, clock, board = setup(meeting("standup", 30))
    board.tick()
    source.expired = True
    clock.advance(minutes=16)
    assert [r.meeting.key for r in board.tick()] == ["standup"]
    assert board.needs_sign_in


def test_sign_in_removes_the_entry_and_reads_again():
    source, _, board = setup()
    source.expired = True
    board.tick()
    source.calendar.append(meeting("review", 10))
    assert board.sign_in()
    assert not board.needs_sign_in
    assert board.calendar_read_due()
    assert [r.meeting.key for r in board.tick()] == ["review"]


def test_failed_sign_in_keeps_the_entry():
    source, _, board = setup()
    source.expired = True
    source.sign_in_works = False
    board.tick()
    assert not board.sign_in()
    assert board.needs_sign_in


def test_notice_comes_again_when_it_expires_again():
    source, clock, board = setup()
    source.expired = True
    board.tick()
    assert board.take_sign_in_notice()
    board.sign_in()
    board.tick()
    source.expired = True
    clock.advance(minutes=5)
    board.tick()
    assert board.take_sign_in_notice()


def test_ics_has_no_sign_in():
    board = ReminderBoard(FakeSource(), FakeClock(NOW))
    assert not board.sign_in()
