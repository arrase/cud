"""Prompt directive editor widget for AGENT.md."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class PromptTab(QWidget):
    """Monospace markdown text editor for custom agent system prompts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Monospace Text Editor
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("# Agent Directive\n\nWrite the agent prompt here...")

        mono_font = QFont("Courier New")
        if not mono_font.exactMatch():
            mono_font = QFont("Fira Code")
            if not mono_font.exactMatch():
                mono_font = QFont("monospace")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(11)
        self.editor.setFont(mono_font)

        self.main_layout.addWidget(self.editor)

    def load_file(self, file_path: Path) -> None:
        """Read and load prompt file content to the monospace text edit."""
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8")
            self.editor.setPlainText(text)
        else:
            self.editor.setPlainText("")

    def save_file(self, file_path: Path) -> None:
        """Write current monospace prompt text content atomically to disk."""
        text = self.editor.toPlainText()
        file_path.write_text(text, encoding="utf-8")
