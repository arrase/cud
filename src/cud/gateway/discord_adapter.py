"""Discord gateway adapter."""

from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from cud.agent.episodic_memory import format_past_conversations_context
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
        # Keyed by the Discord channel/thread; `runtime.thread_id` is what
        # actually selects the LangGraph conversation, so `/new` works.
        self.sessions: dict[str, AgentRuntime] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.bot: commands.Bot | None = None
        self.scheduler = TaskScheduler(self)

    async def aclose_sessions(self) -> None:
        """Close all active runtime sessions.

        Snapshot before awaiting: `session()` and the scheduler mutate the dict
        from other tasks, and iterating it live across an `await` raises. Loop
        until stable so a session opened mid-shutdown is not leaked.
        """
        while self.sessions:
            sessions = list(self.sessions.values())
            self.sessions.clear()
            results = await asyncio.gather(*(rt.aclose() for rt in sessions), return_exceptions=True)
            for exc in results:
                if exc is not None:
                    _log.error("Error closing session", exc_info=exc)

    # -- Session management --------------------------------------------------

    def _get_thread_id(self, message_or_channel: object) -> str:
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
        """Reload config and every live session; one failure must not abort the rest."""
        self.settings = load_settings(self.agent_dir)
        # Snapshot both before awaiting: the dict can change while we reload.
        runtimes = list(self.sessions.items())
        results = await asyncio.gather(*(rt.reload() for _, rt in runtimes), return_exceptions=True)
        for (thread_id, _), exc in zip(runtimes, results, strict=True):
            if exc is not None:
                _log.error("Reload failed for session %s", thread_id, exc_info=exc)

    # -- Message handling ----------------------------------------------------

    async def handle_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return
        thread_id = self._get_thread_id(message)
        try:
            runtime = self.session(thread_id)
            # Serialize per thread: concurrent messages in one channel would
            # race on the same LangGraph checkpoint version.
            async with self._thread_lock(thread_id):
                async with message.channel.typing():
                    response = await runtime.invoke(message.content)

            content = response.content
            chunks = split_message(content)
            await send_response(message, chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)

        except Exception as exc:
            _log.exception("Error handling message in thread %s", thread_id)
            await self._notify_error(message, f"`{type(exc).__name__}`: {str(exc)[:1600]}")

    def _thread_lock(self, thread_id: str) -> asyncio.Lock:
        return self._locks.setdefault(thread_id, asyncio.Lock())

    async def _notify_error(self, message: discord.Message, detail: str) -> None:
        """Report a failure to the channel without leaking internals twice.

        If the original failure *was* the Discord send, this fallback can fail
        too; swallow that so no unhandled task exception escapes.
        """
        try:
            await send_response(message, f"Cud error: {detail}")
        except Exception:
            _log.exception("Failed to deliver the error message to Discord")

    # -- Slash commands ------------------------------------------------------

    async def cmd_new(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        runtime = self.session(thread_id)
        result = runtime.new_session()
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_model(self, interaction: discord.Interaction, model_name: str) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        # set_model() persists and reloads this runtime itself.
        result = await self.session(thread_id).set_model(model_name)
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
        result = await self.session(thread_id).undo_last_exchange()
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_reload(self, interaction: discord.Interaction) -> None:
        await self._reload_sessions()
        self.scheduler.reload()
        await interaction.response.send_message("Agent and tasks reloaded.", ephemeral=True)

    async def cmd_memory_view(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        content = self.session(thread_id).view_memory()
        await interaction.response.send_message(content[:DISCORD_MAX_LENGTH], ephemeral=True)

    async def cmd_memory_clear(self, interaction: discord.Interaction) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        result = await self.session(thread_id).clear_memory()
        await self._reload_sessions()
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_memory_search(self, interaction: discord.Interaction, query: str) -> None:
        thread_id = self._get_thread_id(interaction.channel)
        runtime = self.session(thread_id)
        results = await asyncio.to_thread(runtime.search_past_conversations, query)
        content = format_past_conversations_context(results)
        await interaction.response.send_message(content[:DISCORD_MAX_LENGTH], ephemeral=True)

    # -- Bot lifecycle -------------------------------------------------------

    async def run(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        # `command_prefix` is inert: only slash commands are exposed and
        # `process_commands` is never reached, but Bot still requires the arg.
        bot = commands.Bot(command_prefix="", intents=intents)
        self.bot = bot
        gw = self  # Capture for closures below.
        scheduler_task: asyncio.Task[None] | None = None

        @bot.event
        async def on_ready() -> None:
            # `ready` is re-dispatched on every non-resumable reconnect, so the
            # scheduler must be started exactly once or tasks fire repeatedly.
            nonlocal scheduler_task
            await bot.tree.sync()
            if scheduler_task is None or scheduler_task.done():
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

        @memory_group.command(name="search", description="Search past episodic conversations.")
        @app_commands.describe(query="Keywords or topics to search for")
        async def slash_memory_search(interaction: discord.Interaction, query: str) -> None:
            await gw.cmd_memory_search(interaction, query)

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
