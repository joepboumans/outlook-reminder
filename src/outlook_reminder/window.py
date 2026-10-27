# pyright: reportMissingImports=false
"""The Reminders window (GTK4 / libadwaita). A thin layer over ReminderBoard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .reminders import Reminder  # noqa: E402
from .snooze import SnoozeChoice  # noqa: E402
from .text import describe_start, start_time  # noqa: E402


class Actions(Protocol):
    """What the window asks of the app."""

    def dismiss(self, keys: list[str]) -> None: ...
    def dismiss_all(self) -> None: ...
    def snooze(self, keys: list[str], choice: SnoozeChoice) -> None: ...
    def snooze_choices(self, keys: list[str]) -> list[SnoozeChoice]: ...
    def default_snooze(self, keys: list[str]) -> SnoozeChoice: ...


class SnoozePicker(Gtk.Box):
    """A drop-down of snooze choices plus a Snooze button.

    Follows the default choice until the user picks one, and drops choices
    that have moved into the past.
    """

    def __init__(self, label: str, on_snooze: Callable[[SnoozeChoice], None]) -> None:
        super().__init__(spacing=6)
        self._choices: list[SnoozeChoice] = []
        self._picked: SnoozeChoice | None = None
        self._updating = False
        self._model = Gtk.StringList()
        self.dropdown = Gtk.DropDown(model=self._model)
        self.dropdown.connect("notify::selected", self._on_selected)
        self.button = Gtk.Button(label=label)
        self.button.connect("clicked", lambda *_: self.current and on_snooze(self.current))
        self.append(self.dropdown)
        self.append(self.button)

    @property
    def current(self) -> SnoozeChoice | None:
        index = self.dropdown.get_selected()
        return self._choices[index] if 0 <= index < len(self._choices) else None

    def set_choices(self, choices: list[SnoozeChoice], default: SnoozeChoice) -> None:
        wanted = self._picked if self._picked in choices else default
        self._updating = True
        if choices != self._choices:
            self._choices = list(choices)
            self._model.splice(0, self._model.get_n_items(), [c.label for c in choices])
        if wanted in self._choices:
            self.dropdown.set_selected(self._choices.index(wanted))
        self._updating = False
        self.set_sensitive(bool(choices))

    def _on_selected(self, *_: object) -> None:
        if not self._updating:
            self._picked = self.current


class ReminderRow(Gtk.ListBoxRow):
    def __init__(self, reminder: Reminder, actions: Actions) -> None:
        super().__init__()
        self.key = reminder.meeting.key
        self.reminder = reminder
        self._actions = actions

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        self._title = Gtk.Label(xalign=0, wrap=True, css_classes=["heading"])
        self._when = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self._where = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label", "caption"])
        box.append(self._title)
        box.append(self._when)
        box.append(self._where)

        self.actions = Gtk.Box(spacing=6)
        self.snooze = SnoozePicker("Snooze", lambda c: actions.snooze([self.key], c))
        self.snooze.set_hexpand(True)
        self.actions.append(self.snooze)
        dismiss = Gtk.Button(label="Dismiss")
        dismiss.connect("clicked", lambda *_: actions.dismiss([self.key]))
        self.actions.append(dismiss)
        box.append(self.actions)

        self.set_child(box)

    def update(self, reminder: Reminder, now: datetime) -> None:
        m = reminder.meeting
        self.reminder = reminder
        self._title.set_label(m.title)
        when = start_time(m.start, m.all_day)
        self._when.set_label(when if m.all_day else f"{when} · {describe_start(m.start, now)}")
        self._where.set_label(m.location)
        self._where.set_visible(bool(m.location))
        keys = [self.key]
        self.snooze.set_choices(self._actions.snooze_choices(keys), self._actions.default_snooze(keys))


class RemindersWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, actions: Actions) -> None:
        super().__init__(application=app, title="Reminders", default_width=520, default_height=400)
        self._actions = actions
        self._rows: dict[str, ReminderRow] = {}
        # Closing the window only hides it; it comes back when a Reminder becomes due.
        self.set_hide_on_close(True)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE, css_classes=["boxed-list"])
        self.list.set_margin_top(12)
        self.list.set_margin_bottom(12)
        self.list.set_margin_start(12)
        self.list.set_margin_end(12)
        self.list.connect("selected-rows-changed", lambda *_: self._update_bottom())
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.list)

        bottom = Gtk.Box(spacing=6)
        bottom.set_margin_bottom(12)
        bottom.set_margin_start(12)
        bottom.set_margin_end(12)
        dismiss_all = Gtk.Button(label="Dismiss all")
        dismiss_all.connect("clicked", lambda *_: actions.dismiss_all())
        bottom.append(dismiss_all)
        spacer = Gtk.Box(hexpand=True)
        bottom.append(spacer)
        self.snooze_selected = SnoozePicker(
            "Snooze selected", lambda c: actions.snooze(self.selected_keys(), c)
        )
        bottom.append(self.snooze_selected)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(scroller)
        content.append(bottom)

        view = Adw.ToolbarView(content=content)
        view.add_top_bar(Adw.HeaderBar())
        self.set_content(view)

    def make_row(self, reminder: Reminder) -> ReminderRow:
        return ReminderRow(reminder, self._actions)

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
            row.update(reminder, now)
        self._update_bottom()

    def row(self, key: str) -> ReminderRow | None:
        return self._rows.get(key)

    def selected_keys(self) -> list[str]:
        return [row.key for row in self.list.get_selected_rows() if isinstance(row, ReminderRow)]

    def _update_bottom(self) -> None:
        keys = self.selected_keys()
        if keys:
            self.snooze_selected.set_choices(
                self._actions.snooze_choices(keys), self._actions.default_snooze(keys)
            )
        else:
            self.snooze_selected.set_choices([], self._actions.default_snooze([]))
