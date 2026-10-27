from datetime import UTC, datetime, timedelta

from outlook_reminder.text import describe_start

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def test_describes_upcoming_running_and_now():
    assert describe_start(NOW + timedelta(minutes=10), NOW) == "Starts in 10 minutes"
    assert describe_start(NOW + timedelta(minutes=1), NOW) == "Starts in 1 minute"
    assert describe_start(NOW + timedelta(seconds=20), NOW) == "Starting now"
    assert describe_start(NOW - timedelta(minutes=5), NOW) == "Started 5 minutes ago"
    assert describe_start(NOW + timedelta(minutes=90), NOW) == "Starts in 1 hour 30 min"
    assert describe_start(NOW + timedelta(days=2), NOW) == "Starts in 2 days"
