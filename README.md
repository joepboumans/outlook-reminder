# Outlook Reminder

Outlook-style meeting reminders for a Microsoft 365 work calendar on Ubuntu (GNOME on Wayland).

When a meeting's reminder is due, a small **Reminders** window lists it with Snooze and Dismiss, and a desktop notification with a short chime makes sure you notice it. Terms are defined in [CONTEXT.md](CONTEXT.md) and the requirements are in [docs/requirements.md](docs/requirements.md).

For now the calendar is read from a published ICS link. Reading it through Microsoft Graph comes later, once the app registration is approved ([ADR 0001](docs/adr/0001-microsoft-graph-with-own-app-registration.md)).

## Install

On Ubuntu 26.04, as your own user (no root):

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1   # once, if not installed yet
git clone https://github.com/joepboumans/outlook-reminder.git
cd outlook-reminder
./install.sh
```

`install.sh` installs [uv](https://docs.astral.sh/uv/) if you don't have it, installs the app into `~/.local/share/outlook-reminder`, links `outlook-reminder` into `~/.local/bin`, adds a desktop entry (GNOME needs it to show the notifications), writes a default config file if there is none, and sets the app up to start when you log in. Run it again after a `git pull` to upgrade; your config and your snoozes and dismisses are kept.

## Configure

Edit `~/.config/outlook-reminder/config.toml`:

```toml
[calendar]
# Outlook on the web: Settings > Calendar > Shared calendars > Publish a calendar,
# then copy the ICS link.
ics_url = "https://outlook.office365.com/owa/calendar/.../calendar.ics"
# Your work email; lets the app skip meetings you declined.
email = "you@example.com"

[sound]
chime = true   # false mutes the chime
```

## Run

```sh
outlook-reminder           # runs in the background; the window opens when a reminder is due
outlook-reminder --check   # reads the calendar once and prints the upcoming reminders
```

The calendar is read every 5 minutes, and right after the laptop wakes up or the network changes. Closing the Reminders window only hides it; it comes back with the next due reminder.

Reminders that came due while the laptop was asleep or off are shown when it is back, unless the meeting has already ended. Snoozes and dismisses are saved in `~/.local/state/outlook-reminder/state.json`, so they survive a restart; nothing is changed in Outlook. Moving a meeting to a new time gives it a fresh reminder.

Meetings with a Teams link get a **Join** button, in the Reminders window and in the notification. It opens the meeting in [Teams for Linux](https://github.com/IsmaelMartinez/teams-for-linux) through its `msteams:` link; without Teams for Linux installed, the link opens in your browser.

### Start on login

`install.sh` adds a systemd user service, `outlook-reminder.service`, that starts the app when you log in to your desktop and restarts it if it crashes. To manage it:

```sh
systemctl --user start outlook-reminder     # start it now
systemctl --user stop outlook-reminder      # stop it until the next login
systemctl --user disable outlook-reminder   # stop starting it on login
systemctl --user status outlook-reminder    # is it running?
journalctl --user -u outlook-reminder       # its log
```

### What gets a reminder

- Each meeting uses its own Outlook reminder time, or 15 minutes when the calendar gives none.
- Meetings with the reminder turned off, declined meetings and cancelled meetings get none. Tentative meetings do.
- All-day events only get one when they have a reminder set.

Limits of the ICS link: many published calendars leave out reminder times. When the feed has no reminders at all, every meeting gets the 15 minute default. When it has some, a meeting without one is taken to have its reminder turned off. Declined meetings are only recognised when `email` is set and the feed lists attendees.

## Uninstall

```sh
systemctl --user disable --now outlook-reminder
rm -f ~/.config/systemd/user/outlook-reminder.service
systemctl --user daemon-reload
rm -rf ~/.local/state/outlook-reminder
rm -rf ~/.local/share/outlook-reminder ~/.local/bin/outlook-reminder \
       ~/.local/share/applications/io.github.joepboumans.OutlookReminder.desktop
rm -rf ~/.config/outlook-reminder   # also removes your config
```

## Development

```sh
uv sync                  # dependencies for the tests
uv run pytest            # tests
uv run pyright           # type check
```

The reminder logic (`reminders.py`, `snooze.py`, `state.py`, `ics.py`, `teams.py`) is built test-first against a fake calendar source and a fake clock in `tests/fakes.py`. The GTK window (`window.py`, `app.py`) is a thin layer checked by hand.

GTK comes from the system, so to run the app from the checkout, make the venv see the system packages first:

```sh
uv venv --system-site-packages --python /usr/bin/python3
uv run outlook-reminder -v
```
