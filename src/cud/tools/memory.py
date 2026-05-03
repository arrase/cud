"""Markdown-backed long-term memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class MemoryStore:
    path: Path

    def read(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def update(self, content: str, *, mode: str = "append") -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read()
        if mode == "replace":
            next_text = content.rstrip() + "\n"
        elif mode == "append":
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            entry = f"\n\n## {timestamp}\n\n{content.strip()}\n"
            next_text = existing.rstrip() + entry if existing.strip() else entry.lstrip()
        else:
            raise ValueError("mode must be 'append' or 'replace'")
        self.path.write_text(next_text, encoding="utf-8")
        return "MEMORY.md updated"

    def clear(self) -> str:
        self.path.write_text("# Long-Term Memory\n\nNo persistent memories yet.\n", encoding="utf-8")
        return "MEMORY.md cleared"


def memory_read(agent_dir: Path) -> str:
    return MemoryStore(agent_dir / "MEMORY.md").read()


def memory_update(agent_dir: Path, content: str, mode: str = "append") -> str:
    return MemoryStore(agent_dir / "MEMORY.md").update(content, mode=mode)


def memory_clear(agent_dir: Path) -> str:
    return MemoryStore(agent_dir / "MEMORY.md").clear()

