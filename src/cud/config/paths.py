"""Canonical filesystem paths for Cud."""

from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def cud_home() -> Path:
    """Return ``$CUD_HOME`` (default ``~/.cud``)."""
    return Path(os.environ.get("CUD_HOME", "~/.cud")).expanduser()


def agents_root() -> Path:
    return cud_home() / "agents"


def is_safe_name(name: str) -> bool:
    """Whether *name* is a safe single path segment / identifier."""
    return bool(_SAFE_NAME_RE.fullmatch(name))


def validate_safe_name(name: str, label: str = "name") -> str:
    # fullmatch (not match) so a trailing newline cannot slip past: agent names
    # are interpolated into systemd unit files, which are line-oriented.
    if not is_safe_name(name):
        raise ValueError(
            f"{label} must start with an alphanumeric character and contain only letters, numbers, '.', '_' or '-'"
        )
    return name


def validate_agent_name(name: str) -> str:
    return validate_safe_name(name, "agent name")


def agent_home(name: str) -> Path:
    return agents_root() / validate_agent_name(name)


def existing_agent_home(name: str) -> Path:
    path = agent_home(name)
    if not path.is_dir():
        raise FileNotFoundError(f"Agent '{name}' does not exist: {path}")
    return path
