"""Interactive agent chat history and transaction explorer tab."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cud.gui.core.history_db import LoadMessagesWorker, LoadThreadsWorker


class MessageBubble(QWidget):
    """Visual bubble representing a single message, styled according to sender role."""

    def __init__(self, role: str, content: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(6)

        # 1. Bubble Frame/Container
        self.bubble_frame = QWidget()
        self.bubble_layout = QVBoxLayout(self.bubble_frame)
        self.bubble_layout.setContentsMargins(12, 10, 12, 10)
        self.bubble_layout.setSpacing(6)

        # 2. Role Title Header
        role_map = {
            "user": "👤 User",
            "assistant": "🤖 Assistant",
            "system": "⚙️ System",
            "tool": "🛠️ Tool Result",
        }
        display_role = role_map.get(role.lower(), f"👤 {role.capitalize()}")

        self.role_label = QLabel(display_role)
        self.role_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #888888;")
        self.bubble_layout.addWidget(self.role_label)

        # 3. Main Text Content (Monospace for code/prompts readability)
        self.content_label = QLabel(content)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        mono_font = "Courier New, Fira Code, monospace"
        self.content_label.setStyleSheet(f"font-family: {mono_font}; font-size: 12px; line-height: 1.4;")
        self.bubble_layout.addWidget(self.content_label)

        # 4. JSON expander for tool calls
        self.json_edit = None
        self.btn_toggle = None
        if role.lower() == "tool":
            # Attempt to pretty-print if content is JSON
            try:
                parsed_json = json.loads(content)
                pretty_json = json.dumps(parsed_json, indent=2)
            except Exception:
                pretty_json = content

            self.btn_toggle = QPushButton("🔍 View Full Payload (JSON)")
            self.btn_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #2A2A2A;
                    color: #F1C40F;
                    border: 1px solid #F1C40F;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #F1C40F;
                    color: #000000;
                }
            """)
            self.btn_toggle.clicked.connect(self.toggle_json)
            self.bubble_layout.addWidget(self.btn_toggle)

            self.json_edit = QPlainTextEdit(pretty_json)
            self.json_edit.setReadOnly(True)
            self.json_edit.setFont(self.content_label.font())
            self.json_edit.setFixedHeight(120)
            self.json_edit.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #151515;
                    border: 1px solid #333333;
                    border-radius: 4px;
                    color: #F1C40F;
                }
            """)
            self.json_edit.hide()
            self.bubble_layout.addWidget(self.json_edit)

        # 5. Dynamic alignments and theme setups
        self.setup_aesthetics(role)

        self.layout.addWidget(self.bubble_frame)

    def setup_aesthetics(self, role: str) -> None:
        """Apply beautiful specific styles and align to standard messaging standards."""
        role = role.lower()
        if role == "user":
            # Right-aligned blue bubble
            self.layout.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.bubble_frame.setFixedWidth(500)
            self.bubble_frame.setStyleSheet("""
                background-color: #3F51B5;
                border-radius: 12px;
                border-top-right-radius: 2px;
                color: #FFFFFF;
            """)
            self.role_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #C5CAE9;")
            self.content_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")

        elif role == "assistant":
            # Left-aligned dark bubble with purple/blue highlights
            self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.bubble_frame.setFixedWidth(550)
            self.bubble_frame.setStyleSheet("""
                background-color: #222222;
                border: 1px solid #3F51B5;
                border-radius: 12px;
                border-top-left-radius: 2px;
                color: #E0E0E0;
            """)

        elif role == "system":
            # Center-aligned italicized light indicator
            self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bubble_frame.setStyleSheet("background: transparent;")
            self.role_label.hide()
            self.content_label.setStyleSheet("""
                color: #888888;
                font-style: italic;
                font-size: 11px;
                alignment: center;
            """)
            self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        elif role == "tool":
            # Left-aligned compact amber bubble
            self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.bubble_frame.setFixedWidth(550)
            self.bubble_frame.setStyleSheet("""
                background-color: #2D281E;
                border: 1px solid #F1C40F;
                border-radius: 12px;
                border-top-left-radius: 2px;
                color: #E5E7EB;
            """)
            self.role_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #F1C40F;")

    def toggle_json(self) -> None:
        """Expand or collapse the custom tools output payload text field."""
        if self.json_edit is None or self.btn_toggle is None:
            return
        visible = self.json_edit.isVisible()
        self.json_edit.setVisible(not visible)
        self.btn_toggle.setText(
            "🔽 Hide JSON Payload" if not visible else "🔍 View Full Payload (JSON)"
        )


class HistoryTab(QWidget):
    """View managing historical chat threads list and full conversations view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_name = ""
        self.agent_dir: Path | None = None
        self.selected_thread_id = ""

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Title
        self.title_label = QLabel("Chat History")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        self.layout.addWidget(self.title_label)

        # Splitter Layout: Threads List vs Message Box
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #2B2B2B; width: 2px; }")

        # 1. Threads Sidebar (Left)
        self.sidebar = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(6)

        self.sidebar_title = QLabel("Conversation Threads")
        self.sidebar_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #AAAAAA;")
        self.sidebar_layout.addWidget(self.sidebar_title)

        self.threads_list = QListWidget()
        self.threads_list.setStyleSheet("""
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
        """)
        self.threads_list.itemClicked.connect(self.on_thread_clicked)
        self.sidebar_layout.addWidget(self.threads_list)

        self.splitter.addWidget(self.sidebar)

        # 2. Message Viewer Frame (Right)
        self.chat_view = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_view)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(6)

        self.chat_title = QLabel("Messages")
        self.chat_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #AAAAAA;")
        self.chat_layout.addWidget(self.chat_title)

        # Message Scroll Box
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1A1A1A;
                border: 1px solid #2B2B2B;
                border-radius: 6px;
            }
        """)

        # Message list container widget
        self.bubbles_container = QWidget()
        self.bubbles_container.setStyleSheet("background-color: #121212;")
        self.bubbles_layout = QVBoxLayout(self.bubbles_container)
        self.bubbles_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.bubbles_layout.setContentsMargins(10, 10, 10, 10)
        self.bubbles_layout.setSpacing(12)

        self.scroll_area.setWidget(self.bubbles_container)
        self.chat_layout.addWidget(self.scroll_area)

        self.splitter.addWidget(self.chat_view)

        # Set sizes proportion: 1 (Sidebar) : 3 (Chat view)
        self.splitter.setSizes([200, 600])

        self.layout.addWidget(self.splitter)

        # Setup friendly blank states
        self.clear_bubbles_layout()
        lbl = QLabel("Select a conversation thread from the left to explore the messages.")
        lbl.setStyleSheet("color: #888888; font-size: 13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubbles_layout.addWidget(lbl)

    def load_data(self, agent_dir: Path) -> None:
        """Contextualize database and reload conversation history threads asynchronously."""
        self.agent_dir = agent_dir
        self.agent_name = agent_dir.name
        self.selected_thread_id = ""

        # Trigger Thread Loader Worker
        self.threads_list.clear()
        self.clear_bubbles_layout()

        loading_item = QListWidgetItem("Loading threads...")
        loading_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.threads_list.addItem(loading_item)

        worker = LoadThreadsWorker(self.agent_name)
        worker.signals.threads_loaded.connect(self.on_threads_loaded)
        worker.signals.error.connect(self.on_db_error)
        QThreadPool.globalInstance().start(worker)

    def clear_bubbles_layout(self) -> None:
        """Clear all widgets from the scroll view layout."""
        while self.bubbles_layout.count():
            item = self.bubbles_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_threads_loaded(self, threads: list[dict[str, Any]]) -> None:
        """Render thread listings to Sidebar list widget."""
        self.threads_list.clear()
        if not threads:
            no_threads_item = QListWidgetItem("No registered interactions")
            no_threads_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.threads_list.addItem(no_threads_item)
            return

        for th in threads:
            item = QListWidgetItem()
            # Store the thread_id on the item
            item.setData(Qt.ItemDataRole.UserRole, th["thread_id"])

            time_str = th["timestamp"]
            # Shorten timestamp if it's too long
            if len(time_str) > 16:
                time_str = time_str[:16].replace("T", " ")

            preview = th["latest_message"] or ""
            if len(preview) > 30:
                preview = preview[:27] + "..."

            display_text = f"🧵 Thread: {th['thread_id'][:8]}\n🕒 {time_str}\n💬 {preview}"
            item.setText(display_text)
            self.threads_list.addItem(item)

    def on_thread_clicked(self, item: QListWidgetItem) -> None:
        """Triggered when user clicks a thread row. Spawns message loader worker."""
        thread_id = item.data(Qt.ItemDataRole.UserRole)
        if not thread_id:
            return

        if thread_id == self.selected_thread_id:
            return

        self.selected_thread_id = thread_id
        self.clear_bubbles_layout()

        lbl_loading = QLabel("Loading thread messages...")
        lbl_loading.setStyleSheet("color: #AAAAAA; font-size: 13px; font-style: italic;")
        lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubbles_layout.addWidget(lbl_loading)

        worker = LoadMessagesWorker(self.agent_name, thread_id)
        worker.signals.messages_loaded.connect(self.on_messages_loaded)
        worker.signals.error.connect(self.on_db_error)
        QThreadPool.globalInstance().start(worker)

    def on_messages_loaded(self, thread_id: str, messages: list[dict[str, str]]) -> None:
        """Render standard conversation bubbles in the layout viewport."""
        if thread_id != self.selected_thread_id:
            return

        self.clear_bubbles_layout()

        if not messages:
            lbl = QLabel("The selected thread has no readable messages.")
            lbl.setStyleSheet("color: #888888; font-size: 13px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bubbles_layout.addWidget(lbl)
            return

        for msg in messages:
            bubble = MessageBubble(msg["role"], msg["content"])
            self.bubbles_layout.addWidget(bubble)

        # Force scroll area to bottom after UI repaints
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def on_db_error(self, err_message: str) -> None:
        """Handle SQLite worker errors gracefully."""
        self.clear_bubbles_layout()
        lbl = QLabel(f"⚠️ Error reading history:\n\n{err_message}")
        lbl.setStyleSheet("color: #E74C3C; font-size: 13px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubbles_layout.addWidget(lbl)
