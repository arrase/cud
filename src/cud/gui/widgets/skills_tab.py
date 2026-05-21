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
    monospace_font,
)
from cud.tools._frontmatter import parse_frontmatter, render_frontmatter
from cud.tools.skills import discover_skills

_log = logging.getLogger(__name__)


class SkillsTab(QWidget):
    """View to list, create, edit, and delete local skills within the agent workspace."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None
        self._skills_data: list[dict[str, Any]] = []
        self._selected_index: int = -1

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Title / Description
        self.title_label = QLabel("Local Skills")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Skills are Python modules or scripts packaged within the agent's workspace "
            "that provide additional capabilities to solve problems."
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

        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setStyleSheet(ACTION_BTN_ADD)
        self.btn_add.clicked.connect(self._on_add_clicked)

        self.btn_delete = QPushButton("❌ Delete")
        self.btn_delete.setStyleSheet(ACTION_BTN_DELETE)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.btn_open_folder = QPushButton("📂 Open Folder")
        self.btn_open_folder.setStyleSheet(ACTION_BTN_FOLDER)
        self.btn_open_folder.clicked.connect(self._on_open_folder_clicked)

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

        skills_dir = agent_dir / "workspace" / "skills"
        try:
            skills = discover_skills(skills_dir)
        except Exception as exc:
            _log.warning("Failed to discover skills in %s: %s", skills_dir, exc)
            skills = []

        for skill in skills:
            try:
                raw_text = skill.path.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(raw_text)
            except Exception:
                metadata, body = {}, ""
            self._skills_data.append({
                "name": skill.name,
                "description": skill.description,
                "dir_name": skill.path.parent.name,
                "body": body,
                "metadata": metadata,
            })

        self._refresh_table()

    def save_data(self, agent_dir: Path) -> None:
        """Write all in-memory skill data back to disk as SKILL.md files."""
        skills_dir = agent_dir / "workspace" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Track which directories we write to, so we can detect deletions
        written_dirs: set[str] = set()

        for entry in self._skills_data:
            dir_name = entry["dir_name"]
            skill_dir = skills_dir / dir_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            metadata = dict(entry.get("metadata") or {})
            metadata["name"] = entry["name"]
            metadata["description"] = entry["description"]

            content = render_frontmatter(metadata, entry["body"])
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            written_dirs.add(dir_name)

        # Remove skill directories that were deleted from memory, but skip
        # internal directories like __pycache__ or hidden dot-dirs.
        if skills_dir.exists():
            for existing in skills_dir.iterdir():
                if not existing.is_dir():
                    continue
                if existing.name.startswith(("__", ".")):
                    continue
                if existing.name not in written_dirs:
                    shutil.rmtree(existing)

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

            desc_item = QTableWidgetItem(entry["description"])
            desc_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
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
        existing_dirs = {e["dir_name"] for e in self._skills_data}
        dir_name = name.lower().replace(" ", "-")
        if dir_name in existing_dirs:
            QMessageBox.warning(self, "Duplicate", f"A skill with directory name '{dir_name}' already exists.")
            return

        self._skills_data.append({
            "name": name,
            "description": "New skill",
            "dir_name": dir_name,
            "body": "",
            "metadata": {"name": name, "description": "New skill"},
        })
        self._refresh_table()

        # Select the newly added row
        last_row = len(self._skills_data) - 1
        self.table.selectRow(last_row)

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
        metadata = entry.get("metadata") or {}
        metadata["name"] = name
        metadata["description"] = entry["description"]
        entry["metadata"] = metadata

        self._refresh_table()
        QMessageBox.information(self, "Data Updated", f"Skill '{name}' updated in memory.")

    def _on_open_folder_clicked(self) -> None:
        """Open agent workspace skills folder in the OS native file explorer."""
        if not self.agent_dir:
            return
        skills_dir = self.agent_dir / "workspace" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(skills_dir.resolve())))
