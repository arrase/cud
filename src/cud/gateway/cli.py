"""Gateway CLI commands."""

from __future__ import annotations

import argparse

from rich.console import Console

from cud.config.paths import agent_home
from cud.config.settings import load_settings, save_settings
from cud.gateway import systemd
from cud.gateway.run import run_gateway

console = Console()


def register_gateway_commands(sub: argparse._SubParsersAction) -> None:
    gateway = sub.add_parser("gateway", help="Manage gateway daemon")
    gateway_sub = gateway.add_subparsers(dest="gateway_command", required=True)
    setup = gateway_sub.add_parser("setup", help="Configure gateway credentials")
    setup.add_argument("agent")
    setup.add_argument("platform", choices=["discord", "telegram", "slack"])
    setup.add_argument("--token", required=True)
    setup.set_defaults(func=cmd_gateway_setup)
    run = gateway_sub.add_parser("run", help="Run gateway in foreground")
    run.add_argument("agent")
    run.add_argument("--verbose", action="store_true")
    run.set_defaults(func=cmd_gateway_run)
    start = gateway_sub.add_parser("start", help="Start gateway user service")
    start.add_argument("agent")
    start.set_defaults(func=cmd_gateway_start)
    stop = gateway_sub.add_parser("stop", help="Stop gateway user service")
    stop.add_argument("agent")
    stop.set_defaults(func=cmd_gateway_stop)
    status = gateway_sub.add_parser("status", help="Show gateway service status")
    status.add_argument("agent")
    status.set_defaults(func=cmd_gateway_status)


def cmd_gateway_setup(args: argparse.Namespace) -> int:
    if args.platform != "discord":
        console.print("[yellow]Only Discord is implemented in v1; credentials were still saved as a stub.[/yellow]")
    directory = agent_home(args.agent)
    settings = load_settings(directory)
    settings.gateway.provider = args.platform
    settings.gateway.token = args.token
    save_settings(directory, settings)
    console.print(f"Configured {args.platform} gateway for {args.agent}")
    return 0


def cmd_gateway_run(args: argparse.Namespace) -> int:
    run_gateway(args.agent, verbose=args.verbose)
    return 0


def cmd_gateway_start(args: argparse.Namespace) -> int:
    path = systemd.install_unit(args.agent)
    console.print(f"Wrote {path}")
    if not systemd.systemd_available():
        console.print("[yellow]systemctl not found; run the unit manually or use `cud gateway run`.[/yellow]")
        return 0
    daemon = systemd.systemctl_user("daemon-reload")
    if daemon.returncode != 0:
        console.print(daemon.stderr)
        return daemon.returncode
    enable = systemd.systemctl_user("enable", "--now", systemd.service_name(args.agent))
    console.print(enable.stdout or enable.stderr)
    console.print("For persistent services after logout, run: loginctl enable-linger $USER")
    return enable.returncode


def cmd_gateway_stop(args: argparse.Namespace) -> int:
    result = systemd.systemctl_user("stop", systemd.service_name(args.agent))
    console.print(result.stdout or result.stderr)
    return result.returncode


def cmd_gateway_status(args: argparse.Namespace) -> int:
    status = systemd.systemctl_user("status", systemd.service_name(args.agent))
    logs = systemd.journalctl_user(args.agent)
    console.print(status.stdout or status.stderr)
    console.print(logs.stdout or logs.stderr)
    return 0 if status.returncode in (0, 3) else status.returncode
