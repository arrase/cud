"""Shared GUI styles, fonts, and theme constants for the Cud desktop application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

ICON_PATH = Path(__file__).resolve().parents[1] / "assets" / "icon.png"


# ---------------------------------------------------------------------------
# Font factories and shared widget builders
# ---------------------------------------------------------------------------


def ui_font(point_size: int = 10) -> QFont:
    """Return the best available sans-serif UI font with the given *point_size*."""
    font = QFont("Outfit")
    if not font.exactMatch():
        font = QFont("Inter")
        if not font.exactMatch():
            font = QFont("sans-serif")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(point_size)
    return font


def monospace_font(size: int = 10) -> QFont:
    """Return the best available monospace font with the given point *size*.

    Tries Courier New → Fira Code → generic monospace, setting the style
    hint so Qt falls back gracefully on any platform.
    """
    font = QFont("Courier New")
    if not font.exactMatch():
        font = QFont("Fira Code")
        if not font.exactMatch():
            font = QFont("monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    return font


def create_action_button(text: str, style: str, on_click: Callable[[], None]) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(style)
    btn.clicked.connect(on_click)
    return btn


def create_tab_header(layout: QVBoxLayout, title: str, description: str) -> None:
    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
    layout.addWidget(title_label)

    desc_label = QLabel(description)
    desc_label.setWordWrap(True)
    desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA; line-height: 1.4;")
    layout.addWidget(desc_label)


def create_separator() -> QWidget:
    sep = QWidget()
    sep.setFixedHeight(1)
    sep.setStyleSheet("background-color: #2B2B2B;")
    return sep


def create_readonly_table(headers: list[str], stretch_column: int = -1) -> QTableWidget:
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    for col in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if col == stretch_column else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(col, mode)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(TABLE_STYLE)
    return table


def make_table_item(
    text: str,
    *,
    color: str = "",
    bold: bool = False,
    mono: bool = False,
) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    if color:
        item.setForeground(QColor(color))
    if mono:
        item.setFont(monospace_font())
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    return item


# ---------------------------------------------------------------------------
# Elegant premium dark-mode stylesheet (application-wide)
# ---------------------------------------------------------------------------

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #121212;
}
QWidget {
    background-color: #121212;
    color: #E0E0E0;
}
QLabel {
    color: #E0E0E0;
}
QPushButton {
    background-color: #1E1E1E;
    color: #E0E0E0;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2E2E2E;
    border-color: #444444;
}
QPushButton:pressed {
    background-color: #1A1A1A;
}
QTextEdit, QLineEdit, QListWidget {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2B2B2B;
    border-radius: 6px;
    padding: 6px;
}
QTextEdit:focus, QLineEdit:focus, QListWidget:focus {
    border-color: #3F51B5;
}
QScrollBar:vertical {
    border: none;
    background: #121212;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #2E2E2E;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #444444;
}
"""

# ---------------------------------------------------------------------------
# Reusable widget-level stylesheets
# ---------------------------------------------------------------------------

TABLE_STYLE = """
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
"""

ACTION_BTN_ADD = """
    QPushButton {
        background-color: #2ECC71;
        color: #FFFFFF;
        font-weight: bold;
        padding: 6px 12px;
        border-radius: 4px;
    }
    QPushButton:hover { background-color: #27AE60; }
"""

ACTION_BTN_DELETE = """
    QPushButton {
        background-color: #E74C3C;
        color: #FFFFFF;
        font-weight: bold;
        padding: 6px 12px;
        border-radius: 4px;
    }
    QPushButton:hover { background-color: #C0392B; }
"""

ACTION_BTN_UPDATE = """
    QPushButton {
        background-color: #3F51B5;
        color: #FFFFFF;
        font-weight: bold;
        padding: 8px;
        border-radius: 4px;
    }
    QPushButton:hover { background-color: #303F9F; }
"""

ACTION_BTN_FOLDER = """
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
"""

LIST_STYLE = """
    QListWidget {
        background-color: #1A1A1A;
        border: 1px solid #2B2B2B;
        border-radius: 6px;
        color: #E0E0E0;
    }
    QListWidget::item {
        padding: 10px;
        border-bottom: 1px solid #222222;
        border-radius: 4px;
    }
    QListWidget::item:hover {
        background-color: #26262B;
    }
    QListWidget::item:selected {
        background-color: #3F51B5;
        color: #FFFFFF;
    }
"""
