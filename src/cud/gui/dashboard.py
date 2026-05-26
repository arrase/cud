"""Main QMainWindow orchestrator for the Cud desktop dashboard."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from cud.gui.views.inventory import InventoryView
from cud.gui.views.agent_detail import AgentDetailView

ICON_PATH = Path(__file__).parent / "assets" / "icon.png"


class MainWindow(QMainWindow):
    """Orchestrates high-level stacked navigation and visual layout of the application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cud Agent Controller")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1100, 750)

        # Root stacked widget
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Instantiate sub-views
        self.inventory_view = InventoryView(self)
        self.agent_detail_view = AgentDetailView(self)

        # Add views to stack
        self.stack.addWidget(self.inventory_view)
        self.stack.addWidget(self.agent_detail_view)

        # Connect view signals for stack navigation
        self.inventory_view.agent_selected.connect(self.show_agent_detail)
        self.agent_detail_view.back_to_inventory.connect(self.show_inventory)

        # Initial screen: landing inventory
        self.show_inventory()

    def show_agent_detail(self, agent_name: str) -> None:
        self.agent_detail_view.set_agent(agent_name)
        self.stack.setCurrentWidget(self.agent_detail_view)

    def show_inventory(self) -> None:
        self.inventory_view.reload_agents()
        self.stack.setCurrentWidget(self.inventory_view)
