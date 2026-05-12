"""Cud agent runtime boundary."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from deepagents.middleware.summarization import create_summarization_tool_middleware
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


from cud.agent.subagents import build_subagents
from cud.config.settings import Settings, load_settings, save_settings
from cud.tools.mcp import load_mcp_tools_managed

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeResponse:
    content: str
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class AgentRuntime:
    agent_dir: Path
    thread_id: str = "default"
    settings: Settings = field(init=False)
    prompt: str = field(init=False)
    graph: Any = field(default=None, init=False, repr=False)
    _exit_stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack, init=False, repr=False)

    def __post_init__(self) -> None:
        self.agent_dir = self.agent_dir.expanduser().resolve()
        # Defer reload to first invoke or explicit async call

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def workspace_dir(self) -> Path:
        return self.agent_dir / "workspace"

    async def reload(self) -> None:
        await self._exit_stack.aclose()
        self._exit_stack = contextlib.AsyncExitStack()
        self.settings = load_settings(self.agent_dir)
        agent_md = self.agent_dir / "AGENT.md"
        self.prompt = agent_md.read_text(encoding="utf-8") if agent_md.exists() else ""
        self.graph = await self._build_graph()

    async def _build_graph(self) -> Any:
        model = ChatOllama(
            model=self.settings.model.name,
            base_url=self.settings.model.base_url,
            temperature=self.settings.model.temperature,
            num_ctx=self.settings.model.context_window,
            profile={"max_input_tokens": self.settings.model.context_window},
        )

        virtual_mode = not self.settings.runtime.allow_traversal
        default_backend = LocalShellBackend(root_dir=self.workspace_dir, virtual_mode=virtual_mode)
        agent_backend = FilesystemBackend(root_dir=self.agent_dir, virtual_mode=True)
        backend = CompositeBackend(
            default=default_backend,
            routes={"/agent/": agent_backend},
        )

        mcp_tools, mcp_cleanup = await load_mcp_tools_managed(self.agent_dir)
        if mcp_cleanup:
            self._exit_stack.push_async_callback(mcp_cleanup)

        subagents = build_subagents(
            self.settings.subagents,
            model_settings=self.settings.model,
            exit_stack=self._exit_stack,
            run_async=_run_async_sync,
        )

        kwargs: dict[str, Any] = dict(
            model=model,
            tools=mcp_tools,
            system_prompt=self.prompt,
            backend=backend,
            memory=["/agent/MEMORY.md"],
            skills=["/agent/workspace/skills/"],
            checkpointer=await self._sqlite_checkpointer(),
            middleware=[create_summarization_tool_middleware(model, backend)],
            name=f"cud-{self.agent_dir.name}",
        )
        if subagents:
            kwargs["subagents"] = subagents

        return create_deep_agent(**kwargs)

    async def _sqlite_checkpointer(self) -> Any:
        db_path = self.agent_dir / "history.db"
        saver = AsyncSqliteSaver.from_conn_string(str(db_path))
        return await self._exit_stack.enter_async_context(saver)

    async def invoke(self, message: str, *, thread_id: str | None = None) -> RuntimeResponse:
        thread = thread_id or self.thread_id
        if self.graph is None:
            await self.reload()
        if self.graph is None:
            return RuntimeResponse(
                "Cud runtime dependencies are not installed. Install package dependencies to invoke an agent."
            )
        config = {"configurable": {"thread_id": thread}}
        raw = await self.graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config)
        return _response_from_raw(raw)

    async def undo_last_exchange(self, *, thread_id: str | None = None) -> str:
        if self.graph is None:
            await self.reload()
        if self.graph is None:
            return "Undo requires an initialized graph."
        thread = thread_id or self.thread_id
        config = {"configurable": {"thread_id": thread}}
        state = await self.graph.aget_state(config)
        messages = list((getattr(state, "values", {}) or {}).get("messages", []))
        if not messages:
            return "No messages to undo."
        await self.graph.aupdate_state(config, {"messages": _drop_last_exchange(messages)})
        return "Last exchange removed."

    async def clear_history(self) -> str:
        db_path = self.agent_dir / "history.db"
        if not db_path.exists():
            return "History is already empty."
        try:
            db_path.unlink()
        except OSError as exc:
            return f"Failed to clear history: {exc}"
        await self.reload()
        return "History cleared."

    async def view_memory(self) -> str:
        path = self.agent_dir / "MEMORY.md"
        return path.read_text(encoding="utf-8") if path.exists() else "Memory is empty."

    async def clear_memory(self) -> str:
        path = self.agent_dir / "MEMORY.md"
        path.write_text("# Long-Term Memory\n\nNo persistent memories yet.\n", encoding="utf-8")
        await self.reload()
        return "Memory cleared."

    async def set_model(self, model_name: str) -> str:
        self.settings.model.name = model_name
        save_settings(self.agent_dir, self.settings)
        await self.reload()
        return f"Model set to {model_name}."

    async def aclose(self) -> None:
        await self._exit_stack.aclose()

    def close(self) -> None:
        _run_async_sync(self._exit_stack.aclose())


# ---------------------------------------------------------------------------
# Pure helpers (no state)
# ---------------------------------------------------------------------------


def _extract_content(raw: Any) -> str:
    if isinstance(raw, dict):
        messages = raw.get("messages")
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))
            return str(getattr(last, "content", ""))
        return str(raw.get("content", raw))
    return str(raw)


def _response_from_raw(raw: Any) -> RuntimeResponse:
    content = _extract_content(raw).strip()
    return RuntimeResponse(content=content or "The agent finished without text output.", raw=raw)


def _drop_last_exchange(messages: list[Any]) -> list[Any]:
    """Remove the last user message and all subsequent assistant/tool messages."""
    trimmed = list(messages)
    while trimmed:
        role = _role(trimmed[-1])
        if role == "system":
            break  # Never remove system messages.
        trimmed.pop()
        if role in {"human", "user"}:
            break
    return trimmed


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower()
    return message.__class__.__name__.replace("Message", "").lower()


def _run_async_sync(coro: Any) -> Any:
    """Run an async coroutine from synchronous code, regardless of context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _log.debug("_run_async_sync: no event loop — using asyncio.run()")
        return asyncio.run(coro)
    # Inside a running loop (e.g. Discord's asyncio.to_thread). Spin up a
    # dedicated thread so asyncio.run() can create its own loop.
    _log.debug("_run_async_sync: event loop detected — using thread pool")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()

