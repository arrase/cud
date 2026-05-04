# Research Report: hermes-agent Shell Execution

## 1. Modules Responsible for Shell Execution
- **`tools/terminal_tool.py`**: The main entry point and facade for the terminal tool. It handles configuration, backend selection (local, docker, modal, etc.), and SUDO password management.
- **`tools/environments/base.py`**: Contains the `BaseEnvironment` abstract class, which implements the core logic for command wrapping, execution, output draining, and session management.
- **`tools/environments/local.py`**: Implements `LocalEnvironment` for running commands directly on the host using `subprocess.Popen`.

## 2. Current Working Directory (CWD) and Path Management
- **Initial CWD**: Defaults to the host's `os.getcwd()` or can be overridden by the `TERMINAL_CWD` environment variable.
- **Command Wrapping**: Every command is wrapped in a bash script that:
    1. Sources a session snapshot (if available).
    2. Executes `builtin cd <quoted_cwd> || exit 126`.
    3. Runs the actual command.
    4. Writes the final CWD to a temporary file (local) or stdout marker (remote).
- **CWD Persistence**: After the command completes, the agent reads the temporary file or parses the stdout marker to update its internal `self.cwd`. This ensures that `cd` commands persist across tool calls.
- **Path Restrictions**: 
    - The terminal tool in `hermes-agent` is **unrestricted** for local execution; it operates with the same permissions as the user running the agent.
    - While there is a `HERMES_WRITE_SAFE_ROOT` and `is_write_denied` mechanism in `agent/file_safety.py`, it is primarily used by high-level file tools (like `write_file`) and not by the terminal tool itself.

## 3. Communication and Reporting
- **Output Streaming**:
    - Uses a background "drain thread" that reads from the combined `stdout`/`stderr` pipe using `select.select`.
    - Drains output in chunks to avoid blocking and handles potential hangs from backgrounded grandchild processes.
- **Progress Reporting**:
    - The `_wait_for_process` loop in `BaseEnvironment` fires an `activity_callback` every 10 seconds.
    - This callback typically reports status like `terminal command running (10s elapsed)` to the user or gateway.
- **Interrupt Handling**:
    - Polls a global `is_interrupted()` flag. If an interrupt is detected, it kills the entire process group (`os.killpg`) to ensure no orphans are left behind.

## 4. Key Improvements over `cud`'s Current Implementation
- **Session Snapshots**: Captures environment variables, aliases, and functions to maintain a persistent shell session across calls.
- **Process Group Management**: Using `os.setsid` and `os.killpg` is more robust than just killing the parent process.
- **Draining Logic**: The `select`-based draining is more resilient to background processes inherited pipes.
