# Outlook Reminder

Outlook-style meeting reminders for a Microsoft 365 work calendar on Ubuntu (GNOME on Wayland).

When a meeting's reminder is due, a small **Reminders** window lists it with Snooze and Dismiss, and a desktop notification with a short chime makes sure you notice it. Terms are defined in [CONTEXT.md](CONTEXT.md) and the requirements are in [docs/requirements.md](docs/requirements.md).

The calendar is read through Microsoft Graph with your work sign-in, once IT has approved the app ([ADR 0001](docs/adr/0001-microsoft-graph-with-own-app-registration.md), [IT approval request](docs/it-approval.md)). Until then a published ICS link stands in.

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

Edit `~/.config/outlook-reminder/config.toml`. Pick one of the two calendar sources.

### Microsoft Graph (once IT approved the app)

IT gives you two IDs after registering the app ([what to ask for](docs/it-approval.md)):

```toml
[calendar]
source = "graph"

[graph]
client_id = "00000000-0000-0000-0000-000000000000"   # Application (client) ID
tenant_id = "00000000-0000-0000-0000-000000000000"   # Directory (tenant) ID

[sound]
chime = true
```

Then sign in once:

```sh
outlook-reminder --sign-in
```

Your browser opens the normal Microsoft sign-in page (with MFA as usual) and returns to the app on `http://localhost`. The app only asks to read your calendar (`Calendars.Read`, `User.Read`, `offline_access`) and never changes anything in Outlook. The sign-in is kept in the GNOME keyring and renewed by itself. If you skip this step, the app opens the browser sign-in itself on its first start.

When the sign-in expires or is revoked (for example after a password change), the Reminders window shows **Sign in to keep getting reminders** with a **Sign in** button, and one notification is sent. Reminders for meetings it already knows keep coming; new and changed meetings are picked up again once you sign in.

### Published ICS link

```toml
[calendar]
source = "ics"
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
outlook-reminder --sign-in # signs in to Microsoft 365 in the browser (source = "graph")
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
# The Graph sign-in is in the keyring: open Passwords and Keys and delete the "outlook-reminder" entry.
```

## Development

```sh
uv sync                  # dependencies for the tests
uv run pytest            # tests
uv run pyright           # type check
```

The reminder logic (`reminders.py`, `snooze.py`, `state.py`, `ics.py`, `teams.py`) is built test-first against a fake calendar source and a fake clock in `tests/fakes.py`. The Graph source (`graph.py`) is tested against recorded calendar responses in `tests/data/graph/`, and the sign-in (`auth.py`) against a fake MSAL client. The GTK window (`window.py`, `app.py`) is a thin layer checked by hand.

GTK comes from the system, so to run the app from the checkout, make the venv see the system packages first:

```sh
uv venv --system-site-packages --python /usr/bin/python3
uv run outlook-reminder -v
```
