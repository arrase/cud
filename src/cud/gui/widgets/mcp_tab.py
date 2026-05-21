"""Model Context Protocol (MCP) server management widget for mcp.json configurations."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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

from cud.gui.core.styles import ACTION_BTN_ADD, ACTION_BTN_DELETE, ACTION_BTN_UPDATE, TABLE_STYLE
from cud.tools.mcp import MCPConfig, load_mcp_config, save_mcp_config


class MCPTab(QWidget):
    """View to register, configure, and inspect MCP servers and allowed tools."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None
        self.current_config = MCPConfig()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Title
        self.title_label = QLabel("Model Context Protocol (MCP)")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Connect your agent with external tools and data sources via MCP servers "
            "(Stdio or HTTP SSE)."
        )
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        self.main_layout.addWidget(self.desc_label)

        # Main horizontal split
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # Left Column: Table of Servers
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.servers_table = QTableWidget()
        self.servers_table.setColumnCount(3)
        self.servers_table.setHorizontalHeaderLabels(["Name", "Transport", "Destination"])
        self.servers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.servers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.servers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.servers_table.setAlternatingRowColors(True)
        self.servers_table.setStyleSheet(TABLE_STYLE)
        self.servers_table.itemSelectionChanged.connect(self.on_server_selected)
        self.left_col.addWidget(self.servers_table, 1)

        # Table Action Buttons
        self.table_actions = QHBoxLayout()
        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setStyleSheet(ACTION_BTN_ADD)
        self.btn_add.clicked.connect(self.on_add_clicked)

        self.btn_delete = QPushButton("❌ Delete")
        self.btn_delete.setStyleSheet(ACTION_BTN_DELETE)
        self.btn_delete.clicked.connect(self.on_delete_clicked)

        self.table_actions.addWidget(self.btn_add)
        self.table_actions.addWidget(self.btn_delete)
        self.table_actions.addStretch()
        self.left_col.addLayout(self.table_actions)

        self.split_layout.addLayout(self.left_col, 3)

        # Right Column: Editor Form
        self.right_col = QVBoxLayout()
        self.right_col.setSpacing(8)

        self.group_editor = QGroupBox("Server Editor")
        self.form_layout = QFormLayout(self.group_editor)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., my-mcp-server")

        self.input_transport = QComboBox()
        self.input_transport.addItems(["stdio", "sse", "streamable_http"])
        self.input_transport.currentTextChanged.connect(self.on_transport_changed)

        self.input_cmd_url = QLineEdit()
        self.input_cmd_url.setPlaceholderText("e.g., npx (stdio) or http://localhost:8080/sse (sse)")

        self.input_args = QLineEdit()
        self.input_args.setPlaceholderText("e.g., -y @modelcontextprotocol/server-postgres (space separated)")

        self.input_env = QPlainTextEdit()
        self.input_env.setPlaceholderText("e.g.,\nDB_URL=postgresql://localhost/db\nAPI_KEY=12345")
        self.input_env.setFixedHeight(80)

        self.form_layout.addRow("Server Name:", self.input_name)
        self.form_layout.addRow("Transport Type:", self.input_transport)
        self.form_layout.addRow("Command / URL:", self.input_cmd_url)
        self.form_layout.addRow("Arguments:", self.input_args)
        self.form_layout.addRow("Environment (KEY=VALUE):", self.input_env)

        self.btn_update = QPushButton("💾 Update Server Data")
        self.btn_update.setStyleSheet(ACTION_BTN_UPDATE)
        self.btn_update.clicked.connect(self.on_update_clicked)
        self.form_layout.addRow("", self.btn_update)

        self.right_col.addWidget(self.group_editor)
        self.split_layout.addLayout(self.right_col, 2)

        self.main_layout.addLayout(self.split_layout, 1)

        # Bottom section: Global allowed/disabled tools lists
        self.group_global = QGroupBox("Global Tool Control (Optional)")
        self.global_layout = QFormLayout(self.group_global)

        self.input_allowed = QLineEdit()
        self.input_allowed.setPlaceholderText("e.g., tool_name1, tool_name2 (leave empty to allow all)")

        self.input_disabled = QLineEdit()
        self.input_disabled.setPlaceholderText("e.g., forbidden_tool, risky_tool")

        self.global_layout.addRow("Allowed Tools (Commas):", self.input_allowed)
        self.global_layout.addRow("Disabled Tools (Commas):", self.input_disabled)

        self.main_layout.addWidget(self.group_global)

        # Keep track of the current selected row index
        self.selected_server_name = ""

    def on_transport_changed(self, transport: str) -> None:
        """Enable or disable input fields depending on transport mode."""
        is_stdio = transport == "stdio"
        self.input_args.setEnabled(is_stdio)
        self.input_env.setEnabled(is_stdio)
        if is_stdio:
            self.input_cmd_url.setPlaceholderText("e.g., npx, python, node")
        else:
            self.input_cmd_url.setPlaceholderText("e.g., http://localhost:8080/sse")

    def load_data(self, agent_dir: Path) -> None:
        """Load and parse mcp.json."""
        self.agent_dir = agent_dir
        self.current_config = load_mcp_config(agent_dir)

        # Allowed / Disabled tools inputs
        self.input_allowed.setText(", ".join(self.current_config.allowed_tools))
        self.input_disabled.setText(", ".join(self.current_config.disabled_tools))

        self.refresh_table()

    def refresh_table(self) -> None:
        """Regenerate the list table with the in-memory config dicts."""
        self.servers_table.setRowCount(0)
        self.servers_table.setRowCount(len(self.current_config.servers))

        for idx, (name, server_data) in enumerate(sorted(self.current_config.servers.items())):
            transport = server_data.get("transport") or "stdio"
            dest = server_data.get("url") if transport != "stdio" else server_data.get("command", "")

            # Set items
            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(QColor("#FFFFFF"))
            font_bold = name_item.font()
            font_bold.setBold(True)
            name_item.setFont(font_bold)
            self.servers_table.setItem(idx, 0, name_item)

            transport_item = QTableWidgetItem(transport)
            transport_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.servers_table.setItem(idx, 1, transport_item)

            dest_item = QTableWidgetItem(dest)
            dest_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            font_mono = dest_item.font()
            font_mono.setFamily("monospace")
            dest_item.setFont(font_mono)
            self.servers_table.setItem(idx, 2, dest_item)

        # Clear form fields
        self.clear_form()

    def clear_form(self) -> None:
        self.selected_server_name = ""
        self.input_name.clear()
        self.input_transport.setCurrentIndex(0)
        self.input_cmd_url.clear()
        self.input_args.clear()
        self.input_env.clear()

    def on_server_selected(self) -> None:
        """Triggered when a table row is selected. Populates form fields."""
        selected_items = self.servers_table.selectedItems()
        if not selected_items:
            self.clear_form()
            return

        # Row name is first item
        name = selected_items[0].text()
        server_data = self.current_config.servers.get(name)
        if not server_data:
            return

        self.selected_server_name = name
        self.input_name.setText(name)

        transport = server_data.get("transport") or "stdio"
        self.input_transport.setCurrentText(transport)

        if transport == "stdio":
            self.input_cmd_url.setText(server_data.get("command", ""))
            args_list = server_data.get("args") or []
            self.input_args.setText(" ".join(args_list))

            # Environment Variables dictionary to string
            env_dict = server_data.get("env") or {}
            env_lines = [f"{k}={v}" for k, v in env_dict.items()]
            self.input_env.setPlainText("\n".join(env_lines))
        else:
            self.input_cmd_url.setText(server_data.get("url", ""))
            self.input_args.clear()
            self.input_env.clear()

    def on_add_clicked(self) -> None:
        """Add a new empty/default server entry to edit."""
        new_name = "new-server"
        idx = 1
        while new_name in self.current_config.servers:
            new_name = f"new-server-{idx}"
            idx += 1

        self.current_config.servers[new_name] = {
            "transport": "stdio",
            "command": "python",
            "args": [],
            "env": {},
        }
        self.refresh_table()

        # Find and select the newly added row
        for row in range(self.servers_table.rowCount()):
            item = self.servers_table.item(row, 0)
            if item and item.text() == new_name:
                self.servers_table.selectRow(row)
                break

    def on_delete_clicked(self) -> None:
        """Delete currently selected server row."""
        selected_items = self.servers_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Delete Server", "Please select a server from the table.")
            return

        name = selected_items[0].text()
        confirm = QMessageBox.question(
            self,
            "Delete Server",
            f"Are you sure you want to delete the MCP server '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm == QMessageBox.StandardButton.Yes:
            if name in self.current_config.servers:
                del self.current_config.servers[name]
            self.refresh_table()

    def on_update_clicked(self) -> None:
        """Update active server config with values in input fields."""
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.critical(self, "Data Error", "Server name cannot be empty.")
            return

        transport = self.input_transport.currentText()
        cmd_or_url = self.input_cmd_url.text().strip()

        if not cmd_or_url:
            QMessageBox.critical(self, "Data Error", "Destination Command or URL is required.")
            return

        server_data: dict[str, Any] = {"transport": transport}

        if transport == "stdio":
            server_data["command"] = cmd_or_url

            # Parse arguments cleanly with shlex
            args_str = self.input_args.text().strip()
            try:
                server_data["args"] = shlex.split(args_str) if args_str else []
            except Exception as e:
                QMessageBox.critical(self, "Arguments Error", f"Error parsing arguments: {e}")
                return

            # Parse environment variables
            env_text = self.input_env.toPlainText().strip()
            env_dict = {}
            if env_text:
                for line in env_text.splitlines():
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    env_dict[k.strip()] = v.strip()
            if env_dict:
                server_data["env"] = env_dict
        else:
            server_data["url"] = cmd_or_url

        # Check if the name has changed
        if self.selected_server_name and self.selected_server_name != name:
            if name in self.current_config.servers:
                QMessageBox.critical(self, "Name Error", f"Name '{name}' is already in use.")
                return
            # Delete old entry
            if self.selected_server_name in self.current_config.servers:
                del self.current_config.servers[self.selected_server_name]

        self.current_config.servers[name] = server_data
        self.selected_server_name = name

        self.refresh_table()
        QMessageBox.information(self, "Data Updated", f"Server '{name}' data updated in memory.")

    def save_data(self, agent_dir: Path) -> None:
        """Write current MCPConfig objects back to disk in mcp.json format."""
        # Read allowed tools array from GUI comma separated lists
        allowed_str = self.input_allowed.text().strip()
        if allowed_str:
            self.current_config.allowed_tools = sorted(
                {t.strip() for t in allowed_str.split(",") if t.strip()}
            )
        else:
            self.current_config.allowed_tools = []

        # Read disabled tools array from GUI comma separated lists
        disabled_str = self.input_disabled.text().strip()
        if disabled_str:
            self.current_config.disabled_tools = sorted(
                {t.strip() for t in disabled_str.split(",") if t.strip()}
            )
        else:
            self.current_config.disabled_tools = []

        save_mcp_config(agent_dir, self.current_config)
