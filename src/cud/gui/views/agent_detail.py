"""Workspace administration view (Master-Detail layout) for a selected Cud agent."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cud.config.paths import agent_home
from cud.config.settings import save_settings
from cud.gui.core.system_workers import SystemdWorker

# Import implemented widgets
from cud.gui.widgets.prompt_tab import PromptTab
from cud.gui.widgets.memory_tab import MemoryTab
from cud.gui.widgets.settings_tab import SettingsTab
from cud.gui.widgets.skills_tab import SkillsTab
from cud.gui.widgets.tasks_tab import TasksTab
from cud.gui.widgets.mcp_tab import MCPTab
from cud.gui.widgets.subagents_tab import SubagentsTab
from cud.gui.widgets.history_tab import HistoryTab

_log = logging.getLogger(__name__)


def _load_tab_safe(label: str, loader: Any, *args: Any) -> None:
    """Invoke *loader* catching exceptions so one broken tab cannot abort the rest."""
    try:
        loader(*args)
    except Exception as exc:
        _log.warning("Failed to load tab '%s': %s", label, exc)


class AgentDetailView(QWidget):
    """Maestro-detalle view governing a specific agent lifecycle and tabs configurations."""

    back_to_inventory = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_name = ""

        # Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # 1. Header Toolbar
        self.header = QHBoxLayout()

        self.back_btn = QPushButton("◀ Back")
        self.back_btn.clicked.connect(self.back_to_inventory.emit)

        self.title_label = QLabel("Agent Administration")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF;")

        # Service life-cycle controls
        self.btn_start = QPushButton("▶ Start")
        self.btn_start.setStyleSheet("color: #2ECC71; border-color: #2ECC71;")
        self.btn_start.clicked.connect(self.on_start_clicked)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setStyleSheet("color: #E74C3C; border-color: #E74C3C;")
        self.btn_stop.clicked.connect(self.on_stop_clicked)

        self.btn_restart = QPushButton("⟳ Restart")
        self.btn_restart.setStyleSheet("color: #F1C40F; border-color: #F1C40F;")
        self.btn_restart.clicked.connect(self.on_restart_clicked)

        self.btn_tui = QPushButton(">_ Open TUI")
        self.btn_tui.setStyleSheet("color: #3F51B5; border-color: #3F51B5;")
        self.btn_tui.clicked.connect(self.on_tui_clicked)

        self.btn_save = QPushButton("💾 Save & Restart Agent")
        self.btn_save.setStyleSheet("background-color: #3F51B5; color: #FFFFFF; font-weight: bold;")
        self.btn_save.clicked.connect(self.on_save_clicked)

        self.header.addWidget(self.back_btn)
        self.header.addWidget(self.title_label, 1)
        self.header.addWidget(self.btn_start)
        self.header.addWidget(self.btn_stop)
        self.header.addWidget(self.btn_restart)
        self.header.addWidget(self.btn_tui)
        self.header.addWidget(self.btn_save)

        self.main_layout.addLayout(self.header)

        # Separator line
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #2B2B2B;")
        self.main_layout.addWidget(line)

        # 2. Body Splitter (Left navigation, Right content area)
        self.body_layout = QHBoxLayout()
        self.body_layout.setSpacing(16)

        # Left Vertical Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(180)
        self.nav_list.setSpacing(4)
        self.nav_list.setStyleSheet("""
            QListWidget {
                background-color: #1A1A1A;
                border: 1px solid #2B2B2B;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 10px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background-color: #26262B;
            }
            QListWidget::item:selected {
                background-color: #3F51B5;
                color: #FFFFFF;
            }
        """)

        # Add categories
        self.categories = [
            "⚙️ General",
            "🧠 Instructions",
            "💾 Memory",
            "🛠️ Skills",
            "📅 Scheduled Tasks (Cron)",
            "🔌 MCP Protocol",
            "🤖 Subagents",
            "📜 Chat History",
        ]
        self.nav_list.addItems(self.categories)
        self.nav_list.currentRowChanged.connect(self.on_category_changed)

        # Right Stack Content area
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("""
            QStackedWidget {
                background-color: #1A1A1A;
                border: 1px solid #2B2B2B;
                border-radius: 8px;
            }
        """)

        # Create tabs
        self.tab_settings = SettingsTab()
        self.tab_prompt = PromptTab()
        self.tab_memory = MemoryTab()
        self.tab_skills = SkillsTab()
        self.tab_tasks = TasksTab()
        self.tab_mcp = MCPTab()
        self.tab_subagents = SubagentsTab()
        self.tab_history = HistoryTab()

        # Add widgets in same index order as categories list
        self.content_stack.addWidget(self.tab_settings)   # Index 0
        self.content_stack.addWidget(self.tab_prompt)     # Index 1
        self.content_stack.addWidget(self.tab_memory)     # Index 2
        self.content_stack.addWidget(self.tab_skills)     # Index 3
        self.content_stack.addWidget(self.tab_tasks)      # Index 4
        self.content_stack.addWidget(self.tab_mcp)        # Index 5
        self.content_stack.addWidget(self.tab_subagents)  # Index 6
        self.content_stack.addWidget(self.tab_history)    # Index 7

        self.body_layout.addWidget(self.nav_list)
        self.body_layout.addWidget(self.content_stack, 1)

        self.main_layout.addLayout(self.body_layout, 1)

        # Selection state
        self.nav_list.setCurrentRow(0)

        # Transaction Loading dialogue
        self.loading_dialog = None



    def set_agent(self, agent_name: str) -> None:
        """Contextualize work view and load agent configs to their respective tabs.

        Each tab is loaded independently so that a single corrupt file does not
        prevent the remaining tabs from being populated.

        Args:
            agent_name: Canonical name of the target agent.
        """
        self.agent_name = agent_name
        self.title_label.setText(f"Agent Administration: {agent_name}")

        agent_dir = agent_home(agent_name)

        # Load configurations — each tab is isolated so one failure does not
        # prevent the remaining tabs from loading.
        _load_tab_safe("Settings", self.tab_settings.load_data, agent_dir)
        _load_tab_safe("Prompt", self.tab_prompt.load_file, agent_dir / "AGENT.md")
        _load_tab_safe("Memory", self.tab_memory.load_file, agent_dir / "MEMORY.md")
        _load_tab_safe("Skills", self.tab_skills.load_data, agent_dir)
        _load_tab_safe("Tasks", self.tab_tasks.load_data, agent_dir)
        _load_tab_safe("MCP", self.tab_mcp.load_data, agent_dir)
        _load_tab_safe("Subagents", self.tab_subagents.load_data, agent_dir)
        _load_tab_safe("History", self.tab_history.load_data, agent_dir)

    def on_category_changed(self, row: int) -> None:
        """Switch stacked page upon clicking navigation bar category index."""
        if 0 <= row < self.content_stack.count():
            self.content_stack.setCurrentIndex(row)

    def on_start_clicked(self) -> None:
        """Asynchronously trigger systemd start service."""
        self._run_async_control("start", "Starting gateway service...")

    def on_stop_clicked(self) -> None:
        """Asynchronously trigger systemd stop service."""
        self._run_async_control("stop", "Stopping gateway service...")

    def on_restart_clicked(self) -> None:
        """Asynchronously trigger systemd restart service."""
        self._run_async_control("restart", "Restarting gateway service...")

    def on_tui_clicked(self) -> None:
        """Launch CUD interactive TUI terminal console window asynchronously."""
        try:
            # Attempt launching terminal emulator
            subprocess.Popen(
                ["x-terminal-emulator", "-e", "cud", "tui", self.agent_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            try:
                # Fallback to gnome-terminal
                subprocess.Popen(
                    ["gnome-terminal", "--", "cud", "tui", self.agent_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Terminal not Available",
                    f"Could not automatically launch an interactive terminal emulator.\n"
                    f"Run in your console:\n\n   cud tui {self.agent_name}\n\nDetails: {e}"
                )

    def _run_async_control(self, action: str, label_text: str) -> None:
        """Spawn background control workers in QThreadPool to isolate systemd processes."""
        self.setEnabled(False)
        self.loading_dialog = QProgressDialog(label_text, None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Service Control")
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.setValue(0)
        self.loading_dialog.show()

        worker = SystemdWorker(action, self.agent_name)
        worker.signals.finished.connect(self._on_control_finished)
        worker.signals.error.connect(self._on_control_error)
        QThreadPool.globalInstance().start(worker)

    def _on_control_finished(self, action: str, service_name: str, message: str) -> None:
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        self.setEnabled(True)
        QMessageBox.information(self, "Service Action Completed", f"Action '{action}' completed:\n\n{message}")

    def _on_control_error(self, action: str, service_name: str, error_message: str) -> None:
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        self.setEnabled(True)
        QMessageBox.critical(self, "Service Error", f"Failed to execute '{action}':\n\n{error_message}")

    def on_save_clicked(self) -> None:
        """Atomic serializing workflow: Block screen, write files, call async restart systemd."""
        self.setEnabled(False)
        self.loading_dialog = QProgressDialog("Saving files and restarting agent...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Save Changes")
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.setValue(0)
        self.loading_dialog.show()

        try:
            agent_dir = agent_home(self.agent_name)

            # 1. Save Settings (settings.yaml) — includes subagents
            settings = self.tab_settings.save_data()
            settings.subagents = self.tab_subagents.save_data()
            save_settings(agent_dir, settings)

            # 2. Save Prompt (AGENT.md)
            self.tab_prompt.save_file(agent_dir / "AGENT.md")

            # 3. Save Memory (MEMORY.md)
            self.tab_memory.save_file(agent_dir / "MEMORY.md")

            # 4. Save MCP Config (mcp.json)
            self.tab_mcp.save_data(agent_dir)

            # 5. Save Skills (workspace/skills/)
            self.tab_skills.save_data(agent_dir)

            # 6. Save Tasks (workspace/tasks/)
            self.tab_tasks.save_data(agent_dir)

            # 7. Trigger Async Restart
            worker = SystemdWorker("restart", self.agent_name)
            worker.signals.finished.connect(self._on_save_restart_finished)
            worker.signals.error.connect(self._on_save_restart_error)
            QThreadPool.globalInstance().start(worker)

        except Exception as e:
            if self.loading_dialog:
                self.loading_dialog.close()
                self.loading_dialog = None
            self.setEnabled(True)
            QMessageBox.critical(self, "Save Failed", f"Error writing configurations to disk:\n\n{e}")

    def _on_save_restart_finished(self, action: str, service_name: str, message: str) -> None:
        # Give systemd service 1.5 seconds to bootstrap properly before polling status
        QTimer.singleShot(1500, self._complete_save_workflow)

    def _complete_save_workflow(self) -> None:
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        self.setEnabled(True)
        QMessageBox.information(
            self,
            "Saved Successfully",
            f"Agent '{self.agent_name}' has been successfully saved and restarted."
        )

    def _on_save_restart_error(self, action: str, service_name: str, error_message: str) -> None:
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        self.setEnabled(True)
        QMessageBox.critical(
            self,
            "Service Error",
            f"Files were saved, but an error occurred while restarting the agent:\n\n{error_message}"
        )
