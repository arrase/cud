import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cud.config.scaffold import create_agent
from cud.tools.mcp import (
    MCPConfig,
    _build_stdio_server_config,
    _filter_tools,
    cmd_mcp_add,
    cmd_mcp_list,
    load_mcp_config,
    load_mcp_tools_for_servers,
    load_mcp_tools_managed,
    register_mcp_commands,
    save_mcp_config,
)


@dataclass
class DummyTool:
    name: str


def test_load_mcp_config_missing(tmp_path: Path) -> None:
    config = load_mcp_config(tmp_path)
    assert config.servers == {}
    assert config.allowed_tools == []
    assert config.disabled_tools == []


def test_save_and_load_mcp_config(tmp_path: Path) -> None:
    config = MCPConfig(
        servers={"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}},
        allowed_tools=["fetch"],
        disabled_tools=["delete"],
    )
    save_mcp_config(tmp_path, config)
    loaded = load_mcp_config(tmp_path)
    assert loaded.servers == config.servers
    assert loaded.allowed_tools == ["fetch"]
    assert loaded.disabled_tools == ["delete"]


def test_filter_tools() -> None:
    tools = [DummyTool(name="read"), DummyTool(name="write"), DummyTool(name="execute")]

    # No filter
    config_empty = MCPConfig()
    assert [t.name for t in _filter_tools(tools, config_empty)] == [
        "read",
        "write",
        "execute",
    ]

    # Allowed tools filter
    config_allowed = MCPConfig(allowed_tools=["read", "execute"])
    assert [t.name for t in _filter_tools(tools, config_allowed)] == ["read", "execute"]

    # Disabled tools filter
    config_disabled = MCPConfig(disabled_tools=["write"])
    assert [t.name for t in _filter_tools(tools, config_disabled)] == [
        "read",
        "execute",
    ]

    # Allowed and disabled overlap
    config_both = MCPConfig(allowed_tools=["read", "write"], disabled_tools=["write"])
    assert [t.name for t in _filter_tools(tools, config_both)] == ["read"]


def test_build_stdio_server_config() -> None:
    conf = _build_stdio_server_config(
        "uvx server --debug", ["API_KEY=123", "HOST=localhost"], "stdio"
    )
    assert conf["command"] == "uvx"
    assert conf["args"] == ["server", "--debug"]
    assert conf["transport"] == "stdio"
    assert conf["env"] == {"API_KEY": "123", "HOST": "localhost"}


def test_cmd_mcp_add_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")

    add_args_stdio = argparse.Namespace(
        agent="test-agent",
        server_url_or_cmd="npx -y @modelcontextprotocol/server-filesystem",
        name="fs",
        allowed_tool=["read_file"],
        transport="stdio",
        env=["ROOT=/tmp"],
    )
    assert cmd_mcp_add(add_args_stdio) == 0

    add_args_url = argparse.Namespace(
        agent="test-agent",
        server_url_or_cmd="http://localhost:8000/sse",
        name="remote-sse",
        allowed_tool=[],
        transport=None,
        env=[],
    )
    assert cmd_mcp_add(add_args_url) == 0

    list_args = argparse.Namespace(agent="test-agent")
    assert cmd_mcp_list(list_args) == 0

    loaded = load_mcp_config(tmp_path / "agents" / "test-agent")
    assert "fs" in loaded.servers
    assert "remote-sse" in loaded.servers
    assert loaded.servers["remote-sse"]["transport"] == "sse"
    assert "read_file" in loaded.allowed_tools


def test_load_mcp_tools_empty_servers(tmp_path: Path) -> None:
    assert asyncio.run(load_mcp_tools_managed(tmp_path)) == []
    assert asyncio.run(load_mcp_tools_for_servers({})) == []


@pytest.mark.anyio
async def test_load_mcp_tools_managed_applies_filter(tmp_path: Path) -> None:
    """MultiServerMCPClient has no close(): it opens a session per tool call."""
    config = MCPConfig(servers={"echo": {"command": "echo"}}, allowed_tools=["test_tool"])
    save_mcp_config(tmp_path, config)

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[DummyTool(name="test_tool"), DummyTool(name="other")])

    with patch("cud.tools.mcp.MultiServerMCPClient", return_value=mock_client) as mock_cls:
        tools = await load_mcp_tools_managed(tmp_path)
        assert [t.name for t in tools] == ["test_tool"]
        mock_cls.assert_called_once_with({"echo": {"command": "echo"}})


