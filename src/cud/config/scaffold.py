"""Agent home scaffolding."""

from __future__ import annotations

import shutil
import sqlite3
from importlib.resources import files
from pathlib import Path
from typing import Any

from .paths import agent_home, agents_root

TEMPLATE_NAMES = ["AGENT.md", "MEMORY.md", "settings.yaml", "mcp.json"]


def create_agent(name: str, *, template: str | None = None, overwrite: bool = False) -> Path:
    """Create `~/.cud/agents/<name>` and return its path."""

    if template not in (None, "default"):
        raise ValueError("only the default template is available")
    target = agent_home(name)
    if target.exists() and not overwrite:
        raise FileExistsError(f"agent already exists: {target}")

    target.mkdir(parents=True, exist_ok=True)
    workspace_dir = target / "workspace"
    workspace_dir.mkdir(exist_ok=True)
    (workspace_dir / "skills").mkdir(exist_ok=True)
    (workspace_dir / "tasks").mkdir(exist_ok=True)
    template_root = files("cud.templates")
    for filename in TEMPLATE_NAMES:
        destination = target / filename
        if destination.exists() and not overwrite:
            continue
        source = template_root / filename
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    _copy_bundled_skills(workspace_dir / "skills", template_root, overwrite=overwrite)
    _init_history_db(target / "history.db")
    return target


def _copy_bundled_skills(skills_dir: Path, template_root: Any, *, overwrite: bool = False) -> None:
    """Copy skill templates shipped with the package into the agent workspace."""
    bundled = template_root / "skills"
    try:
        entries = list(bundled.iterdir())
    except Exception:
        return
    for skill in entries:
        if skill.name == "__pycache__":
            continue
        if not _is_directory_resource(skill):
            continue
        dest = skills_dir / skill.name
        if dest.exists() and not overwrite:
            continue
        dest.mkdir(exist_ok=True)
        for child in skill.iterdir():
            if child.name.endswith(".py") or child.name == "__pycache__":
                continue
            (dest / child.name).write_text(child.read_text(encoding="utf-8"), encoding="utf-8")


def _is_directory_resource(resource: Any) -> bool:
    """Check if an importlib.resources traversable is a directory."""
    return hasattr(resource, "is_dir") and resource.is_dir()


def _init_history_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cud_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )


def list_agents() -> list[Path]:
    root = agents_root()
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def delete_agent(name: str, *, yes: bool = False) -> Path:
    target = agent_home(name)  # agent_home validates the name
    if not yes:
        raise PermissionError("delete_agent requires yes=True")
    if not target.exists():
        raise FileNotFoundError(target)
    shutil.rmtree(target)
    return target

