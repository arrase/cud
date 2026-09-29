"""Skills tab widget for managing local agent skills with full CRUD operations."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
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

from cud.gui.core.styles import (
    ACTION_BTN_ADD,
    ACTION_BTN_DELETE,
    ACTION_BTN_FOLDER,
    ACTION_BTN_UPDATE,
    TABLE_STYLE,
    create_action_button,
    monospace_font,
)
from cud.tools._frontmatter import parse_frontmatter, render_frontmatter
from cud.tools.skills import discover_skills, valid_dir_name
from cud.tools.skills import is_safe_dir_name as _is_safe_dir_name

_log = logging.getLogger(__name__)


class SkillsTab(QWidget):
    """View to list, create, edit, and delete local skills within the agent workspace."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None
        self._skills_data: list[dict[str, Any]] = []
        self._selected_index: int = -1
        self._deleted_dirs: set[str] = set()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Title / Description
        self.title_label = QLabel("Local Skills")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Skills are Markdown instruction folders under the agent's workspace. "
            "Each folder contains a SKILL.md that grants the agent a new capability."
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA; line-height: 1.4;")
        self.main_layout.addWidget(self.desc_label)

        # Split layout: left table, right editor
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # --- Left Column: Table + Action Buttons ---
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Location (Path)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.left_col.addWidget(self.table, 1)

        # Action Buttons
        self.table_actions = QHBoxLayout()

        self.btn_add = create_action_button("➕ Add", ACTION_BTN_ADD, self._on_add_clicked)
        self.btn_delete = create_action_button("❌ Delete", ACTION_BTN_DELETE, self._on_delete_clicked)
        self.btn_open_folder = create_action_button("📂 Open Folder", ACTION_BTN_FOLDER, self._on_open_folder_clicked)

        self.table_actions.addWidget(self.btn_add)
        self.table_actions.addWidget(self.btn_delete)
        self.table_actions.addWidget(self.btn_open_folder)
        self.table_actions.addStretch()
        self.left_col.addLayout(self.table_actions)

        self.split_layout.addLayout(self.left_col, 3)

        # --- Right Column: Editor Form ---
        self.right_col = QVBoxLayout()
        self.right_col.setSpacing(8)

        self.group_editor = QGroupBox("Skill Editor")
        self.form_layout = QFormLayout(self.group_editor)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., web-search")

        self.input_description = QLineEdit()
        self.input_description.setPlaceholderText("Brief description of the skill")

        self.input_body = QPlainTextEdit()
        self.input_body.setPlaceholderText("Skill body content (markdown)...")
        self.input_body.setFont(monospace_font())

        self.form_layout.addRow("Name:", self.input_name)
        self.form_layout.addRow("Description:", self.input_description)
        self.form_layout.addRow("Content (SKILL.md):", self.input_body)

        self.btn_update = QPushButton("💾 Update Skill Data")
        self.btn_update.setStyleSheet(ACTION_BTN_UPDATE)
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

    def load_data(self, agent_dir: Path) -> None:
        """Scan skills directory and populate the in-memory data and table."""
        self.agent_dir = agent_dir
        self._skills_data.clear()
        self._selected_index = -1
        self._deleted_dirs = set()

        skills_dir = agent_dir / "workspace" / "skills"
        skills = discover_skills(skills_dir)

        for skill in skills:
            entry: dict[str, Any] = {
                "name": skill.name,
                "description": skill.description,
                "dir_name": skill.path.parent.name,
                "body": "",
                "metadata": {},
                "unreadable": False,
            }
            try:
                metadata, body = parse_frontmatter(skill.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                # Keep the row so it is visible, but never overwrite the file:
                # a transient read error must not destroy the skill body.
                entry["unreadable"] = True
            else:
                entry["metadata"] = metadata
                entry["body"] = body
            self._skills_data.append(entry)

        self._refresh_table()

    def save_data(self, agent_dir: Path) -> list[str]:
        """Write all in-memory skill data back to disk as SKILL.md files.

        Returns the directory names that could not be written, so the caller can
        warn instead of silently losing the entry.
        """
        skills_dir = agent_dir / "workspace" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skipped: list[str] = []
        live_dirs: set[str] = set()

        for entry in self._skills_data:
            if entry["unreadable"]:
                continue
            dir_name = entry["dir_name"]
            if not _is_safe_dir_name(dir_name):
                # Pre-existing on-disk name we cannot safely write to; leave the
                # original file untouched rather than aborting the whole save.
                skipped.append(str(dir_name))
                continue
            live_dirs.add(dir_name)
            skill_dir = skills_dir / dir_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            metadata = dict(entry["metadata"])
            metadata["name"] = entry["name"]
            metadata["description"] = entry["description"]

            content = render_frontmatter(metadata, entry["body"])
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # Only remove directories the user explicitly deleted, and never one that
        # was re-created in this same session. Sweeping "everything not in
        # memory" would destroy skills whose discovery failed.
        for dir_name in self._deleted_dirs - live_dirs:
            target = skills_dir / dir_name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
        self._deleted_dirs = set()
        return skipped

    def _refresh_table(self) -> None:
        """Regenerate the table from in-memory data."""
        self.table.setRowCount(len(self._skills_data))

        for idx, entry in enumerate(self._skills_data):
            name_item = QTableWidgetItem(entry["name"])
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(QColor("#FFFFFF"))
            font_bold = name_item.font()
            font_bold.setBold(True)
            name_item.setFont(font_bold)
            self.table.setItem(idx, 0, name_item)

            desc_item = QTableWidgetItem(
                "[unreadable — will not be overwritten] " + entry["description"]
                if entry["unreadable"]
                else entry["description"]
            )
            desc_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            if entry["unreadable"]:
                desc_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(idx, 1, desc_item)

            path_str = f"workspace/skills/{entry['dir_name']}"
            path_item = QTableWidgetItem(path_str)
            path_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            path_item.setForeground(QColor("#888888"))
            font_mono = path_item.font()
            font_mono.setFamily("monospace")
            path_item.setFont(font_mono)
            self.table.setItem(idx, 2, path_item)

        self._clear_form()

    def _clear_form(self) -> None:
        """Reset the editor form."""
        self._selected_index = -1
        self.input_name.clear()
        self.input_description.clear()
        self.input_body.clear()

    def _on_table_selection_changed(self) -> None:
        """Populate the editor form when a table row is selected."""
        selected = self.table.selectedItems()
        if not selected:
            self._clear_form()
            return

        row = selected[0].row()
        if row < 0 or row >= len(self._skills_data):
            return

        self._selected_index = row
        entry = self._skills_data[row]
        self.input_name.setText(entry["name"])
        self.input_description.setText(entry["description"])
        self.input_body.setPlainText(entry["body"])

    def _on_add_clicked(self) -> None:
        """Add a new empty skill entry."""
        name, ok = QInputDialog.getText(
            self, "Create Skill", "New skill name (used as directory name):"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        dir_name = name.lower().replace(" ", "-")
        try:
            # The name becomes a path segment, so it must not escape the
            # skills directory.
            valid_dir_name(dir_name)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Name", f"Cannot create skill:\n\n{exc}")
            return

        existing_dirs = {e["dir_name"] for e in self._skills_data}
        if dir_name in existing_dirs:
            QMessageBox.warning(self, "Duplicate", f"A skill with directory name '{dir_name}' already exists.")
            return

        # Re-creating a previously deleted name: drop the pending deletion.
        self._deleted_dirs.discard(dir_name)

        self._skills_data.append({
            "name": name,
            "description": "New skill",
            "dir_name": dir_name,
            "body": "",
            "metadata": {"name": name, "description": "New skill"},
            "unreadable": False,
        })
        self._refresh_table()

        # Select the newly added row
        self.table.selectRow(len(self._skills_data) - 1)

    def _on_delete_clicked(self) -> None:
        """Delete the currently selected skill."""
        if self._selected_index < 0 or self._selected_index >= len(self._skills_data):
            QMessageBox.warning(self, "Delete Skill", "Please select a skill from the table.")
            return

        entry = self._skills_data[self._selected_index]
        confirm = QMessageBox.question(
            self,
            "Delete Skill",
            f"Are you sure you want to delete the skill '{entry['name']}'?\n\n"
            f"The directory 'workspace/skills/{entry['dir_name']}/' will be removed on save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._deleted_dirs.add(entry["dir_name"])
            del self._skills_data[self._selected_index]
            self._refresh_table()

    def _on_update_clicked(self) -> None:
        """Update the currently selected skill with values from the form."""
        if self._selected_index < 0 or self._selected_index >= len(self._skills_data):
            QMessageBox.warning(self, "Update Skill", "Please select a skill from the table first.")
            return

        name = self.input_name.text().strip()
        if not name:
            QMessageBox.critical(self, "Data Error", "Skill name cannot be empty.")
            return

        entry = self._skills_data[self._selected_index]
        entry["name"] = name
        entry["description"] = self.input_description.text().strip()
        entry["body"] = self.input_body.toPlainText()

        # Update metadata to reflect new name/description
        metadata = entry["metadata"]
        metadata["name"] = name
        metadata["description"] = entry["description"]
        entry["metadata"] = metadata

        saved_row = self._selected_index
        self._refresh_table()
        self.table.selectRow(saved_row)
        QMessageBox.information(self, "Data Updated", f"Skill '{name}' updated in memory.")

    def _on_open_folder_clicked(self) -> None:
        """Open agent workspace skills folder in the OS native file explorer."""
        if not self.agent_dir:
            return
        skills_dir = self.agent_dir / "workspace" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(skills_dir.resolve())))
