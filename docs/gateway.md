# Discord Gateway & Background Daemons

Cud provides a background service architecture that exposes local agents directly to **Discord** servers and threads, complete with full slash command support, persistent chat threads, and Linux `systemd` daemon integration.

---

## Overview

The Gateway connects Cud agents to external messaging platforms. Rather than requiring users to keep a CLI window open, the gateway runs agents headlessly as user-level background daemons that listen for incoming Discord messages and periodic scheduled triggers.

---

## Gateway Setup & Token Configuration

To connect an agent to a Discord bot:

1. Obtain a Discord Bot Token from the [Discord Developer Portal](https://discord.com/developers/applications) (ensure **Message Content Intent** is enabled).
2. Configure credentials using the `cud gateway setup` command:

```bash
cud gateway setup my-agent discord --token "YOUR_DISCORD_BOT_TOKEN"
```

This saves the token to `~/.cud/agents/my-agent/settings.yaml` under the `gateway` block:

```yaml
gateway:
  provider: discord
  token: "YOUR_DISCORD_BOT_TOKEN"
  mode: bot
```

---

## Managing Gateway Execution

You can run and control the gateway in foreground dev mode or as a background service:

### Running in Foreground (Development Mode)
```bash
cud gateway run my-agent --verbose
```

### Background Management via CLI Commands

```bash
# Generate systemd unit, enable service, and start gateway
cud gateway start my-agent

# View current daemon status and recent journal logs
cud gateway status my-agent

# Stop the running background service
cud gateway stop my-agent
```

---

## Interactive Discord Slash Commands

When the Discord gateway starts up, it automatically syncs application slash commands to Discord. The following commands are available in any channel or thread where the bot has access:

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/new` | None | Reset current thread context and start a brand-new unique session thread. |
| `/model` | `model_name` | Temporarily switch the active Ollama model for this agent (e.g. `qwen3.6:27b`). |
| `/usage` | None | Display a summary of the current agent name, active model, and LangGraph thread ID. |
| `/undo` | None | Drop the last user prompt and assistant response pair from the thread checkpoint history. |
| `/reload` | None | Hot-reload agent configuration, system prompt (`AGENT.md`), skills, and scheduled tasks without restarting the gateway daemon. |
| `/memory view` | None | View long-term persistent agent memory (`/agent/MEMORY.md`). |
| `/memory clear` | None | Clear persistent agent long-term memory and reset `MEMORY.md`. |

---

## Linux `systemd` Integration & Daemonization

Cud provides native user-level `systemd` integration on Linux systems.

### Service Unit File Generation
When you run `cud gateway start <agent>`, Cud automatically generates a systemd service unit file at:
`~/.config/systemd/user/cud-gateway-<agent>.service`

Generated unit structure:

```ini
[Unit]
Description=Cud Gateway - Agent: my-agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/home/user/.local/bin/cud gateway run my-agent
Restart=always
RestartSec=5
RestartForceExitStatus=75
Environment="CUD_HOME=/home/user/.cud"

[Install]
WantedBy=default.target
```

### Systemd Lifecycle Management
The service handles automatic process lifecycle management:
* **Automatic Reloads**: Reloads units using `systemctl --user daemon-reload`.
* **Auto-Restart**: Automatically restarts agent daemons if they crash (`Restart=always`, 5s delay).
* **Persistence across Logouts**: To ensure agent services continue running even after you log out of your SSH or desktop session, enable systemd user lingering:

```bash
loginctl enable-linger $USER
```
