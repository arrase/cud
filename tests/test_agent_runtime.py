import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic.root_model
import pytest

from cud.agent.runtime import AgentRuntime, _run_async_sync
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

    mock_mcp_cleanup = AsyncMock()
    fake_saver = AsyncMock()
    fake_saver.__aenter__.return_value = fake_saver
    fake_saver.__aexit__.return_value = None

    with patch("cud.agent.runtime.create_deep_agent") as mock_create, \
         patch("cud.agent.runtime.load_mcp_tools_managed", AsyncMock(return_value=([], mock_mcp_cleanup))), \
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

    async def fake_reload(self):
        self.graph = MagicMock()
        self.graph.ainvoke = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "Done"}]})

    with patch.object(AgentRuntime, "reload", fake_reload):
        resp = await runtime.invoke("Ping")
        assert resp.content == "Done"


@pytest.mark.anyio
async def test_runtime_undo_last_exchange_empty(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))
    runtime.graph = mock_graph

    result = await runtime.undo_last_exchange()
    assert result == "No messages to undo."


@pytest.mark.anyio
async def test_runtime_undo_last_exchange_success(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_graph = MagicMock()
    messages = [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
    ]
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": messages}))
    mock_graph.aupdate_state = AsyncMock()
    runtime.graph = mock_graph

    result = await runtime.undo_last_exchange(thread_id="t-123")
    assert result == "Last exchange removed."
    mock_graph.aupdate_state.assert_awaited_once_with(
        {"configurable": {"thread_id": "t-123"}},
        {"messages": []},
    )


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
    with patch.object(AgentRuntime, "reload", AsyncMock()) as mock_reload:
        res = await runtime.set_model("new-model-xyz")
        assert res == "Model set to new-model-xyz."
        assert runtime.settings.model.name == "new-model-xyz"
        saved = load_settings(agent_dir)
        assert saved.model.name == "new-model-xyz"
        mock_reload.assert_awaited_once()


@pytest.mark.anyio
async def test_runtime_undo_triggers_reload_if_graph_none(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.graph is None

    async def fake_reload(self):
        self.graph = MagicMock()
        self.graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))

    with patch.object(AgentRuntime, "reload", fake_reload):
        res = await runtime.undo_last_exchange()
        assert res == "No messages to undo."


def test_runtime_new_session_and_view_memory_empty(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    old_thread = runtime.thread_id
    msg = runtime.new_session()
    assert runtime.thread_id != old_thread
    assert runtime.thread_id in msg

    (agent_dir / "MEMORY.md").unlink(missing_ok=True)
    assert runtime.view_memory() == "Memory is empty."


@pytest.mark.anyio
async def test_runtime_aclose_and_close(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    mock_aclose = AsyncMock()
    with patch.object(runtime._exit_stack, "aclose", mock_aclose):
        await runtime.aclose()
        mock_aclose.assert_awaited_once()

    def fake_run_sync(coro):
        coro.close()

    with patch("cud.agent.runtime._run_async_sync", fake_run_sync):
        runtime.close()


def test_run_async_sync_no_event_loop() -> None:
    async def sample():
        return 42

    assert _run_async_sync(sample()) == 42


@pytest.mark.anyio
async def test_run_async_sync_with_running_loop() -> None:
    async def sample():
        return "from thread"

    result = _run_async_sync(sample())
    assert result == "from thread"


def test_runtime_episodic_search_and_prompts(agent_dir: Path) -> None:
    runtime = AgentRuntime(agent_dir=agent_dir)
    assert runtime.load_past_prompts() == []
    assert runtime.search_past_conversations("anything") == []

