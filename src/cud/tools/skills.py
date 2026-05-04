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
            metadata, body = parse_skill_file(skill_file)
            name = metadata.get("name") or skill_file.parent.name
            description = metadata.get("description") or first_non_empty_line(body) or "Local Cud skill"
            cards.append(SkillCard(name=name, description=description, path=skill_file, metadata=metadata))
        except Exception:
            continue
    return cards


def parse_skill_file(skill_file: Path) -> tuple[dict[str, Any], str]:
    text = skill_file.read_text(encoding="utf-8")
    match = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if match:
        raw_frontmatter = match.group(1)
        body = text[match.end():]
        try:
            metadata = yaml.safe_load(raw_frontmatter)
            if not isinstance(metadata, dict):
                metadata = {}
        except yaml.YAMLError:
            metadata = {}
    else:
        metadata = {}
        body = text
    
    return metadata, body


def first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def render_skill_index(cards: list[SkillCard]) -> str:
    if not cards:
        return "No skills installed."
    
    lines = ["Use the `activate_skill` tool to read the full instructions for these capabilities:", ""]
    for card in cards:
        lines.append(f"- **{card.name}**: {card.description}")
    return "\n".join(lines)
