"""Cud command-line interface."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from cud.agent.cli import register_agent_commands
from cud.engine.cli import register_engine_commands
from cud.gateway.cli import register_gateway_commands
from cud.tools.mcp import register_mcp_commands
from cud.tools.skills import register_tools_commands
from cud.tools.tasks import register_task_commands
from cud.tui.cli import register_tui_commands

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cud", description="Local multi-agent framework for Ollama.")
    sub = parser.add_subparsers(dest="command", required=True)

    register_agent_commands(sub)
    register_gateway_commands(sub)
    register_tools_commands(sub)
    register_mcp_commands(sub)
    register_engine_commands(sub)
    register_task_commands(sub)
    register_tui_commands(sub)

    completion = sub.add_parser("completion", help="Generate shell completion")
    completion.add_argument("shell", choices=["bash", "zsh"])
    completion.set_defaults(func=cmd_completion)
    return parser


def cmd_completion(args: argparse.Namespace) -> int:
    if args.shell == "bash":
        console.print("complete -W 'agent gateway tools mcp engine task tui completion' cud")
    else:
        console.print("#compdef cud\n_arguments '1:command:(agent gateway tools mcp engine task tui completion)'")
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
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
