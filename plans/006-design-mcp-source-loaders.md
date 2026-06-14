# Plan 006 Design: MCP Supervisor Source Loaders

## Server/tool resolution

Use the existing `CronSupervisorSpec.source_ref` string and require `server:ref`
for MCP sources. For example, `mcp_note` uses `obsidian:Notes/today.md` and
`mcp_query` uses `obsidian:tag:#athena`.

This avoids changing the persisted cron schema during the spike. If future UX
needs aliases or defaults, those can be layered onto parsing without migrating
stored jobs.

## Tool-name mapping

`mcp_note` maps to `mcp_{server}_read_note` with `{"path": ref}`. `mcp_query`
maps to `mcp_{server}_search_vault` with `{"query": ref}`.

The prototype is strict about these names because AthenaAgent's MCP wrapper
already registers tools in that shape. Supporting server-specific aliases should
be a later compatibility feature once real vault servers are observed.

## Async loading

Source loading is async. `SupervisorExecutor._load_source` awaits MCP calls, and
`run_job` awaits `_load_source` before the decision step.

The executor receives a narrow `mcp_call(name, args)` async callable instead of
the whole agent loop. Runtime wiring adapts `agent_loop.tools` to that callable.

## Failure semantics

MCP source load failures return `SupervisorRunResult(status="error", error=...)`
through the existing `run_job` error path. A missing server/tool, invalid
`source_ref`, unavailable MCP server, or missing note should not crash the cron
loop.

## Security and scoping

MCP-sourced note and search content is untrusted input to the supervisor
decision and execution prompts. Treat it like web content: source text may
contain prompt injection, stale instructions, or misleading task framing.

This spike only loads source content. It does not add write-back behavior, a
custom loader extension point, or new CLI authoring support.
