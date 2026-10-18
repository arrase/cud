---
hide:
  - toc
---

<div class="hero-section">
  <div class="hero-eyebrow">
    <i class="fa-solid fa-users-gear" aria-hidden="true"></i>
    <span>Local-First Multi-Agent Framework</span>
  </div>
  <h1>Cud</h1>
  <p class="hero-subtitle">A lightweight, local-first OpenClaw-like multi-agent framework powered by Ollama. Build specialized autonomous agents with persistent memory, tool-calling, SKILL.md packages, and MCP integration.</p>
  <div class="hero-badges">
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python Version">
    <img src="https://img.shields.io/badge/LLM-Ollama-orange" alt="Ollama">
    <img src="https://img.shields.io/badge/framework-DeepAgents-purple" alt="DeepAgents">
    <img src="https://img.shields.io/badge/gateway-Discord-5865F2" alt="Discord">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT">
  </div>
</div>

<div class="section-header">
  <h2>Key Features</h2>
  <span>Autonomous multi-agent orchestration</span>
</div>

<div class="projects-grid">
  <div class="feature-card">
    <i class="fa-solid fa-feather-pointed feature-icon" aria-hidden="true"></i>
    <h3>Simplicity First</h3>
    <p>Zero convoluted setups or bloated abstractions. Built to be intuitive, inspectable, and easy to hack on.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-user-shield feature-icon" aria-hidden="true"></i>
    <h3>Local &amp; Private</h3>
    <p>Powered by Ollama. Your prompts, source code, and dual declarative and episodic agent memories stay 100% on your machine.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-network-wired feature-icon" aria-hidden="true"></i>
    <h3>Multi-Agent Architecture</h3>
    <p>Deploy fleets of specialized autonomous agents, each with isolated personas, state, and sandboxed workspaces.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-file-code feature-icon" aria-hidden="true"></i>
    <h3>Transparent Markdown Prompts</h3>
    <p>Agent behavior and system prompts are fully transparent, written in plain <code>AGENT.md</code> files.</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-toolbox feature-icon" aria-hidden="true"></i>
    <h3>Tool-Rich Ecosystem</h3>
    <p>Native support for persistent bash sessions, filesystem operations, SKILL.md packages, and Model Context Protocol (MCP).</p>
  </div>
  <div class="feature-card">
    <i class="fa-solid fa-server feature-icon" aria-hidden="true"></i>
    <h3>Daemon-Ready</h3>
    <p>Run agents as background Linux system services via <code>systemd</code> with active Discord gateways and scheduled tasks.</p>
  </div>
</div>

<div class="section-header">
  <h2>Interface &amp; Workflow Gallery</h2>
  <span>Explore Cud across its runtime environments and user interfaces</span>
</div>

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

<div class="section-header">
  <h2>Documentation</h2>
  <span>Explore Cud's architecture, workspace &amp; gateways</span>
</div>

<div class="projects-grid">
  <a href="architecture/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-sitemap feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Architecture &amp; Core Design</h3>
    <p>High-level system design, Ollama LLM integration, DeepAgents execution loop, and state machine graph.</p>
  </a>

  <a href="agent-workspace/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-folder-tree feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Agent &amp; Workspace</h3>
    <p>Deep dive into <code>~/.cud/agents/&lt;name&gt;/</code> directory structure, <code>AGENT.md</code>, <code>MEMORY.md</code>, and <code>history.db</code> with episodic memory recall.</p>
  </a>

  <a href="interfaces/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-desktop feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>User Interfaces (CLI, TUI &amp; GUI)</h3>
    <p>Command line interface, Rich/prompt_toolkit TUI, and PySide6 Qt Desktop application overview.</p>
  </a>

  <a href="tools-skills/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-wand-magic-sparkles feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Built-in Tools &amp; Skills</h3>
    <p>Shell execution, virtual filesystem backends, context compaction, and custom Markdown <code>SKILL.md</code> definitions.</p>
  </a>

  <a href="mcp/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-plug feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Model Context Protocol (MCP)</h3>
    <p>Connect agents to external MCP tools via stdio or HTTP/SSE transports with secret environment injection.</p>
  </a>

  <a href="subagents/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-robot feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Custom Subagents</h3>
    <p>Hierarchical agent delegation patterns, context isolation, and subagent-specific MCP servers.</p>
  </a>

  <a href="gateway/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-comments feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Discord Gateway &amp; Daemons</h3>
    <p>Connect agents to Discord servers with systemd background service integration and thread session management.</p>
  </a>

  <a href="tasks/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-clock feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Scheduled Tasks</h3>
    <p>Autonomous cron-scheduled agent jobs configured using Markdown frontmatter and prompt templates.</p>
  </a>

  <a href="installation/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-download feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Installation &amp; Setup</h3>
    <p>Quick start installation script, manual pipx / uv tool setups, system requirements, and Ollama configuration.</p>
  </a>
</div>
