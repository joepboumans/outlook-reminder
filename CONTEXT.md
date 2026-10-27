# Outlook Reminder

A Linux desktop app that shows Outlook-style meeting reminders for a Microsoft 365 work calendar.

## Language

**Meeting**:
An event on the user's Microsoft 365 calendar that has a start and end time.
_Avoid_: Appointment, event (when meaning one the user will be reminded of)

**Reminder**:
The prompt that a **Meeting** is coming up, due at the **Reminder time**. One per **Meeting** occurrence.
_Avoid_: Alarm, notification, alert

**Reminder time**:
How long before a **Meeting** starts its **Reminder** becomes due, taken from the Meeting's own Outlook setting (15 minutes when Outlook gives none).
_Avoid_: Lead time, offset

**Silent meeting**:
A **Meeting** whose Outlook reminder is turned off, or that is declined or cancelled. It never produces a **Reminder**.

**Due reminder**:
A **Reminder** whose time has come and that is neither snoozed nor dismissed. Shown in the **Reminders window**.

**Overdue reminder**:
A **Due reminder** whose time passed while the app could not show it (machine asleep or off), shown once the app can, as long as the **Meeting** has not ended.

**Snooze**:
Hiding a **Due reminder** until a chosen later moment, either a duration ("10 minutes") or a point relative to the start ("5 minutes before start").

**Dismiss**:
Permanently hiding a **Reminder** on this machine only. Does not change anything in Outlook.

**Reminders window**:
The single small window listing every **Due reminder**, with Dismiss, Snooze and Join actions.
_Avoid_: Popup, notification

**Reminder notification**:
The desktop notification sent when a **Reminder** becomes due, so it is noticed even when the **Reminders window** opens behind other windows. Clicking it brings the Reminders window forward.
_Avoid_: Alert, popup

**Join**:
Opening a **Meeting**'s Teams link in Teams for Linux. Only offered when the Meeting has a Teams link.

## Relationships

- A **Meeting** has at most one **Reminder** (none if it is a **Silent meeting**)
- A **Reminder** is either pending, due, snoozed or dismissed
- Moving a **Meeting** to a new start time discards any **Snooze** or **Dismiss** of its **Reminder**, and a new Reminder is scheduled
- Each time a **Reminder** becomes due (including after a Snooze ends) one **Reminder notification** is sent
- The **Reminders window** shows zero or more **Due reminders**; it closes when none remain

## Flagged ambiguities

- "Start on boot" means start on login: the **Reminders window** needs the user's desktop session.
