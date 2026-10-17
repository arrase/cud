"""Cud command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console

from cud.agent.cli import register_agent_commands
from cud.engine.cli import register_engine_commands
from cud.gateway.cli import register_gateway_commands
from cud.tools.cli import (
    register_mcp_commands,
    register_tasks_commands,
    register_tools_commands,
)
from cud.tui.cli import register_tui_commands

console = Console()
_log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cud", description="Local multi-agent framework for Ollama.")
    sub = parser.add_subparsers(dest="command", required=True)

    register_agent_commands(sub)
    register_gateway_commands(sub)
    register_tools_commands(sub)
    register_mcp_commands(sub)
    register_engine_commands(sub)
    register_tasks_commands(sub)
    register_tui_commands(sub)

    completion = sub.add_parser("completion", help="Generate shell completion")
    completion.add_argument("shell", choices=["bash", "zsh"])
    completion.set_defaults(func=cmd_completion, subcommands=sub.choices)
    return parser


def cmd_completion(args: argparse.Namespace) -> int:
    # Derived from the parser so a new subcommand cannot drift out of the script.
    commands = " ".join(args.subcommands)
    if args.shell == "bash":
        console.print(f"complete -W '{commands}' cud")
    else:
        console.print(f"#compdef cud\n_arguments '1:command:({commands})'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Canceled by user[/yellow]")
        return 130
    except _USER_ERRORS as exc:
        # Expected, user-facing errors: bad names, missing agents, bad values.
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    except Exception as exc:
        # Anything else is a bug: keep the traceback so it is actionable.
        _log.exception("Unhandled error in the '%s' command", args.command)
        console.print(f"[red]Unexpected error:[/red] {type(exc).__name__}: {exc}")
        return 1


# Failures a user can reasonably cause and fix themselves.
_USER_ERRORS = (
    ValueError,
    OSError,  # FileNotFoundError, FileExistsError, PermissionError, ...
    KeyError,
)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
