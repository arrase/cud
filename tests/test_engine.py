import argparse
import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from cud.engine.cli import cmd_engine_pull, cmd_engine_status


def test_cmd_engine_status_success(monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.dumps(
        {"models": [{"name": "gemma4:e4b"}, {"name": "llama3:8b"}]}
    ).encode("utf-8")
    mock_resp = io.BytesIO(data)

    mock_urlopen = MagicMock(return_value=mock_resp)
    mock_resp.__enter__ = lambda s: s  # type: ignore[attr-defined]
    mock_resp.__exit__ = lambda s, *a: None  # type: ignore[attr-defined]
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    args = argparse.Namespace(base_url="http://localhost:11434")
    assert cmd_engine_status(args) == 0


def test_cmd_engine_status_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        MagicMock(side_effect=urllib.error.URLError("connection refused")),
    )
    args = argparse.Namespace(base_url="http://localhost:11434")
    assert cmd_engine_status(args) == 1


def test_cmd_engine_pull(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("subprocess.run", mock_run)

    args = argparse.Namespace(model_name="gemma4:e4b")
    assert cmd_engine_pull(args) == 0
    mock_run.assert_called_once_with(["ollama", "pull", "gemma4:e4b"], text=True)
