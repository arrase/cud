"""Provider-neutral gateway events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    provider: str
    agent: str
    thread_id: str
    author_id: str
    content: str
    raw: Any = None


@dataclass(frozen=True, slots=True)
class OutgoingResponse:
    thread_id: str
    content: str
    progress: list[str] = field(default_factory=list)
    raw: Any = None


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    thread_id: str
    approve: bool
    reason: str = ""


class GatewayAdapter(Protocol):
    async def run(self) -> None:
        ...

