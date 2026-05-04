# Track spec: Analyze hermes-agent shell execution

## Objective
Analyze the shell execution and workspace directory management implementation within the `../hermes-agent` project and determine how to adapt its unrestricted access or directory handling concepts into the `cud` framework.

## Background
Currently, the `cud` agent is restricted to its designated workspace and cannot traverse or execute commands outside of it (e.g., `/home/arrase`). The user observed that `hermes-agent` handles this differently. We need to study their implementation to improve our agent's shell execution flexibility and user reporting.

## Key Goals
1. Analyze `../hermes-agent` source code focusing on shell command execution and directory context management.
2. Understand how `hermes-agent` communicates shell execution progress and results to the user.
3. Design an adaptation plan to safely implement similar unrestricted or user-configurable directory access in `cud`'s shell tools.
4. Implement the adapted solution in `cud/src/cud/tools/shell.py` and related components.