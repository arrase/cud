from pathlib import Path

import pytest

from cud.config.settings import (
    GatewaySettings,
    ModelSettings,
    RuntimeSettings,
    Settings,
    SubAgentMCPServer,
    SubAgentSettings,
    load_settings,
    save_settings,
    validate_settings,
)


def test_default_settings() -> None:
    settings = Settings()
    assert settings.model.provider == "ollama"
    assert settings.model.name == "gemma4:e4b"
    assert settings.model.base_url == "http://localhost:11434"
    assert settings.model.temperature == 0.0
    assert settings.model.context_window == 32768
    assert settings.runtime.allow_traversal is True
    assert settings.gateway.provider == "discord"
    assert settings.gateway.token == ""
    assert settings.gateway.mode == "bot"
    assert settings.subagents == []


def test_from_dict_empty() -> None:
    settings = Settings.from_dict({})
    assert settings.model.provider == "ollama"
    assert settings.subagents == []


def test_from_dict_and_to_dict() -> None:
    raw = {
        "model": {
            "provider": "ollama",
            "name": "llama3:8b",
            "base_url": "http://ollama:11434",
            "temperature": 0.7,
            "context_window": 8192,
        },
        "runtime": {"allow_traversal": False},
        "gateway": {"provider": "discord", "token": "secret_token", "mode": "user"},
        "subagents": [
            {
                "name": "researcher",
                "description": "Performs web searches",
                "system_prompt": "You are a researcher",
                "model": "mistral:7b",
                "context_window": 4096,
                "skills_paths": ["skills/search"],
                "mcp_servers": [
                    {
                        "name": "fetch",
                        "command": "uvx",
                        "args": ["mcp-server-fetch"],
                        "env": {"ENV_VAR": "val"},
                    }
                ],
            }
        ],
    }

    settings = Settings.from_dict(raw)
    assert settings.model.name == "llama3:8b"
    assert settings.runtime.allow_traversal is False
    assert settings.gateway.token == "secret_token"
    assert len(settings.subagents) == 1

    sub = settings.subagents[0]
    assert isinstance(sub, SubAgentSettings)
    assert sub.name == "researcher"
    assert len(sub.mcp_servers) == 1
    assert isinstance(sub.mcp_servers[0], SubAgentMCPServer)
    assert sub.mcp_servers[0].name == "fetch"

    exported = settings.to_dict()
    assert exported["model"]["name"] == "llama3:8b"
    assert exported["subagents"][0]["name"] == "researcher"


def test_save_and_load_settings(tmp_path: Path) -> None:
    settings = Settings(
        model=ModelSettings(name="qwen2.5:7b", temperature=0.2),
        runtime=RuntimeSettings(allow_traversal=True),
        gateway=GatewaySettings(token="test_tok"),
    )
    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)
    assert loaded.model.name == "qwen2.5:7b"
    assert loaded.model.temperature == 0.2
    assert loaded.gateway.token == "test_tok"


def test_load_settings_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="settings.yaml not found"):
        load_settings(tmp_path)


def test_validate_settings_valid() -> None:
    settings = Settings()
    validate_settings(settings)


def test_validate_settings_invalid_provider() -> None:
    settings = Settings()
    settings.model.provider = "openai"
    with pytest.raises(ValueError, match="v1 supports only the ollama model provider"):
        validate_settings(settings)


def test_validate_settings_missing_name() -> None:
    settings = Settings()
    settings.model.name = ""
    with pytest.raises(ValueError, match="model.name is required"):
        validate_settings(settings)


def test_validate_settings_invalid_context_window() -> None:
    settings = Settings()
    settings.model.context_window = 0
    with pytest.raises(ValueError, match="model.context_window must be positive"):
        validate_settings(settings)


def test_validate_settings_negative_temperature() -> None:
    settings = Settings()
    settings.model.temperature = -0.1
    with pytest.raises(ValueError, match="model.temperature must be non-negative"):
        validate_settings(settings)


def test_validate_settings_invalid_gateway_provider() -> None:
    settings = Settings()
    settings.gateway.token = "token123"
    settings.gateway.provider = "slack"
    with pytest.raises(
        ValueError, match="v1 supports only the discord gateway provider"
    ):
        validate_settings(settings)
