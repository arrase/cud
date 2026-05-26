"""Discord gateway adapter."""

from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import load_settings
from cud.gateway._discord_utils import DISCORD_MAX_LENGTH, send_response, split_message
from cud.gateway.scheduler import TaskScheduler

_log = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


class DiscordGateway:
    def __init__(self, agent: str, *, verbose: bool = False):
        self.agent = agent
        self.agent_dir = agent_home(agent)
        self.settings = load_settings(self.agent_dir)
        self.verbose = verbose
        self.sessions: dict[str, AgentRuntime] = {}
        self.bot: commands.Bot | None = None
        self.scheduler = TaskScheduler(self)

    async def aclose_sessions(self) -> None:
        """Close all active runtime sessions."""
        for runtime in self.sessions.values():
            await runtime.aclose()
        self.sessions.clear()

    # -- Session management --------------------------------------------------

    def _get_thread_id(self, message_or_channel: discord.abc.Messageable | discord.Message) -> str:
        """Map a Discord channel/thread/message object to a stable LangGraph thread_id."""
        channel = getattr(message_or_channel, "channel", message_or_channel)
        guild = getattr(channel, "guild", None)
        guild_id = getattr(guild, "id", "dm")
        channel_id = getattr(channel, "id", None)
        if channel_id is None:
            channel_id = getattr(message_or_channel, "id", "unknown")
        return _SAFE.sub("_", f"discord:{guild_id}:{channel_id}")

    def session(self, thread_id: str) -> AgentRuntime:
        runtime = self.sessions.get(thread_id)
        if runtime is None:
            runtime = AgentRuntime(self.agent_dir, thread_id=thread_id)
            self.sessions[thread_id] = runtime
        return runtime

    async def _reload_sessions(self) -> None:
        self.settings = load_settings(self.agent_dir)
        for runtime in self.sessions.values():
            await runtime.reload()

    # -- Message handling ----------------------------------------------------

    async def handle_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return
        thread_id = self._get_thread_id(message)
        try:
            runtime = self.session(thread_id)
            async with message.channel.typing():
                response = await runtime.invoke(message.content, thread_id=thread_id)

            content = response.content
            chunks = split_message(content)
            await send_response(message, chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)

        except Exception as exc:
            _log.exception("Error handling message in thread %s", thread_id)
            error_msg = f"Cud error: `{type(exc).__name__}: {str(exc)[:1600]}`"
            await send_response(message, error_msg)

    # -- Slash commands ------------------------------------------------------

    async def cmd_new(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        runtime = self.session(thread_id)
        result = await runtime.new_session()
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_model(self, interaction: discord.Interaction, model_name: str) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        runtime = self.session(thread_id)
        result = await runtime.set_model(model_name)
        await self._reload_sessions()
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_usage(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        await interaction.response.send_message(
            f"agent=`{self.agent}` model=`{self.settings.model.name}` thread=`{thread_id}`",
            ephemeral=True,
        )

    async def cmd_undo(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        result = await self.session(thread_id).undo_last_exchange(thread_id=thread_id)
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_reload(self, interaction: discord.Interaction) -> None:
        await self._reload_sessions()
        self.scheduler.reload()
        await interaction.response.send_message("Agent and tasks reloaded.", ephemeral=True)

    async def cmd_memory_view(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        content = await self.session(thread_id).view_memory()
        await interaction.response.send_message(content[:DISCORD_MAX_LENGTH], ephemeral=True)

    async def cmd_memory_clear(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        result = await self.session(thread_id).clear_memory()
        await self._reload_sessions()
        await interaction.response.send_message(result, ephemeral=True)

    # -- Bot lifecycle -------------------------------------------------------

    async def run(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!cud ", intents=intents)
        self.bot = bot
        gw = self  # Capture for closures below.

        @bot.event
        async def on_ready() -> None:
            await bot.tree.sync()
            scheduler_task = bot.loop.create_task(gw.scheduler.run(), name="cud-scheduler")
            scheduler_task.add_done_callback(_log_task_error)
            if gw.verbose:
                _log.info("Discord gateway ready as %s", bot.user)

        @bot.event
        async def on_message(message: discord.Message) -> None:
            await gw.handle_message(message)

        # -- Register slash commands -----------------------------------------

        @bot.tree.command(name="new", description="Start a new Cud session in this Discord thread.")
        async def slash_new(interaction: discord.Interaction) -> None:
            await gw.cmd_new(interaction)

        @bot.tree.command(name="model", description="Temporarily switch this agent's configured model.")
        @app_commands.describe(model_name="Ollama model id")
        async def slash_model(interaction: discord.Interaction, model_name: str) -> None:
            await gw.cmd_model(interaction, model_name)

        @bot.tree.command(name="usage", description="Show Cud runtime usage summary.")
        async def slash_usage(interaction: discord.Interaction) -> None:
            await gw.cmd_usage(interaction)

        @bot.tree.command(name="undo", description="Remove the last exchange from this thread.")
        async def slash_undo(interaction: discord.Interaction) -> None:
            await gw.cmd_undo(interaction)

        @bot.tree.command(name="reload", description="Reload tools and prompt for this agent.")
        async def slash_reload(interaction: discord.Interaction) -> None:
            await gw.cmd_reload(interaction)

        memory_group = app_commands.Group(name="memory", description="Manage Cud long-term memory.")

        @memory_group.command(name="view", description="View MEMORY.md.")
        async def slash_memory_view(interaction: discord.Interaction) -> None:
            await gw.cmd_memory_view(interaction)

        @memory_group.command(name="clear", description="Clear MEMORY.md.")
        async def slash_memory_clear(interaction: discord.Interaction) -> None:
            await gw.cmd_memory_clear(interaction)

        bot.tree.add_command(memory_group)

        token = self.settings.gateway.token
        if not token:
            raise RuntimeError("gateway.token is empty; run `cud gateway setup <agent> discord --token ...`")
        async with bot:
            await bot.start(token)


def _log_task_error(task: asyncio.Task[None]) -> None:
    """Log unhandled exceptions from background asyncio tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _log.exception("Background task '%s' failed", task.get_name(), exc_info=exc)
