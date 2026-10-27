# Requirements (v1)

Agreed in the design session of 2026-10-27. Terms are defined in [CONTEXT.md](../CONTEXT.md).

## Platform

- Ubuntu 26.04 LTS, GNOME on Wayland (the default session)
- Python with GTK4 / libadwaita
- Installed per user with `install.sh`; it starts on login through a systemd user service and restarts if it crashes
- Managed with `uv` and with `pyproject.toml`

## Calendar

- Work Microsoft 365 account, read through Microsoft Graph with this project's own app registration ([ADR 0001](adr/0001-microsoft-graph-with-own-app-registration.md), [IT approval note](it-approval.md))
- Sign-in opens the system browser (auth code + PKCE); tokens are kept in the GNOME keyring
- Only the main calendar
- Read-only: nothing is written back to Outlook
- Refreshed every 5 minutes, and right after resume from sleep or a network change
- The calendar source is swappable; a published ICS link may stand in while the app approval is pending
- When the sign-in expires, an entry "Sign in to keep getting reminders" appears in the Reminders window

## Which meetings get a reminder

- Reminder time comes from the meeting's Outlook reminder setting; 15 minutes if none is given
- Silent meetings (reminder off, declined, cancelled) get none
- Tentative meetings do get one
- All-day events only when they have a reminder set
- A meeting moved to a new start time gets a fresh reminder; any snooze or dismiss is discarded

## Reminders window

- One small window listing every due reminder, like Outlook's Reminders window
- Per reminder: Dismiss, Snooze (with a choice), and Join when there is a Teams link
- Dismiss all, plus a snooze that applies to all selected reminders
- Snooze choices copy Outlook: 5, 10, 15, 30 minutes, 1–4 hours, "5 minutes before start", "0 minutes before start". The default is "5 minutes before start" until the meeting starts, then 5 minutes
- Overdue reminders (missed while asleep or off) are shown once the app can show them, if the meeting has not ended
- Snooze and dismiss state survives app restarts
- The window is not forced on top ([ADR 0002](adr/0002-no-forced-always-on-top-on-wayland.md))

## Reminder notification and sound

- Each time a reminder becomes due (also after a snooze ends), one desktop notification is sent, showing the title, start time and location
- Clicking it brings the Reminders window forward; it has a Join button when there is a Teams link
- A short chime plays; it can be muted in the config file

## Join

- Opens the Teams link in Teams for Linux through its `msteams:` link handler

## Settings

- A config file; no top-bar icon in v1

## Testing

- Reminder logic built test-first against a fake calendar source and a fake clock
- Graph access and the GTK window are thin layers that get manual checks
