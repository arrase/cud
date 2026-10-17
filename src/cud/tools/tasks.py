"""Periodic task discovery and parsing."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from croniter import croniter

from cud.config.paths import is_safe_name, validate_safe_name
from cud.tools._frontmatter import parse_frontmatter, render_frontmatter

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


def is_valid_schedule(schedule: str) -> bool:
    return bool(schedule) and croniter.is_valid(schedule)


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
        return None
    if not is_valid_schedule(schedule):
        _log.warning("Task '%s': invalid cron expression %r; skipping", task_file, schedule)
        return None
    prompt = body.strip()
    if not prompt:
        return None
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
    if value is None or isinstance(value, bool):
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


def write_task_entry(tasks_dir: Path, entry: Mapping[str, Any]) -> None:
    dir_name = validate_safe_name(str(entry["dir_name"]))
    task_dir = tasks_dir / dir_name
    task_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, Any] = {
        "name": entry["name"],
        "schedule": entry["schedule"],
        "enabled": entry["enabled"],
    }
    if entry["description"]:
        metadata["description"] = entry["description"]
    if entry["channel_id"] is not None:
        metadata["channel_id"] = entry["channel_id"]
    if entry["user_id"] is not None:
        metadata["user_id"] = entry["user_id"]

    body = "\n" + str(entry["prompt"]).lstrip("\n")
    content = render_frontmatter(metadata, body)
    (task_dir / "TASK.md").write_text(content, encoding="utf-8")


def remove_deleted_tasks(
    tasks_dir: Path,
    deleted_dirs: Iterable[str],
    live_dirs: Iterable[str] = (),
) -> None:
    """Remove only the directories the user explicitly deleted."""
    for dir_name in set(deleted_dirs) - set(live_dirs):
        if not is_safe_name(dir_name):
            continue
        target = tasks_dir / dir_name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)


def save_tasks(
    tasks_dir: Path,
    entries: Iterable[Mapping[str, Any]],
    deleted_dirs: Iterable[str] = (),
) -> list[str]:
    """Write all task entries to *tasks_dir* and remove deleted ones.

    Returns directory names that could not be written because they are unsafe.
    """
    tasks_dir.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    live_dirs: set[str] = set()
    for entry in entries:
        dir_name = str(entry["dir_name"])
        if not is_safe_name(dir_name):
            skipped.append(dir_name)
            continue
        live_dirs.add(dir_name)
        write_task_entry(tasks_dir, entry)
    remove_deleted_tasks(tasks_dir, deleted_dirs, live_dirs)
    return skipped

