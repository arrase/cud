"""Settings form editor for loading and saving settings.yaml configurations."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cud.config.settings import GatewaySettings, ModelSettings, RuntimeSettings, Settings, load_settings


class SettingsTab(QWidget):
    """General agent configuration view covering model parameters and Discord tokens."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(16)

        # Cache settings object
        self.current_settings = Settings()

        # 1. Inferencia / LLM Config
        self.group_model = QGroupBox("Inference Configuration (Ollama)")
        self.model_layout = QFormLayout(self.group_model)

        self.input_provider = QLineEdit("ollama")
        self.input_provider.setReadOnly(True)
        self.input_provider.setStyleSheet("background-color: #252525; color: #888888;")

        self.input_model_name = QLineEdit()
        self.input_model_name.setPlaceholderText("gemma4:e4b")

        self.input_base_url = QLineEdit()
        self.input_base_url.setPlaceholderText("http://localhost:11434")

        self.input_temp = QDoubleSpinBox()
        self.input_temp.setRange(0.0, 2.0)
        self.input_temp.setSingleStep(0.1)
        self.input_temp.setValue(0.0)

        self.input_ctx = QSpinBox()
        self.input_ctx.setRange(1024, 2048576)
        self.input_ctx.setSingleStep(4096)
        self.input_ctx.setValue(32768)

        self.model_layout.addRow("LLM Provider:", self.input_provider)
        self.model_layout.addRow("Model Name:", self.input_model_name)
        self.model_layout.addRow("Base URL:", self.input_base_url)
        self.model_layout.addRow("Temperature:", self.input_temp)
        self.model_layout.addRow("Context Window:", self.input_ctx)

        self.layout.addWidget(self.group_model)

        # 2. Runtime
        self.group_runtime = QGroupBox("Runtime Options")
        self.runtime_layout = QFormLayout(self.group_runtime)

        self.chk_traversal = QCheckBox("Allow filesystem traversal (allow_traversal)")
        self.chk_traversal.setChecked(True)

        self.runtime_layout.addRow("", self.chk_traversal)
        self.layout.addWidget(self.group_runtime)

        # 3. Discord Gateway
        self.group_gateway = QGroupBox("Discord Gateway Bot Config")
        self.gateway_layout = QFormLayout(self.group_gateway)

        self.input_gw_provider = QLineEdit("discord")
        self.input_gw_provider.setReadOnly(True)
        self.input_gw_provider.setStyleSheet("background-color: #252525; color: #888888;")

        self.input_gw_mode = QLineEdit("bot")
        self.input_gw_mode.setReadOnly(True)
        self.input_gw_mode.setStyleSheet("background-color: #252525; color: #888888;")

        # Discord Token field with masked visibility toggle
        token_container = QWidget()
        token_layout = QHBoxLayout(token_container)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.setSpacing(8)

        self.input_token = QLineEdit()
        self.input_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_token.setPlaceholderText("Enter the Discord Bot Token...")

        self.chk_show_token = QCheckBox("Show")
        self.chk_show_token.stateChanged.connect(self.on_show_token_toggled)

        token_layout.addWidget(self.input_token, 1)
        token_layout.addWidget(self.chk_show_token)

        self.gateway_layout.addRow("Gateway Provider:", self.input_gw_provider)
        self.gateway_layout.addRow("Mode:", self.input_gw_mode)
        self.gateway_layout.addRow("Discord Token:", token_container)

        self.layout.addWidget(self.group_gateway)
        self.layout.addStretch(1)

    def on_show_token_toggled(self, state: int) -> None:
        """Toggle QLineEdit password character visibility mask.

        Args:
            state: Toggled integer checkbox state.
        """
        if state == Qt.CheckState.Checked.value:
            self.input_token.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.input_token.setEchoMode(QLineEdit.EchoMode.Password)

    def load_data(self, agent_dir: Path) -> None:
        """Read settings yaml values and bind them to interactive form inputs."""
        try:
            self.current_settings = load_settings(agent_dir)
        except Exception:
            # Fallback if settings.yaml doesn't exist
            self.current_settings = Settings()

        m = self.current_settings.model
        self.input_model_name.setText(m.name)
        self.input_base_url.setText(m.base_url)
        self.input_temp.setValue(m.temperature)
        self.input_ctx.setValue(m.context_window)

        r = self.current_settings.runtime
        self.chk_traversal.setChecked(r.allow_traversal)

        g = self.current_settings.gateway
        self.input_token.setText(g.token)

    def save_data(self) -> Settings:
        """Read active form inputs and return an updated Settings dataclass."""
        m_settings = ModelSettings(
            provider="ollama",
            name=self.input_model_name.text().strip(),
            base_url=self.input_base_url.text().strip(),
            temperature=self.input_temp.value(),
            context_window=self.input_ctx.value(),
        )

        r_settings = RuntimeSettings(
            allow_traversal=self.chk_traversal.isChecked(),
        )

        g_settings = GatewaySettings(
            provider="discord",
            token=self.input_token.text().strip(),
            mode="bot",
        )

        # Mutate current cached settings
        self.current_settings.model = m_settings
        self.current_settings.runtime = r_settings
        self.current_settings.gateway = g_settings

        return self.current_settings
