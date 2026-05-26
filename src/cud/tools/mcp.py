"""MCP config parsing and optional LangChain adapter loading."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console

from cud.config.paths import agent_home

console = Console()

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPConfig:
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    disabled_tools: list[str] = field(default_factory=list)


def load_mcp_config(agent_dir: Path) -> MCPConfig:
    path = agent_dir / "mcp.json"
    if not path.exists():
        return MCPConfig()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return MCPConfig(
        servers=raw.get("servers", {}),
        allowed_tools=raw.get("allowedTools", raw.get("allowed_tools", [])),
        disabled_tools=raw.get("disabledTools", raw.get("disabled_tools", [])),
    )


def save_mcp_config(agent_dir: Path, config: MCPConfig) -> None:
    raw = {
        "servers": config.servers,
        "allowedTools": config.allowed_tools,
        "disabledTools": config.disabled_tools,
    }
    (agent_dir / "mcp.json").write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def _filter_tools(tools: list[Any], config: MCPConfig) -> list[Any]:
    """Return only the tools allowed by the MCP config."""
    allowed = set(config.allowed_tools) if config.allowed_tools else None
    disabled = set(config.disabled_tools)
    return [
        tool for tool in tools
        if (allowed is None or tool.name in allowed) and tool.name not in disabled
    ]


async def load_mcp_tools_managed(agent_dir: Path) -> tuple[list[Any], Callable[[], Coroutine[Any, Any, None]] | None]:
    """Load MCP tools and return a cleanup callback for the client.

    Returns ``(tools, cleanup)`` where *cleanup* must be called to close the
    underlying MCP transports.  When no servers are configured the cleanup
    callback is ``None``.
    """
    config = load_mcp_config(agent_dir)
    if not config.servers:
        return [], None

    client = MultiServerMCPClient(config.servers)
    tools = _filter_tools(await client.get_tools(), config)
    return tools, _make_cleanup(client)


async def load_mcp_tools_for_servers(
    servers: dict[str, dict[str, Any]],
) -> tuple[list[Any], Callable[[], Coroutine[Any, Any, None]] | None]:
    """Load MCP tools from a raw server config dict.

    Same contract as ``load_mcp_tools_managed`` but accepts a pre-built dict
    instead of reading from the agent's ``mcp.json``.
    """
    if not servers:
        return [], None

    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    return tools, _make_cleanup(client)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_cleanup(client: MultiServerMCPClient) -> Callable[[], Coroutine[Any, Any, None]]:
    """Build an async cleanup callback for an MCP client."""

    async def cleanup() -> None:
        try:
            await client.close()
        except Exception:
            _log.warning("MCP client cleanup failed", exc_info=True)

    return cleanup


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
    mcp_add.add_argument("--transport", choices=["stdio", "sse", "streamable_http"], help="Override transport type")
    mcp_add.add_argument("--env", action="append", default=[], help="Environment variables for stdio (e.g. KEY=VALUE)")
    mcp_add.set_defaults(func=cmd_mcp_add)
    mcp_list = mcp_sub.add_parser("list", help="List MCP servers")
    mcp_list.add_argument("agent")
    mcp_list.set_defaults(func=cmd_mcp_list)


def cmd_mcp_add(args: argparse.Namespace) -> int:
    directory = agent_home(args.agent)
    config = load_mcp_config(directory)
    name = args.name or f"server{len(config.servers) + 1}"
    value = args.server_url_or_cmd

    is_url = value.startswith("http://") or value.startswith("https://")
    transport = args.transport
    if not transport:
        transport = "sse" if is_url else "stdio"

    if transport in ("sse", "streamable_http"):
        config.servers[name] = {"url": value, "transport": transport}
    else:
        parts = shlex.split(value)
        command = parts[0] if parts else value
        cmd_args = parts[1:]
        env_dict = {}
        for env_var in args.env:
            if "=" in env_var:
                k, v = env_var.split("=", 1)
                env_dict[k] = v
            else:
                env_dict[env_var] = ""
        server_config: dict[str, Any] = {"command": command, "args": cmd_args, "transport": transport}
        if env_dict:
            server_config["env"] = env_dict
        config.servers[name] = server_config

    if args.allowed_tool:
        config.allowed_tools = sorted(set(config.allowed_tools + args.allowed_tool))
    save_mcp_config(directory, config)
    console.print(f"Added MCP server {name}")
    return 0


def cmd_mcp_list(args: argparse.Namespace) -> int:
    config = load_mcp_config(agent_home(args.agent))
    data = {"servers": config.servers, "allowedTools": config.allowed_tools, "disabledTools": config.disabled_tools}
    console.print(json.dumps(data, indent=2))
    return 0

