import argparse
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from cud.tools.cli import _task_destination, cmd_task_list, register_tasks_commands
from cud.tools.tasks import (
    TaskCard,
    _int_or_none,
    discover_tasks,
    is_valid_schedule,
    next_run,
    save_tasks,
)


def test_int_or_none() -> None:
    assert _int_or_none(None) is None
    assert _int_or_none(True) is None
    assert _int_or_none(False) is None
    assert _int_or_none("123") == 123
    assert _int_or_none(456) == 456
    assert _int_or_none("invalid") is None
    assert _int_or_none([]) is None


def test_is_valid_schedule() -> None:
    assert is_valid_schedule("0 9 * * *") is True
    assert is_valid_schedule("") is False
    assert is_valid_schedule("not a cron") is False


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


def test_cmd_task_list(agent_dir: Path) -> None:
    args = argparse.Namespace(agent="test-agent")

    # Empty list
    assert cmd_task_list(args) == 0

    # With tasks
    tasks_dir = agent_dir / "workspace" / "tasks"
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


def test_register_tasks_commands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_tasks_commands(sub)

    args = parser.parse_args(["task", "list", "my-agent"])
    assert args.agent == "my-agent"


def test_save_tasks_writes_and_removes(tmp_path: Path) -> None:
    entries = [
        {
            "name": "daily",
            "description": "d",
            "schedule": "0 9 * * *",
            "channel_id": 10,
            "user_id": 20,
            "enabled": True,
            "prompt": "do it",
            "dir_name": "daily",
        },
        {
            "name": "bad",
            "description": "",
            "schedule": "0 9 * * *",
            "channel_id": None,
            "user_id": None,
            "enabled": True,
            "prompt": "do it",
            "dir_name": "_unsafe",
        },
    ]
    old = tmp_path / "gone"
    old.mkdir()
    (old / "TASK.md").write_text("old", encoding="utf-8")

    skipped = save_tasks(tmp_path, entries, deleted_dirs=["gone", "_unsafe"])
    assert skipped == ["_unsafe"]
    assert not old.exists()
    cards = discover_tasks(tmp_path)
    assert len(cards) == 1
    assert cards[0].name == "daily"


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def _write_task(tasks_dir: Path, dir_name: str, frontmatter: str, body: str = "do it") -> None:
    d = tasks_dir / dir_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "TASK.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def test_schedule_must_be_a_valid_cron_string(tmp_path: Path) -> None:
    """Regression: `schedule: 5` reached croniter and raised AttributeError,
    which escaped the scheduler's narrow except and looped forever."""
    _write_task(tmp_path, "nonstring", "name: nonstring\nschedule: 5")
    _write_task(tmp_path, "garbage", "name: garbage\nschedule: 'not a cron'")
    _write_task(tmp_path, "listy", "name: listy\nschedule: [1, 2]")
    _write_task(tmp_path, "ok", "name: ok\nschedule: '0 9 * * *'")

    discovered = discover_tasks(tmp_path)
    assert [t.name for t in discovered] == ["ok"], [t.name for t in discovered]


def test_null_description_becomes_empty_string(tmp_path: Path) -> None:
    """Regression: a bare `description:` key parsed to None, crashing the GUI."""
    _write_task(tmp_path, "a", "name: a\ndescription:\nschedule: '* * * * *'")
    card = discover_tasks(tmp_path)[0]
    assert card.description == ""


def test_task_card_is_hashable(tmp_path: Path) -> None:
    _write_task(tmp_path, "a", "name: a\nschedule: '* * * * *'")
    assert len({discover_tasks(tmp_path)[0]}) == 1


def test_next_run_returns_none_for_never_firing_expression() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert next_run("0 0 30 2 *", now) is None
    assert next_run("not a cron", now) is None
    assert next_run("0 9 * * *", now) is not None


def test_task_destination_handles_zero_ids(tmp_path: Path) -> None:
    """Regression: `channel_id: 0` is falsy and silently fell through to DM."""
    _write_task(tmp_path, "a", "name: a\nschedule: '* * * * *'\nchannel_id: 0")
    card = discover_tasks(tmp_path)[0]
    assert card.channel_id == 0
    assert _task_destination(card) == "channel:0"


def test_unreadable_task_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "TASK.md").write_bytes(b"---\nname: \xff\n---\nx")
    _write_task(tmp_path, "good", "name: good\nschedule: '* * * * *'")
    assert [t.name for t in discover_tasks(tmp_path)] == ["good"]
