# pyright: reportMissingImports=false
"""The desktop app: wires the ReminderBoard to the Reminders window and a timer."""

from __future__ import annotations

import logging
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from .notification import has_join, notification_text, play_chime, sign_in_notification_text  # noqa: E402
from .reminders import Reminder, ReminderBoard  # noqa: E402
from .snooze import SnoozeChoice  # noqa: E402
from .teams import msteams_uri  # noqa: E402
from .window import RemindersWindow  # noqa: E402

log = logging.getLogger(__name__)

APP_ID = "io.github.joepboumans.OutlookReminder"
TICK_SECONDS = 10
# A gap this much longer than a tick between two timer runs means the laptop slept.
SLEEP_GAP_SECONDS = 60


class ReminderApp(Adw.Application):
    def __init__(self, board: ReminderBoard, chime: bool = True) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._board = board
        self._chime = chime
        self._window: RemindersWindow | None = None
        self._reading = False
        self._notified: set[str] = set()
        self._last_timer = time.time()
        # The browser sign-in is running, then the calendar read right after it.
        self._signing_in = False
        self._finishing_sign_in = False
        self._first_sign_in_tried = False
        self._sign_in_notified = False

        show = Gio.SimpleAction.new("show-reminders", None)
        show.connect("activate", lambda *_: self._present())
        self.add_action(show)
        join = Gio.SimpleAction.new("join", GLib.VariantType.new("s"))
        join.connect("activate", lambda _action, key: self.join(key.get_string()))
        self.add_action(join)
        sign_in = Gio.SimpleAction.new("sign-in", None)
        sign_in.connect("activate", lambda *_: self.sign_in())
        self.add_action(sign_in)

    # The app runs in the background with no window until a Reminder is due.
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()
        GLib.timeout_add_seconds(TICK_SECONDS, self._on_timer)
        GLib.idle_add(self._on_timer)
        self._watch_resume_and_network()

    def _watch_resume_and_network(self) -> None:
        """Read the calendar right after resume from sleep and after a network change."""
        Gio.NetworkMonitor.get_default().connect("network-changed", lambda *_: self._read_soon("network change"))
        try:
            system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            log.info("No system bus, resume is only noticed by the clock jump: %s", e.message)
            return
        self._system_bus = system_bus
        system_bus.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
            "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, self._on_prepare_for_sleep,
        )

    def _on_prepare_for_sleep(self, _conn, _sender, _path, _iface, _signal, params) -> None:
        going_to_sleep = params.unpack()[0]
        if not going_to_sleep:
            self._read_soon("resume")

    def _read_soon(self, why: str) -> None:
        log.debug("Reading the calendar after %s", why)
        self._board.read_soon()
        GLib.idle_add(self._on_timer_once)

    def _on_timer_once(self) -> bool:
        self._on_timer()
        return GLib.SOURCE_REMOVE

    def do_activate(self) -> None:
        if self._board.due or self._board.needs_sign_in:
            self._present()

    @property
    def window(self) -> RemindersWindow:
        if self._window is None:
            self._window = self.create_window()
        return self._window

    def create_window(self) -> RemindersWindow:
        return RemindersWindow(self, actions=self)

    def _on_timer(self) -> bool:
        # GLib timers stop during suspend, so a jump in wall-clock time means we just woke up.
        wall = time.time()
        if wall - self._last_timer > SLEEP_GAP_SECONDS:
            self._board.read_soon()
        self._last_timer = wall
        # No reads while the browser sign-in runs; it asks for one when it is done.
        if self._board.calendar_read_due() and not self._reading and not self._signing_in:
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
        # The read after a sign-in is done; the window may now hide if nothing is due.
        self._finishing_sign_in = False
        self.on_newly_due(self._board.tick(read_calendar=False))
        if self._board.never_signed_in and not self._first_sign_in_tried:
            # First run: nobody has signed in yet, so open the browser sign-in right away
            # instead of sending the notification.
            self._first_sign_in_tried = True
            self._board.take_sign_in_notice()
            self.sign_in()
            self._present()
        elif self._board.take_sign_in_notice():
            self.send_notification(SIGN_IN_NOTIFICATION, _sign_in_notification())
            self._sign_in_notified = True
            self._present()
        self.update_window()
        return GLib.SOURCE_REMOVE

    def sign_in(self) -> None:
        """Start the browser sign-in on a worker thread; once done, read the calendar."""
        if self._signing_in or self._finishing_sign_in:
            return
        self._signing_in = True
        self.update_window()

        def work() -> None:
            try:
                self._board.sign_in()
            except Exception:
                log.exception("Signing in failed")
            GLib.idle_add(self._after_sign_in)

        threading.Thread(target=work, name="sign-in", daemon=True).start()

    def _after_sign_in(self) -> bool:
        self._signing_in = False
        self._board.read_soon()
        if not self._reading:
            # Keep the window as it is until this read is done, instead of hiding it in between.
            self._finishing_sign_in = True
            self._read_calendar_in_background()
        self.update_window()
        return GLib.SOURCE_REMOVE

    def on_newly_due(self, reminders: list[Reminder]) -> None:
        """One Reminder notification for each Reminder that just became due, and one chime."""
        for reminder in reminders:
            self.send_notification(_notification_id(reminder.meeting.key), _notification(reminder))
        if reminders:
            if self._chime:
                play_chime()
            self._present()

    def update_window(self) -> None:
        due = self._board.due
        # Take back notifications of Reminders that were dismissed or snoozed.
        for key in self._notified - {r.meeting.key for r in due}:
            self.withdraw_notification(_notification_id(key))
        self._notified = {r.meeting.key for r in due}
        needs_sign_in = self._board.needs_sign_in
        if not needs_sign_in and self._sign_in_notified:
            self.withdraw_notification(SIGN_IN_NOTIFICATION)
            self._sign_in_notified = False
        busy = self._signing_in or self._finishing_sign_in
        if not due and not needs_sign_in and not busy:
            if self._window is not None:
                self._window.set_visible(False)
            return
        self.window.show_sign_in(needs_sign_in or busy, signing_in=busy)
        self.window.show_reminders(due, self._board.now())

    def _present(self) -> None:
        self.update_window()
        if self._board.due or self._board.needs_sign_in:
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

    def join(self, key: str) -> None:
        url = next((r.meeting.teams_url for r in self._board.due if r.meeting.key == key), None)
        if url is None:
            return
        # Teams for Linux registers the msteams: scheme; without it, use the browser.
        uri = msteams_uri(url) if Gio.AppInfo.get_default_for_uri_scheme("msteams") else url
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as e:
            log.warning("Could not open the Teams meeting %s: %s", uri, e.message)


SIGN_IN_NOTIFICATION = "sign-in"


def _sign_in_notification() -> Gio.Notification:
    title, body = sign_in_notification_text()
    notification = Gio.Notification.new(title)
    notification.set_body(body)
    notification.set_priority(Gio.NotificationPriority.HIGH)
    notification.set_default_action("app.show-reminders")
    notification.add_button("Sign in", "app.sign-in")
    return notification


def _notification_id(key: str) -> str:
    return f"reminder-{key}"


def _notification(reminder: Reminder) -> Gio.Notification:
    title, body = notification_text(reminder)
    notification = Gio.Notification.new(title)
    notification.set_body(body)
    notification.set_priority(Gio.NotificationPriority.HIGH)
    # Clicking the notification brings the Reminders window forward.
    notification.set_default_action("app.show-reminders")
    if has_join(reminder):
        notification.add_button_with_target("Join", "app.join", GLib.Variant.new_string(reminder.meeting.key))
    return notification
