import argparse
from pathlib import Path
from unittest.mock import patch

import pydantic.root_model
import pytest

from cud.config.paths import agent_home
from cud.config.scaffold import create_agent
from cud.tools.tasks import (
    TaskCard,
    _int_or_none,
    cmd_task_list,
    discover_tasks,
    register_task_commands,
)


def test_int_or_none() -> None:
    assert _int_or_none(None) is None
    assert _int_or_none("123") == 123
    assert _int_or_none(456) == 456
    assert _int_or_none("invalid") is None
    assert _int_or_none([]) is None


def test_discover_tasks_nonexistent(tmp_path: Path) -> None:
    assert discover_tasks(tmp_path / "nonexistent") == []


def test_discover_tasks_empty(tmp_path: Path) -> None:
    assert discover_tasks(tmp_path) == []


def test_discover_tasks_valid(tmp_path: Path) -> None:
    task_dir = tmp_path / "daily-report"
    task_dir.mkdir()
    task_file = task_dir / "TASK.md"
    task_file.write_text(
        "---\n"
        "name: daily-report\n"
        "description: Generate daily report\n"
        "schedule: '0 9 * * *'\n"
        "channel_id: '123456789'\n"
        "user_id: 987654321\n"
        "enabled: true\n"
        "---\n"
        "Summarize daily progress\n",
        encoding="utf-8",
    )

    cards = discover_tasks(tmp_path)
    assert len(cards) == 1
    card = cards[0]
    assert isinstance(card, TaskCard)
    assert card.name == "daily-report"
    assert card.description == "Generate daily report"
    assert card.schedule == "0 9 * * *"
    assert card.channel_id == 123456789
    assert card.user_id == 987654321
    assert card.enabled is True
    assert card.prompt == "Summarize daily progress"
    assert card.path == task_file


def test_discover_tasks_missing_schedule(tmp_path: Path) -> None:
    task_dir = tmp_path / "no-schedule"
    task_dir.mkdir()
    (task_dir / "TASK.md").write_text(
        "---\nname: no-sched\n---\nPrompt without schedule",
        encoding="utf-8",
    )
    assert discover_tasks(tmp_path) == []


def test_discover_tasks_missing_prompt(tmp_path: Path) -> None:
    task_dir = tmp_path / "no-prompt"
    task_dir.mkdir()
    (task_dir / "TASK.md").write_text(
        "---\nschedule: '0 * * * *'\n---\n   \n",
        encoding="utf-8",
    )
    assert discover_tasks(tmp_path) == []


def test_cmd_task_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUD_HOME", str(tmp_path))
    create_agent("test-agent")
    args = argparse.Namespace(agent="test-agent")

    # Empty list
    assert cmd_task_list(args) == 0

    # With tasks
    tasks_dir = agent_home("test-agent") / "workspace" / "tasks"
    task1 = tasks_dir / "task1"
    task1.mkdir()
    (task1 / "TASK.md").write_text(
        "---\nschedule: '* * * * *'\nchannel_id: 111\n---\nDo task 1",
        encoding="utf-8",
    )
    task2 = tasks_dir / "task2"
    task2.mkdir()
    (task2 / "TASK.md").write_text(
        "---\nschedule: 'invalid cron'\nuser_id: 222\nenabled: true\n---\nDo task 2",
        encoding="utf-8",
    )
    task3 = tasks_dir / "task3"
    task3.mkdir()
    (task3 / "TASK.md").write_text(
        "---\nschedule: '0 0 * * *'\nenabled: false\n---\nDo task 3",
        encoding="utf-8",
    )

    assert cmd_task_list(args) == 0


def test_discover_tasks_exception(tmp_path: Path) -> None:
    task_dir = tmp_path / "broken"
    task_dir.mkdir()
    (task_dir / "TASK.md").write_text("invalid", encoding="utf-8")

    with patch("cud.tools.tasks._parse_task_file", side_effect=RuntimeError("parse error")):
        assert discover_tasks(tmp_path) == []


def test_register_task_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_task_commands(sub)

    args = parser.parse_args(["task", "list", "my-agent"])
    assert args.agent == "my-agent"
