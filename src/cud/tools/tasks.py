"""Periodic task discovery and parsing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from croniter import croniter
from rich.console import Console
from rich.table import Table

from cud.config.paths import agent_home
from cud.tools._frontmatter import parse_frontmatter

console = Console()


@dataclass(frozen=True, slots=True)
class TaskCard:
    name: str
    description: str
    schedule: str
    channel_id: int | None
    user_id: int | None
    enabled: bool
    path: Path
    prompt: str


def discover_tasks(tasks_dir: Path) -> list[TaskCard]:
    """Scan ``tasks_dir`` for ``*/TASK.md`` files and return parsed cards."""
    if not tasks_dir.exists():
        return []
    cards: list[TaskCard] = []
    for task_file in sorted(tasks_dir.glob("*/TASK.md")):
        try:
            card = _parse_task_file(task_file)
            if card is not None:
                cards.append(card)
        except Exception:
            continue
    return cards


def _parse_task_file(task_file: Path) -> TaskCard | None:
    text = task_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    name = metadata.get("name") or task_file.parent.name
    schedule = metadata.get("schedule")
    if not schedule:
        return None  # A task without schedule is invalid.
    prompt = body.strip()
    if not prompt:
        return None  # A task without prompt is useless.
    return TaskCard(
        name=name,
        description=metadata.get("description", ""),
        schedule=schedule,
        channel_id=_int_or_none(metadata.get("channel_id")),
        user_id=_int_or_none(metadata.get("user_id")),
        enabled=bool(metadata.get("enabled", True)),
        path=task_file,
        prompt=prompt,
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def register_task_commands(sub: argparse._SubParsersAction) -> None:
    task = sub.add_parser("task", help="Manage periodic tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_list = task_sub.add_parser("list", help="List scheduled tasks")
    task_list.add_argument("agent")
    task_list.set_defaults(func=cmd_task_list)


def cmd_task_list(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    tasks_dir = directory / "workspace" / "tasks"
    tasks = discover_tasks(tasks_dir)
    if not tasks:
        console.print(f"No tasks found in {tasks_dir}")
        return 0
    table = Table("Name", "Schedule", "Destination", "Enabled", "Next Run")
    now = datetime.now(timezone.utc)
    for task in tasks:
        if task.channel_id:
            dest = f"channel:{task.channel_id}"
        elif task.user_id:
            dest = f"DM:{task.user_id}"
        else:
            dest = "none"
        next_run = "—"
        if task.enabled:
            try:
                cron = croniter(task.schedule, now)
                next_run = cron.get_next(datetime).strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                next_run = "invalid cron"
        enabled = "✓" if task.enabled else "✗"
        table.add_row(task.name, task.schedule, dest, enabled, next_run)
    console.print(table)
    return 0

