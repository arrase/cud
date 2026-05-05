"""Periodic task discovery and parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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
    metadata, body = _split_frontmatter(text)
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


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, text[match.end() :]


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
