# Memory in AthenaAgent

AthenaAgent should treat memory as runtime infrastructure, not as a model of a person's life.

The forked runtime is centered on three memory layers:

## 1. Runtime Session Memory

- short-term execution continuity
- active conversation and tool context
- compacted when sessions grow too large

This is primarily handled through session history plus the consolidator flow that appends summarized history into `memory/history.jsonl`.

## 2. Durable Agent Memory

- project facts
- distilled decisions
- stable domain knowledge
- reusable execution context

Today this is represented by durable workspace files such as:

- `memory/MEMORY.md`
- `USER.md`
- `SOUL.md`
- `memory/history.jsonl`

In this fork, these files should be interpreted as agent and runtime knowledge stores, not as personal-assistant personality files.

## 3. External Workspace Memory

- human and agent shared notes
- idea archives
- research inputs
- longer-lived artifacts

This should often live outside the runtime's internal memory files, especially through MCP-backed workspaces such as Obsidian.

## Current Mechanisms

The current codebase still includes two important memory mechanisms:

- `Consolidator`
  - compacts older message history into `memory/history.jsonl`
- `Dream`
  - performs slower distillation into longer-term files

`Consolidator` remains part of the core runtime path.

`Dream` should be treated as optional and under review until it is clearly justified as part of the agent runtime rather than inherited product behavior.

That means:

- the default runtime story should still make sense if Dream is never used
- scheduled supervisor work should not depend on Dream
- Dream can remain useful for slower memory maintenance without becoming the center of the product

## Direction for the Fork

The target memory model for AthenaAgent is:

- internal runtime memory for continuity
- durable agent memory for retained project and domain knowledge
- external MCP workspace memory for human-facing collaboration

That split keeps the runtime useful without centering the system on "learning the user as a person."
