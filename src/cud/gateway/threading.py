"""Thread-id mapping helpers."""

from __future__ import annotations

import re
from typing import Any

_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def discord_thread_id(message_or_channel: Any) -> str:
    """Map a Discord channel/thread/message object to a stable LangGraph thread_id."""

    channel = getattr(message_or_channel, "channel", message_or_channel)
    guild = getattr(channel, "guild", None)
    guild_id = getattr(guild, "id", "dm")
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        channel_id = getattr(message_or_channel, "id", "unknown")
    return sanitize_thread_id(f"discord:{guild_id}:{channel_id}")


def sanitize_thread_id(value: str) -> str:
    return _SAFE.sub("_", value)

