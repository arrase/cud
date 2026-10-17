"""Progressive-disclosure skill discovery."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cud.config.paths import is_safe_name
from cud.tools._frontmatter import parse_frontmatter, render_frontmatter

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkillCard:
    name: str
    description: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict, hash=False)
    body: str = ""


def discover_skills(skills_dir: Path) -> list[SkillCard]:
    if not skills_dir.exists():
        return []
    cards = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(text)
        except Exception:
            _log.warning("Skipping unreadable skill file %s", skill_file, exc_info=True)
            continue
        name = metadata.get("name") or skill_file.parent.name
        description = metadata.get("description") or _first_non_empty_line(body) or "Local Cud skill"
        cards.append(
            SkillCard(
                name=str(name),
                description=str(description),
                path=skill_file,
                metadata=metadata,
                body=body.strip(),
            )
        )
    return cards


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def save_skills(
    skills_dir: Path,
    entries: Iterable[Mapping[str, Any]],
    deleted_dirs: Iterable[str] = (),
) -> list[str]:
    """Write skill entries to *skills_dir* and remove explicitly deleted directories.

    Returns directory names that could not be written because they are unsafe.
    """
    skills_dir.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    live_dirs: set[str] = set()

    for entry in entries:
        dir_name = str(entry["dir_name"])
        if not is_safe_name(dir_name):
            skipped.append(dir_name)
            continue
        live_dirs.add(dir_name)
        skill_dir = skills_dir / dir_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        metadata = dict(entry["metadata"])
        metadata["name"] = entry["name"]
        metadata["description"] = entry["description"]

        content = render_frontmatter(metadata, entry["body"])
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    for dir_name in set(deleted_dirs) - live_dirs:
        if not is_safe_name(dir_name):
            continue
        target = skills_dir / dir_name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
    return skipped
