"""Asynchronous systemd worker threads using PySide6's QRunnable."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, QRunnable, Signal

from cud.gateway.systemd import service_name, systemctl_user, systemd_available


class SystemWorkerSignals(QObject):
    """Signals for communicating systemd service operations to the PySide6 UI thread."""

    # Arguments: (action, agent, stdout_message)
    finished = Signal(str, str, str)

    # Arguments: (action, agent, error_message)
    error = Signal(str, str, str)

    # Arguments: (agent, is_active, status_text)
    status_checked = Signal(str, bool, str)


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
            if not systemd_available():
                raise RuntimeError("systemd is not available on this system (systemctl command not found).")
            s_name = service_name(self.agent)

            if self.action == "status":
                res = systemctl_user("is-active", s_name)
                is_active = res.returncode == 0
                status_text = res.stdout.strip() or ("active" if is_active else "inactive")
                self.signals.status_checked.emit(self.agent, is_active, status_text)
                self.signals.finished.emit(self.action, self.agent, status_text)
            elif self.action in ("start", "stop", "restart"):
                res = systemctl_user(self.action, s_name)
                if res.returncode != 0:
                    err_msg = res.stderr.strip() or f"systemctl process exit code {res.returncode}"
                    raise RuntimeError(f"Failed to {self.action} service: {err_msg}")
                past = {"start": "started", "stop": "stopped", "restart": "restarted"}
                self.signals.finished.emit(self.action, self.agent, f"Service {past[self.action]} successfully")
            else:
                raise ValueError(f"Unsupported systemd action: {self.action!r}")
        except (subprocess.TimeoutExpired, OSError) as e:
            self.signals.error.emit(self.action, self.agent, f"systemd call failed: {e}")
        except Exception as e:
            self.signals.error.emit(self.action, self.agent, str(e))
