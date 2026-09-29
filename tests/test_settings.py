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
    validate_subagents,
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
    with pytest.raises(FileNotFoundError, match=r"settings\.yaml not found"):
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
    with pytest.raises(ValueError, match=r"model.name is required"):
        validate_settings(settings)


def test_validate_settings_invalid_context_window() -> None:
    settings = Settings()
    settings.model.context_window = 0
    with pytest.raises(ValueError, match=r"model\.context_window must be positive"):
        validate_settings(settings)


def test_validate_settings_negative_temperature() -> None:
    settings = Settings()
    settings.model.temperature = -0.1
    with pytest.raises(ValueError, match=r"model\.temperature must be non-negative"):
        validate_settings(settings)


def test_validate_settings_invalid_gateway_provider() -> None:
    settings = Settings()
    settings.gateway.token = "token123"
    settings.gateway.provider = "slack"
    with pytest.raises(
        ValueError, match="v1 supports only the discord gateway provider"
    ):
        validate_settings(settings)


# ---------------------------------------------------------------------------
# Regression tests: a config that load_settings would reject must never persist
# ---------------------------------------------------------------------------


def test_save_settings_rejects_invalid_config(tmp_path: Path) -> None:
    """Regression: saving an invalid config bricked the agent on next load."""
    settings = Settings()
    settings.gateway.provider = "telegram"
    settings.gateway.token = "tok"
    with pytest.raises(ValueError, match="discord gateway provider"):
        save_settings(tmp_path, settings)
    assert not (tmp_path / "settings.yaml").exists()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("model:\n  context_window: abc\n", "must be a number"),
        ("model:\n  temperature: 'hot'\n", "must be a number"),
        ("model: ollama\n", "must be a mapping"),
        ("model:\n  context_window: true\n", "must be a number"),
        ("- a\n- b\n", "must contain a mapping"),
        ("subagents: not-a-list\n", "must be a list"),
        ("model: [unclosed\n", "not valid YAML"),
    ],
)
def test_load_settings_reports_malformed_input(tmp_path: Path, body: str, message: str) -> None:
    """Regression: these used to surface as opaque TypeError/AttributeError."""
    (tmp_path / "settings.yaml").write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_settings(tmp_path)


def test_load_settings_accepts_yaml_int_temperature(tmp_path: Path) -> None:
    (tmp_path / "settings.yaml").write_text("model:\n  temperature: 1\n", encoding="utf-8")
    assert load_settings(tmp_path).model.temperature == 1.0


def test_save_settings_is_atomic_and_private(tmp_path: Path) -> None:
    settings = Settings()
    settings.gateway.token = "super-secret"
    save_settings(tmp_path, settings)

    path = tmp_path / "settings.yaml"
    assert oct(path.stat().st_mode)[-3:] == "600", "the file holds a Discord token"
    assert not list(tmp_path.glob(".settings.yaml.*")), "temp file must be renamed away"


def test_save_settings_does_not_truncate_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a plain write_text truncates the file before writing, so a
    failure mid-write left corrupt YAML on disk."""
    save_settings(tmp_path, Settings())
    path = tmp_path / "settings.yaml"
    before = path.read_text(encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("os.fdopen", boom)
    with pytest.raises(OSError, match="disk full"):
        save_settings(tmp_path, Settings())

    assert path.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob(".settings.yaml.*")), "temp file must be cleaned up"


def test_atomic_write_cleans_up_when_fsync_target_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cud.config.settings import _atomic_write

    target = tmp_path / "out.txt"
    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        _atomic_write(target, "data")
    assert not target.exists()
    assert not list(tmp_path.glob(".out.txt.*"))


def boom(*_args: object, **_kwargs: object) -> None:
    raise OSError("rename failed")


def test_validate_subagents_is_writer_side_only() -> None:
    """Subagent checks must not stop an otherwise startable agent from booting."""
    settings = Settings()
    settings.subagents = [SubAgentSettings(name="a"), SubAgentSettings(name="a")]
    with pytest.raises(ValueError, match="duplicate subagent name"):
        validate_subagents(settings)

    settings.subagents = [SubAgentSettings(name="", description="d")]
    with pytest.raises(ValueError, match=r"subagent\.name is required"):
        validate_subagents(settings)

    settings.subagents = [SubAgentSettings(name="a", context_window=-1)]
    with pytest.raises(ValueError, match="must not be negative"):
        validate_subagents(settings)

    # load_settings only enforces the start-up invariants.
    settings.subagents = [SubAgentSettings(name="a"), SubAgentSettings(name="a")]
    validate_settings(settings)


def test_save_settings_rejects_bad_subagents(tmp_path: Path) -> None:
    settings = Settings()
    settings.subagents = [SubAgentSettings(name=""), SubAgentSettings(name="a")]
    with pytest.raises(ValueError, match=r"subagent\.name is required"):
        save_settings(tmp_path, settings)


def test_settings_yaml_without_unknown_keys_still_loads(tmp_path: Path) -> None:
    (tmp_path / "settings.yaml").write_text(
        "model:\n  name: qwen\n  future_option: 1\n", encoding="utf-8"
    )
    assert load_settings(tmp_path).model.name == "qwen"


def test_load_settings_treats_null_subagent_context_as_inherit(tmp_path: Path) -> None:
    """Regression: `context_window:` must not hard-fail the whole agent."""
    (tmp_path / "settings.yaml").write_text(
        "subagents:\n  - name: a\n    context_window:\n", encoding="utf-8"
    )
    assert load_settings(tmp_path).subagents[0].context_window == 0


def test_load_settings_rejects_non_list_mcp_servers(tmp_path: Path) -> None:
    (tmp_path / "settings.yaml").write_text(
        "subagents:\n  - name: a\n    mcp_servers: 5\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="'mcp_servers' must be a list"):
        load_settings(tmp_path)


def test_save_settings_rejects_non_integer_subagent_context(tmp_path: Path) -> None:
    settings = Settings()
    settings.subagents = [SubAgentSettings(name="a", context_window=None)]  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be an integer"):
        save_settings(tmp_path, settings)
