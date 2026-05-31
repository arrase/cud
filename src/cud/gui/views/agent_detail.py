"""Workspace administration view (Master-Detail layout) for a selected Cud agent."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
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
from cud.config.settings import Settings, load_settings, save_settings
from cud.gui.core.system_workers import SystemdWorker
from cud.gui.widgets.markdown_file_tab import MarkdownFileTab
from cud.gui.widgets.settings_tab import SettingsTab
from cud.gui.widgets.skills_tab import SkillsTab
from cud.gui.widgets.tasks_tab import TasksTab
from cud.gui.widgets.mcp_tab import MCPTab
from cud.gui.widgets.subagents_tab import SubagentsTab

_log = logging.getLogger(__name__)


def _load_tab_safe(label: str, loader: Callable[..., Any], *args: Any) -> None:
    """Invoke *loader* catching exceptions so one broken tab cannot abort the rest."""
    try:
        loader(*args)
    except Exception as exc:
        _log.warning("Failed to load tab '%s': %s", label, exc)


class AgentDetailView(QWidget):
    """Maestro-detalle view governing a specific agent lifecycle and tabs configurations."""

    back_to_inventory = Signal()

    # Compact pill-shaped button stylesheet for service lifecycle controls.
    _SERVICE_BTN = """
        QPushButton {{
            color: {fg};
            background-color: transparent;
            border: 1px solid {fg};
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {fg};
            color: #FFFFFF;
        }}
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_name = ""
        self._active_workers: set[SystemdWorker] = set()

        # Root layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 12)
        self.main_layout.setSpacing(0)

        # ── 1. Navigation header: Back + Title ──────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.back_btn = QPushButton("◀  Back")
        self.back_btn.setStyleSheet("""
            QPushButton {
                color: #8A8A8F;
                background: transparent;
                border: none;
                font-size: 13px;
                padding: 4px 8px;
            }
            QPushButton:hover { color: #FFFFFF; }
        """)
        self.back_btn.clicked.connect(self.back_to_inventory.emit)

        self.title_label = QLabel("Agent Administration")
        self.title_label.setStyleSheet(
            "font-size: 19px; font-weight: bold; color: #FFFFFF; padding-left: 4px;"
        )

        header.addWidget(self.back_btn)
        header.addWidget(self.title_label, 1)
        self.main_layout.addLayout(header)

        # ── 2. Service lifecycle toolbar ────────────────────────────────
        svc_bar = QHBoxLayout()
        svc_bar.setContentsMargins(0, 6, 0, 8)
        svc_bar.setSpacing(8)

        svc_label = QLabel("Service")
        svc_label.setStyleSheet("color: #666666; font-size: 11px; padding-right: 2px;")
        svc_bar.addWidget(svc_label)

        self.btn_start = QPushButton("▶ Start")
        self.btn_start.setStyleSheet(self._SERVICE_BTN.format(fg="#2ECC71"))
        self.btn_start.clicked.connect(self.on_start_clicked)
        svc_bar.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setStyleSheet(self._SERVICE_BTN.format(fg="#E74C3C"))
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        svc_bar.addWidget(self.btn_stop)

        self.btn_restart = QPushButton("⟳ Restart")
        self.btn_restart.setStyleSheet(self._SERVICE_BTN.format(fg="#F1C40F"))
        self.btn_restart.clicked.connect(self.on_restart_clicked)
        svc_bar.addWidget(self.btn_restart)

        self.btn_tui = QPushButton(">_ Open TUI")
        self.btn_tui.setStyleSheet(self._SERVICE_BTN.format(fg="#7986CB"))
        self.btn_tui.clicked.connect(self.on_tui_clicked)
        svc_bar.addWidget(self.btn_tui)

        svc_bar.addStretch(1)
        self.main_layout.addLayout(svc_bar)

        # Thin separator
        sep_top = QWidget()
        sep_top.setFixedHeight(1)
        sep_top.setStyleSheet("background-color: #2B2B2B;")
        self.main_layout.addWidget(sep_top)

        # ── 3. Body: Navigation list + Content stack ────────────────────
        self.body_layout = QHBoxLayout()
        self.body_layout.setContentsMargins(0, 10, 0, 0)
        self.body_layout.setSpacing(14)

        # Left vertical navigation
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(190)
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

        self.categories = [
            "⚙️  General",
            "🧠  Instructions",
            "💾  Memory",
            "🛠️  Skills",
            "📅  Scheduled Tasks",
            "🔌  MCP Protocol",
            "🤖  Subagents",
        ]
        self.nav_list.addItems(self.categories)
        self.nav_list.currentRowChanged.connect(self.on_category_changed)

        # Right content stack
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
        self.tab_prompt = MarkdownFileTab("# Agent Directive\n\nWrite the agent prompt here...")
        self.tab_memory = MarkdownFileTab("# Memory Context\n\nLong-term memory records...")
        self.tab_skills = SkillsTab()
        self.tab_tasks = TasksTab()
        self.tab_mcp = MCPTab()
        self.tab_subagents = SubagentsTab()

        # Add widgets in same index order as categories list
        self.content_stack.addWidget(self.tab_settings)   # Index 0
        self.content_stack.addWidget(self.tab_prompt)     # Index 1
        self.content_stack.addWidget(self.tab_memory)     # Index 2
        self.content_stack.addWidget(self.tab_skills)     # Index 3
        self.content_stack.addWidget(self.tab_tasks)      # Index 4
        self.content_stack.addWidget(self.tab_mcp)        # Index 5
        self.content_stack.addWidget(self.tab_subagents)  # Index 6

        self.body_layout.addWidget(self.nav_list)
        self.body_layout.addWidget(self.content_stack, 1)

        self.main_layout.addLayout(self.body_layout, 1)

        # ── 4. Footer action bar ───────────────────────────────────────
        sep_bottom = QWidget()
        sep_bottom.setFixedHeight(1)
        sep_bottom.setStyleSheet("background-color: #2B2B2B;")
        self.main_layout.addWidget(sep_bottom)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 10, 0, 2)
        footer.setSpacing(12)

        footer_hint = QLabel("Changes are applied after saving.")
        footer_hint.setStyleSheet("color: #555555; font-size: 11px;")
        footer.addWidget(footer_hint)
        footer.addStretch(1)

        # Use && so Qt renders a literal ampersand instead of a mnemonic
        self.btn_save = QPushButton("💾  Save && Restart Agent")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #3F51B5;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                border: none;
                border-radius: 8px;
                padding: 8px 28px;
            }
            QPushButton:hover {
                background-color: #5C6BC0;
            }
            QPushButton:pressed {
                background-color: #303F9F;
            }
        """)
        self.btn_save.clicked.connect(self.on_save_clicked)
        footer.addWidget(self.btn_save)

        self.main_layout.addLayout(footer)

        # Selection state
        self.nav_list.setCurrentRow(0)

        # Transaction loading dialogue
        self.loading_dialog = None

    def _dismiss_loading(self) -> None:
        """Close and clear the loading dialog if open."""
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None

    def set_agent(self, agent_name: str) -> None:
        """Load agent configs into their respective tabs."""
        self.agent_name = agent_name
        self.title_label.setText(f"Agent Administration: {agent_name}")

        agent_dir = agent_home(agent_name)

        # Load settings once and share the snapshot across tabs that need it.
        try:
            settings = load_settings(agent_dir)
        except Exception as exc:
            _log.warning("Failed to load settings for '%s': %s", agent_name, exc)
            settings = Settings()

        # Load configurations — each tab is isolated so one failure does not
        # prevent the remaining tabs from loading.
        _load_tab_safe("Settings", self.tab_settings.load_from_settings, settings)
        _load_tab_safe("Prompt", self.tab_prompt.load_file, agent_dir / "AGENT.md")
        _load_tab_safe("Memory", self.tab_memory.load_file, agent_dir / "MEMORY.md")
        _load_tab_safe("Skills", self.tab_skills.load_data, agent_dir)
        _load_tab_safe("Tasks", self.tab_tasks.load_data, agent_dir)
        _load_tab_safe("MCP", self.tab_mcp.load_data, agent_dir)
        _load_tab_safe("Subagents", self.tab_subagents.load_from_subagents, settings.subagents)

    def on_category_changed(self, row: int) -> None:
        if row >= 0:
            self.content_stack.setCurrentIndex(row)

    def on_start_clicked(self) -> None:
        self._run_async_control("start", "Starting gateway service...")

    def on_stop_clicked(self) -> None:
        self._run_async_control("stop", "Stopping gateway service...")

    def on_restart_clicked(self) -> None:
        self._run_async_control("restart", "Restarting gateway service...")

    def on_tui_clicked(self) -> None:
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
        """Spawn background control workers in QThreadPool."""
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
        worker.signals.finished.connect(lambda *_a, w=worker: self._active_workers.discard(w))
        worker.signals.error.connect(lambda *_a, w=worker: self._active_workers.discard(w))
        self._active_workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_control_finished(self, action: str, service_name: str, message: str) -> None:
        self._dismiss_loading()
        self.setEnabled(True)
        QMessageBox.information(self, "Service Action Completed", f"Action '{action}' completed:\n\n{message}")

    def _on_control_error(self, action: str, service_name: str, error_message: str) -> None:
        self._dismiss_loading()
        self.setEnabled(True)
        QMessageBox.critical(self, "Service Error", f"Failed to execute '{action}':\n\n{error_message}")

    def on_save_clicked(self) -> None:
        """Save all tabs to disk and trigger an async service restart."""
        self.setEnabled(False)
        self.loading_dialog = QProgressDialog("Saving files and restarting agent...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Save Changes")
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.setValue(0)
        self.loading_dialog.show()

        try:
            agent_dir = agent_home(self.agent_name)

            # 1. Build a single Settings object from both tabs that contribute to it.
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
            worker.signals.finished.connect(lambda *_a, w=worker: self._active_workers.discard(w))
            worker.signals.error.connect(lambda *_a, w=worker: self._active_workers.discard(w))
            self._active_workers.add(worker)
            QThreadPool.globalInstance().start(worker)

        except Exception as e:
            self._dismiss_loading()
            self.setEnabled(True)
            QMessageBox.critical(self, "Save Failed", f"Error writing configurations to disk:\n\n{e}")

    def _on_save_restart_finished(self, action: str, service_name: str, message: str) -> None:
        # Give systemd service 1.5 seconds to bootstrap properly before polling status
        QTimer.singleShot(1500, self._complete_save_workflow)

    def _complete_save_workflow(self) -> None:
        self._dismiss_loading()
        self.setEnabled(True)
        QMessageBox.information(
            self,
            "Saved Successfully",
            f"Agent '{self.agent_name}' has been successfully saved and restarted."
        )

    def _on_save_restart_error(self, action: str, service_name: str, error_message: str) -> None:
        self._dismiss_loading()
        self.setEnabled(True)
        QMessageBox.critical(
            self,
            "Service Error",
            f"Files were saved, but an error occurred while restarting the agent:\n\n{error_message}"
        )
