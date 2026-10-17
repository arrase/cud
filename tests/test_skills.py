import argparse
import io
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from cud.config.paths import agent_home
from cud.config.scaffold import create_agent
from cud.tools.cli import cmd_tools_install, cmd_tools_list, register_tools_commands
from cud.tools.skills import (
    SkillCard,
    _first_non_empty_line,
    discover_skills,
    save_skills,
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
    assert card.body == "Documentation body"


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


def test_cmd_tools_install_missing_source(tmp_path: Path, agent_dir: Path) -> None:
    args = argparse.Namespace(agent="test-agent", path=str(tmp_path / "missing.md"))
    exit_code = cmd_tools_install(args)
    assert exit_code == 2


def test_cmd_tools_install_nonexistent_agent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Agent 'ghost' does not exist"):
        cmd_tools_install(argparse.Namespace(agent="ghost", path=str(tmp_path / "x.md")))
    assert not agent_home("ghost").exists()


def test_cmd_tools_list(agent_dir: Path) -> None:
    assert cmd_tools_list(argparse.Namespace(agent="test-agent")) == 0
    assert cmd_tools_list(argparse.Namespace(agent="no-skills-agent")) == 0


def test_cmd_tools_install_local_file(tmp_path: Path, agent_dir: Path) -> None:
    source_file = tmp_path / "calculator.md"
    source_file.write_text("# Calculator skill", encoding="utf-8")

    args = argparse.Namespace(agent="test-agent", path=str(source_file))
    exit_code = cmd_tools_install(args)
    assert exit_code == 0

    installed = agent_dir / "workspace" / "skills" / "calculator" / "SKILL.md"
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == "# Calculator skill"


def test_cmd_tools_install_local_directory(tmp_path: Path, agent_dir: Path) -> None:
    source_dir = tmp_path / "formatter"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("# Formatter", encoding="utf-8")

    args = argparse.Namespace(agent="test-agent", path=str(source_dir))
    exit_code = cmd_tools_install(args)
    assert exit_code == 0

    installed = agent_dir / "workspace" / "skills" / "formatter" / "SKILL.md"
    assert installed.is_file()


def test_cmd_tools_install_already_exists(tmp_path: Path, agent_dir: Path) -> None:
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
    assert _first_non_empty_line("# Header 1\n# Header 2\n   \n") == ""


def test_cmd_tools_install_url_success(agent_dir: Path) -> None:
    mock_resp = io.BytesIO(b"# Remote skill content\n")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        args = argparse.Namespace(
            agent="test-agent",
            path="https://example.com/skills/remote_helper.md",
        )
        assert cmd_tools_install(args) == 0

    installed = agent_dir / "workspace" / "skills" / "remote_helper" / "SKILL.md"
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == "# Remote skill content\n"


def test_cmd_tools_install_url_already_exists(agent_dir: Path) -> None:
    target = agent_dir / "workspace" / "skills" / "remote_helper"
    target.mkdir(parents=True)

    args = argparse.Namespace(
        agent="test-agent",
        path="https://example.com/skills/remote_helper.md",
    )
    assert cmd_tools_install(args) == 2


def test_cmd_tools_install_url_download_error(agent_dir: Path) -> None:
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


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_skill_card_is_hashable_and_comparable() -> None:
    """Regression: `frozen=True` generates __hash__, and hash=False on metadata
    allows both value equality and hashing."""
    card1 = SkillCard(name="n", description="d", path=Path("/x/SKILL.md"), metadata={"a": 1}, body="b")
    card2 = SkillCard(name="n", description="d", path=Path("/x/SKILL.md"), metadata={"a": 1}, body="b")
    assert isinstance(hash(card1), int)
    assert card1 == card2


def test_save_skills_writes_and_removes(tmp_path: Path) -> None:
    entries = [
        {
            "name": "s1",
            "description": "desc1",
            "dir_name": "s1",
            "body": "Body 1",
            "metadata": {},
        },
        {
            "name": "bad",
            "description": "bad",
            "dir_name": "_unsafe",
            "body": "Body bad",
            "metadata": {},
        },
    ]
    old_dir = tmp_path / "to-delete"
    old_dir.mkdir()
    (old_dir / "SKILL.md").write_text("old", encoding="utf-8")

    skipped = save_skills(tmp_path, entries, deleted_dirs=["to-delete", "_unsafe"])
    assert skipped == ["_unsafe"]
    assert not old_dir.exists()
    cards = discover_skills(tmp_path)
    assert len(cards) == 1
    assert cards[0].name == "s1"
    assert cards[0].body == "Body 1"


def test_single_file_install_reports_already_exists(tmp_path: Path) -> None:
    """Regression: the single-.md branch raised an unhandled FileExistsError
    instead of returning the documented exit code 2."""
    create_agent("dup-agent")
    source = tmp_path / "myskill.md"
    source.write_text("---\nname: myskill\ndescription: d\n---\nbody", encoding="utf-8")

    args = argparse.Namespace(agent="dup-agent", path=str(source))
    assert cmd_tools_install(args) == 0
    assert cmd_tools_install(args) == 2


def test_install_rejects_unsafe_local_name(tmp_path: Path) -> None:
    """Regression: a single .md file's stem became a directory name unchecked."""
    target_agent = create_agent("esc-agent")
    source = tmp_path / "-evil.md"
    source.write_text("---\nname: evil\ndescription: d\n---\nbody", encoding="utf-8")

    args = argparse.Namespace(agent="esc-agent", path=str(source))
    assert cmd_tools_install(args) == 2
    assert not (target_agent / "workspace" / "-evil").exists()


def test_unreadable_skill_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_bytes(b"---\nname: \xff\n---\nx")
    good = tmp_path / "good"
    good.mkdir()
    (good / "SKILL.md").write_text("---\nname: good\ndescription: d\n---\nbody", encoding="utf-8")
    assert [c.name for c in discover_skills(tmp_path)] == ["good"]


def test_remote_install_rejects_unsafe_derived_name() -> None:
    """Regression: the directory name was taken from the URL with no validation."""
    target_agent = create_agent("rem-agent")
    skills_dir = target_agent / "workspace" / "skills"
    before = {p.name for p in skills_dir.iterdir()}
    for url in ("https://example.com/..", "https://example.com/a%2Fb/../../.."):
        args = argparse.Namespace(agent="rem-agent", path=url)
        assert cmd_tools_install(args) == 2, url
    assert {p.name for p in skills_dir.iterdir()} == before


def test_remote_install_rejects_oversized_or_binary_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_agent("big-agent")
    payload = b"x" * (512 * 1024 + 1)

    class FakeResponse:
        def read(self, *_args: object) -> bytes:
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr("cud.tools.cli.urllib.request.urlopen", lambda *a, **k: FakeResponse())
    args = argparse.Namespace(agent="big-agent", path="https://example.com/skill.md")
    assert cmd_tools_install(args) == 1

    payload = b"\xff\xfeinvalid utf-8"
    assert cmd_tools_install(args) == 1
