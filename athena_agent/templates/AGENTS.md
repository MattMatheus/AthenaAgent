# Agent Instructions

## Scheduled Reminders

Before scheduling reminders, check available skills and follow skill guidance first.
Use the built-in `cron` tool to create/list/remove jobs (do not call `athena_agent cron` via `exec`).
Use stable runtime/session identifiers when a scheduled job needs continuity across runs.

**Do NOT just write reminders to MEMORY.md** — that will not trigger actual scheduled execution.

## Scheduled Supervisor Work

Use `SUPERVISOR.md` as the default workspace task source for recurring supervisor passes.

When the user asks for recurring or periodic execution:

- prefer cron-backed scheduling
- preserve stable session context when useful
- keep outputs in durable memory or external workspace artifacts when appropriate
