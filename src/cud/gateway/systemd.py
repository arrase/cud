"""User systemd service generation for gateway daemons."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cud.config.paths import cud_home, validate_agent_name

# A hung D-Bus call must not block the CLI (or a GUI worker thread) forever.
_SYSTEMD_TIMEOUT = 15

_CONTROL_ACTIONS = {
    "start": "started",
    "stop": "stopped",
    "restart": "restarted",
}


def service_name(agent: str) -> str:
    return f"cud-gateway-{validate_agent_name(agent)}.service"


def unit_path(agent: str) -> Path:
    return Path("~/.config/systemd/user").expanduser() / service_name(agent)


def render_unit(agent: str) -> str:
    validate_agent_name(agent)
    cud_path = shutil.which("cud") or f"{Path.home()}/.local/bin/cud"
    return f"""[Unit]
Description=Cud Gateway - Agent: {agent}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={cud_path} gateway run {agent}
Restart=always
RestartSec=5
RestartForceExitStatus=75
Environment="CUD_HOME={cud_home()}"

[Install]
WantedBy=default.target
"""


def install_unit(agent: str) -> Path:
    path = unit_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(agent), encoding="utf-8")
    return path


def stop_service(agent: str) -> subprocess.CompletedProcess[str]:
    return systemctl_user("stop", service_name(agent))


def disable_service(agent: str) -> subprocess.CompletedProcess[str]:
    return systemctl_user("disable", service_name(agent))


def remove_unit(agent: str) -> bool:
    path = unit_path(agent)
    if path.exists():
        path.unlink()
        return True
    return False


def uninstall_unit(agent: str) -> bool:
    removed = remove_unit(agent)
    if systemd_available():
        stop_service(agent)
        disable_service(agent)
        systemctl_user("daemon-reload")
    return removed


def get_service_status(agent: str) -> str:
    if not systemd_available():
        raise RuntimeError("systemd is not available on this system (systemctl command not found).")
    res = systemctl_user("is-active", service_name(agent))
    status = res.stdout.strip()
    if "failed" in status or "error" in status:
        return "failed"
    return "active" if res.returncode == 0 else "inactive"


def control_service(agent: str, action: str) -> str:
    if action not in _CONTROL_ACTIONS:
        raise ValueError(f"Unsupported systemd action: {action!r}")
    if not systemd_available():
        raise RuntimeError("systemd is not available on this system (systemctl command not found).")
    res = systemctl_user(action, service_name(agent))
    if res.returncode != 0:
        err_msg = res.stderr.strip() or f"systemctl process exit code {res.returncode}"
        raise RuntimeError(f"Failed to {action} service: {err_msg}")
    return f"Service {_CONTROL_ACTIONS[action]} successfully"


def systemd_available() -> bool:
    return shutil.which("systemctl") is not None


def systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args], check=False, text=True, capture_output=True, timeout=_SYSTEMD_TIMEOUT
    )


def journalctl_user(agent: str, lines: int = 50) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["journalctl", "--user", "-u", service_name(agent), "-n", str(lines), "--no-pager"],
        check=False,
        text=True,
        capture_output=True,
        timeout=_SYSTEMD_TIMEOUT,
    )

