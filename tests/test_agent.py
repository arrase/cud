from dataclasses import dataclass
from pathlib import Path

import pytest

from cud.agent.runtime import (
    AgentRuntime,
    _drop_last_exchange,
    _extract_content,
    _response_from_raw,
    _role,
)
from cud.agent.subagents import _resolve_env
from cud.config.scaffold import create_agent


@dataclass
class DummyMessage:
    content: str


def test_extract_content_from_dict() -> None:
    raw = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello!"},
        ]
    }
    assert _extract_content(raw) == "hello!"


def test_extract_content_from_object() -> None:
    raw = {"messages": [DummyMessage(content="object content")]}
    assert _extract_content(raw) == "object content"


def test_extract_content_fallback() -> None:
    assert _extract_content({"other": "value"}) == "{'other': 'value'}"


def test_response_from_raw() -> None:
    resp = _response_from_raw(
        {"messages": [{"role": "assistant", "content": "answer"}]}
    )
    assert resp.content == "answer"

    resp_empty = _response_from_raw(
        {"messages": [{"role": "assistant", "content": "   "}]}
    )
    assert resp_empty.content == "The agent finished without text output."


def test_role() -> None:
    assert _role({"role": "human"}) == "human"
    assert _role({"type": "ai"}) == "ai"

    class HumanMessage:
        pass

    assert _role(HumanMessage()) == "human"


def test_drop_last_exchange() -> None:
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "question 1"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "question 2"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "tool", "content": "tool result"},
    ]
    trimmed = _drop_last_exchange(messages)
    assert len(trimmed) == 3
    assert trimmed[0]["role"] == "system"
    assert trimmed[1]["content"] == "question 1"
    assert trimmed[2]["content"] == "answer 1"


def test_drop_last_exchange_preserves_system() -> None:
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "question 1"},
    ]
    trimmed = _drop_last_exchange(messages)
    assert trimmed == [{"role": "system", "content": "system prompt"}]


def test_runtime_session_and_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    agent_dir = create_agent("test-agent")
    runtime = AgentRuntime(agent_dir=agent_dir)

    assert runtime.workspace_dir == agent_dir / "workspace"

    initial_thread = runtime.thread_id
    runtime.new_session()
    assert runtime.thread_id != initial_thread

    memory_content = runtime.view_memory()
    assert "Memory" in memory_content


def test_resolve_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR", "secret123")
    resolved = _resolve_env({"API_KEY": "${TEST_VAR}", "STATIC": "fixed"})
    assert resolved == {"API_KEY": "secret123", "STATIC": "fixed"}

    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert _resolve_env({"API_KEY": "${MISSING_VAR}"}) is None
