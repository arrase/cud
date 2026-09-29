import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.message import RemoveMessage

from cud.agent.runtime import AgentRuntime, _drop_last_exchange, _response_from_raw
from cud.config.scaffold import create_agent
from cud.config.settings import SubAgentSettings, load_settings, save_settings


@pytest.fixture
def agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    return create_agent("test-agent")


def test_runtime_sync_context_manager(agent_dir: Path) -> None:
    mock_close = MagicMock()
    with patch.object(AgentRuntime, "close", mock_close):
        with AgentRuntime(agent_dir=agent_dir) as rt:
            assert isinstance(rt, AgentRuntime)
        mock_close.assert_called_once()


@pytest.mark.anyio
async def test_runtime_async_context_manager(agent_dir: Path) -> None:
    mock_aclose = AsyncMock()
    with patch.object(AgentRuntime, "aclose", mock_aclose):
        async with AgentRuntime(agent_dir=agent_dir) as rt:
            assert isinstance(rt, AgentRuntime)
        mock_aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_runtime_reload_and_build_graph(agent_dir: Path) -> None:
    settings = load_settings(agent_dir)
    settings.subagents = [SubAgentSettings(name="subby", description="subagent")]
    save_settings(agent_dir, settings)

    runtime = AgentRuntime(agent_dir=agent_dir)

    fake_saver = AsyncMock()
    fake_saver.__aenter__.return_value = fake_saver
    fake_saver.__aexit__.return_value = None

    with patch("cud.agent.runtime.create_deep_agent") as mock_create, \
         patch("cud.agent.runtime.load_mcp_tools_managed", AsyncMock(return_value=[])), \
         patch("cud.agent.runtime.AsyncSqliteSaver.from_conn_string", return_value=fake_saver):

        mock_agent_instance = MagicMock()
        mock_create.return_value = mock_agent_instance

        await runtime.reload()

        assert runtime.graph is mock_agent_instance
        assert "Cud Agent" in runtime.prompt
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert "subagents" in kwargs
        assert len(kwargs["subagents"]) == 1
        assert "tools" in kwargs
        assert any(t.name == "search_past_conversations" for t in kwargs["tools"])

        # AGENT.md absent branch
        (agent_dir / "AGENT.md").unlink()
        await runtime.reload()
        assert runtime.prompt == ""


@pytest.mark.anyio
async def test_runtime_invoke(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "I am Cud!"}]})
    runtime.graph = mock_graph

    with patch.object(AgentRuntime, "reload", AsyncMock()) as mock_reload:
        resp = await runtime.invoke("Hello", thread_id="custom-thread")
        assert resp.content == "I am Cud!"
        mock_graph.ainvoke.assert_awaited_once_with(
            {"messages": [{"role": "user", "content": "Hello"}]},
            {"configurable": {"thread_id": "custom-thread"}},
        )
        mock_reload.assert_not_called()


@pytest.mark.anyio
async def test_runtime_invoke_triggers_reload_if_graph_none(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.graph is None

    async def fake_reload_locked(self):
        self.graph = MagicMock()
        self.graph.ainvoke = AsyncMock(return_value={"messages": [{"role": "ai", "content": "Done"}]})

    with patch.object(AgentRuntime, "_reload_locked", fake_reload_locked):
        resp = await runtime.invoke("Ping")
        assert resp.content == "Done"
        assert runtime.graph is not None


@pytest.mark.anyio
async def test_runtime_undo_last_exchange_empty(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))
    runtime.graph = mock_graph

    result = await runtime.undo_last_exchange()
    assert result == "Nothing to undo."
    mock_graph.aupdate_state.assert_not_called()


@pytest.mark.anyio
async def test_runtime_undo_sends_remove_messages(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_graph = MagicMock()
    messages = [
        HumanMessage("Question", id="m1"),
        AIMessage("Answer", id="m2"),
    ]
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": messages}))
    mock_graph.aupdate_state = AsyncMock()
    runtime.graph = mock_graph

    result = await runtime.undo_last_exchange(thread_id="t-123")
    assert result == "Last exchange removed."
    _, update = mock_graph.aupdate_state.await_args.args
    removed = update["messages"]
    assert [m.id for m in removed] == ["m1", "m2"]
    assert all(isinstance(m, RemoveMessage) for m in removed)


@pytest.mark.anyio
async def test_undo_actually_removes_messages_from_state(agent_dir: Path) -> None:
    """Regression: the `messages` channel is reduced by `add_messages`, which
    merges by id. Passing the kept messages back therefore re-adds them, so
    undo must send `RemoveMessage` ids instead."""
    from langgraph.graph.message import add_messages

    messages = [
        HumanMessage("first", id="1"),
        AIMessage("answer one", id="2"),
        HumanMessage("second", id="3"),
        AIMessage("answer two", id="4"),
    ]

    kept = _drop_last_exchange(messages)
    assert [m.id for m in kept] == ["1", "2"]

    naive = add_messages(messages, kept)
    assert len(naive) == len(messages), "naive approach must be a no-op"

    removals = [RemoveMessage(id=m.id) for m in messages[len(kept):]]
    assert len(add_messages(messages, removals)) == 2


@pytest.mark.anyio
async def test_runtime_undo_triggers_reload_if_graph_none(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.graph is None

    async def fake_reload_locked(self):
        self.graph = MagicMock()
        self.graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))

    with patch.object(AgentRuntime, "_reload_locked", fake_reload_locked):
        res = await runtime.undo_last_exchange()
        assert res == "Nothing to undo."


