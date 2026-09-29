"""Landing view showcasing agent deployment inventory and lifecycle states."""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from cud.config.paths import validate_agent_name
from cud.config.scaffold import create_agent, list_agents
from cud.gui.core.system_workers import SystemdWorker

_log = logging.getLogger(__name__)

# Model roles for the status LED text and the agent's home path.
STATUS_ROLE_OFFSET = 2
PATH_ROLE_OFFSET = 3
STATUS_CHECKING = "checking"
HOME_PATH = Path.home()


class AgentItemDelegate(QStyledItemDelegate):
    """Custom delegate painting premium dark-themed agent info cards with status LEDs."""

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        return QSize(250, 85)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get metadata roles
        name = index.data(Qt.ItemDataRole.DisplayRole)
        status = index.data(Qt.ItemDataRole.UserRole + STATUS_ROLE_OFFSET) or "inactive"
        home_path = index.data(Qt.ItemDataRole.UserRole + PATH_ROLE_OFFSET) or ""

        # Rect geometries
        rect = option.rect
        card_rect = QRectF(rect.x() + 8, rect.y() + 6, rect.width() - 16, rect.height() - 12)

        # Background card color based on states
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if is_selected:
            bg_color = QColor("#222436")
            border_color = QColor("#3F51B5")
        elif is_hovered:
            bg_color = QColor("#25252B")
            border_color = QColor("#3E3E42")
        else:
            bg_color = QColor("#1E1E1E")
            border_color = QColor("#2B2B2B")

        # Draw card rounded background
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(card_rect, 8.0, 8.0)

        # Draw Status LED Indicator Circle
        led_color = QColor("#7F8C8D")  # Gray for inactive / unknown
        if status == "active":
            led_color = QColor("#2ECC71")  # Active Green
        elif status in ("failed", "error"):
            led_color = QColor("#E74C3C")  # Failed Red
        elif status == "checking":
            led_color = QColor("#F1C40F")  # Loading Yellow

        led_x = card_rect.x() + 18
        led_y = card_rect.y() + (card_rect.height() / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(led_color))
        painter.drawEllipse(QRectF(led_x - 5, led_y - 5, 10, 10))

        # Text labels offsets
        text_x = led_x + 22
        title_y = card_rect.y() + 28
        sub_y = card_rect.y() + 48

        # Draw agent name bold text
        name_font = QFont(painter.font())
        name_font.setBold(True)
        name_font.setPointSize(11)
        painter.setFont(name_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(int(text_x), int(title_y), str(name))

        # Draw details text
        sub_font = QFont(painter.font())
        sub_font.setBold(False)
        sub_font.setPointSize(9)
        painter.setFont(sub_font)
        painter.setPen(QColor("#8A8A8F"))

        display_path = home_path.replace(str(HOME_PATH), "~")
        painter.drawText(int(text_x), int(sub_y), f"{display_path}  •  Status: {status}")

        painter.restore()


class InventoryView(QWidget):
    """View rendering list of agent modules and managing creation scaffolding."""

    agent_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_workers: set[SystemdWorker] = set()
        self._generation = 0

        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(16)

        # Top Toolbar layout
        self.toolbar = QHBoxLayout()
        self.title = QLabel("Infrastructure Dashboard")
        self.title.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFFFFF;")

        self.btn_create = QPushButton("+ Create Agent")
        self.btn_create.setStyleSheet("background-color: #3F51B5; color: #FFFFFF; font-weight: bold;")
        self.btn_create.clicked.connect(self.on_create_agent_clicked)

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.clicked.connect(self.reload_agents)

        self.toolbar.addWidget(self.title)
        self.toolbar.addStretch(1)
        self.toolbar.addWidget(self.btn_create)
        self.toolbar.addWidget(self.btn_refresh)

        self.main_layout.addLayout(self.toolbar)

        # ListView config
        self.list_view = QListView()
        self.list_view.setFrameShape(QFrame.Shape.NoFrame)
        self.list_view.setItemDelegate(AgentItemDelegate(self))
        self.list_view.setSpacing(4)
        self.list_view.doubleClicked.connect(self.on_agent_double_clicked)

        # Model config
        self.model = QStandardItemModel()
        self.list_view.setModel(self.model)

        self.main_layout.addWidget(self.list_view, 1)

        # Load list
        self.reload_agents()

    def reload_agents(self) -> None:
        """Scan ~/.cud/agents/ for folders and retrieve status asynchronously."""
        self._active_workers.clear()
        self.model.clear()
        agents = list_agents()

        if not agents:
            placeholder = QStandardItem("No configured agents found.")
            placeholder.setEnabled(False)
            self.model.appendRow(placeholder)
            return

        # Tag each load so signals from a superseded generation are ignored;
        # a late worker from the previous load would otherwise paint a stale
        # status into the rebuilt model.
        generation = self._generation = self._generation + 1
        for path in agents:
            agent_name = path.name
            item = QStandardItem(agent_name)
            item.setData(STATUS_CHECKING, Qt.ItemDataRole.UserRole + STATUS_ROLE_OFFSET)
            item.setData(str(path), Qt.ItemDataRole.UserRole + PATH_ROLE_OFFSET)
            self.model.appendRow(item)

            # Async Status Query via QThreadPool
            worker = SystemdWorker("status", agent_name)
            worker.signals.status_checked.connect(
                partial(self._on_status_checked, generation))
            worker.signals.error.connect(partial(self._on_status_error, generation))
            worker.signals.finished.connect(lambda *_a, w=worker: self._active_workers.discard(w))
            worker.signals.error.connect(lambda *_a, w=worker: self._active_workers.discard(w))
            self._active_workers.add(worker)
            QThreadPool.globalInstance().start(worker)

    def _set_status(self, agent_name: str, status: str) -> None:
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item and item.text() == agent_name:
                item.setData(status, Qt.ItemDataRole.UserRole + STATUS_ROLE_OFFSET)
                return

    def _on_status_checked(self, generation: int, agent_name: str, is_active: bool, status_text: str) -> None:
        if generation != self._generation:
            return
        status = "active" if is_active else "inactive"
        if "failed" in status_text or "error" in status_text:
            status = "failed"
        self._set_status(agent_name, status)

    def _on_status_error(self, generation: int, action: str, agent_name: str, error_message: str) -> None:
        if generation != self._generation:
            return
        # Surface the failure instead of pretending the service is merely stopped.
        _log.warning("Status check failed for '%s': %s", agent_name, error_message)
        self._set_status(agent_name, "failed")

    def on_create_agent_clicked(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Create Agent",
            "New agent name (only alphanumeric and '.', '_', '-'):"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        try:
            validate_agent_name(name)
            create_agent(name)
            QMessageBox.information(
                self,
                "Success",
                f"Agent '{name}' has been successfully created with the default template."
            )
            self.reload_agents()
        except ValueError as e:
            QMessageBox.critical(self, "Invalid Name", str(e))
        except FileExistsError as e:
            QMessageBox.critical(self, "Agent Already Exists", str(e))
        except OSError as e:
            QMessageBox.critical(self, "Creation Failed", str(e))

    def on_agent_double_clicked(self, index: QModelIndex) -> None:
        item = self.model.itemFromIndex(index)
        if item and item.isEnabled():
            self.agent_selected.emit(item.text())
