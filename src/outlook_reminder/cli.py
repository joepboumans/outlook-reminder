"""Command line entry point: `outlook-reminder`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .clock import SystemClock
from .config import DEFAULT_CONFIG, Config, ConfigError, default_config_path, load_config
from .ics import IcsSource
from .reminders import ReminderBoard
from .source import CalendarSource, SignInFailed
from .state import JsonStateStore, default_state_path
from .text import start_time

if TYPE_CHECKING:
    from .auth import GraphAuth


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outlook-reminder", description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path(), help="config file")
    parser.add_argument("--check", action="store_true",
                        help="read the calendar once, print upcoming reminders and exit")
    parser.add_argument("--init-config", action="store_true",
                        help="write the default config file if there is none, then exit")
    parser.add_argument("--sign-in", action="store_true",
                        help="sign in to Microsoft 365 in the browser (source = graph), then exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.init_config:
        return _init_config(args.config)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"outlook-reminder: {e}", file=sys.stderr)
        return 2

    if args.sign_in:
        return _sign_in(config)

    board = ReminderBoard(make_source(config), SystemClock(), store=JsonStateStore(default_state_path()))
    if args.check:
        return _check(board)

    from .app import ReminderApp  # GTK is only needed for the desktop app

    return ReminderApp(board, chime=config.chime).run([sys.argv[0]])


def make_source(config: Config) -> CalendarSource:
    if config.source == "graph":
        return _graph_source(config)
    return IcsSource(config.ics_url, me=config.email)


def _graph_auth(config: Config) -> GraphAuth:
    # Imported here so the ICS source never loads msal or keyring.
    from .auth import GraphAuth, KeyringTokenStore, msal_app_factory

    store = KeyringTokenStore(f"{config.tenant_id}/{config.client_id}")
    return GraphAuth(msal_app_factory(config.client_id, config.tenant_id), store)


def _graph_source(config: Config) -> CalendarSource:
    from .graph import GraphSource

    return GraphSource(_graph_auth(config))


def _sign_in(config: Config) -> int:
    if config.source != "graph":
        print('outlook-reminder: sign-in is only needed with source = "graph" in the config file', file=sys.stderr)
        return 2
    print("Opening the browser to sign in to Microsoft 365...")
    try:
        user = _graph_auth(config).sign_in()
    except SignInFailed as e:
        print(f"outlook-reminder: {e}", file=sys.stderr)
        return 1
    print(f"Signed in{' as ' + user if user else ''}.")
    return 0


def _check(board: ReminderBoard) -> int:
    if not board.refresh():
        if board.needs_sign_in:
            print("outlook-reminder: sign in first with: outlook-reminder --sign-in", file=sys.stderr)
            return 1
        print("outlook-reminder: could not read the calendar (see the warning above)", file=sys.stderr)
        return 1
    upcoming = board.upcoming()
    for r in upcoming:
        m = r.meeting
        print(f"{start_time(m.start, m.all_day)}  {m.title}  (reminder at {start_time(r.due_at)})")
    if not upcoming:
        print("No upcoming reminders.")
    return 0


def _init_config(path: Path) -> int:
    if path.exists():
        print(f"Keeping the existing config file {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG)
    print(f"Wrote a default config file to {path}; put your ICS link or Graph IDs in it.")
    return 0
