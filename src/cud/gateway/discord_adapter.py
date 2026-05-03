"""Discord gateway adapter.

The module imports discord.py lazily so administrative CLI and tests can run
without gateway dependencies installed.
"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import load_settings, save_settings
from cud.gateway.progress import ProgressBubble
from cud.gateway.threading import discord_thread_id
from cud.tools.memory import MemoryStore


@dataclass(slots=True)
class SessionState:
    runtime: AgentRuntime
    yolo: bool = False
    pending_decision: Any = None
    progress: ProgressBubble = field(default_factory=ProgressBubble)


class DiscordGateway:
    def __init__(self, agent: str, *, verbose: bool = False):
        self.agent = agent
        self.agent_dir = agent_home(agent)
        self.settings = load_settings(self.agent_dir)
        self.verbose = verbose
        self.sessions: dict[str, SessionState] = {}

    def session(self, thread_id: str) -> SessionState:
        state = self.sessions.get(thread_id)
        if state is None:
            state = SessionState(runtime=AgentRuntime(self.agent_dir, thread_id=thread_id))
            self.sessions[thread_id] = state
        return state

    async def run(self) -> None:
        try:
            import discord
            from discord import app_commands
            from discord.ext import commands
        except ImportError as exc:
            raise RuntimeError("discord.py is required for `cud gateway run`") from exc

        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!cud ", intents=intents)

        @bot.event
        async def on_ready() -> None:
            await bot.tree.sync()
            if self.verbose:
                print(f"Discord gateway ready as {bot.user}")

        @bot.event
        async def on_message(message: Any) -> None:
            if message.author.bot:
                return
            if not message.content:
                return
            thread_id = discord_thread_id(message)
            state = self.session(thread_id)
            try:
                async with message.channel.typing():
                    response = await asyncio.to_thread(state.runtime.invoke, message.content, thread_id=thread_id)
                state.pending_decision = response.raw if response.interrupted else None
                await message.reply(response.content[:1900])
            except Exception as exc:
                traceback.print_exc()
                await message.reply(f"Cud error: `{type(exc).__name__}: {str(exc)[:1600]}`")

        @bot.tree.command(name="new", description="Start a new Cud session in this Discord thread.")
        async def new_session(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            old = self.sessions.pop(thread_id, None)
            if old:
                old.runtime.close()
            self.session(thread_id)
            await interaction.response.send_message("New Cud session started.", ephemeral=True)

        @bot.tree.command(name="model", description="Temporarily switch this agent's configured model.")
        @app_commands.describe(model_name="Ollama model id")
        async def model(interaction: Any, model_name: str) -> None:
            self.settings.model.name = model_name
            save_settings(self.agent_dir, self.settings)
            self._reload_sessions()
            await interaction.response.send_message(f"Model set to `{model_name}`.", ephemeral=True)

        @bot.tree.command(name="yolo", description="Toggle approval prompts for this Discord thread.")
        async def yolo(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            state = self.session(thread_id)
            state.yolo = not state.yolo
            state.runtime.close()
            state.runtime = AgentRuntime(self.agent_dir, thread_id=thread_id, yolo=state.yolo)
            await interaction.response.send_message(f"YOLO is now `{state.yolo}`.", ephemeral=True)

        @bot.tree.command(name="compress", description="Force context compaction on the current thread.")
        async def compress(interaction: Any, focus_topic: str | None = None) -> None:
            await interaction.response.send_message(
                "Compaction will run on the next model-managed context window.", ephemeral=True
            )

        @bot.tree.command(name="usage", description="Show Cud runtime usage summary.")
        async def usage(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            state = self.session(thread_id)
            await interaction.response.send_message(
                f"thread_id=`{thread_id}` prompt_hash=`{state.runtime.prompt.system_prompt_hash[:12]}`",
                ephemeral=True,
            )

        @bot.tree.command(name="undo", description="Remove the last exchange from this thread.")
        async def undo(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            result = self.session(thread_id).runtime.undo_last_exchange(thread_id=thread_id)
            await interaction.response.send_message(result, ephemeral=True)

        @bot.tree.command(name="reload-tools", description="Reload tools and prompt for this agent.")
        async def reload_tools(interaction: Any) -> None:
            self._reload_sessions()
            await interaction.response.send_message("Tools reloaded.", ephemeral=True)

        @bot.tree.command(name="reload-mcp", description="Reload MCP tools and prompt for this agent.")
        async def reload_mcp(interaction: Any) -> None:
            self._reload_sessions()
            await interaction.response.send_message("MCP reloaded.", ephemeral=True)

        @bot.tree.command(name="approve", description="Approve the latest pending tool request.")
        async def approve(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            state = self.session(thread_id)
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                response = await asyncio.to_thread(
                    state.runtime.resume_approval,
                    thread_id=thread_id,
                    approve=True,
                )
                state.pending_decision = response.raw if response.interrupted else None
                await interaction.followup.send(response.content[:1900], ephemeral=False)
            except Exception as exc:
                traceback.print_exc()
                await interaction.followup.send(
                    f"Cud error while approving: `{type(exc).__name__}: {str(exc)[:1500]}`",
                    ephemeral=True,
                )

        @bot.tree.command(name="deny", description="Deny the latest pending tool request.")
        async def deny(interaction: Any) -> None:
            thread_id = discord_thread_id(interaction.channel)
            state = self.session(thread_id)
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                response = await asyncio.to_thread(
                    state.runtime.resume_approval,
                    thread_id=thread_id,
                    approve=False,
                    message="User denied the requested tool call from Discord.",
                )
                state.pending_decision = response.raw if response.interrupted else None
                await interaction.followup.send(response.content[:1900], ephemeral=False)
            except Exception as exc:
                traceback.print_exc()
                await interaction.followup.send(
                    f"Cud error while denying: `{type(exc).__name__}: {str(exc)[:1500]}`",
                    ephemeral=True,
                )

        memory_group = app_commands.Group(name="memory", description="Manage Cud long-term memory.")

        @memory_group.command(name="view", description="View MEMORY.md.")
        async def memory_view(interaction: Any) -> None:
            content = MemoryStore(self.agent_dir / "MEMORY.md").read()
            await interaction.response.send_message(content[:1900] or "Memory is empty.", ephemeral=True)

        @memory_group.command(name="clear", description="Clear MEMORY.md.")
        async def memory_clear(interaction: Any) -> None:
            MemoryStore(self.agent_dir / "MEMORY.md").clear()
            self._reload_sessions()
            await interaction.response.send_message("Memory cleared.", ephemeral=True)

        bot.tree.add_command(memory_group)

        token = self.settings.gateway.token
        if not token:
            raise RuntimeError("gateway.token is empty; run `cud gateway setup <agent> discord --token ...`")
        await bot.start(token)

    def _reload_sessions(self) -> None:
        for state in self.sessions.values():
            state.runtime.reload()


def configured_token(agent_dir: Path) -> str:
    return load_settings(agent_dir).gateway.token
