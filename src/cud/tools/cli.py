"""CLI commands for MCP servers, skills, and periodic tasks."""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cud.config.paths import agent_home, existing_agent_home, validate_safe_name
from cud.tools.mcp import (
    TRANSPORTS,
    build_stdio_server_config,
    free_server_name,
    load_mcp_config,
    save_mcp_config,
)
from cud.tools.skills import discover_skills
from cud.tools.tasks import TaskCard, discover_tasks, next_run

console = Console()

# Guard against writing an unbounded remote file straight into the agent's
# prompt surface.
_MAX_SKILL_BYTES = 512 * 1024


# ---------------------------------------------------------------------------
# MCP Commands
# ---------------------------------------------------------------------------


def register_mcp_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    mcp = sub.add_parser("mcp", help="Manage MCP servers")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_add = mcp_sub.add_parser("add", help="Add an MCP server")
    mcp_add.add_argument("agent")
    mcp_add.add_argument("server_url_or_cmd")
    mcp_add.add_argument("--name")
    mcp_add.add_argument("--allowed-tool", action="append", default=[])
    mcp_add.add_argument("--transport", choices=list(TRANSPORTS), help="Override transport type")
    mcp_add.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment variables for stdio (e.g. KEY=VALUE)",
    )
    mcp_add.set_defaults(func=cmd_mcp_add)
    mcp_list = mcp_sub.add_parser("list", help="List MCP servers")
    mcp_list.add_argument("agent")
    mcp_list.set_defaults(func=cmd_mcp_list)


def cmd_mcp_add(args: argparse.Namespace) -> int:
    directory = existing_agent_home(args.agent)
    config = load_mcp_config(directory)
    name = args.name or free_server_name(config.servers)
    value = args.server_url_or_cmd

    is_url = value.startswith(("http://", "https://"))
    transport = args.transport or ("sse" if is_url else "stdio")

    try:
        if transport in ("sse", "streamable_http"):
            config.servers[name] = {"url": value, "transport": transport}
        else:
            config.servers[name] = build_stdio_server_config(value, args.env, transport)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    if args.allowed_tool:
        config.allowed_tools = sorted(set(config.allowed_tools + args.allowed_tool))
    save_mcp_config(directory, config)
    console.print(f"Added MCP server {name}")
    return 0


def cmd_mcp_list(args: argparse.Namespace) -> int:
    config = load_mcp_config(agent_home(args.agent))
    console.print(json.dumps(config.to_dict(), indent=2))
    return 0


# ---------------------------------------------------------------------------
# Skills / Tools Commands
# ---------------------------------------------------------------------------


def register_tools_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    tools = sub.add_parser("tools", help="Manage tools")
    tools_sub = tools.add_subparsers(dest="tools_command", required=True)
    tools_list = tools_sub.add_parser("list", help="List installed skills")
    tools_list.add_argument("agent")
    tools_list.set_defaults(func=cmd_tools_list)
    tools_install = tools_sub.add_parser("install", help="Install a skill from a local path")
    tools_install.add_argument("agent")
    tools_install.add_argument("path")
    tools_install.set_defaults(func=cmd_tools_install)


def cmd_tools_list(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    skills_dir = directory / "workspace" / "skills"
    skills = discover_skills(skills_dir)
    if not skills:
        console.print(f"No skills found in {skills_dir}")
    else:
        table = Table("Name", "Description", "Path")
        for skill in skills:
            table.add_row(skill.name, skill.description, str(skill.path))
        console.print(table)
    return 0


def cmd_tools_install(args: argparse.Namespace) -> int:
    directory = existing_agent_home(args.agent)
    skills_dir = directory / "workspace" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    if args.path.startswith(("http://", "https://")):
        return _install_remote(args.path, skills_dir)

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Not found: {source}[/red]")
        return 2
    try:
        raw_name = source.name if source.is_dir() else source.stem
        target = skills_dir / validate_safe_name(raw_name, "skill name")
    except ValueError as exc:
        console.print(f"[red]Invalid skill name:[/red] {exc}")
        return 2
    if target.exists():
        console.print(f"[red]Skill already exists: {target}[/red]")
        return 2
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.mkdir()
        (target / "SKILL.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(f"Installed skill at {target}")
    return 0


def _install_remote(url: str, skills_dir: Path) -> int:
    raw_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".md") or "remote_skill"
    try:
        name = validate_safe_name(raw_name, "skill name")
    except ValueError as exc:
        console.print(f"[red]Invalid skill name:[/red] {exc}")
        return 2
    target = skills_dir / name
    if target.exists():
        console.print(f"[red]Skill already exists: {target}[/red]")
        return 2
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            payload = response.read(_MAX_SKILL_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        console.print(f"[red]Failed to download skill:[/red] {exc}")
        return 1
    if len(payload) > _MAX_SKILL_BYTES:
        console.print(f"[red]Skill exceeds the {_MAX_SKILL_BYTES} byte limit:[/red] {url}")
        return 1
    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        console.print(f"[red]Skill is not valid UTF-8 text:[/red] {url}")
        return 1
    target.mkdir()
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    console.print(f"Installed skill at {target}")
    return 0


# ---------------------------------------------------------------------------
# Tasks Commands
# ---------------------------------------------------------------------------


def register_tasks_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    task = sub.add_parser("task", help="Manage periodic tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_list = task_sub.add_parser("list", help="List scheduled tasks")
    task_list.add_argument("agent")
    task_list.set_defaults(func=cmd_task_list)


def _task_destination(task: TaskCard) -> str:
    if task.channel_id is not None:
        return f"channel:{task.channel_id}"
    if task.user_id is not None:
        return f"DM:{task.user_id}"
    return "none"


def _task_next_run(task: TaskCard, now: datetime) -> str:
    if not task.enabled:
        return "—"
    upcoming = next_run(task.schedule, now)
    return upcoming.strftime("%Y-%m-%d %H:%M UTC") if upcoming else "invalid cron"


def cmd_task_list(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    tasks_dir = directory / "workspace" / "tasks"
    tasks = discover_tasks(tasks_dir)
    if not tasks:
        console.print(f"No tasks found in {tasks_dir}")
    else:
        table = Table("Name", "Schedule", "Destination", "Enabled", "Next Run")
        now = datetime.now(UTC)
        for task in tasks:
            table.add_row(
                task.name,
                task.schedule,
                _task_destination(task),
                "✓" if task.enabled else "✗",
                _task_next_run(task, now),
            )
        console.print(table)
    return 0
