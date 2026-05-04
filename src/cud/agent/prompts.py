"""Stable system prompt assembly."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cud.config.settings import Settings
from cud.tools.mcp import load_mcp_config, render_mcp_summary


@dataclass(frozen=True, slots=True)
class PromptSnapshot:
    text: str
    system_prompt_hash: str
    memory_hash: str


def build_system_prompt(agent_dir: Path, settings: Settings) -> PromptSnapshot:
    agent_text = _read_or_empty(agent_dir / "AGENT.md")
    memory_text = _read_or_empty(agent_dir / "MEMORY.md")
    mcp_summary = render_mcp_summary(load_mcp_config(agent_dir))
    text = "\n\n".join(
        [
            "# Agent Instructions",
            agent_text.strip(),
            "# Long-Term Memory Snapshot",
            memory_text.strip() or "No memory.",
            "# MCP Summary",
            mcp_summary,
        ]
    ).strip()
    return PromptSnapshot(
        text=text,
        system_prompt_hash=sha256_text(text),
        memory_hash=sha256_text(memory_text),
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_or_empty(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
