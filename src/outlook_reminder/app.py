# pyright: reportMissingImports=false
"""The desktop app: wires the ReminderBoard to the Reminders window and a timer."""

from __future__ import annotations

import logging
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from .reminders import Reminder, ReminderBoard  # noqa: E402
from .snooze import SnoozeChoice  # noqa: E402
from .window import RemindersWindow  # noqa: E402

log = logging.getLogger(__name__)

APP_ID = "io.github.joepboumans.OutlookReminder"
TICK_SECONDS = 10


class ReminderApp(Adw.Application):
    def __init__(self, board: ReminderBoard) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._board = board
        self._window: RemindersWindow | None = None
        self._reading = False

        show = Gio.SimpleAction.new("show-reminders", None)
        show.connect("activate", lambda *_: self._present())
        self.add_action(show)

    # The app runs in the background with no window until a Reminder is due.
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()
        GLib.timeout_add_seconds(TICK_SECONDS, self._on_timer)
        GLib.idle_add(self._on_timer)

    def do_activate(self) -> None:
        if self._board.due:
            self._present()

    @property
    def window(self) -> RemindersWindow:
        if self._window is None:
            self._window = self.create_window()
        return self._window

    def create_window(self) -> RemindersWindow:
        return RemindersWindow(self, actions=self)

    def _on_timer(self) -> bool:
        if self._board.refresh_due() and not self._reading:
            self._read_calendar_in_background()
        self.on_newly_due(self._board.tick(read_calendar=False))
        self.update_window()
        return GLib.SOURCE_CONTINUE

    def _read_calendar_in_background(self) -> None:
        self._reading = True

        def work() -> None:
            try:
                self._board.refresh()
            except Exception:
                log.exception("Reading the calendar failed")
            GLib.idle_add(self._after_read)

        threading.Thread(target=work, name="calendar-read", daemon=True).start()

    def _after_read(self) -> bool:
        self._reading = False
        self.on_newly_due(self._board.tick(read_calendar=False))
        self.update_window()
        return GLib.SOURCE_REMOVE

    def on_newly_due(self, reminders: list[Reminder]) -> None:
        if reminders:
            self._present()

    def update_window(self) -> None:
        due = self._board.due
        if not due:
            if self._window is not None:
                self._window.set_visible(False)
            return
        self.window.show_reminders(due, self._board.now())

    def _present(self) -> None:
        self.update_window()
        if self._board.due:
            self.window.present()

    # Actions asked for by the Reminders window.
    def dismiss(self, keys: list[str]) -> None:
        for key in keys:
            self._board.dismiss(key)
        self.update_window()

    def dismiss_all(self) -> None:
        self._board.dismiss_all()
        self.update_window()

    def snooze(self, keys: list[str], choice: SnoozeChoice) -> None:
        self._board.snooze(keys, choice)
        self.update_window()

    def snooze_choices(self, keys: list[str]) -> list[SnoozeChoice]:
        return self._board.snooze_choices(keys)

    def default_snooze(self, keys: list[str]) -> SnoozeChoice:
        return self._board.default_snooze(keys)
