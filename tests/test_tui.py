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
            raise EOFError()

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
