"""MCP config parsing and optional LangChain adapter loading."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from rich.console import Console

from cud.config.paths import agent_home

console = Console()

# Transport values accepted by the adapter; also the GUI combo box items.
TRANSPORTS = ("stdio", "sse", "streamable_http")
DEFAULT_TRANSPORT = "stdio"


@dataclass(slots=True)
class MCPConfig:
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    disabled_tools: list[str] = field(default_factory=list)


def _string_list(raw: Any, key: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise ValueError(f"mcp.json: '{key}' must be a list of strings")
    return list(raw)


def _server_map(raw: Any) -> dict[str, dict[str, Any]]:
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
        allowed_tools=_string_list(raw.get("allowedTools", raw.get("allowed_tools")), "allowedTools"),
        disabled_tools=_string_list(raw.get("disabledTools", raw.get("disabled_tools")), "disabledTools"),
    )


def save_mcp_config(agent_dir: Path, config: MCPConfig) -> None:
    raw = {
        "servers": config.servers,
        "allowedTools": config.allowed_tools,
        "disabledTools": config.disabled_tools,
    }
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "mcp.json").write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def _filter_tools(tools: list[Any], config: MCPConfig) -> list[Any]:
    """Return only the tools allowed by the MCP config."""
    allowed = set(config.allowed_tools) if config.allowed_tools else None
    disabled = set(config.disabled_tools)
    return [
        tool for tool in tools
        if (allowed is None or tool.name in allowed) and tool.name not in disabled
    ]


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


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def register_mcp_commands(sub: argparse._SubParsersAction) -> None:
    mcp = sub.add_parser("mcp", help="Manage MCP servers")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_add = mcp_sub.add_parser("add", help="Add an MCP server")
    mcp_add.add_argument("agent")
    mcp_add.add_argument("server_url_or_cmd")
    mcp_add.add_argument("--name")
    mcp_add.add_argument("--allowed-tool", action="append", default=[])
    mcp_add.add_argument("--transport", choices=list(TRANSPORTS), help="Override transport type")
    mcp_add.add_argument("--env", action="append", default=[], help="Environment variables for stdio (e.g. KEY=VALUE)")
    mcp_add.set_defaults(func=cmd_mcp_add)
    mcp_list = mcp_sub.add_parser("list", help="List MCP servers")
    mcp_list.add_argument("agent")
    mcp_list.set_defaults(func=cmd_mcp_list)


def _build_stdio_server_config(value: str, env_vars: list[str], transport: str) -> dict[str, Any]:
    parts = shlex.split(value)
    command = parts[0] if parts else value
    cmd_args = parts[1:]
    env_dict: dict[str, str] = {}
    for env_var in env_vars:
        key, sep, v = env_var.partition("=")
        if not sep or not key:
            raise ValueError(f"--env must be KEY=VALUE, got {env_var!r}")
        env_dict[key] = v
    server_config: dict[str, Any] = {"command": command, "args": cmd_args, "transport": transport}
    if env_dict:
        server_config["env"] = env_dict
    return server_config


def cmd_mcp_add(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    config = load_mcp_config(directory)
    name = args.name or _free_server_name(config.servers)
    value = args.server_url_or_cmd

    is_url = value.startswith(("http://", "https://"))
    transport = args.transport or ("sse" if is_url else "stdio")

    try:
        if transport in ("sse", "streamable_http"):
            config.servers[name] = {"url": value, "transport": transport}
        else:
            config.servers[name] = _build_stdio_server_config(value, args.env, transport)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    if args.allowed_tool:
        config.allowed_tools = sorted(set(config.allowed_tools + args.allowed_tool))
    save_mcp_config(directory, config)
    console.print(f"Added MCP server {name}")
    return 0


def _free_server_name(servers: dict[str, dict[str, Any]]) -> str:
    """First unused ``serverN`` name, so an add never silently overwrites one."""
    index = 1
    while f"server{index}" in servers:
        index += 1
    return f"server{index}"


def cmd_mcp_list(args: argparse.Namespace) -> int:
    config = load_mcp_config(agent_home(args.agent))
    data = {"servers": config.servers, "allowedTools": config.allowed_tools, "disabledTools": config.disabled_tools}
    console.print(json.dumps(data, indent=2))
    return 0

