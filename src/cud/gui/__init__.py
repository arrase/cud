"""PySide6 desktop GUI package for Cud."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

# Elegant premium dark mode stylesheet
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

from cud.gui.dashboard import MainWindow


def main() -> None:
    """Execute the PySide6 Cud GUI application event loop."""
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    font = QFont("Outfit")
    if not font.exactMatch():
        font = QFont("Inter")
        if not font.exactMatch():
            font = QFont("sans-serif")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
