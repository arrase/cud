import argparse
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cud.gateway._discord_utils import send_response, split_message
from cud.gateway.cli import cmd_gateway_start, cmd_gateway_status, cmd_gateway_stop
from cud.gateway.run import _run_and_cleanup, run_gateway
from cud.gateway.scheduler import TaskScheduler, _next_scheduled
from cud.gateway.systemd import (
    install_unit,
    remove_unit,
    render_unit,
    service_name,
    unit_path,
)
from cud.tools.tasks import TaskCard


def test_next_scheduled_empty() -> None:
    task, delay = _next_scheduled([])
    assert task is None
    assert delay == 0.0


def test_next_scheduled_valid(tmp_path: Path) -> None:
    t1 = TaskCard(
        name="frequent",
        description="",
        schedule="* * * * *",
        channel_id=None,
        user_id=None,
        enabled=True,
        path=tmp_path / "1",
        prompt="p1",
    )
    t2 = TaskCard(
        name="infrequent",
        description="",
        schedule="0 0 1 1 *",
        channel_id=None,
        user_id=None,
        enabled=True,
        path=tmp_path / "2",
        prompt="p2",
    )
    best_task, delay = _next_scheduled([t2, t1])
    assert best_task is t1
    assert 0 <= delay <= 60


def test_next_scheduled_invalid_cron(tmp_path: Path) -> None:
    invalid = TaskCard(
        name="bad",
        description="",
        schedule="not a cron",
        channel_id=None,
        user_id=None,
        enabled=True,
        path=tmp_path / "bad",
        prompt="bad",
    )
    valid = TaskCard(
        name="good",
        description="",
        schedule="* * * * *",
        channel_id=None,
        user_id=None,
        enabled=True,
        path=tmp_path / "good",
        prompt="good",
    )
    best_task, delay = _next_scheduled([invalid, valid])
    assert best_task is valid
    assert 0 <= delay <= 60


def test_task_scheduler_reload() -> None:
    mock_gateway = MagicMock()
    scheduler = TaskScheduler(mock_gateway)
    assert not scheduler._reload_event.is_set()
    scheduler.reload()
    assert scheduler._reload_event.is_set()


def test_task_scheduler_load_tasks(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "workspace" / "tasks"
    tasks_dir.mkdir(parents=True)
    t1_dir = tasks_dir / "enabled_task"
    t1_dir.mkdir()
    (t1_dir / "TASK.md").write_text(
        "---\nschedule: '* * * * *'\nenabled: true\n---\nPrompt 1\n", encoding="utf-8"
    )
    t2_dir = tasks_dir / "disabled_task"
    t2_dir.mkdir()
    (t2_dir / "TASK.md").write_text(
        "---\nschedule: '* * * * *'\nenabled: false\n---\nPrompt 2\n", encoding="utf-8"
    )

    mock_gateway = MagicMock()
    mock_gateway.agent_dir = tmp_path
    scheduler = TaskScheduler(mock_gateway)
    loaded = scheduler._load_tasks()
    assert len(loaded) == 1
    assert loaded[0].name == "enabled_task"


def test_split_message_short() -> None:
    content = "A brief notification."
    assert split_message(content, limit=100) == [content]


def test_split_message_newline() -> None:
    line1 = "Line one of content"
    line2 = "Line two of content"
    content = f"{line1}\n{line2}"
    chunks = split_message(content, limit=25)
    assert chunks == [line1, line2]


def test_split_message_space() -> None:
    content = "First sentence here. Second sentence continues."
    chunks = split_message(content, limit=25)
    assert chunks == ["First sentence here.", "Second sentence", "continues."]
    assert all(len(c) <= 25 for c in chunks)


def test_split_message_hard_cut() -> None:
    content = "A" * 50
    chunks = split_message(content, limit=20)
    assert chunks == ["A" * 20, "A" * 20, "A" * 10]


def test_send_response_guild() -> None:
    message = MagicMock()
    message.guild = object()
    message.reply = AsyncMock()
    asyncio.run(send_response(message, "Reply text"))
    message.reply.assert_awaited_once_with("Reply text")


def test_send_response_dm() -> None:
    message = MagicMock()
    message.guild = None
    message.channel.send = AsyncMock()
    asyncio.run(send_response(message, "DM text"))
    message.channel.send.assert_awaited_once_with("DM text")


def test_service_name() -> None:
    assert service_name("alpha") == "cud-gateway-alpha.service"


def test_unit_path() -> None:
    expected = Path("~/.config/systemd/user/cud-gateway-alpha.service").expanduser()
    assert unit_path("alpha") == expected


def test_render_unit() -> None:
    unit = render_unit("my-agent")
    assert "Description=Cud Gateway - Agent: my-agent" in unit
    assert "ExecStart=" in unit
    assert "cud gateway run my-agent" in unit


def test_install_and_remove_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "cud.gateway.systemd.unit_path", lambda agent: tmp_path / f"cud-{agent}.service"
    )
    installed = install_unit("my-agent")
    assert installed.is_file()
    assert "my-agent" in installed.read_text(encoding="utf-8")

    remove_unit("my-agent")
    assert not installed.exists()


