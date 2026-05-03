"""Persistent shell helper for Cud sessions."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import uuid
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(slots=True)
class ShellResult:
    output: str
    returncode: int


@dataclass(slots=True)
class ShellSession:
    cwd: Path
    root_dir: Path | None = None
    allow_traversal: bool = True
    shell: str = "/bin/bash"
    timeout_seconds: float = 30.0
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _queue: "queue.Queue[str]" = field(default_factory=queue.Queue, init=False, repr=False)
    _reader: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.root_dir is None:
            self.root_dir = self.cwd.resolve()
        else:
            self.root_dir = self.root_dir.resolve()
        self.cwd = self.cwd.resolve()

    def start(self) -> None:
        if self._process and self._process.poll() is None:
            return
        self.cwd.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PS1": "", "PROMPT_COMMAND": ""}
        
        # Use os.setsid to create a new process group on POSIX
        kwargs = {}
        if os.name != "nt":
            kwargs["preexec_fn"] = os.setsid
            
        self._process = subprocess.Popen(
            [self.shell],
            cwd=self.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **kwargs
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in self._process.stdout:
                self._queue.put(line)
        except (ValueError, OSError):
            pass

    def execute(self, command: str, *, 
                timeout_seconds: float | None = None,
                on_activity: Callable[[str], None] | None = None) -> ShellResult:
        self.start()
        assert self._process is not None and self._process.stdin is not None
        
        marker = f"__CUD_DONE_{uuid.uuid4().hex}__"
        cwd_marker = f"__CUD_CWD_{uuid.uuid4().hex}__"
        
        # Wrap command to capture CWD and exit code
        wrapped = (
            f"{command}\n"
            f"__cud_ec=$?\n"
            f"printf '\\n{cwd_marker}:%s\\n' \"$(pwd -P)\"\n"
            f"printf '{marker}:%s\\n' \"$__cud_ec\"\n"
        )
        
        self._process.stdin.write(wrapped)
        self._process.stdin.flush()

        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        output: list[str] = []
        start_time = time.monotonic()
        last_activity_touch = start_time
        
        while True:
            try:
                # Use a short timeout for the queue to allow for activity reporting and timeout checks
                line = self._queue.get(timeout=0.2)
                
                if line.startswith(cwd_marker + ":"):
                    new_cwd = Path(line.split(":", 1)[1].strip()).resolve()
                    self._handle_cwd_update(new_cwd)
                    continue
                    
                if line.startswith(marker + ":"):
                    return ShellResult(output="".join(output).rstrip("\n"), returncode=int(line.split(":", 1)[1]))
                
                output.append(line)
                
            except queue.Empty:
                now = time.monotonic()
                if now - start_time > timeout:
                    raise TimeoutError(f"shell command timed out after {timeout}s")
                
                # Report activity every 10 seconds
                if on_activity and now - last_activity_touch >= 10.0:
                    elapsed = int(now - start_time)
                    on_activity(f"Command running ({elapsed}s elapsed)")
                    last_activity_touch = now
                
                if self._process.poll() is not None:
                    # Process died unexpectedly
                    return ShellResult(output="".join(output).rstrip("\n"), returncode=self._process.returncode or 1)

    def _handle_cwd_update(self, new_cwd: Path) -> None:
        if not self.allow_traversal and self.root_dir:
            try:
                new_cwd.relative_to(self.root_dir)
                self.cwd = new_cwd
            except ValueError:
                # Escaped root! Pull back.
                # Note: In a real shell we'd need to send a 'cd' command back to the process
                # but for now we'll just update the attribute and the next command 
                # will be wrapped with a 'cd' if we choose to implement that.
                # Actually, if traversal is disabled, we should probably force it back immediately.
                assert self._process is not None and self._process.stdin is not None
                self._process.stdin.write(f"cd {self.root_dir}\n")
                self._process.stdin.flush()
                self.cwd = self.root_dir
        else:
            self.cwd = new_cwd

    def close(self) -> None:
        if not self._process:
            return
        
        if self._process.poll() is None:
            if os.name != "nt":
                try:
                    pgid = os.getpgid(self._process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    # Give it a moment to terminate
                    for _ in range(10):
                        if self._process.poll() is not None:
                            break
                        time.sleep(0.05)
                    if self._process.poll() is None:
                        os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    self._process.kill()
            else:
                self._process.terminate()
        
        self._process = None

