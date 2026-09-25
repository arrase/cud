from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from cud.agent.episodic_memory import (
    connect_history,
    create_search_past_conversations_tool,
    extract_text,
    format_iso_timestamp,
    format_past_conversations_context,
    load_past_conversations,
    load_past_user_prompts,
    search_past_conversations_in_db,
)


def _seed_db(db_path: Path) -> None:
    serializer = JsonPlusSerializer()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE checkpoints (
            thread_id TEXT,
            checkpoint_ns TEXT DEFAULT '',
            checkpoint_id TEXT,
            type TEXT,
            checkpoint BLOB,
            metadata BLOB
        );"""
    )
    cur.execute(
        """CREATE TABLE writes (
            thread_id TEXT,
            checkpoint_ns TEXT DEFAULT '',
            checkpoint_id TEXT,
            task_id TEXT,
            idx INTEGER,
            channel TEXT,
            type TEXT,
            value BLOB
        );"""
    )

    # Thread 1: FastAPI & Docker
    t1_chk = {"ts": "2026-08-20T10:00:00+00:00"}
    chk_typ1, chk_val1 = serializer.dumps_typed(t1_chk)
    cur.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_id, type, checkpoint) VALUES (?, ?, ?, ?)",
        ("thread-100", "cp-1", chk_typ1, chk_val1),
    )
    t1_msgs = [
        HumanMessage(content="How do I dockerize a FastAPI application?"),
        AIMessage(content="You should create a Dockerfile using python:3.11-slim and install uvicorn."),
    ]
    typ1, val1 = serializer.dumps_typed(t1_msgs)
    cur.execute(
        "INSERT INTO writes (thread_id, checkpoint_id, task_id, idx, channel, type, value) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("thread-100", "cp-1", "task-1", 0, "messages", typ1, val1),
    )

    # Thread 2: React Vite
    t2_chk = {"ts": "2026-08-21T14:30:00+00:00"}
    chk_typ2, chk_val2 = serializer.dumps_typed(t2_chk)
    cur.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_id, type, checkpoint) VALUES (?, ?, ?, ?)",
        ("thread-200", "cp-2", chk_typ2, chk_val2),
    )
    t2_msgs = [
        HumanMessage(content="Set up a React Vite project with TypeScript."),
        AIMessage(content="Run npm create vite@latest my-app -- --template react-ts."),
    ]
    typ2, val2 = serializer.dumps_typed(t2_msgs)
    cur.execute(
        "INSERT INTO writes (thread_id, checkpoint_id, task_id, idx, channel, type, value) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("thread-200", "cp-2", "task-2", 0, "messages", typ2, val2),
    )

    # Thread 3: PostgreSQL & Alembic
    t3_chk = {"ts": "2026-08-22T08:15:00+00:00"}
    chk_typ3, chk_val3 = serializer.dumps_typed(t3_chk)
    cur.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_id, type, checkpoint) VALUES (?, ?, ?, ?)",
        ("thread-300", "cp-3", chk_typ3, chk_val3),
    )
    t3_msgs = [
        HumanMessage(content="How to handle PostgreSQL migrations with Alembic?"),
        AIMessage(content="Run alembic revision --autogenerate and alembic upgrade head."),
        ToolMessage(content="Migration output: success", tool_call_id="call-1"),
    ]
    typ3, val3 = serializer.dumps_typed(t3_msgs)
    cur.execute(
        "INSERT INTO writes (thread_id, checkpoint_id, task_id, idx, channel, type, value) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("thread-300", "cp-3", "task-3", 0, "messages", typ3, val3),
    )

    conn.commit()
    conn.close()


def test_format_iso_timestamp() -> None:
    assert format_iso_timestamp("2026-08-20T10:00:00") == "2026-08-20 10:00 UTC"
    assert format_iso_timestamp("2026-08-20T12:00:00+02:00") == "2026-08-20 10:00 UTC"


def test_extract_text() -> None:
    assert extract_text("hello") == "hello"
    assert extract_text(None) == ""
    assert extract_text(["foo", "bar"]) == "foo bar"
    assert extract_text({"text": "custom text"}) == "custom text"
    assert extract_text({"content": "content text"}) == "content text"
    assert extract_text({"type": "tool_use", "id": "123"}) == ""
    assert extract_text(12345) == "12345"


def test_connect_history(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    db.touch()
    with connect_history(db) as conn:
        assert isinstance(conn, sqlite3.Connection)


def test_load_past_user_prompts_empty(tmp_path: Path) -> None:
    assert load_past_user_prompts(tmp_path / "nonexistent.db") == []


def test_load_past_user_prompts_seeded(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)
    prompts = load_past_user_prompts(db)
    assert prompts == [
        "How do I dockerize a FastAPI application?",
        "Set up a React Vite project with TypeScript.",
        "How to handle PostgreSQL migrations with Alembic?",
    ]


def test_load_past_conversations_empty(tmp_path: Path) -> None:
    assert load_past_conversations(tmp_path / "nonexistent.db") == {}


def test_load_past_conversations_seeded(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)
    convs = load_past_conversations(db)
    assert len(convs) == 3
    assert "thread-100" in convs
    assert "thread-200" in convs
    assert "thread-300" in convs
    assert len(convs["thread-100"]["messages"]) == 2
    assert len(convs["thread-300"]["messages"]) == 3


def test_load_past_conversations_exclude_thread(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)
    convs = load_past_conversations(db, exclude_thread_id="thread-200")
    assert len(convs) == 2
    assert "thread-200" not in convs


def test_load_past_conversations_orphan_write(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)
    serializer = JsonPlusSerializer()
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    orphan_msg = HumanMessage(content="Orphan prompt")
    typ, val = serializer.dumps_typed([orphan_msg])
    cur.execute(
        "INSERT INTO writes (thread_id, checkpoint_id, task_id, idx, channel, type, value) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("orphan-thread", "cp-orphan", "task-orphan", 0, "messages", typ, val),
    )
    conn.commit()
    conn.close()

    convs = load_past_conversations(db)
    assert "orphan-thread" not in convs


def test_search_past_conversations_in_db(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)

    results = search_past_conversations_in_db("fastapi docker", db_path=db)
    assert len(results) >= 1
    assert results[0]["thread_id"] == "thread-100"
    assert "FastAPI" in results[0]["snippets"][0]
    assert "2026-08-20" in results[0]["formatted_date"]

    results_date = search_past_conversations_in_db("2026-08-21", db_path=db)
    assert len(results_date) == 1
    assert results_date[0]["thread_id"] == "thread-200"

    assert search_past_conversations_in_db("nonexistent keywords", db_path=db) == []
    assert search_past_conversations_in_db("", db_path=db) == []


def test_search_past_conversations_limit(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)
    results = search_past_conversations_in_db("how to", db_path=db, limit=1)
    assert len(results) == 1


def test_format_past_conversations_context() -> None:
    assert "No relevant past conversations found" in format_past_conversations_context([])

    sample = [
        {
            "thread_id": "thread-12345678",
            "score": 3,
            "formatted_date": "2026-08-21 14:30 UTC",
            "snippets": ["[User]: How to configure CORS?", "[Assistant]: Use CORSMiddleware."],
            "total_messages": 2,
        }
    ]
    out = format_past_conversations_context(sample)
    assert "Session #1 (thread-1)" in out
    assert "2026-08-21 14:30 UTC" in out
    assert "[User]: How to configure CORS?" in out


@pytest.mark.anyio
async def test_search_past_conversations_tool(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    _seed_db(db)

    active_thread = "thread-100"
    tool = create_search_past_conversations_tool(db, lambda: active_thread)

    # Search for React (should find thread-200)
    out = await tool.ainvoke({"query": "React Vite"})
    assert "react" in out.lower()
    assert "thread-2" in out

    # Search for FastAPI (matches thread-100 which is active -> excluded)
    out_excluded = await tool.ainvoke({"query": "FastAPI"})
    assert "No relevant past conversations found" in out_excluded

    # Non-positive limit raises ValueError
    with pytest.raises(ValueError, match="Limit must be greater than 0"):
        await tool.ainvoke({"query": "React Vite", "limit": 0})


@pytest.mark.anyio
async def test_search_past_conversations_tool_error(tmp_path: Path) -> None:
    db = tmp_path / "corrupt.db"
    db.write_text("corrupted sqlite")
    tool = create_search_past_conversations_tool(db, lambda: "t-1")
    out = await tool.ainvoke({"query": "anything"})
    assert "Error searching past conversations" in out
