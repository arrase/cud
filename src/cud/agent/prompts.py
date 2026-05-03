"""Stable system prompt assembly."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cud.config.settings import Settings
from cud.tools.mcp import load_mcp_config, render_mcp_summary
from cud.tools.skills import discover_skills, render_skill_index

CUD_RULES = """\
## Cud Runtime Rules

- Use native tool calls only; do not emit ad-hoc JSON for tools.
- Keep tool use focused and stop if repeated calls do not change the result.
- Memory writes update MEMORY.md but do not refresh this system prompt until reload or compaction.
- Prefer concise answers and cite local file paths when local files matter.
"""


@dataclass(frozen=True, slots=True)
class PromptSnapshot:
    text: str
    system_prompt_hash: str
    memory_hash: str


def build_system_prompt(agent_dir: Path, settings: Settings) -> PromptSnapshot:
    agent_text = _read_or_empty(agent_dir / "AGENT.md")
    memory_text = _read_or_empty(agent_dir / "MEMORY.md")
    skill_index = render_skill_index(discover_skills(agent_dir / "skills"))
    mcp_summary = render_mcp_summary(load_mcp_config(agent_dir), settings.runtime.max_visible_tools)
    text = "\n\n".join(
        [
            "# Agent Instructions",
            agent_text.strip(),
            CUD_RULES.strip(),
            "# Long-Term Memory Snapshot",
            memory_text.strip() or "No memory.",
            "# Skills Index",
            skill_index,
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

