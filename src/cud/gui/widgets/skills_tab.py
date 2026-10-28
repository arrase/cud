"""Skills tab widget for managing local agent skills with full CRUD operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
    ACTION_BTN_FOLDER,
    ACTION_BTN_UPDATE,
    create_action_button,
    create_readonly_table,
    create_tab_header,
    make_table_item,
    monospace_font,
)
from cud.tools.skills import discover_skills, save_skills


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

        create_tab_header(
            self.main_layout,
            "Local Skills",
            "Skills are Markdown instruction folders under the agent's workspace. "
            "Each folder contains a SKILL.md that grants the agent a new capability.",
        )

        # Split layout: left table, right editor
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # --- Left Column: Table + Action Buttons ---
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.table = create_readonly_table(["Name", "Description", "Location (Path)"], stretch_column=1)
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

        self.btn_update = create_action_button("💾 Update Skill Data", ACTION_BTN_UPDATE, self._on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

    def load_data(self, agent_dir: Path) -> None:
        """Scan skills directory and populate the in-memory data and table."""
        self.agent_dir = agent_dir
        self._skills_data = [
            {
                "name": skill.name,
                "description": skill.description,
                "dir_name": skill.path.parent.name,
                "body": skill.body,
                "metadata": dict(skill.metadata),
            }
            for skill in discover_skills(agent_dir / "workspace" / "skills")
        ]
        self._selected_index = -1
        self._deleted_dirs = set()
        self._refresh_table()

    def save_data(self, agent_dir: Path) -> list[str]:
        """Write all in-memory skill data back to disk as SKILL.md files."""
        skipped = save_skills(
            agent_dir / "workspace" / "skills",
            self._skills_data,
            self._deleted_dirs,
        )
        self._deleted_dirs = set()
        return skipped

    def _refresh_table(self) -> None:
        """Regenerate the table from in-memory data."""
        self.table.setRowCount(len(self._skills_data))

        for idx, entry in enumerate(self._skills_data):
            self.table.setItem(idx, 0, make_table_item(entry["name"], color="#FFFFFF", bold=True))
            self.table.setItem(idx, 1, make_table_item(entry["description"]))
            path_str = f"workspace/skills/{entry['dir_name']}"
            self.table.setItem(idx, 2, make_table_item(path_str, color="#888888", mono=True))

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
        name, ok = QInputDialog.getText(self, "Create Skill", "New skill name (used as directory name):")
        if not ok or not name.strip():
            return

        name = name.strip()
        dir_name = name.lower().replace(" ", "-")
        try:
            validate_safe_name(dir_name, "directory name")
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Name", f"Cannot create skill:\n\n{exc}")
            return

        existing_dirs = {e["dir_name"] for e in self._skills_data}
        if dir_name in existing_dirs:
            QMessageBox.warning(self, "Duplicate", f"A skill with directory name '{dir_name}' already exists.")
            return

        # Re-creating a previously deleted name: drop the pending deletion.
        self._deleted_dirs.discard(dir_name)

        self._skills_data.append(
            {
                "name": name,
                "description": "New skill",
                "dir_name": dir_name,
                "body": "",
                "metadata": {"name": name, "description": "New skill"},
            }
        )
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
