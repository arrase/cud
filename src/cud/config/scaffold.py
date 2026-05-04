"""Agent home scaffolding."""

from __future__ import annotations

import shutil
import sqlite3
from importlib.resources import files
from pathlib import Path

from .paths import agent_home, agents_root, validate_agent_name

TEMPLATE_NAMES = ["AGENT.md", "MEMORY.md", "settings.yaml", "mcp.json"]


def create_agent(name: str, *, template: str | None = None, overwrite: bool = False) -> Path:
    """Create `~/.cud/agents/<name>` and return its path."""

    if template not in (None, "default"):
        raise ValueError("only the default template is available")
    target = agent_home(name)
    if target.exists() and not overwrite:
        raise FileExistsError(f"agent already exists: {target}")

    target.mkdir(parents=True, exist_ok=True)
    (target / "skills").mkdir(exist_ok=True)
    (target / "workspace").mkdir(exist_ok=True)
    template_root = files("cud.templates")
    for filename in TEMPLATE_NAMES:
        destination = target / filename
        if destination.exists() and not overwrite:
            continue
        source = template_root / filename
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    _init_history_db(target / "history.db")
    return target


def _init_history_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cud_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.commit()
    finally:
        connection.close()


def list_agents() -> list[Path]:
    root = agents_root()
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def delete_agent(name: str, *, yes: bool = False) -> Path:
    validate_agent_name(name)
    target = agent_home(name)
    if not yes:
        raise PermissionError("delete_agent requires yes=True")
    if not target.exists():
        raise FileNotFoundError(target)
    shutil.rmtree(target)
    return target

