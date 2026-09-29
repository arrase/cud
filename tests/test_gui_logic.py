"""Tests for the pure reconciliation/serialisation logic behind the Qt widgets.

These guard the paths where a GUI save could destroy on-disk user data, so they
are deliberately kept free of widget construction and run headless.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6", reason="the GUI extra is not installed")

# Importing a QWidget subclass is safe without a QApplication as long as we
# only call static/module-level helpers; the offscreen platform keeps any
# incidental QWidget instantiation harmless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cud.config.settings import SubAgentMCPServer
from cud.gui.widgets.mcp_tab import _parse_env_text
from cud.gui.widgets.subagents_tab import (
    SubagentsTab,
    _format_mcp_server,
)
from cud.gui.widgets.tasks_tab import (
    _parse_optional_int,
    _remove_deleted_tasks,
    _write_task_entry,
)

# ---------------------------------------------------------------------------
# Subagent MCP server round-trip (env and quoted args must survive)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "server",
    [
        SubAgentMCPServer(name="pg", command="npx", args=["-y", "@mcp/pg"], env={"PASSWORD": "s3cr3t"}),
        SubAgentMCPServer(name="x", command="echo", args=["a b", "c'd"], env={}),
        SubAgentMCPServer(name="y", command="c", args=[], env={"A": "1", "B": "2"}),
        SubAgentMCPServer(name="with space", command="c d", args=["--flag"], env={}),
    ],
)
def test_mcp_server_text_roundtrip_is_lossless(server: SubAgentMCPServer) -> None:
    assert SubagentsTab._parse_mcp_servers(_format_mcp_server(server)) == [server]


def test_mcp_server_text_preserves_env_on_update() -> None:
    """Regression: env used to be dropped on every Update, silently losing secrets."""
    original = SubAgentMCPServer(name="pg", command="npx", args=["-y"], env={"TOKEN": "abc"})
    reparsed = SubagentsTab._parse_mcp_servers(_format_mcp_server(original))
    assert reparsed[0].env == {"TOKEN": "abc"}


def test_mcp_server_text_skips_malformed_lines() -> None:
    """Lines with too few fields or unbalanced quotes are skipped, not guessed."""
    text = "\n".join(["good cmd arg", "onlyname", "", "unbalanced 'quote cmd"])
    assert [s.name for s in SubagentsTab._parse_mcp_servers(text)] == ["good"]


# ---------------------------------------------------------------------------
# Task directory reconciliation
# ---------------------------------------------------------------------------


def _task_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "name": "daily",
        "description": "d",
        "schedule": "0 9 * * *",
        "channel_id": None,
        "user_id": None,
        "enabled": True,
        "prompt": "do it",
        "dir_name": "daily",
    }
    entry.update(overrides)
    return entry


def test_write_task_entry_creates_task_file(tmp_path: Path) -> None:
    from cud.tools.tasks import discover_tasks

    _write_task_entry(tmp_path, _task_entry(channel_id=42))
    cards = discover_tasks(tmp_path)
    assert [c.name for c in cards] == ["daily"]
    assert cards[0].channel_id == 42
    assert cards[0].prompt == "do it"


@pytest.mark.parametrize("bad_name", ["..", ".", "a/b", "/abs", "-x"])
def test_write_task_entry_rejects_unsafe_dir_name(tmp_path: Path, bad_name: str) -> None:
    """Regression: the name became a path segment and escaped the tasks dir."""
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    with pytest.raises(ValueError, match="alphanumeric"):
        _write_task_entry(tmp_path, _task_entry(dir_name=bad_name))
    # Nothing may appear anywhere under tmp_path, nor next to it.
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    assert not (tmp_path.parent / "TASK.md").exists()


def test_remove_deleted_tasks_only_touches_the_explicit_set(tmp_path: Path) -> None:
    """Regression: sweeping "not in memory" deleted undiscoverable tasks."""
    _write_task_entry(tmp_path, _task_entry(dir_name="keep"))
    _write_task_entry(tmp_path, _task_entry(dir_name="drop"))

    _remove_deleted_tasks(tmp_path, {"drop"})

    assert (tmp_path / "keep" / "TASK.md").exists()
    assert not (tmp_path / "drop").exists()


def test_remove_deleted_tasks_ignores_symlinks(tmp_path: Path) -> None:
    elsewhere = tmp_path.parent / "outside"
    elsewhere.mkdir(exist_ok=True)
    (elsewhere / "keep.txt").write_text("data", encoding="utf-8")
    (tmp_path / "link").symlink_to(elsewhere)

    _remove_deleted_tasks(tmp_path, {"link"})

    assert (elsewhere / "keep.txt").exists(), "rmtree must not follow a symlink"


# ---------------------------------------------------------------------------
# Numeric field parsing
# ---------------------------------------------------------------------------


def test_parse_optional_int_rejects_typos() -> None:
    """Regression: a typo silently turned a channel task into a Console task."""
    with pytest.raises(ValueError, match="Channel ID must be a number"):
        _parse_optional_int("12ab", "Channel ID")


def test_parse_optional_int_accepts_blank_and_digits() -> None:
    assert _parse_optional_int("   ", "User ID") is None
    assert _parse_optional_int(" 42 ", "User ID") == 42


def test_parse_env_text_ignores_blank_lines() -> None:
    assert _parse_env_text("A=1\n\nB=2\n") == {"A": "1", "B": "2"}


# ---------------------------------------------------------------------------
# Regression tests for the reconciliation guards
# ---------------------------------------------------------------------------


def _skill_entry(dir_name: str, **overrides: Any) -> dict[str, Any]:
    entry = {
        "name": dir_name,
        "description": "d",
        "dir_name": dir_name,
        "body": "body",
        "metadata": {},
        "unreadable": False,
    }
    entry.update(overrides)
    return entry


def test_deleted_dir_is_not_removed_when_recreated(tmp_path: Path) -> None:
    """Regression: delete-then-re-create wiped the newly created entry."""
    from cud.gui.widgets.skills_tab import SkillsTab

    tab = SkillsTab.__new__(SkillsTab)  # logic-only, no Qt widget construction
    tab._skills_data = [_skill_entry("alpha")]
    tab._deleted_dirs = {"alpha"}
    tab._selected_index = 0

    skills_dir = tmp_path / "workspace" / "skills"
    _write_skill(skills_dir, "alpha", "old body")

    skipped = tab.save_data(tmp_path)
    assert skipped == []
    assert (skills_dir / "alpha" / "SKILL.md").read_text(encoding="utf-8").endswith("body")


def test_unsafe_preexisting_dir_is_skipped_not_fatal(tmp_path: Path) -> None:
    """Regression: one unusable name aborted the whole save, silently dropping
    unrelated deletions and every other tab's edits."""
    from cud.gui.widgets.skills_tab import SkillsTab

    tab = SkillsTab.__new__(SkillsTab)
    tab._skills_data = [_skill_entry("_draft"), _skill_entry("keep")]
    tab._deleted_dirs = {"gone"}
    tab._selected_index = 0

    skills_dir = tmp_path / "workspace" / "skills"
    _write_skill(skills_dir, "_draft", "original draft")
    _write_skill(skills_dir, "gone", "to be removed")

    skipped = tab.save_data(tmp_path)
    assert skipped == ["_draft"]
    assert "original draft" in (skills_dir / "_draft" / "SKILL.md").read_text(encoding="utf-8")
    assert (skills_dir / "keep" / "SKILL.md").exists(), "unrelated skill must still be written"
    assert not (skills_dir / "gone").exists(), "unrelated deletion must still happen"


def test_unreadable_skill_is_never_overwritten(tmp_path: Path) -> None:
    """Regression: a transient read error replaced the body with an empty string."""
    from cud.gui.widgets.skills_tab import SkillsTab

    tab = SkillsTab.__new__(SkillsTab)
    tab._skills_data = [_skill_entry("bad", unreadable=True)]
    tab._deleted_dirs = set()
    tab._selected_index = 0

    skills_dir = tmp_path / "workspace" / "skills"
    _write_skill(skills_dir, "bad", "precious content")
    assert tab.save_data(tmp_path) == []
    assert "precious content" in (skills_dir / "bad" / "SKILL.md").read_text(encoding="utf-8")


def test_env_values_with_special_characters_roundtrip() -> None:
    """Regression: env values containing ',' were silently truncated."""
    server = SubAgentMCPServer(
        name="pg", command="npx", args=["-y"], env={"DSN": "a,b c=d", "PLAIN": "x"}
    )
    assert SubagentsTab._parse_mcp_servers(_format_mcp_server(server)) == [server]


def _write_skill(skills_dir: Path, dir_name: str, body: str) -> None:
    d = skills_dir / dir_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {dir_name}\n---\n{body}", encoding="utf-8")
