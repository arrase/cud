# Cud 🦙

**Cud** (the bolus of food that llamas chew) is a local-first, OpenClaw-like multi-agent framework focused on **simplicity** and **local** interaction.

## 🌟 Core Principles

- **Local-First & Private**: Your data, prompts, and memory stay on your machine.
- **Multi-Agent by Design**: Create a fleet of specialized agents, each with its own persona, memory, and workspace.
- **Transparent & Hackable**: Agent behavior is defined in plain Markdown. No hidden prompts, no black boxes.
- **Tool-Rich**: Built-in support for persistent shell sessions, surgical filesystem operations, SKILLs, and the Model Context Protocol (MCP).
- **Daemon-Ready**: Seamlessly run your agents as background services using `systemd`.

## 🚀 Quick Start

### 1. Installation

Requires Python 3.11+.

```bash
pipx install git+https://github.com/arrase/cud.git
```

### 2. Create Your First Agent

```bash
# Create an agent named "researcher"
cud agent create researcher

# Configure it to use a specific model (e.g., llama3)
cud agent config researcher --model llama3
```

### 3. Run the Agent (Discord Gateway)

```bash
# Setup your Discord token
cud gateway setup researcher discord --token YOUR_BOT_TOKEN

# Run it in the foreground to test
cud gateway run researcher --verbose

# Or start it as a background service
cud gateway start researcher
```

---

## 🧠 Key Concepts

### Agents & Workspaces
Every agent lives in `~/.cud/agents/<name>/`. This directory contains its entire "soul":
- `settings.yaml`: Model parameters and tool configurations.
- `AGENT.md`: The system prompt—defining its persona and rules.
- `MEMORY.md`: Long-term memory that the agent can read and update.
- `history.db`: A SQLite-backed LangGraph checkpointer for conversation state.
- `mcp.json`: MCP server configurations.
- `workspace/`: The dedicated directory where the agent runs commands and edits files.
- `workspace/skills/`: A directory for custom Markdown-defined abilities.

### Skills (`SKILL.md`)
Skills are portable sets of instructions and tools. Just drop a folder with a `SKILL.md` into an agent's `workspace/skills/` directory, and it instantly gains those capabilities.

### Model Context Protocol (MCP)
Native support for MCP allows you to connect your agents to external tool servers (e.g., Brave Search, GitHub, Google Drive) with a single command:
```bash
cud mcp add researcher https://mcp-server.example.com/sse --name search
```

---

## 🏗️ Architecture

Cud is built on a robust, modular stack:
- **Orchestration**: [DeepAgents](https://docs.langchain.com/oss/python/deepagents/overview) provides the stateful, cyclic reasoning loops.
- **LLM Engine**: [Ollama](https://ollama.com/) powers the local inference.

## 🛠️ Development

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest
```

## 📜 License

MIT License.
