"""Canonical filesystem paths for Cud."""

from __future__ import annotations

import os
import re
from pathlib import Path

_AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def cud_home() -> Path:
    """Return the Cud home directory.

    `CUD_HOME` is supported for tests and deployments. The canonical default is
    `~/.cud`, and agent homes live below `agents/`.
    """

    return Path(os.environ.get("CUD_HOME", "~/.cud")).expanduser()


def agents_root() -> Path:
    return cud_home() / "agents"


def validate_agent_name(name: str) -> str:
    if not _AGENT_RE.match(name):
        raise ValueError(
            "agent name must start with an alphanumeric character and contain "
            "only letters, numbers, '.', '_' or '-'"
        )
    return name


def agent_home(name: str) -> Path:
    return agents_root() / validate_agent_name(name)

