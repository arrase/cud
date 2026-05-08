"""Cud Terminal User Interface using prompt_toolkit and rich."""

from __future__ import annotations

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown

from cud.agent.runtime import AgentRuntime
from cud.config.paths import agent_home
from cud.config.settings import save_settings


async def handle_command(cmd: str, runtime: AgentRuntime, console: Console) -> bool:
    """Handle slash commands. Returns True if the command is /quit or /exit."""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit"):
        return True
    elif command == "/new":
        await runtime.clear_history()
        console.print("[green]Session history cleared.[/green]")
    elif command == "/undo":
        result = await runtime.undo_last_exchange()
        console.print(f"[green]{result}[/green]")
    elif command == "/reload":
        await runtime.reload()
        console.print("[green]Agent tools and prompt reloaded.[/green]")
    elif command == "/memory":
        if args == "view":
            path = runtime.agent_dir / "MEMORY.md"
            content = path.read_text(encoding="utf-8") if path.exists() else "Memory is empty."
            console.print(Markdown(content))
        elif args == "clear":
            path = runtime.agent_dir / "MEMORY.md"
            path.write_text("# Long-Term Memory\n\nNo persistent memories yet.\n", encoding="utf-8")
            await runtime.reload()
            console.print("[green]Memory cleared.[/green]")
        else:
            console.print("[yellow]Usage: /memory view | /memory clear[/yellow]")
    elif command == "/model":
        if not args:
            console.print("[yellow]Usage: /model <model_name>[/yellow]")
            return False
        runtime.settings.model.name = args
        save_settings(runtime.agent_dir, runtime.settings)
        await runtime.reload()
        console.print(f"[green]Model temporarily set to `{args}`.[/green]")
    elif command == "/help":
        console.print(
            """[bold]Available commands:[/bold]
  [cyan]/new[/cyan]          Start a new session (clears history)
  [cyan]/model[/cyan] <name> Switch the model temporarily
  [cyan]/undo[/cyan]         Remove the last exchange
  [cyan]/reload[/cyan]       Reload tools and prompt
  [cyan]/memory[/cyan] view  View the agent's long-term memory
  [cyan]/memory[/cyan] clear Clear the agent's long-term memory
  [cyan]/quit[/cyan]         Exit the TUI"""
        )
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
    return False


async def run_tui(agent_name: str, thread_id: str = "local-tui") -> int:
    """Run the TUI loop for the given agent."""
    console = Console()
    agent_dir = agent_home(agent_name)

    if not agent_dir.exists():
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        return 1

    session = PromptSession()

    console.print(f"[bold green]Starting TUI for agent '{agent_name}' (Thread: {thread_id})[/bold green]")
    console.print("Type [bold]/help[/bold] for a list of commands, or [bold]/quit[/bold] to exit.\n")

    async with AgentRuntime(agent_dir, thread_id=thread_id) as runtime:
        while True:
            try:
                # Use prompt_toolkit for input
                user_input = await session.prompt_async("You: ")
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_exit = await handle_command(user_input, runtime, console)
                    if should_exit:
                        break
                    continue

                with console.status("[bold cyan]Agent is thinking...[/bold cyan]"):
                    response = await runtime.invoke(user_input)

                console.print("\n[bold magenta]Agent:[/bold magenta]")
                console.print(Markdown(response.content))
                console.print()

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")

    return 0
