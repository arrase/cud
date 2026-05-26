"""Asynchronous systemd worker threads using PySide6's QRunnable."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from cud.gateway.systemd import (
    journalctl_user,
    service_name,
    systemctl_user,
    systemd_available,
)


class SystemWorkerSignals(QObject):
    """Signals for communicating systemd service operations to the PySide6 UI thread."""

    # Arguments: (action, service_name, stdout_message)
    finished = Signal(str, str, str)

    # Arguments: (action, service_name, error_message)
    error = Signal(str, str, str)

    # Arguments: (service_name, is_active, status_text)
    status_checked = Signal(str, bool, str)

    # Arguments: (service_name, log_lines)
    logs_retrieved = Signal(str, list)


class SystemdWorker(QRunnable):
    """Runnable worker to manage systemd service state asynchronously."""

    def __init__(self, action: str, agent: str, lines: int = 50) -> None:
        super().__init__()
        self.action = action
        self.agent = agent
        self.lines = lines
        self.signals = SystemWorkerSignals()

    def run(self) -> None:
        """Run the specified systemd action and emit status through Qt Signals."""
        s_name = service_name(self.agent)
        try:
            if not systemd_available():
                raise RuntimeError("systemd is not available on this system (systemctl command not found).")

            if self.action == "status":
                res = systemctl_user("is-active", s_name)
                is_active = (res.returncode == 0)
                status_text = res.stdout.strip() or ("active" if is_active else "inactive")
                self.signals.status_checked.emit(s_name, is_active, status_text)
                self.signals.finished.emit(self.action, s_name, status_text)

            elif self.action in ("start", "stop", "restart"):
                res = systemctl_user(self.action, s_name)
                if res.returncode != 0:
                    err_msg = res.stderr.strip() or f"systemctl process exit code {res.returncode}"
                    raise RuntimeError(f"Failed to {self.action} service: {err_msg}")
                past = {"start": "started", "stop": "stopped", "restart": "restarted"}
                self.signals.finished.emit(self.action, s_name, f"Service {past[self.action]} successfully")

            elif self.action == "journalctl":
                res = journalctl_user(self.agent, lines=self.lines)
                if res.returncode != 0:
                    err_msg = res.stderr.strip() or f"journalctl process exit code {res.returncode}"
                    raise RuntimeError(f"Failed to fetch logs: {err_msg}")
                log_lines = res.stdout.splitlines()
                self.signals.logs_retrieved.emit(s_name, log_lines)
                self.signals.finished.emit(self.action, s_name, f"Retrieved {len(log_lines)} log lines")

            else:
                raise ValueError(f"Unsupported systemd action: '{self.action}'")

        except Exception as e:
            self.signals.error.emit(self.action, s_name, str(e))
