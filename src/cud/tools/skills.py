"""Progressive-disclosure skill discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cud.tools._frontmatter import parse_frontmatter


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
            text = skill_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(text)
            name = metadata.get("name") or skill_file.parent.name
            description = metadata.get("description") or _first_non_empty_line(body) or "Local Cud skill"
            cards.append(SkillCard(name=name, description=description, path=skill_file, metadata=metadata))
        except Exception:
            continue
    return cards


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None
