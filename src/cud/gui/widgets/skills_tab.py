"""Skills tab widget for showcasing and managing local agent skills."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cud.tools.skills import discover_skills


class SkillsTab(QWidget):
    """View to list local skills and quickly access their directory using the native file manager."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Title / Description
        self.title_label = QLabel("Local Skills")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Skills are Python modules or scripts packaged within the agent's workspace "
            "that provide additional capabilities to solve problems."
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA; line-height: 1.4;")
        self.layout.addWidget(self.desc_label)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Location (Path)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
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

        # Actions Toolbar
        self.actions_layout = QHBoxLayout()
        self.btn_open_folder = QPushButton("📂 Open in File Manager")
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #FFFFFF;
                border: 1px solid #3F51B5;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3F51B5;
            }
        """)
        self.btn_open_folder.clicked.connect(self.on_open_folder_clicked)
        self.actions_layout.addWidget(self.btn_open_folder)
        self.actions_layout.addStretch()

        self.layout.addLayout(self.actions_layout)

    def load_data(self, agent_dir: Path) -> None:
        """Scan skills directory and populate table."""
        self.agent_dir = agent_dir
        skills_dir = agent_dir / "workspace" / "skills"

        skills = discover_skills(skills_dir)
        self.table.setRowCount(len(skills))

        for idx, skill in enumerate(skills):
            # Name item
            name_item = QTableWidgetItem(skill.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(QColor("#FFFFFF"))
            font_bold = name_item.font()
            font_bold.setBold(True)
            name_item.setFont(font_bold)
            self.table.setItem(idx, 0, name_item)

            # Description item
            desc_item = QTableWidgetItem(skill.description)
            desc_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(idx, 1, desc_item)

            # Path item
            path_item = QTableWidgetItem(str(skill.path.parent.relative_to(agent_dir)))
            path_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            path_item.setForeground(QColor("#888888"))
            font_mono = path_item.font()
            font_mono.setFamily("monospace")
            path_item.setFont(font_mono)
            self.table.setItem(idx, 2, path_item)

    def on_open_folder_clicked(self) -> None:
        """Open agent workspace skills folder in the OS native file explorer."""
        if not self.agent_dir:
            return
        skills_dir = self.agent_dir / "workspace" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(skills_dir.resolve())))
