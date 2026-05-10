"""Engine CLI commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request

from rich.console import Console

console = Console()


def register_engine_commands(sub: argparse._SubParsersAction) -> None:
    engine = sub.add_parser("engine", help="Manage Ollama")
    engine_sub = engine.add_subparsers(dest="engine_command", required=True)
    engine_status = engine_sub.add_parser("status", help="Check Ollama status")
    engine_status.add_argument("--base-url", default="http://localhost:11434")
    engine_status.set_defaults(func=cmd_engine_status)
    engine_pull = engine_sub.add_parser("pull", help="Pull an Ollama model")
    engine_pull.add_argument("model_name")
    engine_pull.set_defaults(func=cmd_engine_pull)


def cmd_engine_status(args: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen(args.base_url.rstrip("/") + "/api/tags", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        console.print(f"[red]Ollama unavailable:[/red] {exc}")
        return 1
    models = [item.get("name", "") for item in data.get("models", [])]
    console.print(f"Ollama reachable at {args.base_url}. Models: {', '.join(models) or 'none'}")
    return 0


def cmd_engine_pull(args: argparse.Namespace) -> int:
    result = subprocess.run(["ollama", "pull", args.model_name], text=True)
    return result.returncode
