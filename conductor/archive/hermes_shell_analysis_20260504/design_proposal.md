# Design Proposal: Improved Shell Execution for Cud

## Overview
This proposal outlines the adaptation of `hermes-agent`'s robust shell execution concepts into the `cud` framework. The goal is to improve CWD tracking, reporting, and safety while allowing for configurable workspace traversal.

## 1. Core Changes to `ShellSession` (`src/cud/tools/shell.py`)

### 1.1 CWD Tracking and Persistence
Currently, `ShellSession` sets an initial `cwd` but doesn't track changes made via `cd` commands back to the Python instance.
- **Proposed Solution**: Wrap every command in a bash script that captures the final CWD.
- **Implementation**:
    ```bash
    # Wrapped command structure
    {command}
    __cud_ec=$?
    printf '\n__CUD_CWD__%s__CUD_CWD__\n' "$(pwd -P)"
    exit $__cud_ec
    ```
- **Update Logic**: The `execute` method will parse the `__CUD_CWD__` marker and update `self.cwd`.

### 1.2 Configurable Workspace Boundaries
- **New Attributes**:
    - `root_dir: Path`: The absolute path of the workspace root.
    - `allow_traversal: bool`: Whether the agent is allowed to `cd` outside of `root_dir`.
- **Validation**: If `allow_traversal` is `False`, the `execute` method will verify that the captured CWD is still within `root_dir`. If it escapes, it will force a `cd` back to `root_dir` or report an error.

### 1.3 Real-time Progress Reporting
- **Background**: Long-running commands currently block the agent without feedback.
- **Proposed Solution**: 
    - Implement a `select`-based or `Queue.get(timeout)`-based polling loop in `execute`.
    - Every 10 seconds of execution without completion, fire an `on_activity` callback (if provided).
    - This allows the gateway (e.g., Discord) to show "Command running..." status updates.

### 1.4 Robust Process Management
- **Process Groups**: Start the shell process with `os.setsid()` (on POSIX).
- **Cleanup**: In `close()`, use `os.killpg(pgid, signal.SIGTERM)` followed by `SIGKILL` if necessary to ensure all background processes started by the agent are reaped.

### 1.5 Environment Sanitization
- **Blocklist**: Prevent leaking `CUD_*` secrets or provider keys into the shell subprocess unless explicitly allowed.

## 2. Integration with `AgentRuntime` (`src/cud/agent/runtime.py`)
- Pass `workspace_dir` as `root_dir` to `ShellSession`.
- Expose `allow_traversal` as a configurable setting in the agent's `settings.yaml`.

## 3. UI/UX Improvements
- Update the CLI and Discord gateway to handle and display periodic activity updates from the shell tool.
