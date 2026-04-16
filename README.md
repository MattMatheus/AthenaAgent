<div align="center">
  <img src="athena_agent_logo.png" alt="AthenaAgent" width="320">
  <h1>AthenaAgent</h1>
  <p>Task-focused agent runtime.</p>
</div>

AthenaAgent keeps the runtime primitives of the original fork base and strips away the parts aimed at being a broad personal-assistant product.

The fork is centered on:

- CLI-first task execution
- scheduled recurring agent work
- MCP as a first-class extension surface
- subagents
- workspace and file-oriented operation
- memory and session continuity for runtime use

Dream is still available, but only as an optional memory-maintenance subsystem. It is not part of the main runtime path.

The fork is not centered on:

- personal life management
- a wide chat-platform matrix
- built-in consumer messaging surfaces
- demo personas

## Current Direction

This repository is in the middle of a fork transition.

The immediate goal is to preserve the runtime core while reworking the project around:

- direct interactive agent mode
- scheduled supervisor and exploration jobs
- profile-driven tool exposure
- external workspace collaboration through MCP, especially Obsidian MCP

The implementation plan for that transition lives in [fork-implementation-plan.md](./fork-implementation-plan.md).

## Core Runtime Pieces Being Kept

- agent loop and runner
- session and memory systems
- skills
- cron scheduler
- subagents
- MCP
- filesystem, search, shell, and web tools
- provider abstraction

## Surfaces Being De-emphasized or Removed

- multi-channel chat product framing
- websocket and bridge-oriented packaging
- API and gateway surfaces as primary product entrypoints
- onboarding and docs that assume a consumer assistant product
- notebook as a legacy tool pending Obsidian MCP replacement

## Quick Start

The runtime is exposed through the `athena-agent` CLI.

### 1. Install from source

```bash
git clone <your-fork-url>
cd AthenaAgent
pip install -e .
```

### 2. Initialize config

```bash
athena-agent onboard
```

### 3. Add an API key

Edit `~/.athena-agent/config.json` and configure a provider under `providers`.

### 4. Run a task

```bash
athena-agent agent -m "Summarize this repository and identify refactor targets."
```

### 5. Use interactive mode

```bash
athena-agent agent
```

## Runtime Focus

### Interactive agent mode

Use the CLI for direct task execution, research, synthesis, and implementation work.

### Scheduled supervisor mode

Use cron-backed jobs for recurring exploration, triage, synthesis, and follow-up work.
Fresh workspaces now use `SUPERVISOR.md` as the default recurring task source.

### MCP-first workspace model

Use MCP to connect the runtime to external workspaces and tools. Obsidian MCP is the intended shared human/agent workspace path.
See [docs/MCP_WORKSPACE.md](./docs/MCP_WORKSPACE.md) for the recommended workspace model.
See [docs/OBSIDIAN_MCP_INTEGRATION.md](./docs/OBSIDIAN_MCP_INTEGRATION.md) for the recommended `obsidianMCP` wiring pattern.

## Memory Model

AthenaAgent is moving toward a three-layer memory model:

- runtime session memory
- durable agent memory
- external workspace memory via MCP

More detail is in [docs/MEMORY.md](./docs/MEMORY.md).

Dream remains available for slower memory distillation, but it should be treated as optional maintenance rather than a default operating mode.

## Notes on Compatibility

- The Python package now uses the `athena_agent` module path directly.
- Legacy `channels` config still loads as input, but the canonical saved shape is `output`.

## Status

The first implementation milestone focuses on:

- rebranding the project surface
- reducing product and documentation clutter
- preserving core runtime subsystems

Later milestones will cover:

- tool profiles
- cron supervisor jobs
- MCP-first workflow cleanup
