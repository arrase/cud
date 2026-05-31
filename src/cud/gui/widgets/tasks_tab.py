"""Periodic tasks manager with full CRUD for TASK.md schedule configurations."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from croniter import croniter
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cud.gui.core.styles import ACTION_BTN_ADD, ACTION_BTN_DELETE, ACTION_BTN_UPDATE, TABLE_STYLE, monospace_font
from cud.tools._frontmatter import render_frontmatter
from cud.tools.tasks import discover_tasks


class TasksTab(QWidget):
    """View to list, create, edit, and delete scheduled tasks with cron expressions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None
        self._tasks_data: list[dict[str, Any]] = []
        self._selected_index: int = -1

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Title / Description
        self.title_label = QLabel("Scheduled Tasks (Cron)")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Scheduled tasks allow the agent to execute periodic workflows automatically. "
            "Each task is defined within the 'workspace/tasks/' directory using a TASK.md file with YAML frontmatter."
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA; line-height: 1.4;")
        self.main_layout.addWidget(self.desc_label)

        # Split layout
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # --- Left Column: Table + Action Buttons ---
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Name", "Cron / Frequency", "Recipient", "Status", "Next Run Time",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.left_col.addWidget(self.table, 1)

        # Action Buttons
        self.table_actions = QHBoxLayout()

        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setStyleSheet(ACTION_BTN_ADD)
        self.btn_add.clicked.connect(self._on_add_clicked)

        self.btn_delete = QPushButton("❌ Delete")
        self.btn_delete.setStyleSheet(ACTION_BTN_DELETE)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

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

        self.btn_update = QPushButton("💾 Update Task Data")
        self.btn_update.setStyleSheet(ACTION_BTN_UPDATE)
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

    def load_data(self, agent_dir: Path) -> None:
        """Scan tasks directory and populate in-memory data structures."""
        self.agent_dir = agent_dir
        self._tasks_data.clear()
        self._selected_index = -1

        tasks_dir = agent_dir / "workspace" / "tasks"
        tasks = discover_tasks(tasks_dir)

        for task in tasks:
            self._tasks_data.append({
                "name": task.name,
                "description": task.description,
                "schedule": task.schedule,
                "channel_id": task.channel_id,
                "user_id": task.user_id,
                "enabled": task.enabled,
                "prompt": task.prompt,
                "dir_name": task.path.parent.name,
            })

        self._refresh_table()

    def save_data(self, agent_dir: Path) -> None:
        """Write all in-memory task data back to disk as TASK.md files."""
        tasks_dir = agent_dir / "workspace" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        written_dirs: set[str] = set()

        for entry in self._tasks_data:
            dir_name = entry["dir_name"]
            task_dir = tasks_dir / dir_name
            task_dir.mkdir(parents=True, exist_ok=True)

            metadata: dict[str, Any] = {
                "name": entry["name"],
                "schedule": entry["schedule"],
                "enabled": entry["enabled"],
            }
            if entry.get("description"):
                metadata["description"] = entry["description"]
            if entry.get("channel_id") is not None:
                metadata["channel_id"] = entry["channel_id"]
            if entry.get("user_id") is not None:
                metadata["user_id"] = entry["user_id"]

            # render_frontmatter already appends the body right after the
            # closing "---", so we prepend a single newline only to ensure
            # a blank line separating frontmatter from body content.
            body = entry["prompt"]
            body = "\n" + body.lstrip("\n")

            content = render_frontmatter(metadata, body)
            (task_dir / "TASK.md").write_text(content, encoding="utf-8")
            written_dirs.add(dir_name)

        # Remove task directories that were deleted from memory, but skip
        # internal directories like __pycache__ or hidden dot-dirs.
        if tasks_dir.exists():
            for existing in tasks_dir.iterdir():
                if not existing.is_dir():
                    continue
                if existing.name.startswith(("__", ".")):
                    continue
                if existing.name not in written_dirs:
                    shutil.rmtree(existing)

    def _refresh_table(self) -> None:
        """Regenerate the table from in-memory data."""
        self.table.setRowCount(len(self._tasks_data))
        now = datetime.now(timezone.utc)

        for idx, entry in enumerate(self._tasks_data):
            # 1. Name
            name_item = QTableWidgetItem(entry["name"])
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(QColor("#FFFFFF"))
            font_bold = name_item.font()
            font_bold.setBold(True)
            name_item.setFont(font_bold)
            self.table.setItem(idx, 0, name_item)

            # 2. Schedule
            schedule_item = QTableWidgetItem(entry["schedule"])
            schedule_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            schedule_item.setForeground(QColor("#3498DB"))
            font_mono = schedule_item.font()
            font_mono.setFamily("monospace")
            schedule_item.setFont(font_mono)
            self.table.setItem(idx, 1, schedule_item)

            # 3. Destination
            if entry.get("channel_id"):
                dest_str = f"Discord Channel: {entry['channel_id']}"
            elif entry.get("user_id"):
                dest_str = f"User DM: {entry['user_id']}"
            else:
                dest_str = "Console"
            dest_item = QTableWidgetItem(dest_str)
            dest_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(idx, 2, dest_item)

            # 4. Enabled/Disabled
            enabled = entry["enabled"]
            enabled_str = "Active ✓" if enabled else "Inactive ✗"
            enabled_item = QTableWidgetItem(enabled_str)
            enabled_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            font_ebold = enabled_item.font()
            font_ebold.setBold(True)
            enabled_item.setFont(font_ebold)
            enabled_item.setForeground(QColor("#2ECC71") if enabled else QColor("#E74C3C"))
            self.table.setItem(idx, 3, enabled_item)

            # 5. Next Run Time
            next_run = "—"
            if enabled:
                try:
                    cron = croniter(entry["schedule"], now)
                    next_run_dt = cron.get_next(datetime)
                    next_run = next_run_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    next_run = "Invalid Cron"
            next_run_item = QTableWidgetItem(next_run)
            next_run_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            next_run_item.setForeground(QColor("#F1C40F"))
            self.table.setItem(idx, 4, next_run_item)

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
        self.input_channel_id.setText(str(entry["channel_id"]) if entry.get("channel_id") is not None else "")
        self.input_user_id.setText(str(entry["user_id"]) if entry.get("user_id") is not None else "")
        self.input_description.setText(entry.get("description", ""))
        self.chk_enabled.setChecked(entry.get("enabled", True))
        self.input_prompt.setPlainText(entry.get("prompt", ""))

    def _on_add_clicked(self) -> None:
        """Add a new empty task entry."""
        name, ok = QInputDialog.getText(
            self, "Create Task", "New task name (used as directory name):"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        dir_name = name.lower().replace(" ", "-")
        existing_dirs = {e["dir_name"] for e in self._tasks_data}
        if dir_name in existing_dirs:
            QMessageBox.warning(self, "Duplicate", f"A task with directory name '{dir_name}' already exists.")
            return

        self._tasks_data.append({
            "name": name,
            "description": "",
            "schedule": "0 * * * *",
            "channel_id": None,
            "user_id": None,
            "enabled": True,
            "prompt": "Describe what the agent should do...",
            "dir_name": dir_name,
        })
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

        # Validate cron expression
        try:
            croniter(schedule)
        except (ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Invalid Cron", f"The cron expression is not valid:\n\n{exc}")
            return

        # Parse optional integer fields
        channel_id = self._parse_optional_int(self.input_channel_id.text())
        user_id = self._parse_optional_int(self.input_user_id.text())

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

    @staticmethod
    def _parse_optional_int(text: str) -> int | None:
        """Parse an optional integer field, returning None if empty or invalid."""
        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
