"""TUI CLI commands."""

from __future__ import annotations

import argparse
import asyncio

from cud.tui.app import run_tui


def register_tui_commands(sub: argparse._SubParsersAction) -> None:
    tui = sub.add_parser("tui", help="Run agent in local TUI mode")
    tui.add_argument("agent")
    tui.add_argument("--thread-id", default="local-tui", help="Thread ID for the conversation")
    tui.set_defaults(func=cmd_tui)


def cmd_tui(args: argparse.Namespace) -> int:
    return asyncio.run(run_tui(args.agent, thread_id=args.thread_id))
