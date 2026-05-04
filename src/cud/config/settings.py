"""Agent settings loading and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ModelSettings:
    provider: str = "ollama"
    name: str = "qwen2.5-coder:14b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    compressor_temperature: float = 0.0
    context_window: int = 32768


@dataclass(slots=True)
class CompressionSettings:
    threshold_ratio: float = 0.75
    max_tool_output_chars: int = 4000
    keep_recent_messages: int = 12


@dataclass(slots=True)
class RuntimeSettings:
    max_visible_tools: int = 24
    max_tool_calls_per_run: int = 24
    require_approval: bool = True
    allow_shell_traversal: bool = False
    mutable_tools: list[str] = field(
        default_factory=lambda: ["write_file", "edit_file", "shell_exec", "memory_update", "memory_clear"]
    )


@dataclass(slots=True)
class GatewaySettings:
    provider: str = "discord"
    token: str = ""
    mode: str = "bot"


@dataclass(slots=True)
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    compression: CompressionSettings = field(default_factory=CompressionSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    gateway: GatewaySettings = field(default_factory=GatewaySettings)
    workspace: str = "workspace"

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "Settings":
        raw = raw or {}
        return cls(
            model=_dataclass_from_dict(ModelSettings, raw.get("model")),
            compression=_dataclass_from_dict(CompressionSettings, raw.get("compression")),
            runtime=_dataclass_from_dict(RuntimeSettings, raw.get("runtime")),
            gateway=_dataclass_from_dict(GatewaySettings, raw.get("gateway")),
            workspace=str(raw.get("workspace", "workspace")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dataclass_from_dict(cls: type[Any], raw: dict[str, Any] | None) -> Any:
    defaults = cls()
    if not raw:
        return defaults
    valid = {field_name for field_name in defaults.__dataclass_fields__}
    data = {key: value for key, value in raw.items() if key in valid}
    return cls(**{**asdict(defaults), **data})


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
    if not 0 < settings.compression.threshold_ratio <= 1:
        raise ValueError("compression.threshold_ratio must be in (0, 1]")
    if settings.runtime.max_visible_tools <= 0:
        raise ValueError("runtime.max_visible_tools must be positive")

