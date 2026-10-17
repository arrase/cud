"""Agent home scaffolding."""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from .paths import agent_home, agents_root

TEMPLATE_NAMES = ["AGENT.md", "MEMORY.md", "settings.yaml", "mcp.json"]


def create_agent(name: str, *, template: str = "default", overwrite: bool = False) -> Path:
    """Create `~/.cud/agents/<name>` and return its path."""
    if template != "default":
        raise ValueError("only the default template is available")
    target = agent_home(name)
    existed = target.exists()
    if existed and not overwrite:
        raise FileExistsError(f"agent already exists: {target}")

    try:
        _populate_agent(target, template_root=files("cud.templates"), overwrite=overwrite)
    except BaseException:
        # Never leave a half-built agent behind: list_agents() would report it
        # as a real agent that then fails on every load.  Pre-existing agents
        # are left alone — rolling those back would destroy user data.
        if not existed:
            shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _populate_agent(target: Path, *, template_root: Traversable, overwrite: bool) -> None:
    target.mkdir(parents=True, exist_ok=True)
    workspace_dir = target / "workspace"
    for name in ("", "skills", "tasks"):
        (workspace_dir / name).mkdir(parents=True, exist_ok=True)
    for filename in TEMPLATE_NAMES:
        destination = target / filename
        if destination.exists() and not overwrite:
            continue
        source = template_root / filename
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    _copy_bundled_skills(workspace_dir / "skills", template_root, overwrite=overwrite)
    _init_history_db(target / "history.db")


def _copy_bundled_skills(
    skills_dir: Path, template_root: Traversable, *, overwrite: bool = False
) -> None:
    """Copy skill templates shipped with the package into the agent workspace."""
    bundled = template_root / "skills"
    for skill in bundled.iterdir():
        if skill.name == "__pycache__" or not skill.is_dir():
            continue
        dest = skills_dir / skill.name
        if dest.exists() and not overwrite:
            continue
        dest.mkdir(exist_ok=True)
        for child in skill.iterdir():
            if child.name.endswith(".py") or child.name == "__pycache__" or child.is_dir():
                continue
            (dest / child.name).write_bytes(child.read_bytes())


def _init_history_db(path: Path) -> None:
    # `with sqlite3.connect(...)` only manages the transaction, not the
    # connection, so close explicitly or the file handle leaks on error.
    with contextlib.closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cud_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )


def list_agents() -> list[Path]:
    root = agents_root()
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def delete_agent(name: str) -> Path:
    target = agent_home(name)
    if not target.exists():
        raise FileNotFoundError(target)
    shutil.rmtree(target)
    return target

