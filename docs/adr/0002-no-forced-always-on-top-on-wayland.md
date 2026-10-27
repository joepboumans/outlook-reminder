# Don't force the Reminders window on top under Wayland

Ubuntu's default GNOME Wayland session doesn't let an app raise itself above the window the user is working in, so the Reminders window may open behind it. We accept this rather than ask the user to run an X11 session or use compositor hacks. Instead, each Reminder that becomes due also sends a desktop notification with a chime, and clicking the notification brings the window forward.
