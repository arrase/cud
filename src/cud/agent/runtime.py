"""Cud agent runtime boundary."""

from __future__ import annotations

import asyncio
import contextlib
import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from cud.agent.compression import CompactionResult, compact_messages
from cud.agent.prompts import PromptSnapshot, build_system_prompt
from cud.config.settings import Settings, load_settings
from cud.tools.filesystem import FileSystemTools
from cud.tools.mcp import load_langchain_mcp_tools
from cud.tools.memory import MemoryStore
from cud.tools.shell import ShellSession


@dataclass(slots=True)
class RuntimeResponse:
    content: str
    raw: Any = None
    interrupted: bool = False


@dataclass(slots=True)
class AgentRuntime:
    agent_dir: Path
    thread_id: str = "default"
    yolo: bool = False
    settings: Settings = field(init=False)
    prompt: PromptSnapshot = field(init=False)
    graph: Any = field(default=None, init=False, repr=False)
    shell: ShellSession | None = field(default=None, init=False, repr=False)
    _exit_stack: contextlib.ExitStack = field(default_factory=contextlib.ExitStack, init=False, repr=False)

    def __post_init__(self) -> None:
        self.agent_dir = self.agent_dir.expanduser().resolve()
        self.reload()

    @property
    def workspace_dir(self) -> Path:
        return self.agent_dir / self.settings.workspace

    def reload(self) -> None:
        self._exit_stack.close()
        self._exit_stack = contextlib.ExitStack()
        self.settings = load_settings(self.agent_dir)
        self.prompt = build_system_prompt(self.agent_dir, self.settings)
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        model = ChatOllama(
            model=self.settings.model.name,
            base_url=self.settings.model.base_url,
            temperature=self.settings.model.temperature,
            num_ctx=self.settings.model.context_window,
        )
        tools = self._build_langchain_tools()
        checkpointer = self._sqlite_checkpointer()
        interrupt_on = None
        if self.settings.runtime.require_approval and not self.yolo:
            interrupt_on = {name: True for name in self.settings.runtime.mutable_tools}
        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "system_prompt": self.prompt.text,
            "middleware": (),
            "subagents": [] if not self.settings.runtime.enable_subagents else None,
            "checkpointer": checkpointer,
            "interrupt_on": interrupt_on,
            "name": f"cud-{self.agent_dir.name}",
        }
        return create_deep_agent(**{key: value for key, value in kwargs.items() if value is not None})

    def _sqlite_checkpointer(self) -> Any:
        db_path = self.agent_dir / "history.db"
        if hasattr(SqliteSaver, "from_conn_string"):
            saver = SqliteSaver.from_conn_string(str(db_path))
            if hasattr(saver, "__enter__"):
                return self._exit_stack.enter_context(saver)
            return saver
        return SqliteSaver(str(db_path))

    def _build_langchain_tools(self) -> list[Any]:
        allow_trav = self.settings.runtime.allow_shell_traversal
        fs = FileSystemTools(self.workspace_dir, allow_traversal=allow_trav)
        memory = MemoryStore(self.agent_dir / "MEMORY.md")
        self.shell = ShellSession(
            self.workspace_dir, 
            allow_traversal=allow_trav
        )
        
        scope_desc = "anywhere on the system" if allow_trav else "inside the agent workspace only"
        scope_prefix = "system" if allow_trav else "workspace"

        core_tools = [
            StructuredTool.from_function(fs.ls, name="ls", description=f"List files {scope_desc}."),
            StructuredTool.from_function(fs.read_file, name="read_file", description=f"Read a {scope_prefix} UTF-8 file."),
            StructuredTool.from_function(fs.write_file, name="write_file", description=f"Write a {scope_prefix} UTF-8 file."),
            StructuredTool.from_function(fs.edit_file, name="edit_file", description=f"Replace text in a {scope_prefix} file."),
            StructuredTool.from_function(fs.glob, name="glob", description=f"Find files by glob {scope_desc}."),
            StructuredTool.from_function(fs.grep, name="grep", description=f"Search file contents {scope_desc}."),
            StructuredTool.from_function(
                lambda command: self.shell_exec(command),
                name="shell_exec",
                description=f"Run shell commands, including commands for paths {scope_desc}.",
            ),
            StructuredTool.from_function(memory.read, name="memory_read", description="Read long-term memory."),
            StructuredTool.from_function(
                lambda content, mode="append": memory.update(content, mode=mode),
                name="memory_update",
                description="Update MEMORY.md.",
            ),
            StructuredTool.from_function(memory.clear, name="memory_clear", description="Clear MEMORY.md."),
        ]
        mcp_tools = _run_async_sync(
            load_langchain_mcp_tools(self.agent_dir, self.settings.runtime.max_visible_tools)
        )
        return (core_tools + mcp_tools)[: self.settings.runtime.max_visible_tools]

    def shell_exec(self, command: str) -> str:
        if self.shell is None:
            self.shell = ShellSession(
                self.workspace_dir,
                allow_traversal=self.settings.runtime.allow_shell_traversal
            )
        result = self.shell.execute(command)
        if result.returncode != 0:
            return f"exit={result.returncode}\n{result.output}"
        return result.output

    def invoke(self, message: str, *, thread_id: str | None = None) -> RuntimeResponse:
        thread = thread_id or self.thread_id
        if self.graph is None:
            return RuntimeResponse(
                "Cud runtime dependencies are not installed. Install package dependencies to invoke an agent."
            )
        config = {"configurable": {"thread_id": thread}}
        raw = self.graph.invoke({"messages": [{"role": "user", "content": message}]}, config)
        return _response_from_raw(raw)

    def resume_approval(
        self,
        *,
        thread_id: str | None = None,
        approve: bool,
        message: str | None = None,
    ) -> RuntimeResponse:
        if self.graph is None:
            return RuntimeResponse(
                "Cud runtime dependencies are not installed. Install package dependencies to resume an agent."
            )
        
        decision: dict[str, Any]
        if approve:
            decision = {"type": "approve"}
        else:
            decision = {"type": "reject", "message": message or "User denied the tool call."}
        config = {"configurable": {"thread_id": thread_id or self.thread_id}}
        raw = self.graph.invoke(Command(resume={"decisions": [decision]}), config)
        return _response_from_raw(raw)

    def compress(
        self,
        messages: list[Any],
        *,
        focus: str | None = None,
    ) -> CompactionResult:
        return compact_messages(
            messages,
            context_window=self.settings.model.context_window,
            threshold_ratio=self.settings.compression.threshold_ratio,
            keep_recent_messages=self.settings.compression.keep_recent_messages,
            max_tool_output_chars=self.settings.compression.max_tool_output_chars,
            focus=focus,
        )

    def undo_last_exchange(self, *, thread_id: str | None = None) -> str:
        if self.graph is None or not hasattr(self.graph, "get_state") or not hasattr(self.graph, "update_state"):
            return "Undo requires LangGraph runtime dependencies and an initialized graph."
        thread = thread_id or self.thread_id
        config = {"configurable": {"thread_id": thread}}
        state = self.graph.get_state(config)
        values = getattr(state, "values", {}) or {}
        messages = list(values.get("messages", []))
        if not messages:
            return "No messages to undo."
        trimmed = _drop_last_exchange(messages)
        self.graph.update_state(config, {"messages": trimmed})
        return "Last exchange removed."

    def clear_history(self, *, thread_id: str | None = None) -> str:
        thread = thread_id or self.thread_id
        
        db_path = self.agent_dir / "history.db"
        if not db_path.exists():
            return "History is already empty."
            
        try:
            if hasattr(SqliteSaver, "from_conn_string"):
                with SqliteSaver.from_conn_string(str(db_path)) as saver:
                    if hasattr(saver, "delete_thread"):
                        saver.delete_thread(thread)
                    else:
                        return "LangGraph version does not support deleting threads natively."
            else:
                saver = SqliteSaver(str(db_path))
                if hasattr(saver, "delete_thread"):
                    saver.delete_thread(thread)
                else:
                    return "LangGraph version does not support deleting threads natively."
                    
        except Exception as exc:
            return f"Failed to clear history: {exc}"
            
        # Rebuild graph to ensure it picks up the clean state if it caches saver
        self.graph = self._build_graph()
        return "History cleared."

    def close(self) -> None:
        if self.shell is not None:
            self.shell.close()
        self._exit_stack.close()


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
    if _has_interrupt(raw):
        return RuntimeResponse(content=_format_interrupt(raw), raw=raw, interrupted=True)
    content = _extract_content(raw).strip()
    if not content:
        content = "The agent finished without text output."
    return RuntimeResponse(content=content, raw=raw)


