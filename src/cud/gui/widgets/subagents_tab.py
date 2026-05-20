"""Subagents hierarchy representation widget loaded from settings.yaml."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cud.config.settings import load_settings


class SubagentsTab(QWidget):
    """Hierarchical visualizer demonstrating subagent orchestration topologies."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_dir: Path | None = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Title
        self.title_label = QLabel("Subagents Topology")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Visualize the hierarchy of subagents and specialized assistants that this agent "
            "can delegate and orchestrate to solve complex tasks."
        )
        self.desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        self.layout.addWidget(self.desc_label)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Component / Parameter", "Configured Value"])
        self.tree.setColumnWidth(0, 240)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1A1A1A;
                border: 1px solid #2B2B2B;
                border-radius: 6px;
                color: #E0E0E0;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #222222;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #FFFFFF;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #2B2B2B;
            }
            QTreeWidget::item:hover {
                background-color: #26262B;
            }
            QTreeWidget::item:selected {
                background-color: #3F51B5;
                color: #FFFFFF;
            }
        """)
        self.layout.addWidget(self.tree)

    def load_data(self, agent_dir: Path) -> None:
        """Parse settings.yaml to recover subagents configurations and build the QTreeWidget."""
        self.agent_dir = agent_dir
        self.tree.clear()

        try:
            settings = load_settings(agent_dir)
        except Exception:
            # If load fails or settings.yaml is absent/empty
            return

        subagents = settings.subagents
        if not subagents:
            empty_item = QTreeWidgetItem(self.tree)
            empty_item.setText(0, "No subagents configured.")
            empty_item.setText(1, "Define subagents in settings.yaml.")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            return

        for sa in subagents:
            # Root Agent Node
            sa_item = QTreeWidgetItem(self.tree)
            sa_item.setText(0, f"🤖 Subagent: {sa.name}")
            sa_item.setText(1, sa.description or "No description")
            sa_item.setForeground(0, QColor("#FFFFFF"))
            f0 = sa_item.font(0)
            f0.setBold(True)
            f0.setPointSize(13)
            sa_item.setFont(0, f0)

            sa_item.setForeground(1, QColor("#3498DB"))
            f1 = sa_item.font(1)
            f1.setItalic(True)
            sa_item.setFont(1, f1)

            # 1. Model & Context Window
            model_item = QTreeWidgetItem(sa_item)
            model_item.setText(0, "   🧠 Model")
            model_item.setText(1, f"{sa.model or 'Default'} (Context: {sa.context_window or 'Default'})")
            model_item.setForeground(0, QColor("#E0E0E0"))

            # 2. System Prompt
            if sa.system_prompt:
                prompt_item = QTreeWidgetItem(sa_item)
                prompt_item.setText(0, "   📝 Directive Prompt")
                prompt_item.setText(1, sa.system_prompt.replace("\n", " ↵ "))
                prompt_item.setForeground(0, QColor("#E0E0E0"))
                prompt_item.setToolTip(1, sa.system_prompt)

            # 3. Skills Paths
            if sa.skills_paths:
                skills_root = QTreeWidgetItem(sa_item)
                skills_root.setText(0, "   🛠️ Skills Paths")
                skills_root.setText(1, f"{len(sa.skills_paths)} skills")
                skills_root.setForeground(0, QColor("#AAAAAA"))
                for idx, path in enumerate(sa.skills_paths):
                    p_item = QTreeWidgetItem(skills_root)
                    p_item.setText(0, f"      ↳ Skill #{idx+1}")
                    p_item.setText(1, path)
                    p_item.setForeground(1, QColor("#E0E0E0"))
                    fp = p_item.font(1)
                    fp.setFamily("monospace")
                    p_item.setFont(1, fp)

            # 4. MCP Servers
            if sa.mcp_servers:
                mcp_root = QTreeWidgetItem(sa_item)
                mcp_root.setText(0, "   🔌 MCP Servers")
                mcp_root.setText(1, f"{len(sa.mcp_servers)} servers")
                mcp_root.setForeground(0, QColor("#AAAAAA"))
                for srv in sa.mcp_servers:
                    s_item = QTreeWidgetItem(mcp_root)
                    s_item.setText(0, f"      🔌 {srv.name}")
                    cmd_str = f"{srv.command} " + " ".join(srv.args)
                    s_item.setText(1, cmd_str.strip())
                    s_item.setForeground(0, QColor("#FFFFFF"))
                    fs0 = s_item.font(0)
                    fs0.setBold(True)
                    s_item.setFont(0, fs0)

                    s_item.setForeground(1, QColor("#E0E0E0"))
                    fs1 = s_item.font(1)
                    fs1.setFamily("monospace")
                    s_item.setFont(1, fs1)

                    # Server Environment Variables if any
                    if srv.env:
                        env_root = QTreeWidgetItem(s_item)
                        env_root.setText(0, "         Environment Variables")
                        env_root.setText(1, f"{len(srv.env)} variables")
                        for k, v in srv.env.items():
                            var_item = QTreeWidgetItem(env_root)
                            var_item.setText(0, f"            {k}")
                            var_item.setText(1, v)
                            var_item.setForeground(0, QColor("#888888"))
                            fv0 = var_item.font(0)
                            fv0.setFamily("monospace")
                            var_item.setFont(0, fv0)

                            var_item.setForeground(1, QColor("#F1C40F"))
                            fv1 = var_item.font(1)
                            fv1.setFamily("monospace")
                            var_item.setFont(1, fv1)

            # Expand the subagent root node by default
            sa_item.setExpanded(True)
