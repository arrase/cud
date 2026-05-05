"""Progressive-disclosure skill discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class SkillCard:
    name: str
    description: str
    path: Path
    metadata: dict[str, Any]


def discover_skills(skills_dir: Path) -> list[SkillCard]:
    if not skills_dir.exists():
        return []
    cards = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            metadata, body = _parse_skill_file(skill_file)
            name = metadata.get("name") or skill_file.parent.name
            description = metadata.get("description") or _first_non_empty_line(body) or "Local Cud skill"
            cards.append(SkillCard(name=name, description=description, path=skill_file, metadata=metadata))
        except Exception:
            continue
    return cards


def _parse_skill_file(skill_file: Path) -> tuple[dict[str, Any], str]:
    text = skill_file.read_text(encoding="utf-8")
    match = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, text[match.end():]


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None
