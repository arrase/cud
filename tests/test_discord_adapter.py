import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pydantic.root_model
import pytest

from cud.config.scaffold import create_agent
from cud.gateway.discord_adapter import DiscordGateway, _log_task_error


@pytest.fixture
def agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    return create_agent("discord-agent")


def _make_mock_channel(channel_id: int = 123, guild_id: int | None = None) -> MagicMock:
    channel = MagicMock(spec=["guild", "id", "typing", "send"])
    if guild_id is not None:
        channel.guild = MagicMock(spec=["id"])
        channel.guild.id = guild_id
    else:
        channel.guild = None
    channel.id = channel_id
    channel.send = AsyncMock()
    channel.typing.return_value.__aenter__ = AsyncMock()
    channel.typing.return_value.__aexit__ = AsyncMock(return_value=False)
    return channel


def test_init(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent", verbose=True)
    assert gw.agent == "discord-agent"
    assert gw.verbose is True
    assert gw.agent_dir == agent_dir
    assert gw.sessions == {}


@pytest.mark.anyio
async def test_aclose_sessions(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    mock_rt1 = AsyncMock()
    mock_rt2 = AsyncMock()
    gw.sessions = {"t1": mock_rt1, "t2": mock_rt2}

    await gw.aclose_sessions()
    mock_rt1.aclose.assert_awaited_once()
    mock_rt2.aclose.assert_awaited_once()
    assert gw.sessions == {}


def test_get_thread_id(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")

    channel_guild = _make_mock_channel(channel_id=222, guild_id=111)
    msg_guild = MagicMock(spec=["channel"])
    msg_guild.channel = channel_guild
    assert gw._get_thread_id(msg_guild) == "discord:111:222"

    channel_dm = _make_mock_channel(channel_id=333, guild_id=None)
    msg_dm = MagicMock(spec=["channel"])
    msg_dm.channel = channel_dm
    assert gw._get_thread_id(msg_dm) == "discord:dm:333"

    # Channel with no id
    channel_no_id = MagicMock(spec=["guild"])
    channel_no_id.guild = None
    msg_channel_no_id = MagicMock(spec=["channel", "id"])
    msg_channel_no_id.channel = channel_no_id
    msg_channel_no_id.id = 555
    assert gw._get_thread_id(msg_channel_no_id) == "discord:dm:555"

    msg_fallback = MagicMock(spec=["id"])
    msg_fallback.id = 444
    assert gw._get_thread_id(msg_fallback) == "discord:dm:444"


def test_session_caching(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    rt1 = gw.session("thread-1")
    rt2 = gw.session("thread-1")
    assert rt1 is rt2
    assert "thread-1" in gw.sessions


@pytest.mark.anyio
async def test_reload_sessions(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    mock_rt = AsyncMock()
    gw.sessions["t1"] = mock_rt

    await gw._reload_sessions()
    mock_rt.reload.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_message_bot_author(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    msg = MagicMock(spec=["author", "content"])
    msg.author = MagicMock(spec=["bot"])
    msg.author.bot = True
    msg.content = "hello"

    await gw.handle_message(msg)
    assert gw.sessions == {}


@pytest.mark.anyio
async def test_handle_message_empty_content(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    msg = MagicMock(spec=["author", "content"])
    msg.author = MagicMock(spec=["bot"])
    msg.author.bot = False
    msg.content = ""

    await gw.handle_message(msg)
    assert gw.sessions == {}


@pytest.mark.anyio
async def test_handle_message_success_multi_chunk(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    channel = _make_mock_channel(channel_id=2, guild_id=1)
    msg = MagicMock(spec=["author", "content", "channel"])
    msg.author = MagicMock(spec=["bot"])
    msg.author.bot = False
    msg.content = "ping"
    msg.channel = channel

    mock_rt = AsyncMock()
    long_content = "chunk1\n" + "A" * 1995 + "\nchunk2"
    mock_rt.invoke.return_value = MagicMock(content=long_content)
    gw.sessions["discord:1:2"] = mock_rt

    with patch("cud.gateway.discord_adapter.send_response", new_callable=AsyncMock) as mock_send_resp:
        await gw.handle_message(msg)
        mock_rt.invoke.assert_awaited_once_with("ping", thread_id="discord:1:2")
        mock_send_resp.assert_awaited_once()
        channel.send.assert_awaited()


@pytest.mark.anyio
async def test_handle_message_exception(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    channel = _make_mock_channel(channel_id=2, guild_id=None)
    msg = MagicMock(spec=["author", "content", "channel"])
    msg.author = MagicMock(spec=["bot"])
    msg.author.bot = False
    msg.content = "fail"
    msg.channel = channel

    mock_rt = AsyncMock()
    mock_rt.invoke.side_effect = ValueError("Something broke")
    gw.sessions["discord:dm:2"] = mock_rt

    with patch("cud.gateway.discord_adapter.send_response", new_callable=AsyncMock) as mock_send_resp:
        await gw.handle_message(msg)
        mock_send_resp.assert_awaited_once()
        error_arg = mock_send_resp.call_args[0][1]
        assert "Cud error: `ValueError: Something broke`" in error_arg


@pytest.mark.anyio
async def test_cmd_new(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = MagicMock()
    mock_rt.new_session.return_value = "New session started"
    gw.sessions["discord:dm:123"] = mock_rt

    await gw.cmd_new(interaction)
    mock_rt.new_session.assert_called_once()
    interaction.response.send_message.assert_awaited_once_with("New session started", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_model(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = AsyncMock()
    mock_rt.set_model.return_value = "Model set to llama3"
    gw.sessions["discord:dm:123"] = mock_rt
    gw._reload_sessions = AsyncMock()

    await gw.cmd_model(interaction, "llama3")
    mock_rt.set_model.assert_awaited_once_with("llama3")
    gw._reload_sessions.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once_with("Model set to llama3", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_usage(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    await gw.cmd_usage(interaction)
    interaction.response.send_message.assert_awaited_once()
    assert "agent=`discord-agent`" in interaction.response.send_message.call_args[0][0]


@pytest.mark.anyio
async def test_cmd_undo(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = AsyncMock()
    mock_rt.undo_last_exchange.return_value = "Exchange undone"
    gw.sessions["discord:dm:123"] = mock_rt

    await gw.cmd_undo(interaction)
    mock_rt.undo_last_exchange.assert_awaited_once_with(thread_id="discord:dm:123")
    interaction.response.send_message.assert_awaited_once_with("Exchange undone", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_reload(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["response"])
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()
    gw._reload_sessions = AsyncMock()
    gw.scheduler.reload = MagicMock()

    await gw.cmd_reload(interaction)
    gw._reload_sessions.assert_awaited_once()
    gw.scheduler.reload.assert_called_once()
    interaction.response.send_message.assert_awaited_once_with("Agent and tasks reloaded.", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_memory_view(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = MagicMock()
    mock_rt.view_memory.return_value = "Memory notes"
    gw.sessions["discord:dm:123"] = mock_rt

    await gw.cmd_memory_view(interaction)
    interaction.response.send_message.assert_awaited_once_with("Memory notes", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_memory_clear(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = AsyncMock()
    mock_rt.clear_memory.return_value = "Memory cleared."
    gw.sessions["discord:dm:123"] = mock_rt
    gw._reload_sessions = AsyncMock()

    await gw.cmd_memory_clear(interaction)
    mock_rt.clear_memory.assert_awaited_once()
    gw._reload_sessions.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once_with("Memory cleared.", ephemeral=True)


@pytest.mark.anyio
async def test_cmd_memory_search(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    interaction = MagicMock(spec=["channel", "response"])
    interaction.channel = _make_mock_channel(channel_id=123, guild_id=None)
    interaction.response = MagicMock(spec=["send_message"])
    interaction.response.send_message = AsyncMock()

    mock_rt = MagicMock()
    mock_rt.search_past_conversations.return_value = []
    gw.sessions["discord:dm:123"] = mock_rt

    await gw.cmd_memory_search(interaction, "docker")
    mock_rt.search_past_conversations.assert_called_once_with("docker")
    assert interaction.response.send_message.await_count == 1
    args, kwargs = interaction.response.send_message.call_args
    assert "No relevant past conversations found" in args[0]
    assert kwargs.get("ephemeral") is True


@pytest.mark.anyio
async def test_run_missing_token(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent")
    gw.settings.gateway.token = ""

    with pytest.raises(RuntimeError, match="gateway.token is empty"):
        await gw.run()


@pytest.mark.anyio
async def test_run_success_lifecycle(agent_dir: Path) -> None:
    gw = DiscordGateway("discord-agent", verbose=True)
    gw.settings.gateway.token = "fake-token"

    mock_bot = MagicMock()
    mock_bot.start = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock()
    mock_bot.tree.sync = AsyncMock()

    created_events = {}
    registered_commands = {}

    def fake_event(coro):
        created_events[coro.__name__] = coro
        return coro

    def fake_command(**kw):
        name = kw.get("name", "cmd")
        def decorator(f):
            registered_commands[name] = f
            return f
        return decorator

    def fake_create_task(coro, **kw):
        coro.close()
        task_mock = MagicMock()
        return task_mock

    mock_bot.event = fake_event
    mock_bot.tree.command = fake_command
    mock_bot.loop.create_task = fake_create_task

    with patch("cud.gateway.discord_adapter.commands.Bot", return_value=mock_bot), \
         patch("cud.gateway.discord_adapter.app_commands.Group.command", side_effect=fake_command):
        await gw.run()

    mock_bot.start.assert_awaited_once_with("fake-token")
    assert "on_ready" in created_events
    assert "on_message" in created_events

    # Execute on_ready
    await created_events["on_ready"]()
    mock_bot.tree.sync.assert_awaited_once()

    # Execute on_message
    gw.handle_message = AsyncMock()
    fake_msg = MagicMock()
    await created_events["on_message"](fake_msg)
    gw.handle_message.assert_awaited_once_with(fake_msg)

    # Test registered slash commands
    gw.cmd_new = AsyncMock()
    gw.cmd_model = AsyncMock()
    gw.cmd_usage = AsyncMock()
    gw.cmd_undo = AsyncMock()
    gw.cmd_reload = AsyncMock()
    gw.cmd_memory_view = AsyncMock()
    gw.cmd_memory_clear = AsyncMock()

    mock_interaction = MagicMock()
    if "new" in registered_commands:
        await registered_commands["new"](mock_interaction)
        gw.cmd_new.assert_awaited_once()
    if "model" in registered_commands:
        await registered_commands["model"](mock_interaction, "llama3")
        gw.cmd_model.assert_awaited_once_with(mock_interaction, "llama3")
    if "usage" in registered_commands:
        await registered_commands["usage"](mock_interaction)
        gw.cmd_usage.assert_awaited_once()
    if "undo" in registered_commands:
        await registered_commands["undo"](mock_interaction)
        gw.cmd_undo.assert_awaited_once()
    if "reload" in registered_commands:
        await registered_commands["reload"](mock_interaction)
        gw.cmd_reload.assert_awaited_once()
    if "view" in registered_commands:
        await registered_commands["view"](mock_interaction)
        gw.cmd_memory_view.assert_awaited_once()
    if "clear" in registered_commands:
        await registered_commands["clear"](mock_interaction)
        gw.cmd_memory_clear.assert_awaited_once()


def test_log_task_error() -> None:
    # Cancelled task
    cancelled_task = MagicMock()
    cancelled_task.cancelled.return_value = True
    _log_task_error(cancelled_task)

    # Success task
    success_task = MagicMock()
    success_task.cancelled.return_value = False
    success_task.exception.return_value = None
    _log_task_error(success_task)

    # Failed task
    failed_task = MagicMock()
    failed_task.cancelled.return_value = False
    failed_task.exception.return_value = RuntimeError("scheduler died")
    failed_task.get_name.return_value = "cud-scheduler"
    _log_task_error(failed_task)
