"""Shared Discord message utilities.

Extracted so both ``discord_adapter`` and ``scheduler`` can use them
without circular imports.
"""

from __future__ import annotations

from typing import Any

DISCORD_MAX_LENGTH = 1900


async def send_response(message: Any, content: str) -> None:
    """Reply in guilds, send directly in DMs."""
    if message.guild is not None:
        await message.reply(content)
    else:
        await message.channel.send(content)


def split_message(content: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Split *content* into chunks that fit within Discord's message limit.

    Prefers splitting on newlines, then spaces, falling back to hard cuts only
    when a single token exceeds the limit.
    """
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at a newline first, then a space.
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit  # Hard cut — no good break point.

        chunk = remaining[:cut]
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n ")

    return chunks
