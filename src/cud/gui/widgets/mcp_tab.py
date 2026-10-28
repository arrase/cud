"""Model Context Protocol (MCP) server management widget for mcp.json configurations."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from cud.gui.core.styles import (
    ACTION_BTN_ADD,
    ACTION_BTN_DELETE,
    ACTION_BTN_UPDATE,
    create_action_button,
    create_readonly_table,
    create_tab_header,
    make_table_item,
)
from cud.tools.mcp import (
    DEFAULT_TRANSPORT,
    TRANSPORTS,
    MCPConfig,
    free_server_name,
    load_mcp_config,
    parse_env_pairs,
    save_mcp_config,
)


class MCPTab(QWidget):
    """View to register, configure, and inspect MCP servers and allowed tools."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_config = MCPConfig()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        create_tab_header(
            self.main_layout,
            "Model Context Protocol (MCP)",
            "Connect your agent with external tools and data sources via MCP servers (Stdio or HTTP SSE).",
        )

        # Main horizontal split
        self.split_layout = QHBoxLayout()
        self.split_layout.setSpacing(16)

        # Left Column: Table of Servers
        self.left_col = QVBoxLayout()
        self.left_col.setSpacing(8)

        self.servers_table = create_readonly_table(["Name", "Transport", "Destination"], stretch_column=2)
        self.servers_table.itemSelectionChanged.connect(self.on_server_selected)
        self.left_col.addWidget(self.servers_table, 1)

        # Table Action Buttons
        self.table_actions = QHBoxLayout()
        self.btn_add = create_action_button("➕ Add", ACTION_BTN_ADD, self.on_add_clicked)
        self.btn_delete = create_action_button("❌ Delete", ACTION_BTN_DELETE, self.on_delete_clicked)

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
        self.input_transport.addItems(list(TRANSPORTS))
        self.input_cmd_url = QLineEdit()
        self.input_cmd_url.setPlaceholderText("e.g., npx (stdio) or http://localhost:8080/sse (sse)")

        self.input_args = QLineEdit()
        self.input_args.setPlaceholderText("e.g., -y @modelcontextprotocol/server-postgres (space separated)")

        self.input_env = QPlainTextEdit()
        self.input_env.setPlaceholderText("e.g.,\nDB_URL=postgresql://localhost/db\nAPI_KEY=12345")
        self.input_env.setFixedHeight(80)

        # Connected last: the handler touches input_args/input_env.
        self.input_transport.currentTextChanged.connect(self.on_transport_changed)
        self.on_transport_changed(self.input_transport.currentText())

        self.form_layout.addRow("Server Name:", self.input_name)
        self.form_layout.addRow("Transport Type:", self.input_transport)
        self.form_layout.addRow("Command / URL:", self.input_cmd_url)
        self.form_layout.addRow("Arguments:", self.input_args)
        self.form_layout.addRow("Environment (KEY=VALUE):", self.input_env)

        self.btn_update = create_action_button("💾 Update Server Data", ACTION_BTN_UPDATE, self.on_update_clicked)
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
        self.current_config = load_mcp_config(agent_dir)
        self.input_transport.clear()
        self.input_transport.addItems(list(TRANSPORTS))

        # Allowed / Disabled tools inputs
        self.input_allowed.setText(", ".join(self.current_config.allowed_tools))
        self.input_disabled.setText(", ".join(self.current_config.disabled_tools))

        self.refresh_table()

    def refresh_table(self) -> None:
        """Regenerate the list table with the in-memory config dicts."""
        self.servers_table.setRowCount(len(self.current_config.servers))

        for idx, (name, server_data) in enumerate(sorted(self.current_config.servers.items())):
            transport = server_data.get("transport") or DEFAULT_TRANSPORT
            dest = str(server_data.get("url") or "") if transport != "stdio" else str(server_data.get("command") or "")

            self.servers_table.setItem(idx, 0, make_table_item(name, color="#FFFFFF", bold=True))
            self.servers_table.setItem(idx, 1, make_table_item(transport))
            self.servers_table.setItem(idx, 2, make_table_item(dest, mono=True))

        # Clear form fields
        self.clear_form()

    def _selected_name(self) -> str | None:
        """Name of the selected row, or None.

        `selectedItems()[0]` is not guaranteed to be column 0, so read the
        name cell of the selected row explicitly.
        """
        items = self.servers_table.selectionModel().selectedRows()
        if not items:
            return None
        item = self.servers_table.item(items[0].row(), 0)
        return item.text() if item is not None else None

    def _select_by_name(self, name: str) -> None:
        for row in range(self.servers_table.rowCount()):
            item = self.servers_table.item(row, 0)
            if item and item.text() == name:
                self.servers_table.selectRow(row)
                # Re-selecting an already-selected row emits no signal, so
                # repopulate the form explicitly.
                self.on_server_selected()
                return

    def clear_form(self) -> None:
        self.selected_server_name = ""
        self.input_name.clear()
        self.input_transport.setCurrentIndex(0)
        self.on_transport_changed(self.input_transport.currentText())
        self.input_cmd_url.clear()
        self.input_args.clear()
        self.input_env.clear()

    def on_server_selected(self) -> None:
        """Triggered when a table row is selected. Populates form fields."""
        name = self._selected_name()
        if name is None:
            self.clear_form()
            return

        server_data = self.current_config.servers[name]

        self.selected_server_name = name
        self.input_name.setText(name)

        transport = server_data.get("transport") or DEFAULT_TRANSPORT
        if transport not in TRANSPORTS and self.input_transport.findText(transport) < 0:
            # Keep an unknown transport visible instead of silently showing
            # "stdio" and rewriting the entry as stdio on the next update.
            self.input_transport.addItem(transport)
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
        new_name = free_server_name(self.current_config.servers, "new-server-")

        self.current_config.servers[new_name] = {
            "transport": "stdio",
            "command": "python",
            "args": [],
            "env": {},
        }
        self.refresh_table()

        self._select_by_name(new_name)

    def on_delete_clicked(self) -> None:
        """Delete currently selected server row."""
        name = self._selected_name()
        if name is None:
            QMessageBox.warning(self, "Delete Server", "Please select a server from the table.")
            return

        confirm = QMessageBox.question(
            self,
            "Delete Server",
            f"Are you sure you want to delete the MCP server '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm == QMessageBox.StandardButton.Yes:
            del self.current_config.servers[name]
            self.refresh_table()

    def _build_server_data(self, transport: str, cmd_or_url: str) -> dict[str, Any] | None:
        server_data: dict[str, Any] = {"transport": transport}
        if transport != "stdio":
            server_data["url"] = cmd_or_url
            return server_data

        server_data["command"] = cmd_or_url
        args_str = self.input_args.text().strip()
        if args_str:
            try:
                server_data["args"] = shlex.split(args_str)
            except ValueError as e:
                QMessageBox.critical(self, "Arguments Error", f"Error parsing arguments: {e}")
                return None
        else:
            server_data["args"] = []

        try:
            env_dict = parse_env_pairs(self.input_env.toPlainText().splitlines())
        except ValueError as e:
            QMessageBox.critical(self, "Environment Error", str(e))
            return None
        if env_dict:
            server_data["env"] = env_dict
        return server_data

    def _apply_server_rename(self, new_name: str) -> bool:
        if self.selected_server_name == new_name:
            return True
        if new_name in self.current_config.servers:
            QMessageBox.critical(self, "Name Error", f"Name '{new_name}' is already in use.")
            return False
        if self.selected_server_name in self.current_config.servers:
            del self.current_config.servers[self.selected_server_name]
        return True

    def on_update_clicked(self) -> None:
        """Update active server config with values in input fields."""
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.critical(self, "Data Error", "Server name cannot be empty.")
            return

        cmd_or_url = self.input_cmd_url.text().strip()
        if not cmd_or_url:
            QMessageBox.critical(self, "Data Error", "Destination Command or URL is required.")
            return

        transport = self.input_transport.currentText()
        server_data = self._build_server_data(transport, cmd_or_url)
        if server_data is None:
            return

        if not self._apply_server_rename(name):
            return

        self.current_config.servers[name] = server_data
        self.selected_server_name = name

        self.refresh_table()
        self._select_by_name(name)
        QMessageBox.information(self, "Data Updated", f"Server '{name}' data updated in memory.")

    def save_data(self, agent_dir: Path) -> None:
        """Write current MCPConfig to mcp.json."""
        allowed_str = self.input_allowed.text().strip()
        self.current_config.allowed_tools = (
            sorted({t.strip() for t in allowed_str.split(",") if t.strip()}) if allowed_str else []
        )

        disabled_str = self.input_disabled.text().strip()
        self.current_config.disabled_tools = (
            sorted({t.strip() for t in disabled_str.split(",") if t.strip()}) if disabled_str else []
        )

        save_mcp_config(agent_dir, self.current_config)
