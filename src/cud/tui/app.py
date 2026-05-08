"""Cud Terminal User Interface using prompt_toolkit and rich."""

from __future__ import annotations

import time
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import load_settings, save_settings

# ---------------------------------------------------------------------------
# Theme & constants
# ---------------------------------------------------------------------------

_THEME = Theme({
    "cud.accent": "bold cyan",
    "cud.dim": "dim",
    "cud.success": "green",
    "cud.warning": "yellow",
    "cud.error": "bold red",
    "cud.agent_border": "dim cyan",
})


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _welcome_banner(agent_name: str, model_name: str, thread_id: str, console: Console) -> None:
    """Render a styled welcome header panel."""
    title_text = Text()
    title_text.append("◆ ", style="bold bright_cyan")
    title_text.append("cud", style="bold bright_white")
    title_text.append(f" · {agent_name}", style="bold bright_cyan")

    info_lines = Text()
    info_lines.append("  model   ", style="dim")
    info_lines.append(model_name, style="bright_white")
    info_lines.append("\n  thread  ", style="dim")
    info_lines.append(thread_id, style="bright_white")
    info_lines.append("\n  ", style="dim")
    info_lines.append("/help", style="cyan")
    info_lines.append(" commands  ", style="dim")
    info_lines.append("/quit", style="cyan")
    info_lines.append(" exit", style="dim")

    panel = Panel(
        Group(title_text, Text(), info_lines),
        border_style="bright_blue",
        box=box.DOUBLE,
        padding=(1, 2),
    )
    console.print(panel)
    console.print()


def _agent_response(content: str, agent_name: str, elapsed: float, console: Console) -> None:
    """Render the agent's response with a left-border panel."""
    ts = datetime.now().strftime("%H:%M:%S")

    console.print(Text.assemble(
        ("╭ ", "dim cyan"),
        (agent_name, "bold cyan"),
        (f"  {ts}", "dim"),
        (f"  {elapsed:.1f}s", "dim"),
    ))

    panel = Panel(
        Markdown(content),
        border_style="cud.agent_border",
        box=box.ROUNDED,
        padding=(0, 2),
    )
    console.print(panel)
    console.print()


def _system_message(text: str, style: str, console: Console) -> None:
    """Render a system feedback message (command results, errors, etc.)."""
    console.print(Text.assemble(("  ▸ ", style), (text, style)))
    console.print()


def _help_panel(console: Console) -> None:
    """Render a styled help panel with available commands."""
    commands = [
        ("/new", "Start a new session"),
        ("/model <name>", "Switch model"),
        ("/undo", "Remove last exchange"),
        ("/reload", "Reload tools & prompt"),
        ("/memory view", "View agent memory"),
        ("/memory clear", "Clear agent memory"),
        ("/quit", "Exit"),
    ]
    lines = Text()
    for cmd, desc in commands:
        lines.append(f"  {cmd:<16}", style="cyan")
        lines.append(f" {desc}\n", style="dim")

    panel = Panel(
        lines,
        title="[bold white]commands[/bold white]",
        title_align="left",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    console.print(panel)
    console.print()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt_message() -> HTML:
    """Build the prompt_toolkit formatted prompt with a chevron."""
    return HTML('<style fg="#6e6e6e">❯</style> ')


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


async def handle_command(cmd: str, runtime: AgentRuntime, console: Console) -> bool:
    """Handle slash commands. Returns True if the command is /quit or /exit."""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit"):
        _system_message("Goodbye!", "cud.dim", console)
        return True
    elif command == "/new":
        await runtime.clear_history()
        _system_message("Session history cleared.", "cud.success", console)
    elif command == "/undo":
        result = await runtime.undo_last_exchange()
        _system_message(result, "cud.success", console)
    elif command == "/reload":
        await runtime.reload()
        _system_message("Agent tools and prompt reloaded.", "cud.success", console)
    elif command == "/memory":
        if args == "view":
            path = runtime.agent_dir / "MEMORY.md"
            content = path.read_text(encoding="utf-8") if path.exists() else "Memory is empty."
            panel = Panel(
                Markdown(content),
                title="[bold white]memory[/bold white]",
                title_align="left",
                border_style="dim cyan",
                box=box.ROUNDED,
                padding=(0, 2),
            )
            console.print(panel)
            console.print()
        elif args == "clear":
            path = runtime.agent_dir / "MEMORY.md"
            path.write_text("# Long-Term Memory\n\nNo persistent memories yet.\n", encoding="utf-8")
            await runtime.reload()
            _system_message("Memory cleared.", "cud.success", console)
        else:
            _system_message("Usage: /memory view | /memory clear", "cud.warning", console)
    elif command == "/model":
        if not args:
            _system_message("Usage: /model <model_name>", "cud.warning", console)
            return False
        runtime.settings.model.name = args
        save_settings(runtime.agent_dir, runtime.settings)
        await runtime.reload()
        _system_message(f"Model set to {args}.", "cud.success", console)
    elif command == "/help":
        _help_panel(console)
    else:
        _system_message(f"Unknown command: {command}", "cud.error", console)
    return False


# ---------------------------------------------------------------------------
# Main TUI loop
# ---------------------------------------------------------------------------


async def run_tui(agent_name: str, thread_id: str = "local-tui") -> int:
    """Run the TUI loop for the given agent."""
    console = Console(theme=_THEME)
    agent_dir = agent_home(agent_name)

    if not agent_dir.exists():
        _system_message(f"Agent '{agent_name}' not found.", "cud.error", console)
        return 1

    settings = load_settings(agent_dir)
    prompt_message = _build_prompt_message()
    session: PromptSession[str] = PromptSession()

    _welcome_banner(agent_name, settings.model.name, thread_id, console)

    async with AgentRuntime(agent_dir, thread_id=thread_id) as runtime:
        while True:
            try:
                user_input = await session.prompt_async(prompt_message)
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_exit = await handle_command(user_input, runtime, console)
                    if should_exit:
                        break
                    continue

                # Thinking indicator
                t0 = time.monotonic()
                with console.status(
                    "[cyan]thinking…[/cyan]",
                    spinner="dots",
                    spinner_style="cyan",
                ):
                    response = await runtime.invoke(user_input)
                elapsed = time.monotonic() - t0

                console.print()
                _agent_response(response.content, agent_name, elapsed, console)

            except (KeyboardInterrupt, EOFError):
                console.print()
                _system_message("Interrupted.", "cud.dim", console)
                break
            except Exception as e:
                _system_message(f"Error: {e}", "cud.error", console)

    return 0
