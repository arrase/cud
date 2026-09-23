import argparse
from pathlib import Path

import pytest

from cud.agent.cli import (
    cmd_agent_config,
    cmd_agent_create,
    cmd_agent_delete,
    cmd_agent_list,
)
from cud.cli import build_parser, cmd_completion, main
from cud.config.paths import agent_home
from cud.config.settings import load_settings
from cud.gateway.cli import cmd_gateway_setup


def test_build_parser() -> None:
    parser = build_parser()
    assert parser.prog == "cud"


def test_cmd_completion() -> None:
    assert cmd_completion(argparse.Namespace(shell="bash")) == 0
    assert cmd_completion(argparse.Namespace(shell="zsh")) == 0


def test_main_completion() -> None:
    assert main(["completion", "bash"]) == 0


def test_agent_cli_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    monkeypatch.setattr("cud.agent.cli.systemd.systemd_available", lambda: False)

    # Create agent via CLI
    create_args = argparse.Namespace(name="agent-cli-test", template="default")
    assert cmd_agent_create(create_args) == 0

    # List agents via CLI
    list_args = argparse.Namespace(verbose=False)
    assert cmd_agent_list(list_args) == 0

    list_args_verbose = argparse.Namespace(verbose=True)
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

    # Delete agent via CLI with --yes
    delete_yes = argparse.Namespace(name="agent-cli-test", yes=True)
    assert cmd_agent_delete(delete_yes) == 0


def test_gateway_setup_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
