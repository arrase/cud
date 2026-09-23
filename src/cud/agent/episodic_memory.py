"""Episodic memory search engine for past agent conversations and experiences."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

_serializer = JsonPlusSerializer()


class HistoryError(RuntimeError):
    """Raised when the conversation history database cannot be read."""


@contextlib.contextmanager
def connect_history(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open the history database in read-only mode."""
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise HistoryError(f"Failed to open history database {db_path}: {e}") from e
    try:
        yield conn
    finally:
        conn.close()


def format_iso_timestamp(ts: str) -> str:
    """Format ISO timestamp into a human-readable UTC string (YYYY-MM-DD HH:MM UTC)."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def extract_text(content: Any, *, sep: str = " ") -> str:
    """Convert agent payload content into plain text."""
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, (list, tuple)):
        return sep.join(filter(None, (extract_text(item, sep=sep) for item in content))).strip()
    if isinstance(content, dict):
        for key in ("text", "content"):
            if key in content:
                return extract_text(content[key], sep=sep)
        return ""
    return str(content)


def _message_role_and_text(msg: Any) -> tuple[str, str]:
    """Extract role and stripped text content from a message."""
    role = msg.type if hasattr(msg, "type") else msg["role"]
    content = msg.content if hasattr(msg, "content") else msg["content"]
    return str(role), extract_text(content).strip()


def _extract_user_prompts(cursor: sqlite3.Cursor) -> list[str]:
    prompts: list[str] = []
    seen: set[str] = set()
    cursor.execute("SELECT type, value FROM writes WHERE channel = 'messages' ORDER BY rowid ASC")
    for typ, val in cursor.fetchall():
        msgs = _serializer.loads_typed((typ, val))
        msg_list = msgs if isinstance(msgs, list) else [msgs]
        for msg in msg_list:
            role, text = _message_role_and_text(msg)
            if role in ("human", "user") and text and text not in seen:
                seen.add(text)
                prompts.append(text)
    return prompts


def load_past_user_prompts(db_path: Path) -> list[str]:
    """Load past user prompt strings from the SQLite history database in chronological order."""
    if not db_path.exists():
        return []

    try:
        with connect_history(db_path) as conn:
            return _extract_user_prompts(conn.cursor())
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise HistoryError(f"Failed to read history database {db_path}: {e}") from e
    except (sqlite3.Error, OSError) as e:
        raise HistoryError(f"Failed to read history database {db_path}: {e}") from e


def _read_history_checkpoints(cursor: sqlite3.Cursor, exclude_thread_id: str) -> dict[str, str]:
    thread_timestamps: dict[str, str] = {}
    if exclude_thread_id:
        cursor.execute(
            "SELECT thread_id, type, checkpoint FROM checkpoints WHERE thread_id != ? ORDER BY rowid ASC",
            (exclude_thread_id,),
        )
    else:
        cursor.execute("SELECT thread_id, type, checkpoint FROM checkpoints ORDER BY rowid ASC")
    for tid, typ, chk in cursor.fetchall():
        c = _serializer.loads_typed((typ, chk))
        thread_timestamps[tid] = str(c["ts"])
    return thread_timestamps


def _read_history_messages(cursor: sqlite3.Cursor, exclude_thread_id: str) -> defaultdict[str, list[Any]]:
    thread_messages: defaultdict[str, list[Any]] = defaultdict(list)
    if exclude_thread_id:
        cursor.execute(
            "SELECT thread_id, type, value FROM writes WHERE channel = 'messages' AND thread_id != ? ORDER BY rowid ASC",
            (exclude_thread_id,),
        )
    else:
        cursor.execute(
            "SELECT thread_id, type, value FROM writes WHERE channel = 'messages' ORDER BY rowid ASC"
        )
    for tid, typ, val in cursor.fetchall():
        msgs = _serializer.loads_typed((typ, val))
        if isinstance(msgs, list):
            thread_messages[tid].extend(msgs)
        else:
            thread_messages[tid].append(msgs)
    return thread_messages


def load_past_conversations(
    db_path: Path,
    exclude_thread_id: str = "",
) -> dict[str, dict[str, Any]]:
    """Load conversation messages and timestamps grouped by thread_id from SQLite history.

    Threads matching ``exclude_thread_id`` (e.g. active conversation) are skipped.
    """
    if not db_path.exists():
        return {}

    try:
        with connect_history(db_path) as conn:
            cursor = conn.cursor()
            thread_timestamps = _read_history_checkpoints(cursor, exclude_thread_id)
            thread_messages = _read_history_messages(cursor, exclude_thread_id)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return {}
        raise HistoryError(f"Failed to read history database {db_path}: {e}") from e
    except (sqlite3.Error, OSError) as e:
        raise HistoryError(f"Failed to read history database {db_path}: {e}") from e

    conversations: dict[str, dict[str, Any]] = {}
    for tid, msgs in thread_messages.items():
        if tid in thread_timestamps:
            raw_ts = thread_timestamps[tid]
            conversations[tid] = {
                "timestamp": raw_ts,
                "formatted_date": format_iso_timestamp(raw_ts),
                "messages": msgs,
            }

    return conversations


def _format_snippet(role: str, text: str) -> str:
    truncated = text if len(text) <= 300 else f"{text[:297]}..."
    role_label = "User" if role in ("human", "user") else "Assistant"
    return f"[{role_label}]: {truncated}"


def _extract_dialogue(msgs: list[Any]) -> list[tuple[str, str]]:
    dialogue: list[tuple[str, str]] = []
    for msg in msgs:
        role, text = _message_role_and_text(msg)
        if role in ("human", "ai", "user", "assistant") and text:
            dialogue.append((role, text))
    return dialogue


def _score_conversation(data: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    dialogue = _extract_dialogue(data["messages"])
    formatted_date = data["formatted_date"]

    snippets: list[str] = []
    match_count = sum(formatted_date.lower().count(t) for t in terms)

    for role, text in dialogue:
        term_hits = sum(text.lower().count(t) for t in terms)
        if term_hits > 0:
            match_count += term_hits
            if len(snippets) < 4:
                snippets.append(_format_snippet(role, text))

    if match_count > 0 and not snippets:
        snippets = [_format_snippet(r, t) for r, t in dialogue[:2]]

    return match_count, snippets


def search_past_conversations_in_db(
    query: str,
    db_path: Path,
    exclude_thread_id: str = "",
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Search messages across past conversation sessions matching query keywords."""
    terms = [t.lower() for t in query.split()]
    if not terms:
        return []

    conversations = load_past_conversations(db_path, exclude_thread_id=exclude_thread_id)
    scored_results: list[dict[str, Any]] = []

    for tid, data in conversations.items():
        match_count, snippets = _score_conversation(data, terms)
        if match_count > 0:
            scored_results.append(
                {
                    "thread_id": tid,
                    "score": match_count,
                    "timestamp": data["timestamp"],
                    "formatted_date": data["formatted_date"],
                    "snippets": snippets,
                    "total_messages": len(data["messages"]),
                }
            )

    scored_results.sort(key=lambda item: (item["score"], item["timestamp"]), reverse=True)
    return scored_results[:limit]


