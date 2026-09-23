"""Cud Terminal User Interface using prompt_toolkit and rich."""

from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from cud.agent.episodic_memory import load_past_user_prompts
from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import load_settings

# ---------------------------------------------------------------------------
# Theme & constants
# ---------------------------------------------------------------------------

_STYLE_DIM = "cud.dim"
_STYLE_SUCCESS = "cud.success"
_STYLE_WARNING = "cud.warning"
_STYLE_ERROR = "cud.error"
_COLOR_DIM_CYAN = "dim cyan"

_CMD_HELP = "/help"
_CMD_QUIT = "/quit"
_CMD_UNDO = "/undo"
_CMD_RELOAD = "/reload"

_THEME = Theme({
    "cud.accent": "bold cyan",
    _STYLE_DIM: "dim",
    _STYLE_SUCCESS: "green",
    _STYLE_WARNING: "yellow",
    _STYLE_ERROR: "bold red",
    "cud.agent_border": _COLOR_DIM_CYAN,
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
    info_lines.append(_CMD_HELP, style="cyan")
    info_lines.append(" commands  ", style="dim")
    info_lines.append(_CMD_QUIT, style="cyan")
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
        ("╭ ", _COLOR_DIM_CYAN),
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
        (_CMD_UNDO, "Remove last exchange"),
        (_CMD_RELOAD, "Reload tools & prompt"),
        ("/memory view", "View agent memory"),
        ("/memory clear", "Clear agent memory"),
        ("/memory search <q>", "Search past sessions"),
        (_CMD_QUIT, "Exit"),
    ]
    lines = Text()
    for cmd, desc in commands:
        lines.append(f"  {cmd:<18}", style="cyan")
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


_COMMANDS_META = {
    "/new": "Start a new session",
    "/model ": "Switch model",
    _CMD_UNDO: "Remove last exchange",
    _CMD_RELOAD: "Reload tools & prompt",
    "/memory view": "View agent memory",
    "/memory clear": "Clear agent memory",
    "/memory search ": "Search past sessions",
    _CMD_HELP: "Show commands",
    _CMD_QUIT: "Exit",
    "/exit": "Exit",
}

_completer = WordCompleter(
    list(_COMMANDS_META.keys()),
    meta_dict=_COMMANDS_META,
    ignore_case=True,
    sentence=True,
)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


async def handle_command(cmd: str, runtime: AgentRuntime, console: Console) -> bool:
    """Handle slash commands. Returns True if the command is /quit or /exit."""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in (_CMD_QUIT, "/exit"):
        _system_message("Goodbye!", _STYLE_DIM, console)
        return True
    elif command == "/new":
        result = runtime.new_session()
        _system_message(result, _STYLE_SUCCESS, console)
    elif command == _CMD_UNDO:
        result = await runtime.undo_last_exchange()
        _system_message(result, _STYLE_SUCCESS, console)
    elif command == _CMD_RELOAD:
        await runtime.reload()
        _system_message("Agent tools and prompt reloaded.", _STYLE_SUCCESS, console)
    elif command in ("/memory", "/history"):
        if args == "view":
            content = runtime.view_memory()
            panel = Panel(
                Markdown(content),
                title="[bold white]memory[/bold white]",
                title_align="left",
                border_style=_COLOR_DIM_CYAN,
                box=box.ROUNDED,
                padding=(0, 2),
            )
            console.print(panel)
            console.print()
        elif args == "clear":
            result = await runtime.clear_memory()
            _system_message(result, _STYLE_SUCCESS, console)
        elif args.startswith("search"):
            query = args.removeprefix("search").strip()
            if not query:
                _system_message("Usage: /memory search <query>", _STYLE_WARNING, console)
                return False
            results = runtime.search_past_conversations(query, limit=5)
            if not results:
                _system_message(f"No past conversations found matching '{query}'.", _STYLE_WARNING, console)
                return False
            table = Table(title=f"Past Conversations: '{query}'", box=box.ROUNDED)
            table.add_column("Session ID", style="bold cyan")
            table.add_column("Date", style="dim")
            table.add_column("Score", justify="right")
            table.add_column("Snippet Preview")
            for item in results:
                snippets_text = "\n".join(item["snippets"][:2])
                table.add_row(item["thread_id"][:8], item["formatted_date"], str(item["score"]), snippets_text)
            console.print(table)
            console.print()
        else:
            _system_message("Usage: /memory view | /memory clear | /memory search <query>", _STYLE_WARNING, console)
    elif command == "/model":
        if not args:
            _system_message("Usage: /model <model_name>", _STYLE_WARNING, console)
            return False
        result = await runtime.set_model(args)
        _system_message(result, _STYLE_SUCCESS, console)
    elif command == _CMD_HELP:
        _help_panel(console)
    else:
        _system_message(f"Unknown command: {command}", _STYLE_ERROR, console)
    return False


# ---------------------------------------------------------------------------
# Main TUI loop
# ---------------------------------------------------------------------------


async def run_tui(agent_name: str, thread_id: str = "") -> int:
    """Run the TUI loop for the given agent."""
    console = Console(theme=_THEME)
    agent_dir = agent_home(agent_name)

    if not agent_dir.exists():
        _system_message(f"Agent '{agent_name}' not found.", _STYLE_ERROR, console)
        return 1

    settings = load_settings(agent_dir)
    prompt_message = _build_prompt_message()
    prompt_history = InMemoryHistory()
    for prompt_text in load_past_user_prompts(agent_dir / "history.db"):
        prompt_history.append_string(prompt_text)
    session: PromptSession[str] = PromptSession(completer=_completer, history=prompt_history)

    thread_id = thread_id or uuid4().hex
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
                _system_message("Interrupted.", _STYLE_DIM, console)
                break
            except Exception as e:
                _system_message(f"Error: {e}", _STYLE_ERROR, console)

    return 0
