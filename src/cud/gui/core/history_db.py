"""Asynchronous SQLite and LangGraph checkpoint reading for Cud agent history."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Final

from PySide6.QtCore import QObject, QRunnable, Signal
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from cud.config.paths import agent_home

# Constant for fallback timestamp
UNKNOWN_TIME: Final[str] = "Unknown Time"


def parse_message(msg: Any) -> dict[str, str]:
    """Parse a deserialized LangChain message object or dictionary into standard GUI fields.

    Args:
        msg: The deserialized message object or raw dict.

    Returns:
        A dictionary with "role" and "content" string keys.
    """
    role = "unknown"
    content = ""

    # Extract role/type
    if hasattr(msg, "type"):
        role = str(msg.type)
    elif isinstance(msg, dict):
        role = str(msg.get("type") or msg.get("role") or "unknown")

    # Standardize typical roles
    if role == "human":
        role = "user"
    elif role == "ai":
        role = "assistant"

    # Extract content
    if hasattr(msg, "content"):
        content = msg.content
    elif isinstance(msg, dict):
        content = msg.get("content") or ""

    if not isinstance(content, str):
        content = str(content)

    return {
        "role": role,
        "content": content,
    }


class HistoryDBSignals(QObject):
    """Signals for communicating database operations back to the main UI thread."""

    # Arguments: list of threads. Each thread is a dict:
    # {"thread_id": str, "timestamp": str, "latest_message": str}
    threads_loaded = Signal(list)

    # Arguments: (thread_id, list of messages). Each message is a dict:
    # {"role": str, "content": str}
    messages_loaded = Signal(str, list)

    # Arguments: error message
    error = Signal(str)


class LoadThreadsWorker(QRunnable):
    """Worker runnable to load all unique thread IDs and previews from history.db."""

    def __init__(self, agent_name: str) -> None:
        """Initialize the thread loader worker.

        Args:
            agent_name: Name of the agent whose history to load.
        """
        super().__init__()
        self.agent_name = agent_name
        self.signals = HistoryDBSignals()

    def run(self) -> None:
        """Query the history database and emit the list of threads."""
        try:
            db_path = agent_home(self.agent_name) / "history.db"
            if not db_path.exists():
                # If database does not exist, there is simply no history yet
                self.signals.threads_loaded.emit([])
                return

            serializer = JsonPlusSerializer()
            threads_map: dict[str, dict[str, Any]] = {}

            with sqlite3.connect(db_path) as conn:
                # Check if checkpoints table exists
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT count(name) FROM sqlite_master WHERE type='table' AND name='checkpoints'"
                )
                if cursor.fetchone()[0] == 0:
                    # Table checkpoints does not exist yet (no interactions recorded)
                    self.signals.threads_loaded.emit([])
                    return

                # Retrieve checkpoints ordered by latest ID, including type column
                cursor.execute(
                    "SELECT thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata "
                    "FROM checkpoints "
                    "ORDER BY checkpoint_id DESC"
                )
                rows = cursor.fetchall()

            for row in rows:
                thread_id, ns, checkpoint_id, type_col, cp_blob, meta_blob = row

                # Focus on the root namespace checkpoint for clean main-thread view, or fallback to any
                if thread_id not in threads_map or (ns == "" and threads_map[thread_id]["ns"] != ""):
                    try:
                        meta = json.loads(meta_blob) if meta_blob else {}
                    except Exception:
                        meta = {}

                    timestamp = meta.get("created_at") or meta.get("ts") or checkpoint_id or UNKNOWN_TIME

                    last_msg_text = ""
                    try:
                        cp_data = serializer.loads_typed((type_col, cp_blob))
                        if isinstance(cp_data, dict):
                            msgs = cp_data.get("channel_values", {}).get("messages", [])
                            if msgs:
                                parsed = parse_message(msgs[-1])
                                last_msg_text = parsed["content"]
                    except Exception:
                        pass

                    threads_map[thread_id] = {
                        "thread_id": thread_id,
                        "ns": ns,
                        "checkpoint_id": checkpoint_id,
                        "timestamp": str(timestamp),
                        "latest_message": last_msg_text,
                    }

            self.signals.threads_loaded.emit(list(threads_map.values()))

        except sqlite3.Error as e:
            self.signals.error.emit(f"SQLite error loading threads: {e}")
        except Exception as e:
            self.signals.error.emit(f"Failed to load threads: {e}")


class LoadMessagesWorker(QRunnable):
    """Worker runnable to load the full message list for a specific thread from history.db."""

    def __init__(self, agent_name: str, thread_id: str) -> None:
        """Initialize the message loader worker.

        Args:
            agent_name: Name of the agent whose history to load.
            thread_id: Thread ID to load the messages for.
        """
        super().__init__()
        self.agent_name = agent_name
        self.thread_id = thread_id
        self.signals = HistoryDBSignals()

    def run(self) -> None:
        """Query the latest checkpoint for the thread, deserialize, and emit messages list."""
        try:
            db_path = agent_home(self.agent_name) / "history.db"
            if not db_path.exists():
                self.signals.error.emit(f"History database does not exist for agent '{self.agent_name}'.")
                return

            serializer = JsonPlusSerializer()
            checkpoint_blob = None
            type_col = None

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # 1. Try fetching the latest checkpoint in the root namespace
                cursor.execute(
                    "SELECT type, checkpoint FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = '' "
                    "ORDER BY checkpoint_id DESC LIMIT 1",
                    (self.thread_id,),
                )
                row = cursor.fetchone()
                if row:
                    type_col, checkpoint_blob = row
                else:
                    # 2. Fallback: try fetching any latest checkpoint for this thread ID
                    cursor.execute(
                        "SELECT type, checkpoint FROM checkpoints "
                        "WHERE thread_id = ? "
                        "ORDER BY checkpoint_id DESC LIMIT 1",
                        (self.thread_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        type_col, checkpoint_blob = row

            if checkpoint_blob is None or type_col is None:
                self.signals.messages_loaded.emit(self.thread_id, [])
                return

            checkpoint_data = serializer.loads_typed((type_col, checkpoint_blob))
            messages_list: list[Any] = []

            if isinstance(checkpoint_data, dict):
                channel_values = checkpoint_data.get("channel_values", {})
                if isinstance(channel_values, dict):
                    messages_list = channel_values.get("messages", [])

            parsed_messages = [parse_message(msg) for msg in messages_list]
            self.signals.messages_loaded.emit(self.thread_id, parsed_messages)

        except sqlite3.Error as e:
            self.signals.error.emit(f"SQLite error loading messages: {e}")
        except Exception as e:
            self.signals.error.emit(f"Failed to load messages: {e}")
