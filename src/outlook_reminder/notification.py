"""What a Reminder notification says, and the chime that goes with it."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading

from .reminders import Reminder
from .text import start_time

log = logging.getLogger(__name__)

FREEDESKTOP_SOUND = "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"


def notification_text(reminder: Reminder) -> tuple[str, str]:
    """The notification's title and body: the Meeting's title, start time and location."""
    m = reminder.meeting
    when = start_time(m.start, m.all_day) + (" · All day" if m.all_day else "")
    return m.title, " · ".join(part for part in (when, m.location) if part)


def sign_in_notification_text() -> tuple[str, str]:
    """The one notification sent when the Microsoft 365 sign-in has expired."""
    return (
        "Sign in to keep getting reminders",
        "Your Microsoft 365 sign-in has expired, so new meetings are not picked up.",
    )


def has_join(reminder: Reminder) -> bool:
    """The Reminder notification and the Reminders window offer Join only with a Teams link."""
    return reminder.meeting.teams_url is not None


def play_chime() -> None:
    """Play a short chime without blocking. Silently does nothing when no player is installed."""
    if shutil.which("canberra-gtk-play"):
        command = ["canberra-gtk-play", "--id", "message-new-instant", "--description", "Meeting reminder"]
    elif shutil.which("paplay"):
        command = ["paplay", FREEDESKTOP_SOUND]
    elif shutil.which("pw-play"):
        command = ["pw-play", FREEDESKTOP_SOUND]
    else:
        log.info("No sound player found; skipping the chime")
        return

    def play() -> None:
        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("Could not play the chime: %s", e)

    threading.Thread(target=play, name="chime", daemon=True).start()
