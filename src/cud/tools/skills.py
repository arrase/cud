"""Progressive-disclosure skill discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import re
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
    cards: list[SkillCard] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        metadata, body = parse_skill_file(skill_file)
        name = str(metadata.get("name") or skill_file.parent.name)
        description = str(metadata.get("description") or first_non_empty_line(body) or "Local Cud skill")
        cards.append(SkillCard(name=name, description=description, path=skill_file, metadata=metadata))
    return cards


def parse_skill_file(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if match:
        raw_frontmatter = match.group(1)
        body = text[match.end():]
        try:
            metadata = yaml.safe_load(raw_frontmatter) or {}
            if isinstance(metadata, dict):
                return metadata, body
        except yaml.YAMLError:
            pass
    return {}, text


def first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def render_skill_index(cards: list[SkillCard]) -> str:
    if not cards:
        return "No skills installed."
    lines = ["Use the `activate_skill` tool to read the full instructions for these capabilities:"]
    for card in cards:
        lines.append(f"- {card.name}: {card.description}")
    return "\n".join(lines)

