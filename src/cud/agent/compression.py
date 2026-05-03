"""Deterministic context pruning and compaction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMPACTION_PREFIX = "[CONTEXT COMPACTION - REFERENCE ONLY]"


@dataclass(slots=True)
class CompactionResult:
    messages: list[Any]
    compacted: bool
    summary: str


def message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "")
    return message.__class__.__name__.replace("Message", "").lower()


def message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def tool_call_ids(message: Any) -> list[str]:
    calls = message.get("tool_calls", []) if isinstance(message, dict) else getattr(message, "tool_calls", [])
    ids: list[str] = []
    for call in calls or []:
        if isinstance(call, dict) and call.get("id"):
            ids.append(str(call["id"]))
    return ids


def tool_message_id(message: Any) -> str | None:
    if isinstance(message, dict):
        value = message.get("tool_call_id")
        return str(value) if value else None
    value = getattr(message, "tool_call_id", None)
    return str(value) if value else None


def with_content(message: Any, content: str) -> Any:
    if isinstance(message, dict):
        copied = dict(message)
        copied["content"] = content
        return copied
    try:
        return message.copy(update={"content": content})
    except AttributeError:
        message.content = content
        return message


def make_system_message(content: str) -> dict[str, str]:
    return {"role": "system", "content": content}


def prune_tool_outputs(messages: list[Any], max_chars: int) -> list[Any]:
    pruned = []
    for message in messages:
        role = message_role(message)
        content = message_content(message)
        if role in {"tool", "toolmessage"} and len(content) > max_chars:
            preview = content[: max_chars // 2].rstrip()
            replacement = f"{preview}\n\n[tool output pruned; original length={len(content)} chars]"
            pruned.append(with_content(message, replacement))
        else:
            pruned.append(message)
    return pruned


def validate_tool_pairs(messages: list[Any]) -> None:
    pending: set[str] = set()
    for message in messages:
        for call_id in tool_call_ids(message):
            pending.add(call_id)
        result_id = tool_message_id(message)
        if result_id:
            pending.discard(result_id)
    if pending:
        raise ValueError(f"AI tool calls without matching tool messages: {sorted(pending)}")


def compact_messages(
    messages: list[Any],
    *,
    context_window: int,
    threshold_ratio: float,
    keep_recent_messages: int,
    max_tool_output_chars: int,
    focus: str | None = None,
) -> CompactionResult:
    """Compact a message list using character count as a conservative fallback.

    LangChain token-aware trimming can wrap this later. This deterministic path
    is useful for tests and for environments where LangChain is not installed.
    """

    pruned = prune_tool_outputs(messages, max_tool_output_chars)
    threshold = int(context_window * threshold_ratio)
    total_chars = sum(len(message_content(message)) for message in pruned)
    if total_chars < threshold or len(pruned) <= keep_recent_messages + 2:
        validate_tool_pairs(pruned)
        return CompactionResult(messages=pruned, compacted=False, summary="")

    first = pruned[:1]
    recent = pruned[-keep_recent_messages:]
    middle = pruned[1:-keep_recent_messages]
    summary = summarize_messages(middle, focus=focus)
    compacted = first + [make_system_message(summary)] + recent
    validate_tool_pairs(compacted)
    return CompactionResult(messages=compacted, compacted=True, summary=summary)


def summarize_messages(messages: list[Any], *, focus: str | None = None) -> str:
    lines = [COMPACTION_PREFIX]
    if focus:
        lines.append(f"Focus: {focus}")
    for index, message in enumerate(messages, start=1):
        role = message_role(message) or "message"
        content = " ".join(message_content(message).split())
        if len(content) > 240:
            content = content[:237].rstrip() + "..."
        lines.append(f"- {index}. {role}: {content}")
    return "\n".join(lines)

