from pathlib import Path

import pytest

from cud.config.paths import (
    agent_home,
    agents_root,
    cud_home,
    validate_agent_name,
)


def test_cud_home_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUD_HOME", raising=False)
    assert cud_home() == Path("~/.cud").expanduser()


def test_cud_home_custom(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    assert cud_home() == tmp_path


def test_agents_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    assert agents_root() == tmp_path / "agents"


@pytest.mark.parametrize(
    "name",
    [
        "agent",
        "agent-1",
        "agent_2",
        "agent.3",
        "Agent",
        "007",
        "a" * 64,
    ],
)
def test_validate_agent_name_valid(name: str) -> None:
    assert validate_agent_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "-invalid",
        ".invalid",
        "_invalid",
        "invalid name",
        "invalid/name",
        "agent@name",
        "a" * 65,
    ],
)
def test_validate_agent_name_invalid(name: str) -> None:
    with pytest.raises(
        ValueError, match="agent name must start with an alphanumeric character"
    ):
        validate_agent_name(name)


def test_agent_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    assert agent_home("test-agent") == tmp_path / "agents" / "test-agent"


def test_agent_home_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        agent_home("../invalid")
