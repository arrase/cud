import argparse
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cud.config.paths import agent_home, validate_agent_name
from cud.gateway._discord_utils import send_response, split_message
from cud.gateway.cli import cmd_gateway_start, cmd_gateway_status, cmd_gateway_stop
from cud.gateway.run import run_gateway
from cud.gateway.systemd import (
    control_service,
    get_service_status,
    install_unit,
    journalctl_user,
    remove_unit,
    render_unit,
    service_name,
    systemctl_user,
    uninstall_unit,
    unit_path,
)


def test_split_message_empty() -> None:
    assert split_message("") == [""]


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


@pytest.mark.anyio
async def test_send_response_guild() -> None:
    message = MagicMock()
    message.guild = object()
    message.reply = AsyncMock()
    await send_response(message, "Reply text")
    message.reply.assert_awaited_once_with("Reply text")


@pytest.mark.anyio
async def test_send_response_dm() -> None:
    message = MagicMock()
    message.guild = None
    message.channel.send = AsyncMock()
    await send_response(message, "DM text")
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


def test_install_and_remove_unit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("cud.gateway.systemd.unit_path", lambda agent: tmp_path / f"cud-{agent}.service")
    installed = install_unit("my-agent")
    assert installed.is_file()
    assert "my-agent" in installed.read_text(encoding="utf-8")

    assert remove_unit("my-agent") is True
    assert not installed.exists()
    assert remove_unit("my-agent") is False


def test_uninstall_unit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("cud.gateway.systemd.unit_path", lambda agent: tmp_path / f"cud-{agent}.service")
    install_unit("my-agent")
    mock_systemctl = MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""))
    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: True)
    monkeypatch.setattr("cud.gateway.systemd.systemctl_user", mock_systemctl)

    assert uninstall_unit("my-agent") is True
    assert mock_systemctl.call_count == 3


def test_get_service_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: False)
    with pytest.raises(RuntimeError, match="systemd is not available"):
        get_service_status("my-agent")

    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: True)
    monkeypatch.setattr(
        "cud.gateway.systemd.systemctl_user",
        lambda *_a: subprocess.CompletedProcess(args=[], returncode=0, stdout="active\n", stderr=""),
    )
    assert get_service_status("my-agent") == "active"

    monkeypatch.setattr(
        "cud.gateway.systemd.systemctl_user",
        lambda *_a: subprocess.CompletedProcess(args=[], returncode=3, stdout="failed\n", stderr=""),
    )
    assert get_service_status("my-agent") == "failed"

    monkeypatch.setattr(
        "cud.gateway.systemd.systemctl_user",
        lambda *_a: subprocess.CompletedProcess(args=[], returncode=3, stdout="inactive\n", stderr=""),
    )
    assert get_service_status("my-agent") == "inactive"


def test_control_service(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="Unsupported systemd action"):
        control_service("my-agent", "reload")

    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: False)
    with pytest.raises(RuntimeError, match="systemd is not available"):
        control_service("my-agent", "start")

    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: True)
    monkeypatch.setattr(
        "cud.gateway.systemd.systemctl_user",
        lambda *_a: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    )
    assert control_service("my-agent", "restart") == "Service restarted successfully"

    monkeypatch.setattr(
        "cud.gateway.systemd.systemctl_user",
        lambda *_a: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError, match="Failed to stop service: boom"):
        control_service("my-agent", "stop")


def test_cmd_gateway_start_no_systemd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    agent_home("my-agent").mkdir(parents=True)
    monkeypatch.setattr("cud.gateway.systemd.unit_path", lambda agent: tmp_path / f"cud-{agent}.service")
    monkeypatch.setattr("cud.gateway.systemd.systemd_available", lambda: False)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_start(args) == 0


def test_cmd_gateway_start_nonexistent_agent() -> None:
    args = argparse.Namespace(agent="missing-agent")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        cmd_gateway_start(args)


def test_cmd_gateway_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_systemctl = MagicMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="stopped", stderr="")
    )
    monkeypatch.setattr("cud.gateway.systemd.systemctl_user", mock_systemctl)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_stop(args) == 0


def test_cmd_gateway_status(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_systemctl = MagicMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="active", stderr="")
    )
    mock_journalctl = MagicMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="logs", stderr="")
    )
    monkeypatch.setattr("cud.gateway.systemd.systemctl_user", mock_systemctl)
    monkeypatch.setattr("cud.gateway.systemd.journalctl_user", mock_journalctl)
    args = argparse.Namespace(agent="my-agent")
    assert cmd_gateway_status(args) == 0


def test_run_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_gw_class = MagicMock()
    mock_instance = MagicMock()
    mock_instance.run = AsyncMock()
    mock_gw_class.return_value = mock_instance
    monkeypatch.setattr("cud.gateway.run.DiscordGateway", mock_gw_class)

    run_gateway("test-agent")
    mock_gw_class.assert_called_once_with("test-agent", verbose=False)
    mock_instance.run.assert_awaited_once()

    mock_instance.run = AsyncMock(side_effect=KeyboardInterrupt)
    run_gateway("test-agent", verbose=True)


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["../../tmp/evil", "a/../../b", "..", "agent\nExecStartPre=/tmp/x"])
def test_systemd_helpers_validate_the_agent_name(name: str) -> None:
    """Regression: the raw name was interpolated into a path that install_unit
    then mkdir'd, so a traversal escaped ~/.config/systemd."""
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


def test_start_reports_daemon_reload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_home("solo").mkdir(parents=True)
    monkeypatch.setattr("cud.gateway.cli.systemd.install_unit", MagicMock())
    monkeypatch.setattr("cud.gateway.cli.systemd.systemd_available", lambda: True)
    monkeypatch.setattr(
        "cud.gateway.cli.systemd.systemctl_user",
        MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="bus error")),
    )
    assert cmd_gateway_start(argparse.Namespace(agent="solo")) == 1


def test_systemctl_and_journalctl_user(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr("cud.gateway.systemd.subprocess.run", mock_run)

    assert systemctl_user("status", "cud-gateway-solo.service").stdout == "ok"
    assert journalctl_user("solo", lines=20).stdout == "ok"
    assert mock_run.call_count == 2
