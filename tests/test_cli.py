import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cud.agent.cli import (
    cmd_agent_config,
    cmd_agent_create,
    cmd_agent_delete,
    cmd_agent_list,
    register_agent_commands,
)
from cud.cli import build_parser, cmd_completion, main
from cud.config.paths import agent_home
from cud.config.settings import load_settings
from cud.gateway.cli import (
    cmd_gateway_run,
    cmd_gateway_setup,
    cmd_gateway_start,
    cmd_gateway_stop,
    register_gateway_commands,
)
from cud.tui.cli import cmd_tui, register_tui_commands


def test_build_parser() -> None:
    parser = build_parser()
    assert parser.prog == "cud"


def test_cmd_completion() -> None:
    assert cmd_completion(argparse.Namespace(shell="bash")) == 0
    assert cmd_completion(argparse.Namespace(shell="zsh")) == 0


def test_main_completion() -> None:
    assert main(["completion", "bash"]) == 0


def test_main_keyboard_interrupt() -> None:
    with patch("cud.cli.build_parser") as mock_bp:
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.func.side_effect = KeyboardInterrupt()
        mock_parser.parse_args.return_value = mock_args
        mock_bp.return_value = mock_parser
        assert main(["completion", "bash"]) == 130


def test_main_exception() -> None:
    with patch("cud.cli.build_parser") as mock_bp:
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.func.side_effect = RuntimeError("Something went wrong")
        mock_parser.parse_args.return_value = mock_args
        mock_bp.return_value = mock_parser
        assert main(["completion", "bash"]) == 1


def test_agent_cli_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    monkeypatch.setattr("cud.agent.cli.systemd.systemd_available", lambda: False)

    # Empty list
    assert cmd_agent_list(argparse.Namespace(verbose=False)) == 0

    # Create agent via CLI
    create_args = argparse.Namespace(name="agent-cli-test", template="default")
    assert cmd_agent_create(create_args) == 0

    # List agents via CLI
    list_args = argparse.Namespace(verbose=False)
    assert cmd_agent_list(list_args) == 0

    list_args_verbose = argparse.Namespace(verbose=True)
    assert cmd_agent_list(list_args_verbose) == 0

    # Create a corrupted agent without settings.yaml for verbose listing test
    corrupt_agent = tmp_path / "agents" / "corrupted-agent"
    corrupt_agent.mkdir(parents=True)
    assert cmd_agent_list(list_args_verbose) == 0

    # Configure agent via CLI
    config_args = argparse.Namespace(
        name="agent-cli-test",
        model="llama3.2:1b",
        context_window=16384,
        temperature=0.5,
        allow_traversal=False,
    )
    assert cmd_agent_config(config_args) == 0

    settings = load_settings(agent_home("agent-cli-test"))
    assert settings.model.name == "llama3.2:1b"
    assert settings.model.context_window == 16384
    assert settings.model.temperature == 0.5
    assert settings.runtime.allow_traversal is False

    # Delete agent via CLI without --yes
    delete_no_yes = argparse.Namespace(name="agent-cli-test", yes=False)
    assert cmd_agent_delete(delete_no_yes) == 2

    # Delete agent via CLI with systemd available
    monkeypatch.setattr("cud.agent.cli.systemd.systemd_available", lambda: True)
    monkeypatch.setattr("cud.agent.cli.systemd.stop_service", MagicMock())
    monkeypatch.setattr("cud.agent.cli.systemd.disable_service", MagicMock())
    monkeypatch.setattr("cud.agent.cli.systemd.remove_unit", MagicMock())
    monkeypatch.setattr("cud.agent.cli.systemd.systemctl_user", MagicMock())

    delete_yes = argparse.Namespace(name="agent-cli-test", yes=True)
    assert cmd_agent_delete(delete_yes) == 0


def test_gateway_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_args = argparse.Namespace(name="gw-agent", template="default")
    cmd_agent_create(create_args)

    setup_args = argparse.Namespace(
        agent="gw-agent", platform="discord", token="bot_token_123"
    )
    assert cmd_gateway_setup(setup_args) == 0

    settings = load_settings(agent_home("gw-agent"))
    assert settings.gateway.provider == "discord"
    assert settings.gateway.token == "bot_token_123"

    # Gateway setup for telegram (platform != discord)
    setup_tg = argparse.Namespace(
        agent="gw-agent", platform="telegram", token="bot_token_tg"
    )
    assert cmd_gateway_setup(setup_tg) == 0

    # Gateway run
    with patch("cud.gateway.cli.run_gateway") as mock_rg:
        assert cmd_gateway_run(argparse.Namespace(agent="gw-agent", verbose=True)) == 0
        mock_rg.assert_called_once_with("gw-agent", verbose=True)

    # Gateway start with systemd
    mock_proc = MagicMock(returncode=0, stdout="enabled", stderr="")
    monkeypatch.setattr("cud.gateway.cli.systemd.systemd_available", lambda: True)
    monkeypatch.setattr("cud.gateway.cli.systemd.install_unit", MagicMock())
    monkeypatch.setattr("cud.gateway.cli.systemd.systemctl_user", MagicMock(return_value=mock_proc))
    assert cmd_gateway_start(argparse.Namespace(agent="gw-agent")) == 0


def test_tui_cli() -> None:
    with patch("cud.tui.cli.run_tui", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = 0
        args = argparse.Namespace(agent="agent1", thread_id="th1")
        assert cmd_tui(args) == 0


def test_register_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_agent_commands(sub)
    register_gateway_commands(sub)
    register_tui_commands(sub)

    args_agent = parser.parse_args(["agent", "list"])
    assert hasattr(args_agent, "func")
    args_gw = parser.parse_args(["gateway", "run", "gw-agent"])
    assert hasattr(args_gw, "func")
    args_tui = parser.parse_args(["tui", "agent-x"])
    assert args_tui.agent == "agent-x"
