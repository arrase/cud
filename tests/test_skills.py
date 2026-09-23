import argparse
import io
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pydantic.root_model
import pytest

from cud.config.paths import agent_home
from cud.config.scaffold import create_agent
from cud.tools.skills import (
    SkillCard,
    _first_non_empty_line,
    cmd_tools_install,
    discover_skills,
    register_tools_commands,
)


def test_discover_skills_nonexistent(tmp_path: Path) -> None:
    assert discover_skills(tmp_path / "nonexistent") == []


def test_discover_skills_empty(tmp_path: Path) -> None:
    assert discover_skills(tmp_path) == []


def test_discover_skills_with_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "web-search"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: web-search\ndescription: Search the web\n---\nDocumentation body\n",
        encoding="utf-8",
    )

    cards = discover_skills(tmp_path)
    assert len(cards) == 1
    card = cards[0]
    assert isinstance(card, SkillCard)
    assert card.name == "web-search"
    assert card.description == "Search the web"
    assert card.path == skill_file
    assert card.metadata["name"] == "web-search"


def test_discover_skills_without_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "custom-helper"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "# Header\n\nFirst line of description.\nSecond line.\n",
        encoding="utf-8",
    )

    cards = discover_skills(tmp_path)
    assert len(cards) == 1
    card = cards[0]
    assert card.name == "custom-helper"
    assert card.description == "First line of description."


def test_cmd_tools_install_missing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")
    args = argparse.Namespace(agent="test-agent", path=str(tmp_path / "missing.md"))
    exit_code = cmd_tools_install(args)
    assert exit_code == 2


def test_cmd_tools_install_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")
    source_file = tmp_path / "calculator.md"
    source_file.write_text("# Calculator skill", encoding="utf-8")

    args = argparse.Namespace(agent="test-agent", path=str(source_file))
    exit_code = cmd_tools_install(args)
    assert exit_code == 0

    installed = (
        agent_home("test-agent") / "workspace" / "skills" / "calculator" / "SKILL.md"
    )
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == "# Calculator skill"


def test_cmd_tools_install_local_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")
    source_dir = tmp_path / "formatter"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("# Formatter", encoding="utf-8")

    args = argparse.Namespace(agent="test-agent", path=str(source_dir))
    exit_code = cmd_tools_install(args)
    assert exit_code == 0

    installed = (
        agent_home("test-agent") / "workspace" / "skills" / "formatter" / "SKILL.md"
    )
    assert installed.is_file()


def test_cmd_tools_install_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")
    source_dir = tmp_path / "existing_skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")

    args = argparse.Namespace(agent="test-agent", path=str(source_dir))
    assert cmd_tools_install(args) == 0
    # Installing again should fail with code 2
    assert cmd_tools_install(args) == 2


def test_discover_skills_read_exception(tmp_path: Path) -> None:
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("invalid", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        assert discover_skills(tmp_path) == []


def test_first_non_empty_line_only_headers() -> None:
    assert _first_non_empty_line("# Header 1\n# Header 2\n   \n") is None


def test_cmd_tools_install_url_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")

    mock_resp = io.BytesIO(b"# Remote skill content\n")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        args = argparse.Namespace(
            agent="test-agent",
            path="https://example.com/skills/remote_helper.md",
        )
        assert cmd_tools_install(args) == 0

    installed = agent_home("test-agent") / "workspace" / "skills" / "remote_helper" / "SKILL.md"
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == "# Remote skill content\n"


def test_cmd_tools_install_url_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")

    target = agent_home("test-agent") / "workspace" / "skills" / "remote_helper"
    target.mkdir(parents=True)

    args = argparse.Namespace(
        agent="test-agent",
        path="https://example.com/skills/remote_helper.md",
    )
    assert cmd_tools_install(args) == 2


def test_cmd_tools_install_url_download_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network error")):
        args = argparse.Namespace(
            agent="test-agent",
            path="https://example.com/skills/failing_skill.md",
        )
        assert cmd_tools_install(args) == 1


def test_register_tools_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_tools_commands(sub)
    args = parser.parse_args(["tools", "install", "my-agent", "/path"])
    assert args.agent == "my-agent"
    assert args.path == "/path"
