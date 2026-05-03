# Cud

**Cud** is a local multi-agent framework designed to bring autonomous AI agents to your terminal and messaging platforms like Discord. It leverages Ollama for local LLM execution, LangGraph for orchestration, and supports extensible tools via MCP (Model Context Protocol) and Markdown-defined "skills".

## Features

- **Local First**: Prioritizes local execution via Ollama and local storage for agent state and memory.
- **Multi-Agent Architecture**: Create and manage multiple named agent instances, each with their own configuration, memory (`MEMORY.md`), and isolated workspace.
- **Platform Gateways**: Connect your agents to external platforms. Currently features a Discord gateway, with planned support for Telegram and Slack.
- **Daemon Support**: Built-in integration with `systemd` to run your agent gateways as background user services.
- **Extensible Tooling**: 
  - **Core Tools**: Filesystem operations, shell execution, and memory management.
  - **MCP**: Native support for the Model Context Protocol to add external tool servers.
  - **Skills**: Progressive-disclosure skill discovery allowing you to install tools and instructions directly via Markdown (`SKILL.md`).

## Installation

Requires Python 3.11+.

Clone the repository and install it (optionally with development dependencies):

```bash
git clone https://github.com/your-username/cud.git
cd cud
pip install -e .
```

*To install test dependencies, use `pip install -e .[dev]`.*

## Quick Start

The main entry point is the `cud` CLI.

```bash
# Display help
cud --help
```

### 1. Manage Agents

```bash
# Create a new agent named "my-agent"
cud agent create my-agent

# List all local agents
cud agent list

# Configure the agent to use a specific Ollama model
cud agent config my-agent --model llama3
```

### 2. Configure Gateways (e.g., Discord)

```bash
# Setup the Discord gateway with your bot token
cud gateway setup my-agent discord --token YOUR_BOT_TOKEN

# Run the gateway in the foreground
cud gateway run my-agent --verbose

# Or start it as a systemd background service
cud gateway start my-agent
cud gateway status my-agent
```

### 3. Manage Tools & Skills

```bash
# List available tools for an agent
cud tools list my-agent

# Install a skill from a local path or URL
cud tools install my-agent /path/to/skill/dir
```

### 4. Manage Ollama Engine

```bash
# Check Ollama engine status
cud engine status

# Pull a new model
cud engine pull phi3
```

## Architecture

- **`src/cud/agent/`**: Core LangGraph runtime, prompt construction, and message compression logic.
- **`src/cud/gateway/`**: Platform adapters (e.g., `discord_adapter.py`) and background service (`systemd.py`) management.
- **`src/cud/tools/`**: Built-in tools and the MCP client integration.

## License

MIT License.
