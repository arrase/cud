"""Subagents CRUD management widget for settings.yaml subagent configurations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cud.config.settings import SubAgentMCPServer, SubAgentSettings
from cud.gui.core.styles import (
    ACTION_BTN_ADD,
    ACTION_BTN_DELETE,
    ACTION_BTN_UPDATE,
    LIST_STYLE,
    monospace_font,
)


class SubagentsTab(QWidget):
    """View to list, create, edit, and delete subagent configurations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._subagents: list[SubAgentSettings] = []
        self._selected_index: int = -1

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Title
        self.title_label = QLabel("Subagents Topology")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Manage the hierarchy of subagents and specialized assistants that this agent "
            "can delegate and orchestrate to solve complex tasks."
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        self.main_layout.addWidget(self.desc_label)

        # Split layout
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # --- Left Column: List + Action Buttons ---
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.subagent_list = QListWidget()
        self.subagent_list.setStyleSheet(LIST_STYLE)
        self.subagent_list.currentRowChanged.connect(self._on_list_selection_changed)
        self.left_col.addWidget(self.subagent_list, 1)

        self.list_actions = QHBoxLayout()
        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setStyleSheet(ACTION_BTN_ADD)
        self.btn_add.clicked.connect(self._on_add_clicked)

        self.btn_delete = QPushButton("❌ Delete")
        self.btn_delete.setStyleSheet(ACTION_BTN_DELETE)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.list_actions.addWidget(self.btn_add)
        self.list_actions.addWidget(self.btn_delete)
        self.list_actions.addStretch()
        self.left_col.addLayout(self.list_actions)

        self.split_layout.addLayout(self.left_col, 1)

        # --- Right Column: Editor Form ---
        self.right_col = QVBoxLayout()
        self.right_col.setSpacing(8)

        self.group_editor = QGroupBox("Subagent Editor")
        self.form_layout = QFormLayout(self.group_editor)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., research-assistant")

        self.input_description = QLineEdit()
        self.input_description.setPlaceholderText("Brief description of the subagent role")

        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("e.g., gemma4:e4b (leave empty for parent default)")

        self.input_ctx = QSpinBox()
        self.input_ctx.setRange(0, 2048576)
        self.input_ctx.setSingleStep(4096)
        self.input_ctx.setValue(0)
        self.input_ctx.setSpecialValueText("Default")

        mono = monospace_font()

        self.input_prompt = QPlainTextEdit()
        self.input_prompt.setPlaceholderText("System prompt / directive for the subagent...")
        self.input_prompt.setFont(mono)
        self.input_prompt.setFixedHeight(120)

        self.input_skills = QLineEdit()
        self.input_skills.setPlaceholderText("Comma-separated skill paths (e.g., skill1, skill2)")

        self.input_mcp = QPlainTextEdit()
        self.input_mcp.setPlaceholderText(
            "MCP servers, one per line:\n"
            "name command arg1 arg2\n"
            "e.g., postgres npx -y @modelcontextprotocol/server-postgres"
        )
        self.input_mcp.setFont(mono)
        self.input_mcp.setFixedHeight(100)

        self.form_layout.addRow("Name:", self.input_name)
        self.form_layout.addRow("Description:", self.input_description)
        self.form_layout.addRow("Model:", self.input_model)
        self.form_layout.addRow("Context Window:", self.input_ctx)
        self.form_layout.addRow("System Prompt:", self.input_prompt)
        self.form_layout.addRow("Skills Paths:", self.input_skills)
        self.form_layout.addRow("MCP Servers:", self.input_mcp)

        self.btn_update = QPushButton("💾 Update Subagent Data")
        self.btn_update.setStyleSheet(ACTION_BTN_UPDATE)
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

    def load_from_subagents(self, subagents: list[SubAgentSettings]) -> None:
        """Populate the tab from a list of subagent settings."""
        self._subagents = list(subagents)
        self._selected_index = -1
        self._refresh_list()

    def save_data(self) -> list[SubAgentSettings]:
        """Return the current in-memory list of subagent settings for external serialization."""
        return list(self._subagents)

    def _refresh_list(self) -> None:
        """Regenerate the sidebar list from in-memory data."""
        self.subagent_list.clear()
        if not self._subagents:
            placeholder = QListWidgetItem("No subagents configured.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.subagent_list.addItem(placeholder)
        else:
            for sa in self._subagents:
                desc = sa.description or "No description"
                model_str = sa.model or "Default"
                text = f"🤖 {sa.name}\n   Model: {model_str} • {desc}"
                item = QListWidgetItem(text)
                item.setForeground(QColor("#E0E0E0"))
                self.subagent_list.addItem(item)

        self._clear_form()

    def _clear_form(self) -> None:
        """Reset the editor form."""
        self._selected_index = -1
        self.input_name.clear()
        self.input_description.clear()
        self.input_model.clear()
        self.input_ctx.setValue(0)
        self.input_prompt.clear()
        self.input_skills.clear()
        self.input_mcp.clear()

    def _on_list_selection_changed(self, row: int) -> None:
        """Populate the editor form when a list item is selected."""
        if row < 0 or row >= len(self._subagents):
            self._clear_form()
            return

        self._selected_index = row
        sa = self._subagents[row]

        self.input_name.setText(sa.name)
        self.input_description.setText(sa.description)
        self.input_model.setText(sa.model)
        self.input_ctx.setValue(sa.context_window)
        self.input_prompt.setPlainText(sa.system_prompt)
        self.input_skills.setText(", ".join(sa.skills_paths))

        # Serialize MCP servers to readable lines
        mcp_lines: list[str] = []
        for srv in sa.mcp_servers:
            parts = [srv.name, srv.command] + srv.args
            mcp_lines.append(" ".join(parts))
        self.input_mcp.setPlainText("\n".join(mcp_lines))

    def _on_add_clicked(self) -> None:
        """Add a new empty subagent entry."""
        new_name = "new-subagent"
        idx = 1
        existing_names = {sa.name for sa in self._subagents}
        while new_name in existing_names:
            new_name = f"new-subagent-{idx}"
            idx += 1

        self._subagents.append(SubAgentSettings(
            name=new_name,
            description="New subagent",
        ))
        self._refresh_list()
        self.subagent_list.setCurrentRow(len(self._subagents) - 1)

    def _on_delete_clicked(self) -> None:
        """Delete the currently selected subagent."""
        if self._selected_index < 0 or self._selected_index >= len(self._subagents):
            QMessageBox.warning(self, "Delete Subagent", "Please select a subagent from the list.")
            return

        sa = self._subagents[self._selected_index]
        confirm = QMessageBox.question(
            self,
            "Delete Subagent",
            f"Are you sure you want to delete the subagent '{sa.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            del self._subagents[self._selected_index]
            self._refresh_list()

    def _on_update_clicked(self) -> None:
        """Update the currently selected subagent with values from the form."""
        if self._selected_index < 0 or self._selected_index >= len(self._subagents):
            QMessageBox.warning(self, "Update Subagent", "Please select a subagent first.")
            return

        name = self.input_name.text().strip()
        if not name:
            QMessageBox.critical(self, "Data Error", "Subagent name cannot be empty.")
            return

        # Check name uniqueness (excluding current)
        for i, sa in enumerate(self._subagents):
            if i != self._selected_index and sa.name == name:
                QMessageBox.critical(self, "Name Error", f"Name '{name}' is already in use.")
                return

        # Parse skills paths
        skills_text = self.input_skills.text().strip()
        skills_paths = sorted({s.strip() for s in skills_text.split(",") if s.strip()}) if skills_text else []

        # Parse MCP servers
        mcp_servers = self._parse_mcp_servers(self.input_mcp.toPlainText())

        sa = self._subagents[self._selected_index]
        sa.name = name
        sa.description = self.input_description.text().strip()
        sa.model = self.input_model.text().strip()
        sa.context_window = self.input_ctx.value()
        sa.system_prompt = self.input_prompt.toPlainText()
        sa.skills_paths = skills_paths
        sa.mcp_servers = mcp_servers

        self._refresh_list()
        QMessageBox.information(self, "Data Updated", f"Subagent '{name}' updated in memory.")

    @staticmethod
    def _parse_mcp_servers(text: str) -> list[SubAgentMCPServer]:
        """Parse MCP server definitions from multi-line text.

        Each line format: ``name command arg1 arg2 ...``
        """
        servers: list[SubAgentMCPServer] = []
        for line in text.strip().splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            servers.append(SubAgentMCPServer(
                name=parts[0],
                command=parts[1],
                args=parts[2:],
            ))
        return servers
