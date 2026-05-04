"""Cud command-line interface."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cud.config.paths import agent_home, agents_root
from cud.config.scaffold import create_agent, delete_agent, list_agents
from cud.config.settings import load_settings, save_settings
from cud.gateway import systemd
from cud.tools.mcp import load_mcp_config, save_mcp_config
from cud.tools.skills import discover_skills

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cud", description="Local multi-agent framework for Ollama.")
    sub = parser.add_subparsers(dest="command", required=True)

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

    gateway = sub.add_parser("gateway", help="Manage gateway daemon")
    gateway_sub = gateway.add_subparsers(dest="gateway_command", required=True)
    setup = gateway_sub.add_parser("setup", help="Configure gateway credentials")
    setup.add_argument("agent")
    setup.add_argument("platform", choices=["discord", "telegram", "slack"])
    setup.add_argument("--token", required=True)
    setup.set_defaults(func=cmd_gateway_setup)
    run = gateway_sub.add_parser("run", help="Run gateway in foreground")
    run.add_argument("agent")
    run.add_argument("--verbose", action="store_true")
    run.set_defaults(func=cmd_gateway_run)
    start = gateway_sub.add_parser("start", help="Start gateway user service")
    start.add_argument("agent")
    start.set_defaults(func=cmd_gateway_start)
    stop = gateway_sub.add_parser("stop", help="Stop gateway user service")
    stop.add_argument("agent")
    stop.set_defaults(func=cmd_gateway_stop)
    status = gateway_sub.add_parser("status", help="Show gateway service status")
    status.add_argument("agent")
    status.set_defaults(func=cmd_gateway_status)

    tools = sub.add_parser("tools", help="Manage tools")
    tools_sub = tools.add_subparsers(dest="tools_command", required=True)
    tools_list = tools_sub.add_parser("list", help="List built-in and skill tools")
    tools_list.add_argument("agent")
    tools_list.set_defaults(func=cmd_tools_list)
    tools_install = tools_sub.add_parser("install", help="Install a skill from a local path")
    tools_install.add_argument("agent")
    tools_install.add_argument("path")
    tools_install.set_defaults(func=cmd_tools_install)

    mcp = sub.add_parser("mcp", help="Manage MCP servers")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_add = mcp_sub.add_parser("add", help="Add an MCP server")
    mcp_add.add_argument("agent")
    mcp_add.add_argument("server_url_or_cmd")
    mcp_add.add_argument("--name")
    mcp_add.add_argument("--allowed-tool", action="append", default=[])
    mcp_add.set_defaults(func=cmd_mcp_add)
    mcp_list = mcp_sub.add_parser("list", help="List MCP servers")
    mcp_list.add_argument("agent")
    mcp_list.set_defaults(func=cmd_mcp_list)

    engine = sub.add_parser("engine", help="Manage Ollama")
    engine_sub = engine.add_subparsers(dest="engine_command", required=True)
    engine_status = engine_sub.add_parser("status", help="Check Ollama status")
    engine_status.add_argument("--base-url", default="http://localhost:11434")
    engine_status.set_defaults(func=cmd_engine_status)
    engine_pull = engine_sub.add_parser("pull", help="Pull an Ollama model")
    engine_pull.add_argument("model_name")
    engine_pull.set_defaults(func=cmd_engine_pull)

    completion = sub.add_parser("completion", help="Generate shell completion")
    completion.add_argument("shell", choices=["bash", "zsh"])
    completion.set_defaults(func=cmd_completion)
    return parser


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
            except Exception:
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


def cmd_gateway_setup(args: argparse.Namespace) -> int:
    if args.platform != "discord":
        console.print("[yellow]Only Discord is implemented in v1; credentials were still saved as a stub.[/yellow]")
    directory = agent_home(args.agent)
    settings = load_settings(directory)
    settings.gateway.provider = args.platform
    settings.gateway.token = args.token
    save_settings(directory, settings)
    console.print(f"Configured {args.platform} gateway for {args.agent}")
    return 0


def cmd_gateway_run(args: argparse.Namespace) -> int:
    from cud.gateway.run import main as gateway_main

    return gateway_main([args.agent] + (["--verbose"] if args.verbose else []))


def cmd_gateway_start(args: argparse.Namespace) -> int:
    path = systemd.install_unit(args.agent)
    console.print(f"Wrote {path}")
    if not systemd.systemd_available():
        console.print("[yellow]systemctl not found; run the unit manually or use `cud gateway run`.[/yellow]")
        return 0
    daemon = systemd.systemctl_user("daemon-reload")
    if daemon.returncode != 0:
        console.print(daemon.stderr)
        return daemon.returncode
    enable = systemd.systemctl_user("enable", "--now", systemd.service_name(args.agent))
    console.print(enable.stdout or enable.stderr)
    console.print("For persistent services after logout, run: loginctl enable-linger $USER")
    return enable.returncode


def cmd_gateway_stop(args: argparse.Namespace) -> int:
    result = systemd.systemctl_user("stop", systemd.service_name(args.agent))
    console.print(result.stdout or result.stderr)
    return result.returncode


def cmd_gateway_status(args: argparse.Namespace) -> int:
    status = systemd.systemctl_user("status", systemd.service_name(args.agent))
    logs = systemd.journalctl_user(args.agent)
    console.print(status.stdout or status.stderr)
    console.print(logs.stdout or logs.stderr)
    return 0 if status.returncode in (0, 3) else status.returncode


def cmd_tools_list(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    settings = load_settings(directory)
    table = Table("Tool", "Source")
    for name in [
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "memory_read",
        "memory_update",
        "memory_clear",
    ]:
        table.add_row(name, "core")
    for card in discover_skills(directory / "skills"):
        table.add_row(card.name, "skill")
    mcp = load_mcp_config(directory)
    for name in sorted(mcp.allowed_tools):
        table.add_row(name, "mcp allowed")
    console.print(table)
    return 0


def cmd_tools_install(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    skills_dir = directory / "skills"
    skills_dir.mkdir(exist_ok=True)
    if args.path.startswith("http://") or args.path.startswith("https://"):
        name = args.path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".md") or "remote_skill"
        target = skills_dir / name
        if target.exists():
            console.print(f"[red]Skill already exists: {target}[/red]")
            return 2
        target.mkdir()
        with urllib.request.urlopen(args.path, timeout=10) as response:
            content = response.read().decode("utf-8")
        (target / "SKILL.md").write_text(content, encoding="utf-8")
        console.print(f"Installed skill at {target}")
        return 0

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Not found: {source}[/red]")
        return 2
    if source.is_dir():
        target = skills_dir / source.name
        if target.exists():
            console.print(f"[red]Skill already exists: {target}[/red]")
            return 2
        import shutil

        shutil.copytree(source, target)
    else:
        target = skills_dir / source.stem
        target.mkdir(exist_ok=False)
        (target / "SKILL.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(f"Installed skill at {target}")
    return 0


def cmd_mcp_add(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    config = load_mcp_config(directory)
    name = args.name or f"server{len(config.servers) + 1}"
    value = args.server_url_or_cmd
    if value.startswith("http://") or value.startswith("https://"):
        config.servers[name] = {"url": value, "transport": "streamable_http"}
    else:
        config.servers[name] = {"command": value, "transport": "stdio"}
    if args.allowed_tool:
        config.allowed_tools = sorted(set(config.allowed_tools + args.allowed_tool))
    save_mcp_config(directory, config)
    console.print(f"Added MCP server {name}")
    return 0


def cmd_mcp_list(args: argparse.Namespace) -> int:
    config = load_mcp_config(agent_home(args.agent))
    console.print(json.dumps(asdict(config), indent=2))
    return 0


def cmd_engine_status(args: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen(args.base_url.rstrip("/") + "/api/tags", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        console.print(f"[red]Ollama unavailable:[/red] {exc}")
        return 1
    models = [item.get("name", "") for item in data.get("models", [])]
    console.print(f"Ollama reachable at {args.base_url}. Models: {', '.join(models) or 'none'}")
    return 0


def cmd_engine_pull(args: argparse.Namespace) -> int:
    result = subprocess.run(["ollama", "pull", args.model_name], text=True)
    return result.returncode


def cmd_completion(args: argparse.Namespace) -> int:
    if args.shell == "bash":
        console.print("complete -W 'agent gateway tools mcp engine completion' cud")
    else:
        console.print("#compdef cud\n_arguments '1:command:(agent gateway tools mcp engine completion)'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