def test_cmd_gateway_start_no_systemd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "cud.gateway.systemd.unit_path", lambda agent: tmp_path / f"cud-{agent}.service"
    )
    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: False)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_start(args) == 0


def test_cmd_gateway_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_systemctl = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="stopped", stderr=""
        )
    )
    monkeypatch.setattr("cud.gateway.systemd.systemctl_user", mock_systemctl)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_stop(args) == 0


def test_cmd_gateway_status(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_systemctl = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="active", stderr=""
        )
    )
    mock_journalctl = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="logs", stderr=""
        )
    )
    monkeypatch.setattr("cud.gateway.systemd.systemctl_user", mock_systemctl)
    monkeypatch.setattr("cud.gateway.systemd.journalctl_user", mock_journalctl)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_status(args) == 0


def test_gateway_run_and_cleanup() -> None:
    mock_gw = MagicMock()
    mock_gw.run = AsyncMock()
    mock_gw.aclose_sessions = AsyncMock()
    asyncio.run(_run_and_cleanup(mock_gw))
    mock_gw.run.assert_awaited_once()
    mock_gw.aclose_sessions.assert_awaited_once()


def test_run_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_gw_class = MagicMock()
    mock_instance = MagicMock()
    mock_instance.run = AsyncMock()
    mock_instance.aclose_sessions = AsyncMock()
    mock_gw_class.return_value = mock_instance
    monkeypatch.setattr("cud.gateway.run.DiscordGateway", mock_gw_class)

    run_gateway("test-agent")
    mock_gw_class.assert_called_once_with("test-agent", verbose=False)
    mock_instance.run.assert_awaited_once()
    mock_instance.aclose_sessions.assert_awaited_once()


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["../../tmp/evil", "a/../../b", "..", "agent\nExecStartPre=/tmp/x"]
)
def test_systemd_helpers_validate_the_agent_name(name: str) -> None:
    """Regression: the raw name was interpolated into a path that install_unit
    then mkdir'd, so a traversal escaped ~/.config/systemd."""
    from cud.config.paths import validate_agent_name

    for fn in (service_name, unit_path, render_unit):
        with pytest.raises(ValueError, match="agent name must start with"):
            fn(name)
    with pytest.raises(ValueError, match="agent name must start with"):
        install_unit(name)
    with pytest.raises(ValueError, match="agent name must start with"):
        remove_unit(name)
    assert validate_agent_name("ok-agent") == "ok-agent"


def test_render_unit_keeps_token_out_of_the_unit_file() -> None:
    unit = render_unit("solo")
    assert "gateway.token" not in unit
    assert "ExecStart=" in unit
    assert "solo" in unit


def test_split_message_chunks_are_reassemblable() -> None:
    """No content may be lost: whitespace is normalised at split points, so
    compare with whitespace removed."""
    for text in ["a" * 5000, "line\n" * 900, "a\n" + "b" * 3000, "word " * 1200]:
        chunks = split_message(text)
        assert all(chunks), "no empty chunks"
        assert all(len(c) <= 2000 for c in chunks)
        squashed = lambda s: "".join(s.split())  # noqa: E731
        assert squashed("".join(chunks)) == squashed(text)


def test_stop_and_status_require_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: without systemctl these printed a raw FileNotFoundError."""
    monkeypatch.setattr("cud.gateway.cli.systemd.systemd_available", lambda: False)
    for cmd in (cmd_gateway_stop, cmd_gateway_status):
        assert cmd(argparse.Namespace(agent="solo")) == 1


def test_status_treats_unit_not_found_as_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = MagicMock(returncode=3, stdout="", stderr="not found")
    monkeypatch.setattr("cud.gateway.cli.systemd.systemd_available", lambda: True)
    monkeypatch.setattr("cud.gateway.cli.systemd.systemctl_user", MagicMock(return_value=proc))
    monkeypatch.setattr("cud.gateway.cli.systemd.journalctl_user", MagicMock(return_value=proc))
    assert cmd_gateway_status(argparse.Namespace(agent="solo")) == 0

    proc.returncode = 4
    assert cmd_gateway_status(argparse.Namespace(agent="solo")) == 4


def test_start_reports_daemon_reload_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cud.gateway.cli.systemd.install_unit", MagicMock())
    monkeypatch.setattr("cud.gateway.cli.systemd.systemd_available", lambda: True)
    monkeypatch.setattr(
        "cud.gateway.cli.systemd.systemctl_user",
        MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="bus error")),
    )
    assert cmd_gateway_start(argparse.Namespace(agent="solo")) == 1
