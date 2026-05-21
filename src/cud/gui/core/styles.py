"""Shared GUI styles, fonts, and theme constants for the Cud desktop application."""

from __future__ import annotations

from PySide6.QtGui import QFont


# ---------------------------------------------------------------------------
# Monospace font factory
# ---------------------------------------------------------------------------


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
