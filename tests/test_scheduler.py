import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic.root_model
import pytest

from cud.gateway.scheduler import TaskScheduler, _next_scheduled
from cud.tools.tasks import TaskCard


def test_next_scheduled_empty() -> None:
    task, delay = _next_scheduled([])
    assert task is None
    assert delay == 0.0


def test_next_scheduled_valid(tmp_path: Path) -> None:
    t1 = TaskCard(
        name="task1",
        description="",
        schedule="* * * * *",
        channel_id=123,
        user_id=None,
        enabled=True,
        path=tmp_path / "1",
        prompt="run 1",
    )
    t2 = TaskCard(
        name="task2",
        description="",
        schedule="0 0 1 1 *",
        channel_id=456,
        user_id=None,
        enabled=True,
        path=tmp_path / "2",
        prompt="run 2",
    )
    best_task, delay = _next_scheduled([t2, t1])
    assert best_task is t1
    assert 0.0 <= delay <= 60.0


def test_next_scheduled_invalid_cron(tmp_path: Path) -> None:
    invalid = TaskCard(
        name="bad",
        description="",
        schedule="not_a_valid_cron",
        channel_id=None,
        user_id=None,
        enabled=True,
        path=tmp_path / "bad",
        prompt="bad",
    )
    task, delay = _next_scheduled([invalid])
    assert task is None
    assert delay == 0.0


def test_scheduler_reload() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    assert not scheduler._reload_event.is_set()
    scheduler.reload()
    assert scheduler._reload_event.is_set()


