"""Discord gateway adapter."""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import load_settings, save_settings
from cud.gateway.scheduler import TaskScheduler
from cud.gateway.threading import discord_thread_id

DISCORD_MAX_LENGTH = 1900


@dataclass(slots=True)
class SessionState:
    runtime: AgentRuntime


class DiscordGateway:
    def __init__(self, agent: str, *, verbose: bool = False):
        self.agent = agent
        self.agent_dir = agent_home(agent)
        self.settings = load_settings(self.agent_dir)
        self.verbose = verbose
        self.sessions: dict[str, SessionState] = {}
        self.bot: commands.Bot | None = None
        self.scheduler = TaskScheduler(self)

    # -- Session management --------------------------------------------------

    def session(self, thread_id: str) -> SessionState:
        state = self.sessions.get(thread_id)
        if state is None:
            state = SessionState(runtime=AgentRuntime(self.agent_dir, thread_id=thread_id))
            self.sessions[thread_id] = state
        return state

    def _reload_sessions(self) -> None:
        self.settings = load_settings(self.agent_dir)
        for state in self.sessions.values():
            state.runtime.reload()

    # -- Message handling ----------------------------------------------------

    async def handle_message(self, message: Any) -> None:
        if message.author.bot or not message.content:
            return
        thread_id = discord_thread_id(message)
        try:
            state = self.session(thread_id)
            async with message.channel.typing():
                response = await asyncio.to_thread(state.runtime.invoke, message.content, thread_id=thread_id)

            content = response.content
            if not content:
                return

            chunks = _split_message(content)
            first, rest = chunks[0], chunks[1:]

            if message.guild is not None:
                await message.reply(first)
            else:
                await message.channel.send(first)

            for chunk in rest:
                await message.channel.send(chunk)

        except Exception as exc:
            traceback.print_exc()
            error_msg = f"Cud error: `{type(exc).__name__}: {str(exc)[:1600]}`"
            if message.guild is not None:
                await message.reply(error_msg)
            else:
                await message.channel.send(error_msg)

    # -- Slash commands ------------------------------------------------------

    async def cmd_new(self, interaction: Any) -> None:
        thread_id = discord_thread_id(interaction.channel)
        old = self.sessions.pop(thread_id, None)
        if old:
            await asyncio.to_thread(old.runtime.clear_history)
            old.runtime.close()
        self.session(thread_id)
        await interaction.response.send_message("New Cud session started. History cleared.", ephemeral=True)

    async def cmd_model(self, interaction: Any, model_name: str) -> None:
        self.settings.model.name = model_name
        save_settings(self.agent_dir, self.settings)
        self._reload_sessions()
        await interaction.response.send_message(f"Model set to `{model_name}`.", ephemeral=True)

    async def cmd_compress(self, interaction: Any, focus_topic: str | None = None) -> None:
        await interaction.response.send_message(
            "Compaction will run on the next model-managed context window.", ephemeral=True
        )

    async def cmd_usage(self, interaction: Any) -> None:
        thread_id = discord_thread_id(interaction.channel)
        await interaction.response.send_message(
            f"agent=`{self.agent}` model=`{self.settings.model.name}` thread=`{thread_id}`",
            ephemeral=True,
        )

    async def cmd_undo(self, interaction: Any) -> None:
        thread_id = discord_thread_id(interaction.channel)
        result = self.session(thread_id).runtime.undo_last_exchange(thread_id=thread_id)
        await interaction.response.send_message(result, ephemeral=True)

    async def cmd_reload(self, interaction: Any) -> None:
        self._reload_sessions()
        self.scheduler.reload()
        await interaction.response.send_message("Agent and tasks reloaded.", ephemeral=True)

    async def cmd_memory_view(self, interaction: Any) -> None:
        path = self.agent_dir / "MEMORY.md"
        content = path.read_text(encoding="utf-8") if path.exists() else "Memory is empty."
        await interaction.response.send_message(content[:DISCORD_MAX_LENGTH], ephemeral=True)

    async def cmd_memory_clear(self, interaction: Any) -> None:
        path = self.agent_dir / "MEMORY.md"
        path.write_text("# Long-Term Memory\n\nNo persistent memories yet.\n", encoding="utf-8")
        self._reload_sessions()
        await interaction.response.send_message("Memory cleared.", ephemeral=True)

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
            bot.loop.create_task(gw.scheduler.run())
            if gw.verbose:
                print(f"Discord gateway ready as {bot.user}")

        @bot.event
        async def on_message(message: Any) -> None:
            await gw.handle_message(message)

        # -- Register slash commands -----------------------------------------

        @bot.tree.command(name="new", description="Start a new Cud session in this Discord thread.")
        async def slash_new(interaction: Any) -> None:
            await gw.cmd_new(interaction)

        @bot.tree.command(name="model", description="Temporarily switch this agent's configured model.")
        @app_commands.describe(model_name="Ollama model id")
        async def slash_model(interaction: Any, model_name: str) -> None:
            await gw.cmd_model(interaction, model_name)

        @bot.tree.command(name="compress", description="Force context compaction on the current thread.")
        async def slash_compress(interaction: Any, focus_topic: str | None = None) -> None:
            await gw.cmd_compress(interaction, focus_topic)

        @bot.tree.command(name="usage", description="Show Cud runtime usage summary.")
        async def slash_usage(interaction: Any) -> None:
            await gw.cmd_usage(interaction)

        @bot.tree.command(name="undo", description="Remove the last exchange from this thread.")
        async def slash_undo(interaction: Any) -> None:
            await gw.cmd_undo(interaction)

        @bot.tree.command(name="reload", description="Reload tools and prompt for this agent.")
        async def slash_reload(interaction: Any) -> None:
            await gw.cmd_reload(interaction)

        memory_group = app_commands.Group(name="memory", description="Manage Cud long-term memory.")

        @memory_group.command(name="view", description="View MEMORY.md.")
        async def slash_memory_view(interaction: Any) -> None:
            await gw.cmd_memory_view(interaction)

        @memory_group.command(name="clear", description="Clear MEMORY.md.")
        async def slash_memory_clear(interaction: Any) -> None:
            await gw.cmd_memory_clear(interaction)

        bot.tree.add_command(memory_group)

        token = self.settings.gateway.token
        if not token:
            raise RuntimeError("gateway.token is empty; run `cud gateway setup <agent> discord --token ...`")
        await bot.start(token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_message(content: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Split *content* into chunks that fit within Discord's message limit.

    Prefers splitting on newlines, then spaces, falling back to hard cuts only
    when a single token exceeds the limit.
    """
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at a newline first, then a space.
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit  # Hard cut — no good break point.

        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")

    return chunks

