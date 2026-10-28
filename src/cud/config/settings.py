"""Agent settings loading and validation."""

from __future__ import annotations

import os
import shlex
import tempfile
import urllib.parse
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Self

import yaml

# Trailing marker used to round-trip env vars through plain-text editors.
ENV_MARKER = "env:"


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
    # such in gh-pages/tools-skills.md; flip to False for a sandboxed default.
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


_NUMERIC_FIELDS = {
    ("ModelSettings", "temperature"),
    ("ModelSettings", "context_window"),
    ("SubAgentSettings", "context_window"),
}


def _coerce_numeric(owner: str, name: str, value: Any) -> int | float:
    if (owner, name) == ("SubAgentSettings", "context_window") and value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"settings field '{owner}.{name}' must be a number, got {type(value).__name__}")
    if (owner, name) == ("ModelSettings", "temperature"):
        return float(value)
    if not isinstance(value, int):
        raise ValueError(f"settings field '{owner}.{name}' must be an integer, got {type(value).__name__}")
    return value


def _coerce(owner: str, name: str, value: Any) -> Any:
    """Check that *value* matches the declared type of settings field *name*."""
    key = (owner, name)
    if key == ("RuntimeSettings", "allow_traversal"):
        if not isinstance(value, bool):
            raise ValueError(f"allow_traversal must be a boolean, got {type(value).__name__}")
        return value
    if key in _NUMERIC_FIELDS:
        return _coerce_numeric(owner, name, value)
    if name in ("skills_paths", "args"):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"settings field '{owner}.{name}' must be a list of strings")
        return list(value)
    if name == "env":
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise ValueError(f"settings field '{owner}.{name}' must be a string mapping")
        return dict(value)
    if not isinstance(value, str):
        raise ValueError(f"settings field '{owner}.{name}' must be a string, got {type(value).__name__}")
    return value


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


def format_subagent_mcp_server(srv: SubAgentMCPServer) -> str:
    """Render one MCP server as a single lossless editable line.

    Env values are percent-encoded so commas, spaces and ``=`` inside a value
    survive the round trip intact.
    """
    line = shlex.join([srv.name, srv.command, *srv.args])
    if srv.env:
        encoded = ",".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" for k, v in srv.env.items()
        )
        line = f"{line} {ENV_MARKER}[{encoded}]"
    return line


def _split_mcp_server_env(line: str) -> tuple[str, dict[str, str]]:
    if not (line.endswith("]") and ENV_MARKER in line):
        return line, {}
    head, _, env_blob = line.rpartition(ENV_MARKER)
    env: dict[str, str] = {}
    for pair in env_blob.strip().lstrip("[").rstrip("]").split(","):
        key, sep, value = pair.partition("=")
        if sep:
            env[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
    return head.rstrip(), env


def parse_subagent_mcp_servers(text: str) -> list[SubAgentMCPServer]:
    """Parse MCP server definitions from multi-line text.

    Each line is ``name command arg1 arg2 ... [env:KEY=VALUE,...]``.
    Arguments are shlex-quoted and env values percent-encoded, so values
    containing spaces, commas or ``=`` survive the round trip.
    """
    servers: list[SubAgentMCPServer] = []
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line, env = _split_mcp_server_env(line)
        try:
            parts = shlex.split(line)
        except ValueError:
            continue  # Unbalanced quotes: skip the line rather than corrupt the config.
        if len(parts) < 2:
            continue
        servers.append(
            SubAgentMCPServer(
                name=parts[0],
                command=parts[1],
                args=parts[2:],
                env=env,
            )
        )
    return servers


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
    agent_dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(settings.to_dict(), sort_keys=False, allow_unicode=True)
    _atomic_write(agent_dir / "settings.yaml", text)


def _atomic_write(path: Path, text: str) -> None:
    """Write *text* to *path* via a same-directory temp file and one rename.

    A crash or a concurrent reader can no longer observe a truncated file.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp.chmod(0o600)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _validate_subagent(sa: SubAgentSettings, seen: set[str]) -> None:
    if not isinstance(sa.name, str) or not sa.name:
        raise ValueError("subagent.name is required")
    if sa.name in seen:
        raise ValueError(f"duplicate subagent name: {sa.name!r}")
    seen.add(sa.name)
    if not isinstance(sa.description, str) or not isinstance(sa.system_prompt, str) or not isinstance(sa.model, str):
        raise ValueError(f"subagent '{sa.name}': string fields must be strings")
    if not isinstance(sa.skills_paths, list) or not all(isinstance(p, str) for p in sa.skills_paths):
        raise ValueError(f"subagent '{sa.name}': skills_paths must be a list of strings")
    if isinstance(sa.context_window, bool) or not isinstance(sa.context_window, int):
        raise ValueError(
            f"subagent '{sa.name}': context_window must be an integer, got {type(sa.context_window).__name__}"
        )
    if sa.context_window < 0:
        raise ValueError(f"subagent '{sa.name}': context_window must not be negative")


def validate_settings(settings: Settings) -> None:
    """Validate all settings and subagent invariants."""
    if not isinstance(settings.runtime.allow_traversal, bool):
        raise ValueError("allow_traversal must be a boolean")
    if settings.model.provider != "ollama":
        raise ValueError("v1 supports only the ollama model provider")
    if not isinstance(settings.model.name, str) or not settings.model.name:
        raise ValueError("model.name is required")
    if (
        isinstance(settings.model.context_window, bool)
        or not isinstance(settings.model.context_window, int)
        or settings.model.context_window <= 0
    ):
        raise ValueError("model.context_window must be positive")
    if (
        isinstance(settings.model.temperature, bool)
        or not isinstance(settings.model.temperature, (int, float))
        or settings.model.temperature < 0
    ):
        raise ValueError("model.temperature must be non-negative")
    if settings.gateway.token and settings.gateway.provider != "discord":
        raise ValueError("v1 supports only the discord gateway provider")
    seen: set[str] = set()
    for sa in settings.subagents:
        _validate_subagent(sa, seen)
