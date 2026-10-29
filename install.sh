#!/usr/bin/env bash
# Install Outlook Reminder for the current user (no root needed).
# Running it again upgrades in place and keeps your config and saved state.
set -euo pipefail

APP_ID="io.github.joepboumans.OutlookReminder"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/outlook-reminder"
VENV="$APP_DIR/venv"
BIN_DIR="$HOME/.local/bin"
SYSTEM_PYTHON="${SYSTEM_PYTHON:-/usr/bin/python3}"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "run this as your own user, not as root."

# GTK4, libadwaita and their Python bindings come from Ubuntu, not from PyPI.
say "Checking GTK4 and libadwaita"
if ! "$SYSTEM_PYTHON" -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw" 2>/dev/null; then
    die "GTK4 / libadwaita for Python are missing. Install them with:
    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
and run ./install.sh again."
fi

# uv installs the app and its Python dependencies.
if ! command -v uv >/dev/null 2>&1; then
    if [[ -x "$BIN_DIR/uv" ]]; then
        export PATH="$BIN_DIR:$PATH"
    else
        say "Installing uv for your user (https://docs.astral.sh/uv/)"
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        elif command -v wget >/dev/null 2>&1; then
            wget -qO- https://astral.sh/uv/install.sh | sh
        else
            die "neither curl nor wget is installed. Install uv (https://docs.astral.sh/uv/) or curl first."
        fi
        export PATH="$BIN_DIR:$PATH"
    fi
fi

say "Installing Outlook Reminder into $VENV"
mkdir -p "$APP_DIR" "$BIN_DIR"
# The venv sees the system packages so it can import the GTK bindings (gi).
uv venv --quiet --allow-existing --system-site-packages --python "$SYSTEM_PYTHON" "$VENV"
uv pip install --quiet --python "$VENV/bin/python" --reinstall-package outlook-reminder "$SRC_DIR"
ln -sf "$VENV/bin/outlook-reminder" "$BIN_DIR/outlook-reminder"

# GNOME shows notifications only for apps with a desktop entry.
say "Adding the desktop entry"
mkdir -p "$DATA_HOME/applications"
cat > "$DATA_HOME/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Outlook Reminder
Comment=Outlook-style meeting reminders
Exec=$BIN_DIR/outlook-reminder
Icon=alarm-symbolic
Terminal=false
Categories=Office;Calendar;
NoDisplay=true
EOF

"$VENV/bin/outlook-reminder" --init-config

# Start on login: a systemd user service tied to the graphical session (the
# Reminders window needs it), restarted when it crashes. The unit name is always
# the same, so running install.sh again only updates it.
say "Setting up start on login"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/outlook-reminder.service" <<EOF
[Unit]
Description=Outlook-style meeting reminders
PartOf=graphical-session.target
After=graphical-session.target
# Stop retrying after 5 crashes in a minute.
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
ExecStart=$VENV/bin/outlook-reminder
Restart=on-failure
RestartSec=5
# Exit code 2 is a config problem; restarting won't fix it.
RestartPreventExitStatus=2

[Install]
WantedBy=graphical-session.target
EOF
SERVICE_OK=0
if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable --quiet outlook-reminder.service
    # On an upgrade, restart a running copy so it runs the new version.
    systemctl --user try-restart outlook-reminder.service || true
    SERVICE_OK=1
else
    echo "Note: could not reach your systemd user session, so the app won't start on login yet. Run ./install.sh again from your desktop session."
fi

say "Done."
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: $BIN_DIR is not on your PATH yet; log out and in, or run $BIN_DIR/outlook-reminder." ;;
esac
echo "Put your ICS link in ${XDG_CONFIG_HOME:-$HOME/.config}/outlook-reminder/config.toml."
if [[ $SERVICE_OK == 1 ]]; then
    echo "The app starts by itself from your next login. To start it now: systemctl --user start outlook-reminder"
else
    echo "Then start the app with: outlook-reminder"
fi
