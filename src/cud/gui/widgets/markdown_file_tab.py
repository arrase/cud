"""Reusable monospace markdown file editor widget.

Replaces the former ``PromptTab`` and ``MemoryTab`` which were identical
apart from their placeholder text.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from cud.gui.core.styles import monospace_font


class MarkdownFileTab(QWidget):
    """Monospace markdown text editor for loading and saving a single file."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Monospace Text Editor
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(placeholder)
        self.editor.setFont(monospace_font(11))

        self.main_layout.addWidget(self.editor)

    def load_file(self, file_path: Path) -> None:
        """Read and load file content into the monospace text editor."""
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8")
            self.editor.setPlainText(text)
        else:
            self.editor.setPlainText("")

    def save_file(self, file_path: Path) -> None:
        """Write current text content to disk."""
        text = self.editor.toPlainText()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(text, encoding="utf-8")
