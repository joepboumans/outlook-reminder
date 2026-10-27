"""The config file (~/.config/outlook-reminder/config.toml)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG = """\
# Outlook Reminder configuration.

[calendar]
# Published ICS link of your Outlook calendar
# (Outlook on the web: Settings > Calendar > Shared calendars > Publish a calendar).
ics_url = ""
# Your work email address. Used to spot meetings you declined in the ICS feed.
# email = "you@example.com"
"""


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    ics_url: str
    email: str | None = None


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "outlook-reminder" / "config.toml"


def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"No config file found. Create {path} with your ICS link.") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from None

    calendar = data.get("calendar", {})
    ics_url = str(calendar.get("ics_url", "")).strip()
    if not ics_url:
        raise ConfigError(f"Set calendar.ics_url in {path} to your published ICS link.")
    email = str(calendar.get("email", "")).strip() or None
    return Config(ics_url=ics_url, email=email)
