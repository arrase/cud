# Product Guide: Cud

## Initial Concept
Cud is a local multi-agent framework designed to bring autonomous AI agents to your terminal and messaging platforms like Discord, prioritizing privacy and local execution with Small Language Models (SLMs).

## Target Audience
- **Developers & Engineers:** Building, deploying, and managing local AI agent systems.
- **AI Tinkerers:** Enthusiasts experimenting with and optimizing local SLMs (~15B parameters).

## Core Problem Solved
Cud holistically addresses the primary challenges of modern AI agent development by ensuring **Privacy & Data Control** (keeping data local), eliminating **Cloud API Costs**, and significantly reducing **Agent Complexity** through a simplified, extensible architecture.

## Key Features
- **Local-First Execution:** Powered by Ollama and LangGraph for private, cost-effective inference.
- **Extensibility:** Portable Markdown-based skills and Model Context Protocol (MCP) support for tool integrations.
- **Daemon Management:** Seamlessly run and manage agents as background `systemd` services.
- **SLM Optimization:** Built-in tool guardrails and message compression optimized for smaller local models.
- **Robust Shell Execution:** Persistent sessions with CWD tracking, configurable workspace boundaries, and real-time progress reporting.

## Future Direction
While future roadmaps include expanding to **New Gateways** (like Telegram and Slack), the immediate focus is on **perfection and optimization**. The goal is to highly optimize the framework for small language models and polish existing features to deliver a flawless, high-quality user experience before expanding the ecosystem.
