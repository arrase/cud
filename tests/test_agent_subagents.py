from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cud.agent.subagents import (
    _build_spec,
    _load_mcp_tools,
    _resolve_env,
    build_subagents,
)
from cud.config.settings import ModelSettings, SubAgentMCPServer, SubAgentSettings


def test_resolve_env_empty() -> None:
    assert _resolve_env({}) == {}


def test_resolve_env_no_placeholders() -> None:
    assert _resolve_env({"KEY": "val"}) == {"KEY": "val"}


def test_resolve_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_SECRET", "supersecret")
    assert _resolve_env({"SECRET": "${MY_SECRET}"}) == {"SECRET": "supersecret"}


def test_resolve_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_ENV_VAR", raising=False)
    assert _resolve_env({"SECRET": "${MISSING_ENV_VAR}"}) is None


@pytest.mark.anyio
async def test_build_spec_minimal() -> None:
    sa = SubAgentSettings(name="worker", description="Does work")
    model_settings = ModelSettings(name="qwen", base_url="http://localhost:11434")

    spec = await _build_spec(sa, model_settings=model_settings)
    assert spec["name"] == "worker"
    assert spec["description"] == "Does work"
    assert spec["system_prompt"] == "Does work"
    assert "model" not in spec
    assert "skills" not in spec
    assert "tools" not in spec


@pytest.mark.anyio
async def test_build_spec_custom_model_and_skills() -> None:
    sa = SubAgentSettings(
        name="specialist",
        description="A specialist",
        system_prompt="You are a specialist.",
        model="llama3",
        context_window=8192,
        skills_paths=["./skills/search", "skills/calc"],
    )
    model_settings = ModelSettings(name="qwen", base_url="http://localhost:11434")

    spec = await _build_spec(sa, model_settings=model_settings)
    assert spec["name"] == "specialist"
    assert spec["description"] == "A specialist"
    assert spec["system_prompt"] == "You are a specialist."
    assert spec["model"].model == "llama3"
    assert spec["model"].num_ctx == 8192
    assert spec["skills"] == ["/agent/skills/search", "/agent/skills/calc"]


@pytest.mark.anyio
async def test_load_mcp_tools_empty_servers() -> None:
    assert await _load_mcp_tools("test-agent", []) == []


@pytest.mark.anyio
async def test_load_mcp_tools_unresolved_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSET_VAR", raising=False)
    server = SubAgentMCPServer(name="srv", command="cmd", args=[], env={"KEY": "${UNSET_VAR}"})

    loader = AsyncMock()
    with patch("cud.agent.subagents.load_mcp_tools_for_servers", loader):
        assert await _load_mcp_tools("test-agent", [server]) == []
        loader.assert_not_called()


@pytest.mark.anyio
async def test_load_mcp_tools_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV_KEY", "env_val")
    server = SubAgentMCPServer(name="srv", command="echo", args=["hi"], env={"KEY": "${ENV_KEY}"})
    dummy_tool = MagicMock()

    with patch("cud.agent.subagents.load_mcp_tools_for_servers", AsyncMock(return_value=[dummy_tool])):
        assert await _load_mcp_tools("test-agent", [server]) == [dummy_tool]


@pytest.mark.anyio
async def test_load_mcp_tools_swallows_transport_errors() -> None:
    """An unreachable MCP server must not prevent the agent from starting."""
    server = SubAgentMCPServer(name="srv", command="echo", args=[], env={})
    with patch(
        "cud.agent.subagents.load_mcp_tools_for_servers",
        AsyncMock(side_effect=RuntimeError("connection error")),
    ):
        assert await _load_mcp_tools("test-agent", [server]) == []


@pytest.mark.anyio
async def test_build_subagents_integration() -> None:
    sa = SubAgentSettings(
        name="helper",
        description="Helper agent",
        mcp_servers=[SubAgentMCPServer(name="srv", command="echo", args=[], env={})],
    )
    model_settings = ModelSettings(name="qwen", base_url="http://localhost:11434")
    dummy_tool = MagicMock()

    with patch("cud.agent.subagents.load_mcp_tools_for_servers", AsyncMock(return_value=[dummy_tool])):
        subagents = await build_subagents([sa], model_settings=model_settings)
    assert len(subagents) == 1
    assert subagents[0]["name"] == "helper"
    assert subagents[0]["tools"] == [dummy_tool]
