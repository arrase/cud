"""MCP config parsing and optional LangChain adapter loading."""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection

# Transport values accepted by the adapter; also the GUI combo box items.
TRANSPORTS = ("stdio", "sse", "streamable_http")
DEFAULT_TRANSPORT = "stdio"


@dataclass(slots=True)
class MCPConfig:
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    disabled_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "servers": self.servers,
            "allowedTools": self.allowed_tools,
            "disabledTools": self.disabled_tools,
        }


def _string_list(raw: object, key: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise ValueError(f"mcp.json: '{key}' must be a list of strings")
    return list(raw)


def _server_map(raw: object) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("mcp.json: 'servers' must be an object mapping name -> server config")
    for name, server in raw.items():
        if not isinstance(server, dict):
            raise ValueError(f"mcp.json: server '{name}' must be an object")
    return raw


def load_mcp_config(agent_dir: Path) -> MCPConfig:
    path = agent_dir / "mcp.json"
    if not path.exists():
        return MCPConfig()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict):
        raise ValueError(f"mcp.json: expected an object, got {type(raw).__name__}")
    return MCPConfig(
        servers=_server_map(raw.get("servers")),
        allowed_tools=_string_list(raw.get("allowedTools"), "allowedTools"),
        disabled_tools=_string_list(raw.get("disabledTools"), "disabledTools"),
    )


def save_mcp_config(agent_dir: Path, config: MCPConfig) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "mcp.json").write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")


def parse_env_pairs(pairs: Iterable[str]) -> dict[str, str]:
    env_dict: dict[str, str] = {}
    for raw in pairs:
        item = raw.strip()
        if not item:
            continue
        key, sep, v = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"--env must be KEY=VALUE, got {raw!r}")
        env_dict[key] = v.strip()
    return env_dict


def build_stdio_server_config(
    value: str,
    env_pairs: Iterable[str] = (),
    transport: str = DEFAULT_TRANSPORT,
) -> dict[str, Any]:
    parts = shlex.split(value)
    if not parts:
        raise ValueError("MCP server command cannot be empty")
    env_dict = parse_env_pairs(env_pairs)
    server_config: dict[str, Any] = {
        "command": parts[0],
        "args": parts[1:],
        "transport": transport,
    }
    if env_dict:
        server_config["env"] = env_dict
    return server_config


def free_server_name(servers: Mapping[str, Any], base: str = "server") -> str:
    """First unused ``{base}N`` name, so an add never silently overwrites one."""
    index = 1
    while f"{base}{index}" in servers:
        index += 1
    return f"{base}{index}"


def _filter_tools(tools: list[Any], config: MCPConfig) -> list[Any]:
    """Return only the tools allowed by the MCP config."""
    allowed = set(config.allowed_tools) if config.allowed_tools else None
    disabled = set(config.disabled_tools)
    return [tool for tool in tools if (allowed is None or tool.name in allowed) and tool.name not in disabled]


async def load_mcp_tools_managed(agent_dir: Path) -> list[Any]:
    """Load the MCP tools declared in the agent's ``mcp.json``.

    ``MultiServerMCPClient`` opens a fresh session per tool call and exposes no
    ``close``, so there is nothing to tear down here.
    """
    config = load_mcp_config(agent_dir)
    if not config.servers:
        return []
    client = MultiServerMCPClient(cast("dict[str, Connection]", config.servers))
    return _filter_tools(await client.get_tools(), config)


async def load_mcp_tools_for_servers(servers: dict[str, dict[str, Any]]) -> list[Any]:
    """Load MCP tools from a pre-built server config dict (used by subagents)."""
    if not servers:
        return []
    client = MultiServerMCPClient(cast("dict[str, Connection]", servers))
    return list(await client.get_tools())
