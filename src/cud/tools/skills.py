"""Progressive-disclosure skill discovery."""

from __future__ import annotations

import argparse
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from cud.config.paths import agent_home
from cud.tools._frontmatter import parse_frontmatter

console = Console()


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


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def register_tools_commands(sub: argparse._SubParsersAction) -> None:
    tools = sub.add_parser("tools", help="Manage tools")
    tools_sub = tools.add_subparsers(dest="tools_command", required=True)
    tools_install = tools_sub.add_parser("install", help="Install a skill from a local path")
    tools_install.add_argument("agent")
    tools_install.add_argument("path")
    tools_install.set_defaults(func=cmd_tools_install)


def cmd_tools_install(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    skills_dir = directory / "workspace" / "skills"
    skills_dir.mkdir(exist_ok=True)
    if args.path.startswith("http://") or args.path.startswith("https://"):
        name = args.path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".md") or "remote_skill"
        target = skills_dir / name
        if target.exists():
            console.print(f"[red]Skill already exists: {target}[/red]")
            return 2
        try:
            with urllib.request.urlopen(args.path, timeout=10) as response:
                content = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            console.print(f"[red]Failed to download skill:[/red] {exc}")
            return 1
        target.mkdir()
        (target / "SKILL.md").write_text(content, encoding="utf-8")
        console.print(f"Installed skill at {target}")
        return 0

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Not found: {source}[/red]")
        return 2
    if source.is_dir():
        target = skills_dir / source.name
        if target.exists():
            console.print(f"[red]Skill already exists: {target}[/red]")
            return 2
        shutil.copytree(source, target)
    else:
        target = skills_dir / source.stem
        target.mkdir(exist_ok=False)
        (target / "SKILL.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(f"Installed skill at {target}")
    return 0
