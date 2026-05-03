"""Discord progress bubble deduplication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cud.agent.guardrails import stable_hash


@dataclass(slots=True)
class ProgressEntry:
    name: str
    args_hash: str
    preview: str
    count: int = 1


@dataclass(slots=True)
class ProgressBubble:
    entries: list[ProgressEntry] = field(default_factory=list)

    def add(self, name: str, args: Any) -> None:
        args_hash = stable_hash(args)
        preview = render_args_preview(args)
        for entry in self.entries:
            if entry.name == name and entry.args_hash == args_hash:
                entry.count += 1
                return
        self.entries.append(ProgressEntry(name=name, args_hash=args_hash, preview=preview))

    def render(self) -> str:
        if not self.entries:
            return "Working..."
        lines = []
        for entry in self.entries:
            suffix = f" (x{entry.count})" if entry.count > 1 else ""
            lines.append(f"{entry.name}: {entry.preview}{suffix}")
        return "\n".join(lines)


def render_args_preview(args: Any, limit: int = 80) -> str:
    text = str(args)
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text

