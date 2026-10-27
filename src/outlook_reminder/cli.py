"""Command line entry point: `outlook-reminder`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .clock import SystemClock
from .config import ConfigError, default_config_path, load_config
from .ics import IcsSource
from .reminders import ReminderBoard
from .text import start_time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outlook-reminder", description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path(), help="config file")
    parser.add_argument("--check", action="store_true",
                        help="read the calendar once, print upcoming reminders and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"outlook-reminder: {e}", file=sys.stderr)
        return 2

    board = ReminderBoard(IcsSource(config.ics_url, me=config.email), SystemClock())
    if args.check:
        return _check(board)

    from .app import ReminderApp  # GTK is only needed for the desktop app

    return ReminderApp(board, chime=config.chime).run([sys.argv[0]])


def _check(board: ReminderBoard) -> int:
    if not board.refresh():
        print("outlook-reminder: could not read the calendar (see the warning above)", file=sys.stderr)
        return 1
    upcoming = board.upcoming()
    for r in upcoming:
        m = r.meeting
        print(f"{start_time(m.start, m.all_day)}  {m.title}  (reminder at {start_time(r.due_at)})")
    if not upcoming:
        print("No upcoming reminders.")
    return 0
