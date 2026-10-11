# Installation & Setup Guide

This guide covers system requirements, installation options, Ollama model setup, and post-installation verification for **Cud**.

---

## System Requirements

Before installing Cud, ensure your environment meets the following requirements:

* **Operating System**: Linux (Ubuntu 22.04+, Debian 12+, Arch, Fedora, etc.) with active `systemd` user service support.
* **Python**: Python 3.11 or higher.
* **Package / Tool Manager**: Either `pipx` or `uv`.
* **Local LLM Engine**: [Ollama](https://ollama.com) installed and running locally or accessible via network base URL.

---

## Installation Methods

Cud can be installed using automated scripts, package managers, or manually from source code.

### Option 1: Automated `install.sh` Script (Recommended)
The official setup script automatically checks system prerequisites (`systemd`, `pipx`/`uv`), installs the latest version of Cud from GitHub, sets up desktop integration, and registers application icons.

```bash
curl -fsSL https://raw.githubusercontent.com/arrase/cud/main/install.sh | bash
```

> [!WARNING]
> Do **not** run `install.sh` as root or with `sudo`. Cud services and configuration directories belong to your regular user account.

---

### Option 2: Installation via `pipx`
If you already have `pipx` installed:

```bash
pipx install git+https://github.com/arrase/cud.git
```

To update an existing installation:
```bash
pipx install --force git+https://github.com/arrase/cud.git
```

---

### Option 3: Installation via `uv`
If you use `uv`:

```bash
uv tool install git+https://github.com/arrase/cud.git
```

To update:
```bash
uv tool install --force git+https://github.com/arrase/cud.git
```

---

### Option 4: Building from Git Source Clone
For local development or custom modifications:

```bash
git clone https://github.com/arrase/cud.git
cd cud

# Create virtual environment and install in editable mode
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Ollama Setup & Tool-Calling Models

Cud relies on Ollama for local LLM inference.

### 1. Installing & Starting Ollama
Install Ollama following instructions from [ollama.com](https://ollama.com/download/linux):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Ensure the service is active:
```bash
systemctl status ollama
```

### 2. Required Model Capabilities
Cud relies heavily on **Tool Calling (Function Calling)** capabilities. You must pull models that support tool-calling schemas:

```bash
# Recommended default model (32k context, fast tool calling)
ollama pull gemma4:e4b

# Recommended high-capacity reasoning model
ollama pull qwen3.6:27b
```

---

## Verifying Installation

Verify that the CLI binaries and desktop GUI are correctly installed and available in your `$PATH`:

### 1. Verify CLI Tool
```bash
cud --help
```

Expected output:
```text
usage: cud [-h] {agent,gateway,tools,mcp,engine,task,tui,completion} ...

Local multi-agent framework for Ollama.

positional arguments:
  {agent,gateway,tools,mcp,engine,task,tui,completion}
    agent               Manage agents
    gateway             Manage gateway daemon
    tools               Manage skills
    mcp                 Manage MCP servers
    engine              Manage Ollama engine
    task                Manage periodic tasks
    tui                 Launch TUI REPL
    completion          Generate shell completion
```

### 2. Launch Graphical Interface (GUI)
Launch the PySide6 desktop dashboard:

```bash
cud-gui
```

Alternatively, launch **Cud** from your desktop application launcher menu.
