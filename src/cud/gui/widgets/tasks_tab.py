"""Periodic tasks manager and dashboard display for TASK.md schedules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from croniter import croniter
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cud.tools.tasks import discover_tasks


class TasksTab(QWidget):
    """View displaying periodic tasks configured for the selected agent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Title / Description
        self.title_label = QLabel("Scheduled Tasks (Cron)")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Scheduled tasks allow the agent to execute periodic workflows automatically. "
            "Each task is defined within the 'workspace/tasks/' directory using a TASK.md file with YAML frontmatter."
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA; line-height: 1.4;")
        self.layout.addWidget(self.desc_label)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Name",
            "Cron / Frequency",
            "Recipient",
            "Status",
            "Next Run Time",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1A1A1A;
                alternate-background-color: #222222;
                gridline-color: #2B2B2B;
                border: 1px solid #2B2B2B;
                border-radius: 6px;
                color: #E0E0E0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #FFFFFF;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #2B2B2B;
            }
            QTableWidget::item:selected {
                background-color: #3F51B5;
                color: #FFFFFF;
            }
        """)
        self.layout.addWidget(self.table)

    def load_data(self, agent_dir: Path) -> None:
        """Scan tasks directory, compute cron intervals and render to table."""
        self.agent_dir = agent_dir
        tasks_dir = agent_dir / "workspace" / "tasks"

        tasks = discover_tasks(tasks_dir)
        self.table.setRowCount(len(tasks))

        now = datetime.now(timezone.utc)

        for idx, task in enumerate(tasks):
            # 1. Name
            name_item = QTableWidgetItem(task.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(QColor("#FFFFFF"))
            font_bold = name_item.font()
            font_bold.setBold(True)
            name_item.setFont(font_bold)
            self.table.setItem(idx, 0, name_item)

            # 2. Schedule
            schedule_item = QTableWidgetItem(task.schedule)
            schedule_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            schedule_item.setForeground(QColor("#3498DB"))
            font_mono = schedule_item.font()
            font_mono.setFamily("monospace")
            schedule_item.setFont(font_mono)
            self.table.setItem(idx, 1, schedule_item)

            # 3. Destination (Channel or Direct Message)
            if task.channel_id:
                dest_str = f"Discord Channel: {task.channel_id}"
            elif task.user_id:
                dest_str = f"User DM: {task.user_id}"
            else:
                dest_str = "Console"
            dest_item = QTableWidgetItem(dest_str)
            dest_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(idx, 2, dest_item)

            # 4. Enabled/Disabled
            enabled_str = "Active ✓" if task.enabled else "Inactive ✗"
            enabled_item = QTableWidgetItem(enabled_str)
            enabled_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            font_ebold = enabled_item.font()
            font_ebold.setBold(True)
            enabled_item.setFont(font_ebold)
            if task.enabled:
                enabled_item.setForeground(QColor("#2ECC71"))
            else:
                enabled_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(idx, 3, enabled_item)

            # 5. Next Run Time (calculated via croniter)
            next_run = "—"
            if task.enabled:
                try:
                    cron = croniter(task.schedule, now)
                    next_run_dt = cron.get_next(datetime)
                    next_run = next_run_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    next_run = "Invalid Cron"
            next_run_item = QTableWidgetItem(next_run)
            next_run_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            next_run_item.setForeground(QColor("#F1C40F"))
            self.table.setItem(idx, 4, next_run_item)
