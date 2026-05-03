"""Persistent shell helper for Cud sessions."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ShellResult:
    output: str
    returncode: int


@dataclass(slots=True)
class ShellSession:
    cwd: Path
    shell: str = "/bin/bash"
    timeout_seconds: float = 30.0
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _queue: "queue.Queue[str]" = field(default_factory=queue.Queue, init=False, repr=False)
    _reader: threading.Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        if self._process and self._process.poll() is None:
            return
        self.cwd.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PS1": "", "PROMPT_COMMAND": ""}
        self._process = subprocess.Popen(
            [self.shell],
            cwd=self.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._queue.put(line)

    def execute(self, command: str, *, timeout_seconds: float | None = None) -> ShellResult:
        self.start()
        assert self._process is not None and self._process.stdin is not None
        marker = f"__CUD_DONE_{uuid.uuid4().hex}__"
        wrapped = f"{command}\nprintf '\\n{marker}:%s\\n' \"$?\"\n"
        self._process.stdin.write(wrapped)
        self._process.stdin.flush()

        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        output: list[str] = []
        while True:
            try:
                line = self._queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"shell command timed out after {timeout}s") from exc
            if line.startswith(marker + ":"):
                return ShellResult(output="".join(output).rstrip("\n"), returncode=int(line.split(":", 1)[1]))
            output.append(line)

    def close(self) -> None:
        if not self._process:
            return
        if self._process.poll() is None:
            self._process.terminate()
        self._process = None