def _has_interrupt(raw: Any) -> bool:
    return isinstance(raw, dict) and bool(raw.get("__interrupt__"))


def _format_interrupt(raw: Any) -> str:
    requests = _interrupt_action_requests(raw)
    if not requests:
        return "Tool approval required. Use `/approve` or `/deny`."
    lines = ["Tool approval required. Use `/approve` to continue or `/deny` to reject."]
    for request in requests:
        name = request.get("name", "tool")
        args = request.get("args", {})
        lines.append(f"- {name}: {args}")
    return "\n".join(lines)


def _interrupt_action_requests(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    interrupts = raw.get("__interrupt__") or []
    requests: list[dict[str, Any]] = []
    for item in interrupts:
        value = getattr(item, "value", None)
        if isinstance(value, dict):
            requests.extend(value.get("action_requests", []) or [])
    return requests


def _drop_last_exchange(messages: list[Any]) -> list[Any]:
    trimmed = list(messages)
    seen_user = False
    while trimmed:
        role = _role(trimmed[-1])
        item = trimmed.pop()
        if role in {"human", "user"}:
            seen_user = True
            break
        if role == "system" and not seen_user:
            trimmed.append(item)
            break
    return trimmed


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower()
    return message.__class__.__name__.replace("Message", "").lower()


def _run_async_sync(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if not loop.is_running():
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()
