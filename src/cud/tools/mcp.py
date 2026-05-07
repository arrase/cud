"""MCP config parsing and optional LangChain adapter loading."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

log = logging.getLogger(__name__)


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
        servers=raw.get("servers", {}) or {},
        allowed_tools=raw.get("allowedTools", raw.get("allowed_tools", [])) or [],
        disabled_tools=raw.get("disabledTools", raw.get("disabled_tools", [])) or [],
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
    names = [tool.name for tool in tools]
    if config.allowed_tools:
        allowed = set(config.allowed_tools)
        names = [n for n in names if n in allowed]
    enabled = set(names) - set(config.disabled_tools)
    return [tool for tool in tools if tool.name in enabled]


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
            if hasattr(client, "close"):
                await client.close()
        except Exception:
            log.warning("MCP client cleanup failed", exc_info=True)

    return cleanup

