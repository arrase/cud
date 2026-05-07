"""Build subagent specifications for create_deep_agent."""

from __future__ import annotations

import logging
import os
import re
from contextlib import ExitStack
from typing import Any, Callable

from langchain_ollama import ChatOllama

from cud.config.settings import ModelSettings, SubAgentMCPServer, SubAgentSettings
from cud.tools.mcp import load_mcp_tools_for_servers

_log = logging.getLogger(__name__)
_ENV_RE = re.compile(r"\$\{(\w+)\}")


def build_subagents(
    subagent_settings: list[SubAgentSettings],
    *,
    model_settings: ModelSettings,
    exit_stack: ExitStack,
    run_async: Callable[..., Any],
) -> list[dict[str, Any]]:
    """Convert ``SubAgentSettings`` into dicts for ``create_deep_agent(subagents=...)``."""
    specs = []
    for sa in subagent_settings:
        spec = _build_spec(sa, model_settings=model_settings, exit_stack=exit_stack, run_async=run_async)
        if spec is not None:
            specs.append(spec)
    return specs


def _build_spec(
    sa: SubAgentSettings,
    *,
    model_settings: ModelSettings,
    exit_stack: ExitStack,
    run_async: Callable[..., Any],
) -> dict[str, Any] | None:
    spec: dict[str, Any] = {
        "name": sa.name,
        "description": sa.description,
        "system_prompt": sa.system_prompt or sa.description,
    }
    if sa.model or sa.context_window:
        name = sa.model or model_settings.name
        num_ctx = sa.context_window or model_settings.context_window
        spec["model"] = ChatOllama(
            model=name,
            base_url=model_settings.base_url,
            num_ctx=num_ctx,
            profile={"max_input_tokens": num_ctx},
        )
    if sa.skills_paths:
        spec["skills"] = [f"/agent/{p.removeprefix('./')}" for p in sa.skills_paths]
    if sa.mcp_servers:
        tools = _load_mcp_tools(sa.name, sa.mcp_servers, exit_stack, run_async)
        if tools:
            spec["tools"] = tools
    return spec


def _load_mcp_tools(
    subagent_name: str,
    mcp_servers: list[SubAgentMCPServer],
    exit_stack: ExitStack,
    run_async: Callable[..., Any],
) -> list[Any]:
    servers: dict[str, dict[str, Any]] = {}
    for srv in mcp_servers:
        env = _resolve_env(srv.env)
        if env is None:
            _log.warning("Subagent '%s': skipping MCP '%s' (unresolved env vars)", subagent_name, srv.name)
            continue
        entry: dict[str, Any] = {"command": srv.command, "args": srv.args, "transport": "stdio"}
        if env:
            entry["env"] = env
        servers[srv.name] = entry
    if not servers:
        return []
    try:
        tools, cleanup = run_async(load_mcp_tools_for_servers(servers))
        if cleanup:
            exit_stack.callback(cleanup)
        return tools
    except Exception as exc:
        _log.warning("Subagent '%s': MCP tools failed to load: %s", subagent_name, exc)
        return []


def _resolve_env(env: dict[str, str]) -> dict[str, str] | None:
    """Resolve ``${VAR}`` patterns against ``os.environ``.

    Returns the resolved dict, or ``None`` when any variable is missing.
    """
    if not env:
        return {}
    resolved = {}
    for key, value in env.items():
        missing: list[str] = []

        def _repl(m: re.Match[str]) -> str:
            val = os.environ.get(m.group(1))
            if val is None:
                missing.append(m.group(1))
                return m.group(0)
            return val

        resolved[key] = _ENV_RE.sub(_repl, value)
        if missing:
            _log.warning("Missing environment variables: %s", ", ".join(missing))
            return None
    return resolved