def format_past_conversations_context(results: list[dict[str, Any]]) -> str:
    """Format matching episodic conversation sessions into a markdown context string with dates."""
    if not results:
        return "No relevant past conversations found in episodic memory."

    lines: list[str] = [f"Found {len(results)} relevant past conversation(s) in episodic memory:\n"]
    for idx, item in enumerate(results, start=1):
        tid = item["thread_id"]
        short_id = tid[:8]
        header_date = f" - [Date: {item['formatted_date']}]"
        lines.append(
            f"### Session #{idx} ({short_id}){header_date} - [Total messages: {item['total_messages']}]"
        )
        for snippet in item["snippets"]:
            indented = "\n  ".join(snippet.splitlines())
            lines.append(f"  {indented}")
        lines.append("")

    return "\n".join(lines).strip()


def create_search_past_conversations_tool(
    db_path: Path,
    get_thread_id: Callable[[], str],
) -> BaseTool:
    """Create a LangChain tool allowing agents to search episodic conversation history."""

    @tool
    async def search_past_conversations(query: str, limit: int = 3) -> str:
        """Search past conversation sessions and episodic memory by keywords, topics, or dates
        (e.g. 'yesterday', 'auth', 'database'). Returns timestamped excerpts of previous sessions.
        """
        if limit <= 0:
            raise ValueError(f"Limit must be greater than 0, got {limit}")
        try:
            results = await asyncio.to_thread(
                search_past_conversations_in_db,
                query=query,
                db_path=db_path,
                exclude_thread_id=get_thread_id(),
                limit=limit,
            )
        except HistoryError as exc:
            return f"Error searching past conversations: {exc}"
        return format_past_conversations_context(results)

    return search_past_conversations
