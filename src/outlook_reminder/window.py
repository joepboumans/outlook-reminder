# pyright: reportMissingImports=false
"""The Reminders window (GTK4 / libadwaita). A thin layer over ReminderBoard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .reminders import Reminder  # noqa: E402
from .text import describe_start, start_time  # noqa: E402


class ReminderRow(Gtk.ListBoxRow):
    def __init__(self, reminder: Reminder, on_dismiss: Callable[[str], None]) -> None:
        super().__init__()
        self.key = reminder.meeting.key
        self.reminder = reminder

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self._title = Gtk.Label(xalign=0, wrap=True, css_classes=["heading"])
        self._when = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self._where = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label", "caption"])
        labels.append(self._title)
        labels.append(self._when)
        labels.append(self._where)
        box.append(labels)

        self.actions = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        dismiss = Gtk.Button(label="Dismiss")
        dismiss.connect("clicked", lambda *_: on_dismiss(self.key))
        self.actions.append(dismiss)
        box.append(self.actions)

        self.set_child(box)
        self.update(reminder, reminder.due_at)

    def update(self, reminder: Reminder, now: datetime) -> None:
        m = reminder.meeting
        self.reminder = reminder
        self._title.set_label(m.title)
        when = start_time(m.start, m.all_day)
        self._when.set_label(when if m.all_day else f"{when} · {describe_start(m.start, now)}")
        self._where.set_label(m.location)
        self._where.set_visible(bool(m.location))


class RemindersWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, on_dismiss: Callable[[str], None]) -> None:
        super().__init__(application=app, title="Reminders", default_width=480, default_height=360)
        self._on_dismiss = on_dismiss
        self._rows: dict[str, ReminderRow] = {}
        # Closing the window only hides it; it comes back when a Reminder becomes due.
        self.set_hide_on_close(True)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE, css_classes=["boxed-list"])
        self.list.set_margin_top(12)
        self.list.set_margin_bottom(12)
        self.list.set_margin_start(12)
        self.list.set_margin_end(12)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.list)

        self.bottom = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.bottom.set_margin_bottom(12)
        self.bottom.set_margin_end(12)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(scroller)
        content.append(self.bottom)

        view = Adw.ToolbarView(content=content)
        view.add_top_bar(Adw.HeaderBar())
        self.set_content(view)

    def make_row(self, reminder: Reminder) -> ReminderRow:
        return ReminderRow(reminder, self._on_dismiss)

    def show_reminders(self, reminders: list[Reminder], now: datetime) -> None:
        """Show exactly these Reminders, keeping existing rows (and their selection)."""
        wanted = {r.meeting.key: r for r in reminders}
        for key in list(self._rows):
            if key not in wanted:
                self.list.remove(self._rows.pop(key))
        for position, reminder in enumerate(reminders):
            row = self._rows.get(reminder.meeting.key)
            if row is None:
                row = self._rows[reminder.meeting.key] = self.make_row(reminder)
                self.list.insert(row, position)
            else:
                row.update(reminder, now)

    def selected_keys(self) -> list[str]:
        return [row.key for row in self.list.get_selected_rows() if isinstance(row, ReminderRow)]
