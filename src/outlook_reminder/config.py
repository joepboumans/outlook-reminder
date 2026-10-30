"""The config file (~/.config/outlook-reminder/config.toml)."""

from __future__ import annotations

import os
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_CONFIG = """\
# Outlook Reminder configuration.

[calendar]
# Where the calendar is read from:
#   "ics"   a published ICS link (works without IT approval, but lags behind)
#   "graph" Microsoft Graph with your work sign-in (needs the app approved by IT,
#           see docs/it-approval.md, and the IDs in [graph] below)
source = "ics"

# Published ICS link of your Outlook calendar
# (Outlook on the web: Settings > Calendar > Shared calendars > Publish a calendar).
ics_url = ""
# Your work email address. Used to spot meetings you declined in the ICS feed.
# email = "you@example.com"

[graph]
# From IT once the app is registered (docs/it-approval.md). Neither is a secret.
client_id = ""   # Application (client) ID
tenant_id = ""   # Directory (tenant) ID

[sound]
# Play a short chime with each reminder notification.
chime = true
"""


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    source: Literal["ics", "graph"] = "ics"
    ics_url: str = ""
    email: str | None = None
    chime: bool = True
    client_id: str = ""
    tenant_id: str = ""


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
    source = str(calendar.get("source", "ics")).strip().lower()
    ics_url = str(calendar.get("ics_url", "")).strip()
    email = str(calendar.get("email", "")).strip() or None
    chime = data.get("sound", {}).get("chime", True)
    if not isinstance(chime, bool):
        raise ConfigError(f"sound.chime in {path} must be true or false.")

    if source == "ics":
        if not ics_url:
            raise ConfigError(f"Set calendar.ics_url in {path} to your published ICS link.")
        return Config(source="ics", ics_url=ics_url, email=email, chime=chime)
    if source == "graph":
        graph = data.get("graph", {})
        client_id = str(graph.get("client_id", "")).strip()
        tenant_id = str(graph.get("tenant_id", "")).strip()
        if not client_id or not tenant_id:
            raise ConfigError(
                f"Set graph.client_id and graph.tenant_id in {path} to the IDs from IT (see docs/it-approval.md)."
            )
        try:
            uuid.UUID(client_id)
        except ValueError:
            raise ConfigError(f"graph.client_id in {path} should look like 00000000-0000-0000-0000-000000000000.") from None
        return Config(source="graph", ics_url=ics_url, email=email, chime=chime,
                      client_id=client_id, tenant_id=tenant_id)
    raise ConfigError(f'calendar.source in {path} must be "ics" or "graph", not "{source}".')
