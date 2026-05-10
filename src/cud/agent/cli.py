"""Agent CLI commands."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from cud.config.paths import agent_home, agents_root
from cud.config.scaffold import create_agent, delete_agent, list_agents
from cud.config.settings import load_settings, save_settings
from cud.gateway import systemd

console = Console()


def register_agent_commands(sub: argparse._SubParsersAction) -> None:
    agent = sub.add_parser("agent", help="Manage agents")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    create = agent_sub.add_parser("create", help="Create an agent")
    create.add_argument("name")
    create.add_argument("--template", default="default")
    create.set_defaults(func=cmd_agent_create)
    list_cmd = agent_sub.add_parser("list", help="List agents")
    list_cmd.add_argument("-v", "--verbose", action="store_true")
    list_cmd.set_defaults(func=cmd_agent_list)
    delete = agent_sub.add_parser("delete", help="Delete an agent")
    delete.add_argument("name")
    delete.add_argument("--yes", action="store_true")
    delete.set_defaults(func=cmd_agent_delete)
    config = agent_sub.add_parser("config", help="Edit agent settings")
    config.add_argument("name")
    config.add_argument("--model")
    config.add_argument("--context-window", type=int)
    config.add_argument("--temperature", type=float)
    config.add_argument("--allow-traversal", action="store_true", default=None)
    config.add_argument("--no-traversal", action="store_false", dest="allow_traversal")
    config.set_defaults(func=cmd_agent_config)


def cmd_agent_create(args: argparse.Namespace) -> int:
    path = create_agent(args.name, template=args.template)
    console.print(f"Created agent [bold]{args.name}[/bold] at {path}")
    return 0


def cmd_agent_list(args: argparse.Namespace) -> int:
    agents = list_agents()
    if not agents:
        console.print(f"No agents found under {agents_root()}")
        return 0
    columns = ("Name", "Path", "Model") if args.verbose else ("Name", "Path")
    table = Table(*columns)
    for path in agents:
        if args.verbose:
            try:
                model = load_settings(path).model.name
            except (FileNotFoundError, ValueError):
                model = "invalid settings"
            table.add_row(path.name, str(path), model)
        else:
            table.add_row(path.name, str(path))
    console.print(table)
    return 0


def cmd_agent_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        console.print("[red]Refusing to delete without --yes[/red]")
        return 2

    if systemd.systemd_available():
        console.print(f"Stopping service for [bold]{args.name}[/bold]...")
        systemd.stop_service(args.name)
        console.print(f"Disabling service for [bold]{args.name}[/bold]...")
        systemd.disable_service(args.name)
        console.print(f"Removing systemd unit for [bold]{args.name}[/bold]...")
        systemd.remove_unit(args.name)
        systemd.systemctl_user("daemon-reload")

    path = delete_agent(args.name, yes=True)
    console.print(f"Deleted agent directory: [bold]{path}[/bold]")
    return 0


def cmd_agent_config(args: argparse.Namespace) -> int:
    directory = agent_home(args.name)
    settings = load_settings(directory)
    if args.model:
        settings.model.name = args.model
    if args.context_window:
        settings.model.context_window = args.context_window
    if args.temperature is not None:
        settings.model.temperature = args.temperature
    if args.allow_traversal is not None:
        settings.runtime.allow_traversal = args.allow_traversal
    save_settings(directory, settings)
    console.print(f"Updated {directory / 'settings.yaml'}")
    return 0
