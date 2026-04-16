# MCP Workspace Guide

AthenaAgent treats MCP as a normal operating surface, not an add-on.

## Recommended Model

Use three layers of persistence:

- runtime session memory for active conversational continuity
- durable internal memory for compact retained agent knowledge
- external workspace memory for shared notes, plans, and artifacts

The external workspace layer is where MCP fits best.

## Obsidian-Oriented Workflow

A practical default is:

- keep active agent/runtime state inside the workspace memory files
- keep durable human-facing notes in Obsidian
- expose Obsidian to AthenaAgent through an MCP server
- use cron supervisor jobs to revisit shared task sources and notes

For concrete `obsidianMCP` wiring, see [ObsidianMCP Integration](./OBSIDIAN_MCP_INTEGRATION.md).

This gives you:

- a human-readable source of truth
- lower pressure on internal memory files
- cleaner collaboration between operator and agent

## What Belongs Where

Use internal runtime memory for:

- recent execution continuity
- summarized session history
- compact durable facts the runtime needs immediately

Use MCP-backed workspace memory for:

- project plans
- research notes
- operating checklists
- meeting notes
- durable references you want to read and edit directly

## Supervisor Pattern

A good recurring pattern is:

1. Put recurring work cues in `SUPERVISOR.md` or an MCP-backed notes source.
2. Run a cron supervisor job on a stable interval.
3. Let the supervisor decide whether there is actionable work.
4. Write human-facing outputs back to the MCP workspace when appropriate.

That keeps recurring work visible and shared instead of hiding it inside the runtime.

## Configuration Direction

In this fork, the intended direction is:

- `scheduler.supervisor` for recurring runtime defaults
- `tools.mcpServers` for MCP connections
- `output` for transport/output behavior

Legacy `channels` config still loads for compatibility, but it is not the preferred shape.
