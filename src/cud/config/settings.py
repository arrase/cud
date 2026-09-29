"""Agent settings loading and validation."""

from __future__ import annotations

import os
import tempfile
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
    # True = the agent gets the host shell (virtual_mode=False). Documented as
    # such in docs/tools-skills.md; flip to False for a sandboxed default.
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
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        return cls(
            model=_dataclass_from_dict(ModelSettings, raw.get("model")),
            runtime=_dataclass_from_dict(RuntimeSettings, raw.get("runtime")),
            gateway=_dataclass_from_dict(GatewaySettings, raw.get("gateway")),
            subagents=_subagents_from_list(raw.get("subagents")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dataclass_from_dict(cls: type[Any], raw: Any) -> Any:
    """Build a settings dataclass from a mapping, ignoring unknown keys.

    Raises ``ValueError`` with an actionable message on malformed input so a
    hand-edited ``settings.yaml`` never surfaces as an opaque ``TypeError``.
    """
    if raw is None:
        return cls()
    if not isinstance(raw, dict):
        raise ValueError(f"'{cls.__name__}' must be a mapping, got {type(raw).__name__}")
    valid = {f.name for f in fields(cls)}
    known = {k: _coerce(cls.__name__, k, v) for k, v in raw.items() if k in valid}
    return cls(**known)


# Numeric settings fields, keyed by owning dataclass *and* field name so a future
# dataclass with a same-named field of another type is not coerced silently.
_NUMERIC_FIELDS = {
    ("ModelSettings", "temperature"),
    ("ModelSettings", "context_window"),
    ("SubAgentSettings", "context_window"),
}

# Subset where a null is accepted and normalised to the "inherit" sentinel.
_NULLABLE_NUMERIC_FIELDS = {("SubAgentSettings", "context_window")}


def _coerce(owner: str, name: str, value: Any) -> Any:
    """Check that *value* matches the declared type of settings field *name*.

    YAML writes `0` where a float is expected, so ints are widened for float
    fields; anything else is rejected with an actionable message.
    """
    if (owner, name) not in _NUMERIC_FIELDS:
        return value
    if value is None and (owner, name) in _NULLABLE_NUMERIC_FIELDS:
        # `context_window: ` is a plausible way of writing "inherit the parent
        # default", which is what 0 already means downstream.
        return 0
    # `bool` is a subclass of `int`, so reject it explicitly for numbers.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"settings field '{owner}.{name}' must be a number, got {type(value).__name__}")
    return float(value) if (owner, name) == ("ModelSettings", "temperature") else int(value)


def _subagents_from_list(raw: Any) -> list[SubAgentSettings]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"'subagents' must be a list, got {type(raw).__name__}")
    subagents = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"each subagent must be a mapping, got {type(item).__name__}")
        mcp_raw = item.get("mcp_servers")
        if mcp_raw is not None and not isinstance(mcp_raw, list):
            raise ValueError(f"'mcp_servers' must be a list, got {type(mcp_raw).__name__}")
        mcp_servers = [_dataclass_from_dict(SubAgentMCPServer, m) for m in (mcp_raw or [])]
        sa = _dataclass_from_dict(SubAgentSettings, {k: v for k, v in item.items() if k != "mcp_servers"})
        sa.mcp_servers = mcp_servers
        subagents.append(sa)
    return subagents


def load_settings(agent_dir: Path) -> Settings:
    path = agent_dir / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(f"settings.yaml not found in {agent_dir}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping, got {type(raw).__name__}")
    settings = Settings.from_dict(raw)
    validate_settings(settings)
    return settings


def save_settings(agent_dir: Path, settings: Settings) -> None:
    """Validate and atomically persist *settings*.

    Validation happens here so no caller (CLI, GUI, gateway) can write a
    config that ``load_settings`` would later reject and brick the agent.
    """
    validate_settings(settings)
    validate_subagents(settings)
    agent_dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(settings.to_dict(), sort_keys=False, allow_unicode=True)
    _atomic_write(agent_dir / "settings.yaml", text, mode=0o600)  # holds the Discord token


def _atomic_write(path: Path, text: str, *, mode: int | None = None) -> None:
    """Write *text* to *path* via a same-directory temp file and one rename.

    A crash or a concurrent reader can no longer observe a truncated file.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if mode is not None:
            tmp.chmod(mode)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def validate_settings(settings: Settings) -> None:
    """Invariants that must hold for an agent to be able to start at all."""
    if settings.model.provider != "ollama":
        raise ValueError("v1 supports only the ollama model provider")
    if not settings.model.name:
        raise ValueError("model.name is required")
    if settings.model.context_window <= 0:
        raise ValueError("model.context_window must be positive")
    if settings.model.temperature < 0:
        raise ValueError("model.temperature must be non-negative")
    if settings.gateway.token and settings.gateway.provider != "discord":
        raise ValueError("v1 supports only the discord gateway provider")


def validate_subagents(settings: Settings) -> None:
    """Writer-side checks for subagent definitions.

    Deliberately *not* part of :func:`validate_settings`: a hand-edited
    ``settings.yaml`` with a dubious subagent should not stop the whole agent
    from booting, and a null ``context_window`` is a plausible way of writing
    "inherit the parent default".
    """
    seen: set[str] = set()
    for sa in settings.subagents:
        if not sa.name:
            raise ValueError("subagent.name is required")
        if sa.name in seen:
            raise ValueError(f"duplicate subagent name: {sa.name!r}")
        seen.add(sa.name)
        if not isinstance(sa.context_window, int):
            raise ValueError(
                f"subagent '{sa.name}': context_window must be an integer, "
                f"got {type(sa.context_window).__name__}"
            )
        if sa.context_window < 0:
            raise ValueError(f"subagent '{sa.name}': context_window must not be negative")
