"""Async task scheduler for periodic TASK.md execution."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from croniter import croniter

from cud.tools.tasks import TaskCard, discover_tasks

log = logging.getLogger(__name__)


class TaskScheduler:
    """Runs inside the gateway's asyncio loop.

    Discovers tasks once at startup.  Sleeps until the next scheduled
    execution or until :meth:`reload` is called.  No polling.
    """

    def __init__(self, gateway: object) -> None:
        # gateway is a DiscordGateway but we avoid the circular import.
        self.gateway = gateway  # type: ignore[assignment]
        self._reload_event = asyncio.Event()

    # -- public api ----------------------------------------------------------

    def reload(self) -> None:
        """Signal the scheduler to rediscover tasks."""
        self._reload_event.set()

    async def run(self) -> None:
        """Main loop — must be launched as an asyncio task."""
        tasks = self._load_tasks()
        while True:
            try:
                task, delay = _next_scheduled(tasks)

                if task is None:
                    # No tasks: sleep indefinitely until reload.
                    await self._reload_event.wait()
                    self._reload_event.clear()
                    tasks = self._load_tasks()
                    continue

                # Sleep until the next task fires OR a reload arrives.
                try:
                    await asyncio.wait_for(self._reload_event.wait(), timeout=delay)
                    # Reload arrived before the task was due.
                    self._reload_event.clear()
                    tasks = self._load_tasks()
                    continue
                except asyncio.TimeoutError:
                    # Timeout expired — time to execute.
                    pass

                await self._execute(task)
                tasks = self._load_tasks()

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler loop error; retrying in 30s")
                await asyncio.sleep(30)
                tasks = self._load_tasks()

    # -- internals -----------------------------------------------------------

    def _load_tasks(self) -> list[TaskCard]:
        tasks_dir = self.gateway.agent_dir / "workspace" / "tasks"
        return [t for t in discover_tasks(tasks_dir) if t.enabled]

    async def _execute(self, task: TaskCard) -> None:
        from cud.gateway._discord_utils import split_message

        thread_id = f"task-{uuid4().hex}"
        runtime = self.gateway.session(thread_id)
        try:
            response = await runtime.invoke(task.prompt, thread_id=thread_id)
            target = await self._resolve_target(task)
            if target is None:
                log.warning("Task '%s': no valid target (channel_id or user_id), skipping output", task.name)
                return
            for chunk in split_message(response.content):
                await target.send(chunk)
        except Exception:
            log.exception("Task '%s' failed", task.name)
        finally:
            self.gateway.sessions.pop(thread_id, None)
            await runtime.aclose()

    async def _resolve_target(self, task: TaskCard) -> object | None:
        """Resolve the Discord destination: channel or DM."""
        if task.channel_id:
            channel = self.gateway.bot.get_channel(task.channel_id)
            if channel is not None:
                return channel
        if task.user_id:
            try:
                user = await self.gateway.bot.fetch_user(task.user_id)
                return user
            except Exception:
                return None
        return None


def _next_scheduled(tasks: list[TaskCard]) -> tuple[TaskCard | None, float]:
    """Return the task with the soonest next run and the delay in seconds."""
    if not tasks:
        return None, 0.0

    now = datetime.now(timezone.utc)
    best_task: TaskCard | None = None
    best_delay = float("inf")

    for task in tasks:
        try:
            cron = croniter(task.schedule, now)
            next_dt = cron.get_next(datetime)
            delay = (next_dt - now).total_seconds()
            if delay < best_delay:
                best_delay = delay
                best_task = task
        except (ValueError, KeyError):
            log.debug("Task '%s': invalid cron expression '%s', skipping", task.name, task.schedule)
            continue

    if best_task is None:
        return None, 0.0
    return best_task, max(best_delay, 0.0)
