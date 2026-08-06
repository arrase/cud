# Cud

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![Ollama](https://img.shields.io/badge/LLM-Ollama-orange)
![DeepAgents](https://img.shields.io/badge/framework-DeepAgents-purple)
![Discord](https://img.shields.io/badge/gateway-Discord-5865F2)
![License MIT](https://img.shields.io/badge/license-MIT-green)

# Simplicity is the Ultimate Foundation

**Cud** (named after the bolus of food that llamas chew) is a lightweight, local-first multi-agent framework. Built from the ground up to eliminate artificial complexity, Cud brings autonomous, tool-calling AI agents directly to your workstation or private infrastructure without third-party API dependencies or hidden prompt abstractions.

---

## ⚡ Key Features

<div class="projects-grid">
  <div class="feature-card">
    <i class="fa-solid fa-feather-pointed feature-icon"></i>
    <h3>Simplicity First</h3>
    <p>Zero convoluted setups or bloated abstractions. Built to be intuitive, inspectable, and easy to hack on.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-user-shield feature-icon"></i>
    <h3>Local & Private</h3>
    <p>Powered by Ollama. Your prompts, source code, and long-term agent memories stay 100% on your machine.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-network-wired feature-icon"></i>
    <h3>Multi-Agent Architecture</h3>
    <p>Deploy fleets of specialized autonomous agents, each with isolated personas, state, and sandboxed workspaces.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-file-code feature-icon"></i>
    <h3>Transparent Markdown Prompts</h3>
    <p>Agent behavior and system prompts are fully transparent, written in plain <code>AGENT.md</code> files.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-toolbox feature-icon"></i>
    <h3>Tool-Rich Ecosystem</h3>
    <p>Native support for persistent bash sessions, filesystem operations, SKILL.md packages, and Model Context Protocol (MCP).</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-server feature-icon"></i>
    <h3>Daemon-Ready</h3>
    <p>Run agents as background Linux system services via <code>systemd</code> with active Discord gateways and scheduled tasks.</p>
  </div>
</div>

---

## 🖼️ Interface & Workflow Gallery

Explore Cud in action across its runtime environments and user interfaces:

=== "System Flow"
    ![Cud Interaction Flow](screenshots/cud-flow.jpeg)

=== "Desktop GUI"
    ![Cud Desktop GUI Dashboard](screenshots/dashboard.png)

=== "Agent Settings"
    ![Agent Configuration Panel](screenshots/general.png)

=== "Instructions Editor"
    ![AGENT.md Prompt Editor](screenshots/instructions.png)

=== "Memory Management"
    ![Long-term Memory View](screenshots/menory.png)

=== "Skills & Capabilities"
    ![Agent Skills Manager](screenshots/skills.png)

=== "Periodic Tasks"
    ![Scheduled Tasks Monitor](screenshots/tasks.png)

=== "MCP Integrations"
    ![Model Context Protocol Manager](screenshots/mcp.png)

=== "Subagents Delegation"
    ![Custom Subagents Configuration](screenshots/subagents.png)

---

## 📚 Documentation Index

Navigate through the comprehensive technical documentation for Cud:

<div class="projects-grid">
  <a class="feature-card" href="architecture.md">
    <i class="fa-solid fa-sitemap feature-icon"></i>
    <h3>Architecture & Core Design</h3>
    <p>High-level system design, Ollama LLM integration, DeepAgents execution loop, and state machine graph.</p>
  </a>

  <a class="feature-card" href="agent-workspace.md">
    <i class="fa-solid fa-folder-tree feature-icon"></i>
    <h3>Agent & Workspace</h3>
    <p>Deep dive into <code>~/.cud/agents/&lt;name&gt;/</code> directory structure, <code>AGENT.md</code>, <code>MEMORY.md</code>, and <code>history.db</code>.</p>
  </a>

  <a class="feature-card" href="interfaces.md">
    <i class="fa-solid fa-desktop feature-icon"></i>
    <h3>User Interfaces (CLI, TUI & GUI)</h3>
    <p>Command line interface, Rich/prompt_toolkit TUI, and PySide6 Qt Desktop application overview.</p>
  </a>

  <a class="feature-card" href="tools-skills.md">
    <i class="fa-solid fa-wand-magic-sparkles feature-icon"></i>
    <h3>Built-in Tools & Skills</h3>
    <p>Shell execution, virtual filesystem backends, context compaction, and custom Markdown <code>SKILL.md</code> definitions.</p>
  </a>

  <a class="feature-card" href="mcp.md">
    <i class="fa-solid fa-plug feature-icon"></i>
    <h3>Model Context Protocol (MCP)</h3>
    <p>Connect agents to external MCP tools via stdio or HTTP/SSE transports with secret environment injection.</p>
  </a>

  <a class="feature-card" href="subagents.md">
    <i class="fa-solid fa-robot feature-icon"></i>
    <h3>Custom Subagents</h3>
    <p>Hierarchical agent delegation patterns, context isolation, and subagent-specific MCP servers.</p>
  </a>

  <a class="feature-card" href="gateway.md">
    <i class="fa-solid fa-comments feature-icon"></i>
    <h3>Discord Gateway & Daemons</h3>
    <p>Connect agents to Discord servers with systemd background service integration and thread session management.</p>
  </a>

  <a class="feature-card" href="tasks.md">
    <i class="fa-solid fa-clock feature-icon"></i>
    <h3>Scheduled Tasks</h3>
    <p>Autonomous cron-scheduled agent jobs configured using Markdown frontmatter and prompt templates.</p>
  </a>

  <a class="feature-card" href="installation.md">
    <i class="fa-solid fa-download feature-icon"></i>
    <h3>Installation & Setup</h3>
    <p>Quick start installation script, manual pipx / uv tool setups, system requirements, and Ollama configuration.</p>
  </a>
</div>
