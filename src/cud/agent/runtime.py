"""Cud agent runtime boundary."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from deepagents.middleware.summarization import create_summarization_tool_middleware
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import RemoveMessage

from cud.agent.episodic_memory import (
    create_search_past_conversations_tool,
    load_past_user_prompts,
    search_past_conversations_in_db,
)
from cud.agent.subagents import build_subagents
from cud.config.settings import Settings, load_settings, save_settings
from cud.tools.mcp import load_mcp_tools_managed

_log = logging.getLogger(__name__)

EMPTY_MEMORY = "# Long-Term Memory\n\nNo persistent memories yet.\n"
NO_TEXT_OUTPUT = "The agent finished without text output."


@dataclass(slots=True)
class RuntimeResponse:
    content: str


@dataclass(slots=True)
class AgentRuntime:
    agent_dir: Path
    thread_id: str = "default"
    # Defaults keep the runtime usable before the first `reload()`, e.g. a
    # `/model` slash command in a channel with no prior message.
    settings: Settings = field(default_factory=Settings, init=False)
    prompt: str = field(default="", init=False)
    graph: Any = field(default=None, init=False, repr=False)
    _exit_stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack, init=False, repr=False)
    _build_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.agent_dir = self.agent_dir.expanduser().resolve()

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

    @property
    def history_db_path(self) -> Path:
        return self.agent_dir / "history.db"

    async def reload(self) -> None:
        """Rebuild the graph from disk, replacing the previous resources."""
        async with self._build_lock:
            await self._reload_locked()

    async def _reload_locked(self) -> None:
        """Reload with `_build_lock` already held (it is not reentrant)."""
        settings = load_settings(self.agent_dir)
        agent_md = self.agent_dir / "AGENT.md"
        prompt = agent_md.read_text(encoding="utf-8") if agent_md.exists() else ""

        new_stack: Any = contextlib.AsyncExitStack()
        try:
            graph = await self._build_graph(settings, prompt, new_stack)
        except BaseException:
            await new_stack.aclose()
            raise
        # pop_all() is sync and transfers resource ownership to this scope.
        new_stack.pop_all()

        old_stack, self._exit_stack = self._exit_stack, new_stack
        self.settings = settings
        self.prompt = prompt
        self.graph = graph
        await old_stack.aclose()

    async def _ensure_graph(self) -> Any:
        """Return the live graph, building it exactly once even under concurrency."""
        if self.graph is not None:
            return self.graph
        async with self._build_lock:
            # Re-check under the lock: a concurrent caller may have built it
            # while we were waiting, and rebuilding would churn the checkpointer.
            if self.graph is None:
                await self._reload_locked()
            if self.graph is None:  # pragma: no cover - reload either sets it or raises
                raise RuntimeError("graph build produced no graph")
            return self.graph

    async def _build_graph(
        self,
        settings: Settings,
        prompt: str,
        stack: contextlib.AsyncExitStack,
    ) -> Any:
        model = ChatOllama(
            model=settings.model.name,
            base_url=settings.model.base_url,
            temperature=settings.model.temperature,
            num_ctx=settings.model.context_window,
            profile={"max_input_tokens": settings.model.context_window},
        )

        virtual_mode = not settings.runtime.allow_traversal
        default_backend = LocalShellBackend(root_dir=self.workspace_dir, virtual_mode=virtual_mode)
        agent_backend = FilesystemBackend(root_dir=self.agent_dir, virtual_mode=True)
        backend = CompositeBackend(
            default=default_backend,
            routes={"/agent/": agent_backend},
        )

        mcp_tools = await load_mcp_tools_managed(self.agent_dir)
        subagents = await build_subagents(settings.subagents, model_settings=settings.model)

        memory_tool = create_search_past_conversations_tool(
            db_path=self.history_db_path,
            get_thread_id=lambda: self.thread_id,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "tools": [*mcp_tools, memory_tool],
            "system_prompt": prompt,
            "backend": backend,
            "memory": ["/agent/MEMORY.md"],
            "skills": ["/agent/workspace/skills/"],
            "checkpointer": await self._sqlite_checkpointer(stack),
            "middleware": [create_summarization_tool_middleware(model, backend)],
            "name": f"cud-{self.agent_dir.name}",
        }
        if subagents:
            kwargs["subagents"] = subagents

        return create_deep_agent(**kwargs)

    async def _sqlite_checkpointer(self, stack: contextlib.AsyncExitStack) -> Any:
        saver = AsyncSqliteSaver.from_conn_string(str(self.history_db_path))
        return await stack.enter_async_context(saver)

    async def invoke(self, message: str, *, thread_id: str | None = None) -> RuntimeResponse:
        graph = await self._ensure_graph()
        config = {"configurable": {"thread_id": thread_id or self.thread_id}}
        raw = await graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config)
        return _response_from_raw(raw)

    async def undo_last_exchange(self, *, thread_id: str | None = None) -> str:
        graph = await self._ensure_graph()
        config = {"configurable": {"thread_id": thread_id or self.thread_id}}
        state = await graph.aget_state(config)
        messages = list(state.values.get("messages", []))
        kept = _drop_last_exchange(messages)
        if len(kept) == len(messages):
            return "Nothing to undo."
        # The `messages` channel is reduced by `add_messages`, which merges by
        # id: passing the kept messages back would re-add the removed ones.
        await graph.aupdate_state(
            config,
            {"messages": [RemoveMessage(id=m.id) for m in messages[len(kept):]]},
        )
        return "Last exchange removed."

    def new_session(self) -> str:
        """Start a fresh session by switching to a new unique thread_id."""
        self.thread_id = uuid4().hex
        return f"New session started (thread: {self.thread_id})."

    def view_memory(self) -> str:
        path = self.agent_dir / "MEMORY.md"
        return path.read_text(encoding="utf-8") if path.exists() else "Memory is empty."

    async def clear_memory(self) -> str:
        path = self.agent_dir / "MEMORY.md"
        path.write_text(EMPTY_MEMORY, encoding="utf-8")
        await self.reload()
        return "Memory cleared."

    def search_past_conversations(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        return search_past_conversations_in_db(
            query=query,
            db_path=self.history_db_path,
            exclude_thread_id=self.thread_id,
            limit=limit,
        )

    def load_past_prompts(self) -> list[str]:
        return load_past_user_prompts(self.history_db_path)

    async def set_model(self, model_name: str) -> str:
        if self.graph is None:
            # Not built yet: read from disk so unrelated in-memory defaults
            # are never written over the real config.
            settings = load_settings(self.agent_dir)
            settings.model.name = model_name
            save_settings(self.agent_dir, settings)
            self.settings = settings
        else:
            self.settings.model.name = model_name
            save_settings(self.agent_dir, self.settings)
            await self.reload()
        return f"Model set to {model_name}."

    async def aclose(self) -> None:
        async with self._build_lock:
            await self._exit_stack.aclose()
            self.graph = None

    def close(self) -> None:
        """Synchronous teardown, for use outside an event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.aclose())
            return
        raise RuntimeError("AgentRuntime.close() cannot be used inside a running event loop; await aclose()")


