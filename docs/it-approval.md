# Request: approve "Outlook Reminder" for Microsoft 365 sign-in

## What it is

A small desktop app for Ubuntu Linux that shows Outlook-style meeting reminders (the "Reminders" window Outlook for Windows has). It runs only on my own laptop, under my own account.

## What it accesses

- **Delegated** permissions only. It acts as the signed-in user and can only see that user's own calendar.
- `Calendars.Read`: read events on my own calendar (title, time, location, reminder setting, my response, Teams link)
- `User.Read`: basic sign-in profile
- `offline_access`: stay signed in without asking again every hour

It never writes to the mailbox or calendar, and it reads no mail, files, chats or other users' data.

## How it signs in

- Registered as a **public client** (a desktop app). It has no client secret or certificate.
- Interactive sign-in through the system browser, using the authorization code flow with PKCE. MFA and Conditional Access apply as usual.
- Device code flow is not used, and "Allow public client flows" can stay **off**.
- Tokens are stored in the GNOME keyring on the laptop. Nothing is sent to any third-party server; the app talks only to `login.microsoftonline.com` and `graph.microsoft.com`.

## What I need

Either:

1. **IT registers the app**, or lets me register it, with these settings:
   - Supported account types: *Accounts in this organizational directory only* (single tenant)
   - Platform: **Mobile and desktop applications**, redirect URI `http://localhost`
   - API permissions (Microsoft Graph, delegated): `Calendars.Read`, `User.Read`, `offline_access`
2. **Grant consent** for those permissions, either admin consent for me only, or by allowing user consent for this app.

Afterwards I need the **Application (client) ID** and the **Directory (tenant) ID**. Neither is a secret.

Source code: https://github.com/joepboumans/outlook-reminder
