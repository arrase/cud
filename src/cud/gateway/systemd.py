"""User systemd service generation for gateway daemons."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cud.config.paths import agent_home


def service_name(agent: str) -> str:
    return f"cud-gateway-{agent}.service"


def unit_path(agent: str) -> Path:
    return Path("~/.config/systemd/user").expanduser() / service_name(agent)


def render_unit(agent: str, *, python_path: str | None = None) -> str:
    python_path = python_path or sys.executable
    home = agent_home(agent)
    return f"""[Unit]
Description=Cud Gateway - Agent: {agent}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python_path} -m cud.gateway.run {agent}
Restart=always
RestartSec=5
RestartForceExitStatus=75
Environment=\"CUD_HOME={home.parent.parent}\"

[Install]
WantedBy=default.target
"""


def install_unit(agent: str) -> Path:
    path = unit_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(agent), encoding="utf-8")
    return path


def systemd_available() -> bool:
    return shutil.which("systemctl") is not None


def systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", "--user", *args], check=False, text=True, capture_output=True)


def journalctl_user(agent: str, lines: int = 50) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["journalctl", "--user", "-u", service_name(agent), "-n", str(lines), "--no-pager"],
        check=False,
        text=True,
        capture_output=True,
    )