# ---------------------------------------------------------------------------
# Pure helpers (no state)
# ---------------------------------------------------------------------------


def _response_from_raw(raw: dict[str, Any]) -> RuntimeResponse:
    return RuntimeResponse(content=_extract_content(raw).strip() or NO_TEXT_OUTPUT)


def _extract_content(raw: dict[str, Any]) -> str:
    """Return the final assistant text of a graph result.

    Walks back past tool results: a run that ended on a ``ToolMessage`` must
    not surface raw tool output as if it were the assistant's answer.
    """
    for message in reversed(raw.get("messages") or []):
        if isinstance(message, dict):
            role, content = message.get("type") or message.get("role"), message.get("content")
        else:
            role, content = getattr(message, "type", None), getattr(message, "content", None)
        # "assistant" is LangChain's legacy alias for the "ai" message type.
        if str(role).lower() in ("ai", "assistant"):
            return str(content or "")
    return ""


def _drop_last_exchange(messages: list[Any]) -> list[Any]:
    """Return *messages* without the last user message and everything after it."""
    trimmed = list(messages)
    while trimmed:
        role = _role(trimmed[-1])
        if role == "system":
            break  # Never remove system messages.
        trimmed.pop()
        if role in ("human", "user"):
            break
    return trimmed


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower()
    if role := getattr(message, "type", None):
        return str(role).lower()
    return message.__class__.__name__.replace("Message", "").lower()
