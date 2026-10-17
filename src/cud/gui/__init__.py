"""PySide6 desktop GUI package for Cud."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from cud.gui.core.styles import DARK_STYLESHEET, ICON_PATH, ui_font
from cud.gui.dashboard import MainWindow


def main() -> None:
    """Execute the PySide6 Cud GUI application event loop."""
    # Without this, _log.warning/_log.exception output is lost when launched
    # from a .desktop file (no stderr).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setFont(ui_font())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
