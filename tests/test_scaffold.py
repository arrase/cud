import sqlite3
from pathlib import Path

import pytest

from cud.config import scaffold
from cud.config.paths import agent_home
from cud.config.scaffold import _init_history_db, create_agent, delete_agent, list_agents


def test_create_agent_default() -> None:
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
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cud_meta'")
        assert cursor.fetchone() is not None
    conn.close()


def test_create_agent_invalid_template() -> None:
    with pytest.raises(ValueError, match="only the default template is available"):
        create_agent("agent-bad", template="non-default")


def test_create_agent_already_exists() -> None:
    create_agent("existing-agent")
    with pytest.raises(FileExistsError, match="agent already exists"):
        create_agent("existing-agent")


def test_create_agent_overwrite() -> None:
    target = create_agent("overwrite-agent")
    agent_file = target / "AGENT.md"
    agent_file.write_text("Custom prompt", encoding="utf-8")

    create_agent("overwrite-agent", overwrite=True)
    assert agent_file.read_text(encoding="utf-8") != "Custom prompt"


def test_list_agents_empty() -> None:
    assert list_agents() == []


def test_list_agents_populated() -> None:
    p1 = create_agent("agent-1")
    p2 = create_agent("agent-2")
    assert list_agents() == [p1, p2]


def test_delete_agent_nonexistent() -> None:
    with pytest.raises(FileNotFoundError):
        delete_agent("no-such-agent")


def test_delete_agent_success() -> None:
    target = create_agent("agent-to-delete")
    assert target.exists()
    deleted = delete_agent("agent-to-delete")
    assert deleted == target
    assert not target.exists()


def test_create_agent_rolls_back_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a mid-loop failure used to leave a half-built agent that
    list_agents() then reported as a real, permanently broken agent."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(scaffold, "_copy_bundled_skills", boom)

    with pytest.raises(OSError, match="disk full"):
        scaffold.create_agent("halfbaked")

    assert not agent_home("halfbaked").exists()
    assert scaffold.list_agents() == []


def test_create_agent_does_not_delete_existing_agent_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed --overwrite must not rmtree the user's existing agent."""
    target = scaffold.create_agent("keeper")
    (target / "custom.md").write_text("mine", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("nope")

    monkeypatch.setattr(scaffold, "_copy_bundled_skills", boom)
    with pytest.raises(OSError):
        scaffold.create_agent("keeper", overwrite=True)

    assert (target / "custom.md").read_text(encoding="utf-8") == "mine"


def test_init_history_db_closes_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: `with sqlite3.connect(...)` manages the transaction, not the
    connection, so the handle leaked if a statement raised."""
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(path, *args, **kwargs):
        conn = real_connect(path, *args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr("cud.config.scaffold.sqlite3.connect", spy)
    _init_history_db(tmp_path / "history.db")
    assert opened, "the spy should have intercepted connect()"
    assert all(_is_closed(conn) for conn in opened)


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False
