"""Tool-call guardrails for small local models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def stable_hash(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class ToolCallLimitGuard:
    max_calls: int
    calls: int = 0

    def record(self, count: int = 1) -> None:
        self.calls += count
        if self.calls > self.max_calls:
            raise RuntimeError(f"tool call limit exceeded ({self.max_calls})")


@dataclass(slots=True)
class ToolLoopGuard:
    max_repeats: int = 3
    _failures: dict[str, int] = field(default_factory=dict)
    _results: dict[str, int] = field(default_factory=dict)

    def record_call(self, name: str, args: dict[str, Any], *, ok: bool, result: Any = None) -> None:
        call_key = f"{name}:{stable_hash(args)}"
        if not ok:
            count = self._failures.get(call_key, 0) + 1
            self._failures[call_key] = count
            if count >= self.max_repeats:
                raise RuntimeError(f"blocked repeated failing tool call: {name}")
            return

        result_key = f"{call_key}:{stable_hash(result)}"
        count = self._results.get(result_key, 0) + 1
        self._results[result_key] = count
        if count >= self.max_repeats:
            raise RuntimeError(f"blocked repeated identical tool result: {name}")

    def reset(self) -> None:
        self._failures.clear()
        self._results.clear()

