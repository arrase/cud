"""Agent settings loading and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Self

import yaml


@dataclass(slots=True)
class ModelSettings:
    provider: str = "ollama"
    name: str = "gemma4:e4b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.0
    context_window: int = 32768


@dataclass(slots=True)
class RuntimeSettings:
    allow_traversal: bool = True


@dataclass(slots=True)
class GatewaySettings:
    provider: str = "discord"
    token: str = ""
    mode: str = "bot"


@dataclass(slots=True)
class SubAgentMCPServer:
    name: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SubAgentSettings:
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    context_window: int = 0
    skills_paths: list[str] = field(default_factory=list)
    mcp_servers: list[SubAgentMCPServer] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    gateway: GatewaySettings = field(default_factory=GatewaySettings)
    subagents: list[SubAgentSettings] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Self:
        raw = raw or {}
        return cls(
            model=_dataclass_from_dict(ModelSettings, raw.get("model")),
            runtime=_dataclass_from_dict(RuntimeSettings, raw.get("runtime")),
            gateway=_dataclass_from_dict(GatewaySettings, raw.get("gateway")),
            subagents=_subagents_from_list(raw.get("subagents")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dataclass_from_dict(cls: type[Any], raw: dict[str, Any] | None) -> Any:
    if raw is None:
        return cls()
    valid = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in valid})


def _subagents_from_list(raw: list[dict[str, Any]] | None) -> list[SubAgentSettings]:
    if not raw:
        return []
    subagents = []
    for item in raw:
        mcp_servers = [_dataclass_from_dict(SubAgentMCPServer, m) for m in (item.get("mcp_servers") or [])]
        sa = _dataclass_from_dict(SubAgentSettings, {k: v for k, v in item.items() if k != "mcp_servers"})
        sa.mcp_servers = mcp_servers
        subagents.append(sa)
    return subagents


def load_settings(agent_dir: Path) -> Settings:
    path = agent_dir / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(f"settings.yaml not found in {agent_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings = Settings.from_dict(raw)
    validate_settings(settings)
    return settings


def save_settings(agent_dir: Path, settings: Settings) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(settings.to_dict(), sort_keys=False, allow_unicode=False)
    (agent_dir / "settings.yaml").write_text(text, encoding="utf-8")


def validate_settings(settings: Settings) -> None:
    if settings.model.provider != "ollama":
        raise ValueError("v1 supports only the ollama model provider")
    if not settings.model.name:
        raise ValueError("model.name is required")
    if settings.model.context_window <= 0:
        raise ValueError("model.context_window must be positive")
    if settings.model.temperature < 0:
        raise ValueError("model.temperature must be non-negative")