@pytest.mark.anyio
async def test_load_mcp_tools_for_servers_with_servers() -> None:
    mock_client = MagicMock()
    tool = DummyTool(name="test_tool_2")
    mock_client.get_tools = AsyncMock(return_value=[tool])

    with patch("cud.tools.mcp.MultiServerMCPClient", return_value=mock_client):
        assert await load_mcp_tools_for_servers({"echo": {"command": "echo"}}) == [tool]


def test_mcp_client_has_no_close_api() -> None:
    """Guards the assumption that removed the dead cleanup plumbing."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    assert not hasattr(MultiServerMCPClient, "close")


def test_load_mcp_config_rejects_bad_types(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text('{"servers": ["oops"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="'servers' must be an object"):
        load_mcp_config(tmp_path)

    (tmp_path / "mcp.json").write_text('{"servers": {"a": "not-an-object"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="server 'a' must be an object"):
        load_mcp_config(tmp_path)

    (tmp_path / "mcp.json").write_text('{"allowedTools": "read_file"}', encoding="utf-8")
    with pytest.raises(ValueError, match="'allowedTools' must be a list of strings"):
        load_mcp_config(tmp_path)

    (tmp_path / "mcp.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected an object"):
        load_mcp_config(tmp_path)


def test_mcp_config_with_string_allowed_tools_keeps_tools(tmp_path: Path) -> None:
    """Regression: a string allowedTools used to become a set of characters
    and silently delete the agent's entire toolset."""
    (tmp_path / "mcp.json").write_text(
        '{"servers": {"a": {"command": "x"}}, "allowedTools": ["read_file"]}', encoding="utf-8"
    )
    config = load_mcp_config(tmp_path)
    assert config.allowed_tools == ["read_file"]
    tools = [DummyTool(name="read_file"), DummyTool(name="write_file")]
    assert [t.name for t in _filter_tools(tools, config)] == ["read_file"]


def test_build_stdio_server_config_rejects_bad_env() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        _build_stdio_server_config("uvx server", ["NOEQUALS"], "stdio")


def test_mcp_add_picks_free_default_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Regression: the default name used to overwrite an existing entry."""
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("agent-a")
    agent_dir = tmp_path / "agents" / "agent-a"
    save_mcp_config(agent_dir, MCPConfig(servers={"server2": {"command": "keepme"}}))

    assert cmd_mcp_add(argparse.Namespace(
        agent="agent-a", server_url_or_cmd="echo", name=None,
        allowed_tool=[], transport=None, env=[],
    )) == 0

    loaded = load_mcp_config(agent_dir)
    assert loaded.servers["server2"] == {"command": "keepme"}
    assert "server1" in loaded.servers


def test_mcp_add_rejects_bad_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("agent-b")
    assert cmd_mcp_add(argparse.Namespace(
        agent="agent-b", server_url_or_cmd="echo", name="x",
        allowed_tool=[], transport=None, env=["NOEQUALS"],
    )) == 2


def test_save_mcp_config_creates_agent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "agent"
    save_mcp_config(target, MCPConfig(servers={}))
    assert (target / "mcp.json").exists()


def test_register_mcp_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_mcp_commands(sub)

    args_add = parser.parse_args(["mcp", "add", "agent1", "echo", "--name", "srv1"])
    assert args_add.agent == "agent1"
    assert args_add.server_url_or_cmd == "echo"
    assert args_add.name == "srv1"

    args_list = parser.parse_args(["mcp", "list", "agent1"])
    assert args_list.agent == "agent1"
