"""Periodic tasks manager with full CRUD for TASK.md schedule configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from cud.config.paths import validate_safe_name
from cud.gui.core.styles import (
    ACTION_BTN_ADD,
    ACTION_BTN_DELETE,
    ACTION_BTN_UPDATE,
    create_action_button,
    create_readonly_table,
    create_tab_header,
    make_table_item,
    monospace_font,
)
from cud.tools.tasks import (
    discover_tasks,
    is_valid_schedule,
    next_run,
    save_tasks,
)


def _parse_optional_int(text: str, label: str) -> int | None:
    """Parse an optional integer field; raise on a non-numeric value."""
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number, got {text!r}") from exc


class TasksTab(QWidget):
    """View to list, create, edit, and delete scheduled tasks with cron expressions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks_data: list[dict[str, Any]] = []
        self._selected_index: int = -1
        self._deleted_dirs: set[str] = set()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        create_tab_header(
            self.main_layout,
            "Scheduled Tasks (Cron)",
            "Scheduled tasks allow the agent to execute periodic workflows automatically. "
            "Each task is defined within the 'workspace/tasks/' directory using a TASK.md file with YAML frontmatter.",
        )

        # Split layout
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # --- Left Column: Table + Action Buttons ---
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.table = create_readonly_table(
            ["Name", "Cron / Frequency", "Recipient", "Status", "Next Run Time"],
            stretch_column=2,
        )
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.left_col.addWidget(self.table, 1)

        # Action Buttons
        self.table_actions = QHBoxLayout()

        self.btn_add = create_action_button("➕ Add", ACTION_BTN_ADD, self._on_add_clicked)
        self.btn_delete = create_action_button("❌ Delete", ACTION_BTN_DELETE, self._on_delete_clicked)

        self.table_actions.addWidget(self.btn_add)
        self.table_actions.addWidget(self.btn_delete)
        self.table_actions.addStretch()
        self.left_col.addLayout(self.table_actions)

        self.split_layout.addLayout(self.left_col, 3)

        # --- Right Column: Editor Form ---
        self.right_col = QVBoxLayout()
        self.right_col.setSpacing(8)

        self.group_editor = QGroupBox("Task Editor")
        self.form_layout = QFormLayout(self.group_editor)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., daily-report")

        self.input_schedule = QLineEdit()
        self.input_schedule.setPlaceholderText("e.g., 0 9 * * * (cron expression)")

        self.input_channel_id = QLineEdit()
        self.input_channel_id.setPlaceholderText("Discord channel ID (optional)")

        self.input_user_id = QLineEdit()
        self.input_user_id.setPlaceholderText("Discord user ID for DM (optional)")

        self.chk_enabled = QCheckBox("Enabled")
        self.chk_enabled.setChecked(True)

        self.input_description = QLineEdit()
        self.input_description.setPlaceholderText("Brief description of the task")

        self.input_prompt = QPlainTextEdit()
        self.input_prompt.setPlaceholderText("Task prompt / instructions for the agent...")
        self.input_prompt.setFont(monospace_font())

        self.form_layout.addRow("Name:", self.input_name)
        self.form_layout.addRow("Schedule (Cron):", self.input_schedule)
        self.form_layout.addRow("Channel ID:", self.input_channel_id)
        self.form_layout.addRow("User ID (DM):", self.input_user_id)
        self.form_layout.addRow("Description:", self.input_description)
        self.form_layout.addRow("", self.chk_enabled)
        self.form_layout.addRow("Prompt:", self.input_prompt)

        self.btn_update = create_action_button("💾 Update Task Data", ACTION_BTN_UPDATE, self._on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

    def load_data(self, agent_dir: Path) -> None:
        """Scan tasks directory and populate in-memory data structures."""
        self._tasks_data = [
            {
                "name": task.name,
                "description": task.description,
                "schedule": task.schedule,
                "channel_id": task.channel_id,
                "user_id": task.user_id,
                "enabled": task.enabled,
                "prompt": task.prompt,
                "dir_name": task.path.parent.name,
            }
            for task in discover_tasks(agent_dir / "workspace" / "tasks")
        ]
        self._selected_index = -1
        self._deleted_dirs = set()
        self._refresh_table()

    def save_data(self, agent_dir: Path) -> list[str]:
        """Write all in-memory task data back to disk as TASK.md files."""
        skipped = save_tasks(
            agent_dir / "workspace" / "tasks",
            self._tasks_data,
            self._deleted_dirs,
        )
        self._deleted_dirs = set()
        return skipped

    def _refresh_table(self) -> None:
        """Regenerate the table from in-memory data."""
        self.table.setRowCount(len(self._tasks_data))
        now = datetime.now(UTC)

        for idx, entry in enumerate(self._tasks_data):
            self.table.setItem(idx, 0, make_table_item(entry["name"], color="#FFFFFF", bold=True))
            self.table.setItem(idx, 1, make_table_item(entry["schedule"], color="#3498DB", mono=True))

            if entry["channel_id"] is not None:
                dest_str = f"Discord Channel: {entry['channel_id']}"
            elif entry["user_id"] is not None:
                dest_str = f"User DM: {entry['user_id']}"
            else:
                dest_str = "Console"
            self.table.setItem(idx, 2, make_table_item(dest_str))

            enabled = entry["enabled"]
            enabled_str = "Active ✓" if enabled else "Inactive ✗"
            enabled_color = "#2ECC71" if enabled else "#E74C3C"
            self.table.setItem(idx, 3, make_table_item(enabled_str, color=enabled_color, bold=True))

            next_run_text = "—"
            if enabled:
                upcoming = next_run(entry["schedule"], now)
                next_run_text = upcoming.strftime("%Y-%m-%d %H:%M UTC") if upcoming else "Invalid Cron"
            self.table.setItem(idx, 4, make_table_item(next_run_text, color="#F1C40F"))

        self._clear_form()

    def _clear_form(self) -> None:
        """Reset the editor form."""
        self._selected_index = -1
        self.input_name.clear()
        self.input_schedule.clear()
        self.input_channel_id.clear()
        self.input_user_id.clear()
        self.input_description.clear()
        self.chk_enabled.setChecked(True)
        self.input_prompt.clear()

    def _on_table_selection_changed(self) -> None:
        """Populate the editor form when a table row is selected."""
        selected = self.table.selectedItems()
        if not selected:
            self._clear_form()
            return

        row = selected[0].row()
        if row < 0 or row >= len(self._tasks_data):
            return

        self._selected_index = row
        entry = self._tasks_data[row]
        self.input_name.setText(entry["name"])
        self.input_schedule.setText(entry["schedule"])
        self.input_channel_id.setText(str(entry["channel_id"]) if entry["channel_id"] is not None else "")
        self.input_user_id.setText(str(entry["user_id"]) if entry["user_id"] is not None else "")
        self.input_description.setText(entry["description"])
        self.chk_enabled.setChecked(entry["enabled"])
        self.input_prompt.setPlainText(entry["prompt"])

    def _on_add_clicked(self) -> None:
        """Add a new empty task entry."""
        name, ok = QInputDialog.getText(self, "Create Task", "New task name (used as directory name):")
        if not ok or not name.strip():
            return

        name = name.strip()
        dir_name = name.lower().replace(" ", "-")
        try:
            validate_safe_name(dir_name, "directory name")
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Name", f"Cannot create task:\n\n{exc}")
            return

        existing_dirs = {e["dir_name"] for e in self._tasks_data}
        if dir_name in existing_dirs:
            QMessageBox.warning(self, "Duplicate", f"A task with directory name '{dir_name}' already exists.")
            return

        # Re-creating a previously deleted name: drop the pending deletion.
        self._deleted_dirs.discard(dir_name)

        self._tasks_data.append(
            {
                "name": name,
                "description": "",
                "schedule": "0 * * * *",
                "channel_id": None,
                "user_id": None,
                "enabled": True,
                "prompt": "Describe what the agent should do...",
                "dir_name": dir_name,
            }
        )
        self._refresh_table()
        self.table.selectRow(len(self._tasks_data) - 1)

    def _on_delete_clicked(self) -> None:
        """Delete the currently selected task."""
        if self._selected_index < 0 or self._selected_index >= len(self._tasks_data):
            QMessageBox.warning(self, "Delete Task", "Please select a task from the table.")
            return

        entry = self._tasks_data[self._selected_index]
        confirm = QMessageBox.question(
            self,
            "Delete Task",
            f"Are you sure you want to delete the task '{entry['name']}'?\n\n"
            f"The directory 'workspace/tasks/{entry['dir_name']}/' will be removed on save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._deleted_dirs.add(entry["dir_name"])
            del self._tasks_data[self._selected_index]
            self._refresh_table()

    def _on_update_clicked(self) -> None:
        """Update the currently selected task with values from the form."""
        if self._selected_index < 0 or self._selected_index >= len(self._tasks_data):
            QMessageBox.warning(self, "Update Task", "Please select a task from the table first.")
            return

        name = self.input_name.text().strip()
        schedule = self.input_schedule.text().strip()
        if not name:
            QMessageBox.critical(self, "Data Error", "Task name cannot be empty.")
            return
        if not schedule:
            QMessageBox.critical(self, "Data Error", "Schedule (cron expression) is required.")
            return

        if not is_valid_schedule(schedule):
            QMessageBox.critical(self, "Invalid Cron", f"The cron expression is not valid: {schedule!r}")
            return

        # Parse optional integer fields; a typo must not silently retarget the task
        try:
            channel_id = _parse_optional_int(self.input_channel_id.text(), "Channel ID")
            user_id = _parse_optional_int(self.input_user_id.text(), "User ID")
        except ValueError as exc:
            QMessageBox.critical(self, "Data Error", str(exc))
            return

        entry = self._tasks_data[self._selected_index]
        entry["name"] = name
        entry["schedule"] = schedule
        entry["channel_id"] = channel_id
        entry["user_id"] = user_id
        entry["description"] = self.input_description.text().strip()
        entry["enabled"] = self.chk_enabled.isChecked()
        entry["prompt"] = self.input_prompt.toPlainText()

        saved_row = self._selected_index
        self._refresh_table()
        self.table.selectRow(saved_row)
        QMessageBox.information(self, "Data Updated", f"Task '{name}' updated in memory.")