def test_response_from_raw_ignores_tool_output() -> None:
    """A run ending on a ToolMessage must not surface raw tool output."""
    raw = {"messages": [AIMessage("answer", id="a"), ToolMessage("SECRET", tool_call_id="t", id="b")]}
    assert _response_from_raw(raw).content == "answer"

    assert _response_from_raw({"messages": [ToolMessage("SECRET", tool_call_id="t")]}).content == (
        "The agent finished without text output."
    )
    assert _response_from_raw({"other": 1}).content == "The agent finished without text output."


@pytest.mark.anyio
async def test_runtime_clear_memory(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    with patch.object(AgentRuntime, "reload", AsyncMock()) as mock_reload:
        res = await runtime.clear_memory()
        assert res == "Memory cleared."
        assert "# Long-Term Memory" in (agent_dir / "MEMORY.md").read_text(encoding="utf-8")
        mock_reload.assert_awaited_once()


@pytest.mark.anyio
async def test_runtime_set_model(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    runtime.settings = load_settings(agent_dir)
    runtime.graph = MagicMock()
    with patch.object(AgentRuntime, "reload", AsyncMock()) as mock_reload:
        res = await runtime.set_model("new-model-xyz")
        assert res == "Model set to new-model-xyz."
        assert runtime.settings.model.name == "new-model-xyz"
        saved = load_settings(agent_dir)
        assert saved.model.name == "new-model-xyz"
        mock_reload.assert_awaited_once()


@pytest.mark.anyio
async def test_runtime_undo_triggers_reload_if_graph_none_legacy(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.graph is None

    async def fake_reload(self):
        self.graph = MagicMock()
        self.graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))

    with patch.object(AgentRuntime, "_reload_locked", fake_reload):
        res = await runtime.undo_last_exchange()
        assert res == "Nothing to undo."


def test_runtime_new_session_and_view_memory_empty(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    old_thread = runtime.thread_id
    msg = runtime.new_session()
    assert runtime.thread_id != old_thread
    assert runtime.thread_id in msg

    (agent_dir / "MEMORY.md").unlink(missing_ok=True)
    assert runtime.view_memory() == "Memory is empty."


@pytest.mark.anyio
async def test_runtime_aclose_resets_graph(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    runtime.graph = MagicMock()
    mock_aclose = AsyncMock()
    with patch.object(runtime._exit_stack, "aclose", mock_aclose):
        await runtime.aclose()
        mock_aclose.assert_awaited_once()
        assert runtime.graph is None


def test_runtime_close_outside_event_loop(agent_dir: Path) -> None:
    AgentRuntime(agent_dir=agent_dir).close()


@pytest.mark.anyio
async def test_runtime_close_inside_loop_raises(agent_dir: Path) -> None:
    with pytest.raises(RuntimeError, match="running event loop"):
        AgentRuntime(agent_dir=agent_dir).close()


@pytest.mark.anyio
async def test_set_model_before_first_reload_keeps_other_settings(agent_dir: Path) -> None:
    """Regression: set_model must not overwrite the on-disk config with the
    in-memory defaults when the graph has not been built yet."""
    settings = load_settings(agent_dir)
    settings.model.base_url = "http://ollama.internal:11434"
    settings.model.context_window = 8192
    save_settings(agent_dir, settings)

    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.graph is None
    assert await runtime.set_model("new-model-xyz") == "Model set to new-model-xyz."

    saved = load_settings(agent_dir)
    assert saved.model.name == "new-model-xyz"
    assert saved.model.base_url == "http://ollama.internal:11434"
    assert saved.model.context_window == 8192


@pytest.mark.anyio
async def test_reload_failure_keeps_previous_graph(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    good = MagicMock()
    runtime.graph = good

    with patch("cud.agent.runtime.load_settings", side_effect=ValueError("broken yaml")):
        with pytest.raises(ValueError, match="broken yaml"):
            await runtime.reload()

    assert runtime.graph is good, "a failed reload must not drop the live graph"


@pytest.mark.anyio
async def test_concurrent_invoke_builds_graph_once(agent_dir: Path) -> None:
    """Regression: concurrent first-use must not build N graphs or N reloads."""
    runtime = AgentRuntime(agent_dir=agent_dir)
    builds = 0

    async def fake_build(self, settings, prompt, stack):
        nonlocal builds
        builds += 1
        await asyncio.sleep(0)
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [{"role": "ai", "content": "ok"}]})
        return graph

    with patch.object(AgentRuntime, "_build_graph", fake_build):
        results = await asyncio.gather(*(runtime.invoke(f"m{i}") for i in range(3)))

    assert builds == 1
    assert [r.content for r in results] == ["ok", "ok", "ok"]


def test_runtime_episodic_search_and_prompts(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.load_past_prompts() == []

