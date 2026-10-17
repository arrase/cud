"""Async task scheduler for periodic TASK.md execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import discord
from discord.abc import Messageable
from discord.ext import commands

from cud.agent.runtime import AgentRuntime
from cud.gateway._discord_utils import split_message
from cud.tools.tasks import TaskCard, discover_tasks, next_run

_log = logging.getLogger(__name__)


class TaskScheduler:
    """Runs inside the gateway's asyncio loop.

    Discovers tasks once at startup.  Sleeps until the next scheduled
    execution or until :meth:`reload` is called.  No polling.
    """

    def __init__(
        self,
        agent_dir: Path,
        get_bot: Callable[[], commands.Bot | None] = lambda: None,
    ) -> None:
        self.agent_dir = agent_dir
        self._get_bot = get_bot
        self._reload_event = asyncio.Event()

    # -- public api ----------------------------------------------------------

    def reload(self) -> None:
        """Signal the scheduler to rediscover tasks."""
        self._reload_event.set()

    async def run(self) -> None:
        """Main loop — must be launched as an asyncio task."""
        while True:
            try:
                self._reload_event.clear()
                tasks = self._load_tasks()
                task, delay = _next_scheduled(tasks)

                if task is None:
                    # No tasks: sleep indefinitely until reload.
                    await self._reload_event.wait()
                    continue

                # Sleep until the next task fires OR a reload arrives.
                try:
                    await asyncio.wait_for(self._reload_event.wait(), timeout=delay)
                    continue
                except TimeoutError:
                    await self._execute(task)

            except Exception:
                _log.exception("Scheduler loop error; retrying in 30s")
                await asyncio.sleep(30)

    # -- internals -----------------------------------------------------------

    def _load_tasks(self) -> list[TaskCard]:
        tasks_dir = self.agent_dir / "workspace" / "tasks"
        return [t for t in discover_tasks(tasks_dir) if t.enabled]

    async def _execute(self, task: TaskCard) -> None:
        # Resolve the destination first: a cache miss would otherwise burn a
        # full agent run and then throw the result away.
        target = await self._resolve_target(task)
        if target is None:
            _log.warning("Task '%s': no valid target (channel_id or user_id), skipping", task.name)
            return

        thread_id = f"task-{uuid4().hex}"
        try:
            async with AgentRuntime(self.agent_dir, thread_id=thread_id) as runtime:
                response = await runtime.invoke(task.prompt)
            for chunk in split_message(response.content):
                await target.send(chunk)
        except Exception:
            _log.exception("Task '%s' failed", task.name)

    async def _resolve_target(self, task: TaskCard) -> Messageable | None:
        """Resolve the Discord destination: channel or DM."""
        bot = self._get_bot()
        if bot is None:
            return None
        if task.channel_id is not None:
            try:
                channel = bot.get_channel(task.channel_id) or await bot.fetch_channel(task.channel_id)
            except (discord.NotFound, discord.HTTPException):
                _log.warning("Task '%s': cannot fetch channel %s", task.name, task.channel_id, exc_info=True)
                channel = None
            # CategoryChannel and friends are not Messageable; sending would AttributeError.
            if isinstance(channel, discord.abc.Messageable):
                return channel
            _log.warning("Task '%s': channel %s cannot receive messages", task.name, task.channel_id)
        if task.user_id is not None:
            try:
                return await bot.fetch_user(task.user_id)
            except (discord.NotFound, discord.HTTPException):
                _log.warning("Task '%s': cannot DM user %s", task.name, task.user_id, exc_info=True)
        return None


def _next_scheduled(tasks: list[TaskCard]) -> tuple[TaskCard | None, float]:
    """Return the task with the soonest next run and the delay in seconds."""
    if not tasks:
        return None, 0.0

    now = datetime.now(UTC)
    best_task: TaskCard | None = None
    best_delay = float("inf")

    for task in tasks:
        upcoming = next_run(task.schedule, now)
        if upcoming is None:
            _log.warning("Task '%s': invalid cron expression %r, skipping", task.name, task.schedule)
            continue
        delay = (upcoming - now).total_seconds()
        if delay < best_delay:
            best_delay = delay
            best_task = task

    if best_task is None:
        return None, 0.0
    return best_task, max(best_delay, 0.0)
