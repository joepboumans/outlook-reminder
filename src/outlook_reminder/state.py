"""Snooze and Dismiss state, saved locally so it survives app restarts. Nothing goes to Outlook."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dismissed:
    """A Dismiss, made for the Meeting starting at `start` (moving the Meeting discards it)."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class Snoozed:
    """A Snooze until `until`, made for the Meeting starting at `start`."""

    start: datetime
    end: datetime
    until: datetime


@dataclass
class ReminderState:
    """Per Meeting key (one per occurrence of a recurring Meeting)."""

    dismissed: dict[str, Dismissed] = field(default_factory=dict)
    snoozed: dict[str, Snoozed] = field(default_factory=dict)


class StateStore(Protocol):
    def load(self) -> ReminderState: ...
    def save(self, state: ReminderState) -> None: ...


class MemoryStateStore:
    """Keeps nothing across restarts."""

    def load(self) -> ReminderState:
        return ReminderState()

    def save(self, state: ReminderState) -> None:
        pass


def default_state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "outlook-reminder" / "state.json"


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> ReminderState:
        try:
            data = json.loads(self._path.read_text())
            return ReminderState(
                dismissed={k: Dismissed(_time(v["start"]), _time(v["end"])) for k, v in data["dismissed"].items()},
                snoozed={
                    k: Snoozed(_time(v["start"]), _time(v["end"]), _time(v["until"]))
                    for k, v in data["snoozed"].items()
                },
            )
        except FileNotFoundError:
            return ReminderState()
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            log.warning("Ignoring the unreadable state file %s: %s", self._path, e)
            return ReminderState()

    def save(self, state: ReminderState) -> None:
        data: dict[str, Any] = {
            "dismissed": {k: {"start": v.start.isoformat(), "end": v.end.isoformat()}
                          for k, v in state.dismissed.items()},
            "snoozed": {k: {"start": v.start.isoformat(), "end": v.end.isoformat(), "until": v.until.isoformat()}
                        for k, v in state.snoozed.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write a new file and rename it, so a crash never leaves half a file.
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1))
            tmp.replace(self._path)
        except OSError as e:
            log.warning("Could not save the state file %s: %s", self._path, e)


def _time(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError(f"time without a timezone: {value}")
    return t
