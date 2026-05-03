"""MCP config parsing and optional LangChain adapter loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


def filter_tool_names(tool_names: list[str], config: MCPConfig, max_tools: int) -> list[str]:
    names = tool_names
    if config.allowed_tools:
        allowed = set(config.allowed_tools)
        names = [name for name in names if name in allowed]
    disabled = set(config.disabled_tools)
    names = [name for name in names if name not in disabled]
    if len(names) > max_tools and not config.allowed_tools:
        raise ValueError("MCP exposes too many tools; configure allowedTools in mcp.json")
    return names[:max_tools]


def render_mcp_summary(config: MCPConfig, max_tools: int) -> str:
    if not config.servers:
        return "No MCP servers configured."
    server_names = ", ".join(sorted(config.servers))
    filters = []
    if config.allowed_tools:
        filters.append(f"allowedTools={len(config.allowed_tools)}")
    if config.disabled_tools:
        filters.append(f"disabledTools={len(config.disabled_tools)}")
    budget = f"maxVisible={max_tools}"
    return f"Servers: {server_names}. Filters: {', '.join(filters + [budget])}."


async def load_langchain_mcp_tools(agent_dir: Path, max_tools: int) -> list[Any]:
    """Load MCP tools through langchain-mcp-adapters when installed.

    The adapter API has changed across releases, so this function keeps the
    dependency boundary narrow and returns an empty list when no servers exist.
    """

    config = load_mcp_config(agent_dir)
    if not config.servers:
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("langchain-mcp-adapters is required to load MCP tools") from exc

    client = MultiServerMCPClient(config.servers)
    tools = await client.get_tools()
    enabled_names = set(filter_tool_names([tool.name for tool in tools], config, max_tools))
    return [tool for tool in tools if tool.name in enabled_names]

