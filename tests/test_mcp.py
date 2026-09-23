import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

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
    tools, cleanup = asyncio.run(load_mcp_tools_managed(tmp_path))
    assert tools == []
    assert cleanup is None

    tools2, cleanup2 = asyncio.run(load_mcp_tools_for_servers({}))
    assert tools2 == []
    assert cleanup2 is None
