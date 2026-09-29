import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from cud.config.scaffold import create_agent
from cud.tui.app import (
    _THEME,
    _agent_response,
    _build_prompt_message,
    _help_panel,
    _system_message,
    _welcome_banner,
    handle_command,
    run_tui,
)


@pytest.fixture
def agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    return create_agent("tui-agent")


def test_ui_display_helpers() -> None:
    output = io.StringIO()
    console = Console(file=output, theme=_THEME, force_terminal=False, color_system=None)

    _welcome_banner("tui-agent", "gemma", "th-123", console)
    _agent_response("Here is the answer", "tui-agent", 1.5, console)
    _system_message("Status ok", "green", console)
    _help_panel(console)

    rendered = output.getvalue()
    assert "tui-agent" in rendered
    assert "gemma" in rendered
    assert "Here is the answer" in rendered
    assert "Status ok" in rendered
    assert "commands" in rendered


def test_build_prompt_message() -> None:
    msg = _build_prompt_message()
    assert isinstance(msg, HTML)


@pytest.mark.anyio
async def test_handle_command_quit_and_exit() -> None:
    console = Console(file=io.StringIO())
    runtime = MagicMock()

    assert await handle_command("/quit", runtime, console) is True
    assert await handle_command("/exit", runtime, console) is True


@pytest.mark.anyio
async def test_handle_command_new_session() -> None:
    console = Console(file=io.StringIO())
    runtime = MagicMock()
    runtime.new_session.return_value = "New session started"

    assert await handle_command("/new", runtime, console) is False
    runtime.new_session.assert_called_once()


@pytest.mark.anyio
async def test_handle_command_undo() -> None:
    console = Console(file=io.StringIO())
    runtime = AsyncMock()
    runtime.undo_last_exchange.return_value = "Exchange removed"

    assert await handle_command("/undo", runtime, console) is False
    runtime.undo_last_exchange.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_command_reload() -> None:
    console = Console(file=io.StringIO())
    runtime = AsyncMock()

    assert await handle_command("/reload", runtime, console) is False
    runtime.reload.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_command_memory() -> None:
    output = io.StringIO()
    console = Console(file=output, theme=_THEME)
    runtime = AsyncMock()
    runtime.view_memory = MagicMock(return_value="# Memory notes")
    runtime.clear_memory.return_value = "Memory cleared."

    # memory view
    assert await handle_command("/memory view", runtime, console) is False
    runtime.view_memory.assert_called_once()
    assert "Memory notes" in output.getvalue()

    # memory clear
    assert await handle_command("/memory clear", runtime, console) is False
    runtime.clear_memory.assert_awaited_once()

    # memory search empty
    assert await handle_command("/memory search", runtime, console) is False

    # memory search no results
    runtime.search_past_conversations = MagicMock(return_value=[])
    assert await handle_command("/memory search docker", runtime, console) is False
    runtime.search_past_conversations.assert_called_with("docker", limit=5)

    # memory search with results
    runtime.search_past_conversations = MagicMock(return_value=[{
        "thread_id": "thread-12345678",
        "formatted_date": "2026-08-20 10:00 UTC",
        "score": 3,
        "snippets": ["[User]: How to dockerize FastAPI?"],
        "total_messages": 2,
    }])
    assert await handle_command("/memory search fastapi", runtime, console) is False
    assert "thread-1" in output.getvalue()
    assert "2026-08-20" in output.getvalue()

    # memory invalid arg
    assert await handle_command("/memory invalid", runtime, console) is False


@pytest.mark.anyio
async def test_handle_command_model() -> None:
    console = Console(file=io.StringIO())
    runtime = AsyncMock()
    runtime.set_model.return_value = "Model set to llama3"

    # missing arg
    assert await handle_command("/model", runtime, console) is False
    runtime.set_model.assert_not_called()

    # with arg
    assert await handle_command("/model llama3", runtime, console) is False
    runtime.set_model.assert_awaited_once_with("llama3")


@pytest.mark.anyio
async def test_handle_command_help_and_unknown() -> None:
    output = io.StringIO()
    console = Console(file=output)
    runtime = MagicMock()

    assert await handle_command("/help", runtime, console) is False
    assert "commands" in output.getvalue()

    assert await handle_command("/unknown_cmd", runtime, console) is False
    assert "Unknown command" in output.getvalue()


@pytest.mark.anyio
async def test_run_tui_agent_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    code = await run_tui("nonexistent")
    assert code == 1


