# Cud Project Context

`cud` is a local multi-agent framework designed to bring autonomous AI agents to your terminal and messaging platforms like Discord. It integrates Ollama for local LLM execution, LangGraph for orchestration, and supports extensible tools via MCP (Model Context Protocol) and Markdown-defined "skills".

## Project Structure

- `src/cud/`: Main source code directory.
    - `cli.py`: Command-line interface for managing agents, gateways, and tools.
    - `agent/`: Core agent runtime, prompts, and message management logic.
    - `gateway/`: Adapters for external platforms (e.g., Discord) and background service management.
    - `tools/`: Implementation of core agent tools (filesystem, memory, shell, MCP).
    - `config/`: Path management, settings, and agent scaffolding.
    - `templates/`: Default templates for agents, memory, and configuration.
- `tests/`: Project test suite.
- `design/`: Design documents and specifications.

## Key Concepts

- **Agent**: A named instance with its own configuration (`settings.yaml`), long-term memory (`MEMORY.md`), and workspace.
- **Gateway**: A daemon that connects an agent to a platform (e.g., Discord).
- **Skill**: A set of tools or instructions defined in a `SKILL.md` file within an agent's directory.
- **MCP (Model Context Protocol)**: Support for external tool servers.
- **Memory**: Agents use a local `MEMORY.md` file for persistent, long-term context.

## Development Workflow

### Installation
To set up the development environment:
```bash
pip install -e .[dev]
```

### Running the CLI
The main entry point is the `cud` command:
```bash
cud --help
```

### Testing
Run the test suite using `pytest`:
```bash
pytest
```

### Managing Agents
- Create: `cud agent create <name>`
- List: `cud agent list`
- Configure: `cud agent config <name> --model <model_name>`

### Running the Gateway
- Foreground: `cud gateway run <agent_name>`
- Background (systemd): `cud gateway start <agent_name>`

## Conventions

- **Type Safety**: The project uses Python type hints and `pydantic` for settings.
- **AsyncIO**: Core gateway and tool discovery logic utilize asynchronous programming.
- **Rich Output**: The CLI uses the `rich` library for formatted terminal output.
- **Local First**: Prioritizes local execution via Ollama and local storage for agent state and memory.

## TODOs / Roadmap
- Implement Telegram and Slack gateways (currently stubs).
- Enhance sub-agent capabilities.
- Expand built-in skill library.
