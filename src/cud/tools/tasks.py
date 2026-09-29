"""Periodic task discovery and parsing."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from croniter import croniter
from rich.console import Console
from rich.table import Table

from cud.config.paths import agent_home
from cud.tools._frontmatter import parse_frontmatter

console = Console()
_log = logging.getLogger(__name__)


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
        except Exception:
            _log.warning("Skipping unreadable task file %s", task_file, exc_info=True)
            continue
        if card is not None:
            cards.append(card)
    return cards


def _parse_task_file(task_file: Path) -> TaskCard | None:
    text = task_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    name = metadata.get("name") or task_file.parent.name
    schedule = str(metadata.get("schedule") or "").strip()
    if not schedule:
        return None  # A task without schedule is invalid.
    if not croniter.is_valid(schedule):
        _log.warning("Task '%s': invalid cron expression %r; skipping", task_file, schedule)
        return None
    prompt = body.strip()
    if not prompt:
        return None  # A task without prompt is useless.
    return TaskCard(
        name=str(name),
        description=str(metadata.get("description") or ""),
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


def next_run(schedule: str, now: datetime) -> datetime | None:
    """Return the next fire time for *schedule*, or ``None`` if it never fires.

    Single source of truth for cron evaluation shared by the scheduler, the CLI
    and the GUI, so an unschedulable expression is handled identically everywhere.
    """
    try:
        return croniter(schedule, now).get_next(datetime)
    except (ValueError, KeyError):
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