def test_scheduler_load_tasks(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "workspace" / "tasks"
    tasks_dir.mkdir(parents=True)
    t1 = tasks_dir / "t1"
    t1.mkdir()
    (t1 / "TASK.md").write_text("---\nschedule: '* * * * *'\nenabled: true\n---\nPrompt 1\n", encoding="utf-8")
    t2 = tasks_dir / "t2"
    t2.mkdir()
    (t2 / "TASK.md").write_text("---\nschedule: '* * * * *'\nenabled: false\n---\nPrompt 2\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.agent_dir = tmp_path
    scheduler = TaskScheduler(gateway)
    tasks = scheduler._load_tasks()
    assert len(tasks) == 1
    assert tasks[0].name == "t1"


@pytest.mark.anyio
async def test_resolve_target_channel() -> None:
    gateway = MagicMock()
    channel_mock = MagicMock()
    gateway.bot.get_channel.return_value = channel_mock
    scheduler = TaskScheduler(gateway)

    task = TaskCard(
        name="t", description="", schedule="*", channel_id=999, user_id=None,
        enabled=True, path=Path("/t"), prompt="p"
    )
    target = await scheduler._resolve_target(task)
    assert target is channel_mock
    gateway.bot.get_channel.assert_called_once_with(999)


@pytest.mark.anyio
async def test_resolve_target_user() -> None:
    gateway = MagicMock()
    gateway.bot.get_channel.return_value = None
    user_mock = MagicMock()
    gateway.bot.fetch_user = AsyncMock(return_value=user_mock)
    scheduler = TaskScheduler(gateway)

    task = TaskCard(
        name="t", description="", schedule="*", channel_id=999, user_id=888,
        enabled=True, path=Path("/t"), prompt="p"
    )
    target = await scheduler._resolve_target(task)
    assert target is user_mock
    gateway.bot.fetch_user.assert_awaited_once_with(888)


@pytest.mark.anyio
async def test_resolve_target_user_exception() -> None:
    gateway = MagicMock()
    gateway.bot.get_channel.return_value = None
    gateway.bot.fetch_user = AsyncMock(side_effect=RuntimeError("user not found"))
    scheduler = TaskScheduler(gateway)

    task = TaskCard(
        name="t", description="", schedule="*", channel_id=None, user_id=888,
        enabled=True, path=Path("/t"), prompt="p"
    )
    target = await scheduler._resolve_target(task)
    assert target is None


@pytest.mark.anyio
async def test_resolve_target_none() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    task = TaskCard(
        name="t", description="", schedule="*", channel_id=None, user_id=None,
        enabled=True, path=Path("/t"), prompt="p"
    )
    target = await scheduler._resolve_target(task)
    assert target is None


@pytest.mark.anyio
async def test_execute_success() -> None:
    gateway = MagicMock()
    runtime_mock = AsyncMock()
    runtime_mock.invoke.return_value = MagicMock(content="Hello from scheduler!")
    gateway.session.return_value = runtime_mock
    gateway.sessions = {"some_thread": runtime_mock}

    scheduler = TaskScheduler(gateway)
    target_mock = AsyncMock()
    scheduler._resolve_target = AsyncMock(return_value=target_mock)

    task = TaskCard(
        name="t", description="", schedule="*", channel_id=1, user_id=None,
        enabled=True, path=Path("/t"), prompt="do it"
    )
    await scheduler._execute(task)

    runtime_mock.invoke.assert_awaited_once()
    target_mock.send.assert_awaited_once_with("Hello from scheduler!")
    runtime_mock.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_execute_no_target() -> None:
    gateway = MagicMock()
    runtime_mock = AsyncMock()
    runtime_mock.invoke.return_value = MagicMock(content="Hello")
    gateway.session.return_value = runtime_mock
    gateway.sessions = {}

    scheduler = TaskScheduler(gateway)
    scheduler._resolve_target = AsyncMock(return_value=None)

    task = TaskCard(
        name="t", description="", schedule="*", channel_id=None, user_id=None,
        enabled=True, path=Path("/t"), prompt="do it"
    )
    await scheduler._execute(task)

    runtime_mock.invoke.assert_awaited_once()
    runtime_mock.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_execute_invoke_exception() -> None:
    gateway = MagicMock()
    runtime_mock = AsyncMock()
    runtime_mock.invoke.side_effect = RuntimeError("invoke failed")
    gateway.session.return_value = runtime_mock
    gateway.sessions = {}

    scheduler = TaskScheduler(gateway)
    task = TaskCard(
        name="t", description="", schedule="*", channel_id=1, user_id=None,
        enabled=True, path=Path("/t"), prompt="do it"
    )
    await scheduler._execute(task)

    runtime_mock.invoke.assert_awaited_once()
    runtime_mock.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_run_no_tasks_then_reload() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    scheduler._load_tasks = MagicMock(return_value=[])

    call_count = 0

    async def fake_wait() -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return True
        raise asyncio.CancelledError()

    scheduler._reload_event.wait = fake_wait

    with pytest.raises(asyncio.CancelledError):
        await scheduler.run()

    assert call_count == 2


@pytest.mark.anyio
async def test_run_timeout_executes_task() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    task = TaskCard(
        name="t", description="", schedule="*", channel_id=1, user_id=None,
        enabled=True, path=Path("/t"), prompt="do it"
    )
    scheduler._load_tasks = MagicMock(return_value=[task])
    scheduler._execute = AsyncMock()

    call_count = 0

    def fake_next_scheduled(tasks):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return task, 0.001
        raise asyncio.CancelledError()

    with patch("cud.gateway.scheduler._next_scheduled", side_effect=fake_next_scheduled):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run()

    scheduler._execute.assert_awaited_once_with(task)


@pytest.mark.anyio
async def test_run_reload_before_timeout() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    task = TaskCard(
        name="t", description="", schedule="*", channel_id=1, user_id=None,
        enabled=True, path=Path("/t"), prompt="do it"
    )
    scheduler._load_tasks = MagicMock(return_value=[task])
    scheduler._execute = AsyncMock()

    scheduler.reload()  # sets _reload_event so wait_for returns immediately

    call_count = 0

    def fake_next_scheduled(tasks):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return task, 100.0
        raise asyncio.CancelledError()

    with patch("cud.gateway.scheduler._next_scheduled", side_effect=fake_next_scheduled):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run()

    scheduler._execute.assert_not_called()


@pytest.mark.anyio
async def test_run_loop_exception_retry() -> None:
    gateway = MagicMock()
    scheduler = TaskScheduler(gateway)
    scheduler._load_tasks = MagicMock(side_effect=[[], asyncio.CancelledError()])

    with patch("cud.gateway.scheduler._next_scheduled", side_effect=RuntimeError("unexpected")):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                await scheduler.run()
            mock_sleep.assert_awaited_once_with(30)
