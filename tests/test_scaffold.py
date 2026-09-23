import sqlite3
from pathlib import Path

import pytest

from cud.config.scaffold import create_agent, delete_agent, list_agents


def test_create_agent_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    target = create_agent("test-agent")
    assert target.exists()
    assert (target / "AGENT.md").is_file()
    assert (target / "MEMORY.md").is_file()
    assert (target / "settings.yaml").is_file()
    assert (target / "mcp.json").is_file()
    assert (target / "history.db").is_file()
    assert (target / "workspace" / "skills").is_dir()
    assert (target / "workspace" / "tasks").is_dir()
    assert (target / "workspace" / "skills" / "create-task" / "SKILL.md").is_file()

    with sqlite3.connect(target / "history.db") as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cud_meta'"
        )
        assert cursor.fetchone() is not None
    conn.close()


def test_create_agent_invalid_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="only the default template is available"):
        create_agent("agent-bad", template="non-default")


def test_create_agent_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("existing-agent")
    with pytest.raises(FileExistsError, match="agent already exists"):
        create_agent("existing-agent")


def test_create_agent_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    target = create_agent("overwrite-agent")
    agent_file = target / "AGENT.md"
    agent_file.write_text("Custom prompt", encoding="utf-8")

    create_agent("overwrite-agent", overwrite=True)
    assert agent_file.read_text(encoding="utf-8") != "Custom prompt"


def test_list_agents_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    assert list_agents() == []


def test_list_agents_populated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    p1 = create_agent("agent-1")
    p2 = create_agent("agent-2")
    assert list_agents() == [p1, p2]


def test_delete_agent_requires_yes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("agent-to-delete")
    with pytest.raises(PermissionError, match="delete_agent requires yes=True"):
        delete_agent("agent-to-delete", yes=False)


def test_delete_agent_nonexistent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        delete_agent("no-such-agent", yes=True)


def test_delete_agent_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    target = create_agent("agent-to-delete")
    assert target.exists()
    deleted = delete_agent("agent-to-delete", yes=True)
    assert deleted == target
    assert not target.exists()
