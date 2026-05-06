# 🦙 Cud

> **Cud** (the bolus of food that llamas chew) is a local-first, multi-agent framework where **simplicity** is the ultimate foundation. 

Designed to be lightweight, straightforward, and incredibly easy to use, Cud brings the power of autonomous AI agents directly to your local machine.

---

## ✨ Core Principles

- 🎯 **Simplicity First**: No convoluted setups or bloated abstractions. Cud is built to be intuitive, readable, and easy to hack on.
- 🔒 **Local & Private**: Powered by **[Ollama](https://ollama.com/)**, your data, prompts, and memory stay 100% on your machine.
- 🤖 **Multi-Agent Architecture**: Create a fleet of specialized agents, each with its own persona, memory, and workspace.
- 📖 **Transparent**: Agent behavior is defined in plain Markdown (`AGENT.md`). No hidden prompts, no black boxes.
- 🛠️ **Tool-Rich**: Built-in support for persistent shell sessions, surgical filesystem operations, Custom SKILLs, and the Model Context Protocol (MCP).
- 👻 **Daemon-Ready**: Seamlessly run your agents as background services using `systemd`.

---

## 🦙 Ollama & Tool Calling

Cud relies on **Ollama** for local inference. 

> [!IMPORTANT]
> **Tool Calling Support is Required!**  
> Because Cud agents interact with your local environment (shell, filesystem, etc.), you **must** download and use models in Ollama that explicitly support **tool calling** (e.g., `gpt-oss:20b`, `gemma4:e4b`, `qwen3.6:27b`). 

---

## 🚀 Quick Start

### 1. Installation

*Requires Python 3.11+.*

```bash
pipx install git+https://github.com/arrase/cud.git
```

### 2. Configure Ollama

Ensure you have Ollama installed and a tool-calling capable model downloaded:

```bash
ollama run gemma4:e4b
```

### 3. Create Your First Agent

```bash
# Create an agent named "researcher"
cud agent create researcher

# Configure it to use a specific model with tool calling support
cud agent config researcher --model gemma4:e4b

# Setup your Discord token
cud gateway setup researcher discord --token YOUR_BOT_TOKEN
```

### 4. Run the Agent (Discord Gateway)

```bash
# Start it as a background service
cud gateway start researcher
```

---

## 💬 Discord Commands

When interacting with your agent via the Discord Gateway, you can use the following slash commands:

- `/new`: Start a new Cud session in the current Discord thread (clears context history).
- `/model <model_name>`: Temporarily switch the agent's configured model.
- `/usage`: Show Cud runtime usage summary (agent name, current model, and thread ID).
- `/undo`: Remove the last exchange from the current thread.
- `/reload`: Reload tools and the system prompt (`AGENT.md`) for this agent.
- `/memory view`: View the contents of the agent's long-term `MEMORY.md`.
- `/memory clear`: Clear the agent's long-term `MEMORY.md`.

---

## 🧠 Key Concepts

### 📂 Agents & Workspaces
Every agent lives in `~/.cud/agents/<name>/`. This directory contains its entire "soul":
- ⚙️ `settings.yaml`: Model parameters and tool configurations.
- 🎭 `AGENT.md`: The system prompt—defining its persona and rules.
- 📝 `MEMORY.md`: Long-term memory that the agent can read and update.
- 💾 `history.db`: A SQLite-backed checkpointer for conversation state.
- 🔌 `mcp.json`: MCP server configurations.
- 💻 `workspace/`: The dedicated directory where the agent runs commands and edits files.
- 🧰 `workspace/skills/`: A directory for custom Markdown-defined abilities.

### 🪄 Skills (`SKILL.md`)
Skills are portable sets of instructions and tools. Just drop a folder with a `SKILL.md` into an agent's `workspace/skills/` directory, and it instantly gains those capabilities.

### 🗜️ Context Compression
To keep agents fast and prevent them from hitting token limits during long conversations, Cud features automatic context compression.
- **Automatic Summarization**: When a conversation gets too long, older messages are automatically summarized by the LLM.
- **No Data Lost**: The full, uncompressed conversation history is safely offloaded to a markdown file in the agent's workspace (`workspace/conversation_history/<thread_id>.md`).
- **Manual Compaction**: Agents have access to a `compact_conversation` tool, allowing them to proactively free up context when finishing a large task.

### ⏱️ Periodic Tasks
Agents can execute scheduled, periodic tasks autonomously. Tasks are defined as Markdown files (`TASK.md`) located in the agent's `workspace/tasks/<name>/` directory.
- Use a YAML frontmatter to configure the `schedule` (cron expression) and the destination (`channel_id` or `user_id`).
- The rest of the file is the prompt the agent executes.
- Ask your agent to create tasks for you, or edit them manually.
- Use the `/reload` command in Discord to activate changes.
- Check active tasks via the CLI: `cud task list <agent>`.

**Example: `workspace/tasks/daily-news/TASK.md`**
```markdown
---
name: "Daily Tech News"
description: "Searches for latest AI news and summarizes it"
schedule: "0 9 * * *"
channel_id: 123456789012345678
enabled: true
---

Search the web for the latest AI news.
Summarize the top 3 stories.
Make it sound enthusiastic!
```

### 🌐 Model Context Protocol (MCP)
Native support for MCP allows you to connect your agents to external tool servers (e.g., Brave Search, GitHub, Google Drive) with a single command:
```bash
cud mcp add researcher https://mcp-server.example.com/sse --name search
```

---

## 🏗️ Architecture

Cud is built on a robust, modular stack:
- **Orchestration**: [DeepAgents](https://docs.langchain.com/oss/python/deepagents/overview) provides the stateful, cyclic reasoning loops.
- **LLM Engine**: [Ollama](https://ollama.com/) powers the local inference with tool calling capabilities.

---

## 🛠️ Development

To set up a local development environment:

```bash
# Clone the repository
git clone https://github.com/arrase/cud.git
cd cud

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -e .
```

---

## 📜 License

MIT License.
