"""Asynchronous systemd worker threads using PySide6's QRunnable."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, QRunnable, Signal

from cud.gateway.systemd import control_service, get_service_status


class SystemWorkerSignals(QObject):
    """Signals for communicating systemd service operations to the PySide6 UI thread."""

    finished = Signal(str, str, str)
    error = Signal(str, str, str)
    status_checked = Signal(str, str)


class SystemdWorker(QRunnable):
    """Runnable worker to manage systemd service state asynchronously."""

    def __init__(self, action: str, agent: str) -> None:
        super().__init__()
        self.action = action
        self.agent = agent
        self.signals = SystemWorkerSignals()

    def run(self) -> None:
        """Run the specified systemd action and emit status through Qt Signals."""
        try:
            if self.action == "status":
                status_text = get_service_status(self.agent)
                self.signals.status_checked.emit(self.agent, status_text)
                self.signals.finished.emit(self.action, self.agent, status_text)
            else:
                msg = control_service(self.agent, self.action)
                self.signals.finished.emit(self.action, self.agent, msg)
        except (subprocess.TimeoutExpired, OSError) as e:
            self.signals.error.emit(self.action, self.agent, f"systemd call failed: {e}")
        except (RuntimeError, ValueError) as e:
            self.signals.error.emit(self.action, self.agent, str(e))
