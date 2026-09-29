"""Progressive-disclosure skill discovery."""

from __future__ import annotations

import argparse
import logging
import re
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
_log = logging.getLogger(__name__)

# Skill directories become filesystem paths, so the name is restricted to a
# single safe path segment.
_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Guard against writing an unbounded remote file straight into the agent's
# prompt surface.
_MAX_SKILL_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True, eq=False)
class SkillCard:
    name: str
    description: str
    path: Path
    metadata: dict[str, Any]


def is_safe_dir_name(name: str) -> bool:
    """Whether *name* is usable as a single directory name."""
    return bool(_DIR_NAME_RE.fullmatch(name))


def valid_dir_name(name: str) -> str:
    """Return *name* if it is usable as a single directory name, else raise."""
    if not is_safe_dir_name(name):
        raise ValueError(
            "name must start with an alphanumeric character and contain only "
            "letters, numbers, '.', '_' or '-'"
        )
    return name


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
        cards.append(SkillCard(name=str(name), description=str(description), path=skill_file, metadata=metadata))
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
    skills_dir.mkdir(parents=True, exist_ok=True)
    if args.path.startswith(("http://", "https://")):
        return _install_remote(args.path, skills_dir)

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Not found: {source}[/red]")
        return 2
    try:
        if source.is_dir():
            target = skills_dir / valid_dir_name(source.name)
            if target.exists():
                console.print(f"[red]Skill already exists: {target}[/red]")
                return 2
            shutil.copytree(source, target)
        else:
            target = skills_dir / valid_dir_name(source.stem)
            if target.exists():
                console.print(f"[red]Skill already exists: {target}[/red]")
                return 2
            target.mkdir()
            (target / "SKILL.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    except ValueError as exc:
        console.print(f"[red]Invalid skill name:[/red] {exc}")
        return 2
    console.print(f"Installed skill at {target}")
    return 0


def _install_remote(url: str, skills_dir: Path) -> int:
    raw_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".md") or "remote_skill"
    try:
        name = valid_dir_name(raw_name)
    except ValueError as exc:
        console.print(f"[red]Invalid skill name:[/red] {exc}")
        return 2
    target = skills_dir / name
    if target.exists():
        console.print(f"[red]Skill already exists: {target}[/red]")
        return 2
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = response.read(_MAX_SKILL_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        console.print(f"[red]Failed to download skill:[/red] {exc}")
        return 1
    if len(payload) > _MAX_SKILL_BYTES:
        console.print(f"[red]Skill exceeds the {_MAX_SKILL_BYTES} byte limit:[/red] {url}")
        return 1
    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        console.print(f"[red]Skill is not valid UTF-8 text:[/red] {url}")
        return 1
    target.mkdir()
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    console.print(f"Installed skill at {target}")
    return 0
