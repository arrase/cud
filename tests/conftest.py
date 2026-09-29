"""Shared pytest fixtures and isolation guards."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Pin the async test backend explicitly.

    The suite uses ``@pytest.mark.anyio``; without this fixture the backend
    comes from the anyio pytest plugin's default, which silently changes if a
    transitive dependency moves.
    """
    return "asyncio"


@pytest.fixture(autouse=True)
def isolate_cud_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force every test to operate in its own throwaway CUD home.

    Autouse so a test can never create agents in the developer's real
    ``~/.cud`` by forgetting to set the variable.  Individual tests that need
    a different layout override it afterwards.
    """
    home = tmp_path / "cud-home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CUD_HOME", str(home))
    yield