@pytest.mark.anyio
async def test_run_tui_prompt_loop(agent_dir: Path) -> None:
    mock_runtime_instance = AsyncMock()
    mock_runtime_instance.__aenter__.return_value = mock_runtime_instance
    mock_runtime_instance.__aexit__.return_value = None
    mock_runtime_instance.invoke.side_effect = [
        MagicMock(content="First response"),
        RuntimeError("Invoke failed"),
    ]

    inputs = ["", "/new", "hello", "fail", "exit_now"]
    input_iter = iter(inputs)

    async def fake_prompt_async(prompt_msg):
        try:
            val = next(input_iter)
            if val == "exit_now":
                raise EOFError()
            return val
        except StopIteration:
            raise EOFError() from None

    with patch("cud.tui.app.AgentRuntime", return_value=mock_runtime_instance), \
         patch("prompt_toolkit.PromptSession.prompt_async", side_effect=fake_prompt_async), \
         patch("cud.tui.app.handle_command", AsyncMock(return_value=False)):

        code = await run_tui("tui-agent", thread_id="th-fixed")
        assert code == 0
        assert mock_runtime_instance.invoke.await_count == 2


@pytest.mark.anyio
async def test_run_tui_slash_quit(agent_dir: Path) -> None:
    mock_runtime_instance = AsyncMock()
    mock_runtime_instance.__aenter__.return_value = mock_runtime_instance
    mock_runtime_instance.__aexit__.return_value = None

    async def fake_prompt_async(prompt_msg):
        return "/quit"

    with patch("cud.tui.app.AgentRuntime", return_value=mock_runtime_instance), \
         patch("prompt_toolkit.PromptSession.prompt_async", side_effect=fake_prompt_async):

        code = await run_tui("tui-agent")
        assert code == 0


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_empty_command_does_not_raise(agent_dir: Path) -> None:
    """Regression: `handle_command("")` raised IndexError on parts[0]."""
    console = Console(file=io.StringIO(), theme=_THEME)
    assert await handle_command("", MagicMock(), console) is False


@pytest.mark.anyio
async def test_memory_search_requires_a_space_before_the_query(agent_dir: Path) -> None:
    """Regression: `/memory searchable` was split into the query "able"."""
    runtime = MagicMock()
    console = Console(file=io.StringIO(), theme=_THEME)
    with patch("cud.tui.app._handle_memory_search") as search:
        await handle_command("/memory searchable", runtime, console)
    search.assert_not_called()

    with patch("cud.tui.app._handle_memory_search") as search:
        await handle_command("/memory search docker", runtime, console)
    search.assert_called_once()


@pytest.mark.anyio
async def test_memory_search_runs_off_the_event_loop(agent_dir: Path) -> None:
    """Regression: the search scans the whole DB synchronously, freezing the loop."""
    runtime = MagicMock()
    console = Console(file=io.StringIO(), theme=_THEME)
    real_to_thread = asyncio.to_thread

    with patch("cud.tui.app.asyncio.to_thread", wraps=real_to_thread) as to_thread:
        with patch("cud.tui.app._handle_memory_search"):
            await handle_command("/memory search docker", runtime, console)
    to_thread.assert_called_once()


@pytest.mark.anyio
async def test_run_tui_survives_broken_settings(agent_dir: Path) -> None:
    """Regression: an unreadable settings.yaml killed the TUI at startup."""
    (agent_dir / "settings.yaml").write_text("model: not-a-mapping\n", encoding="utf-8")
    with patch("cud.tui.app.PromptSession") as session_cls, \
         patch("cud.tui.app.AgentRuntime", new_callable=MagicMock):
        session_cls.return_value.prompt_async = AsyncMock(side_effect=EOFError)
        assert await run_tui("tui-agent") == 0


@pytest.mark.anyio
async def test_run_tui_survives_unreadable_history(agent_dir: Path) -> None:
    (agent_dir / "history.db").write_bytes(b"this is not a sqlite database")
    with patch("cud.tui.app.PromptSession") as session_cls, \
         patch("cud.tui.app.AgentRuntime", new_callable=MagicMock):
        session_cls.return_value.prompt_async = AsyncMock(side_effect=EOFError)
        assert await run_tui("tui-agent") == 0


@pytest.mark.anyio
async def test_run_tui_does_not_block_on_history_load(agent_dir: Path) -> None:
    with patch("cud.tui.app.PromptSession") as session_cls, \
         patch("cud.tui.app.AgentRuntime", new_callable=MagicMock), \
         patch("cud.tui.app.load_past_user_prompts", return_value=["a", "b"]), \
         patch("cud.tui.app.asyncio.to_thread", wraps=asyncio.to_thread) as to_thread:
        session_cls.return_value.prompt_async = AsyncMock(side_effect=EOFError)
        assert await run_tui("tui-agent") == 0
    assert to_thread.call_count >= 1


def test_help_panel_and_completer_stay_in_sync() -> None:
    """Regression: /help and the completer were two hand-kept lists that drifted."""
    from cud.tui.app import _COMMANDS_META, _completer

    rendered = io.StringIO()
    _help_panel(Console(file=rendered, theme=_THEME))
    for command in _COMMANDS_META:
        assert command.strip() in rendered.getvalue(), command
    for command in _completer.words:
        assert command in _COMMANDS_META
