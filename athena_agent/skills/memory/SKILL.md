---
name: memory
description: Runtime memory guidance with optional Dream-based maintenance for durable files.
always: true
---

# Memory

## Structure

- `SOUL.md` — Runtime identity and communication guidance. Usually maintained by the runtime's durable memory flow.
- `USER.md` — User profile and preferences. Usually maintained by the runtime's durable memory flow.
- `memory/MEMORY.md` — Long-term facts (project context, important events). Usually maintained by the runtime's durable memory flow.
- `memory/history.jsonl` — append-only JSONL, not loaded into context. Prefer the built-in `grep` tool to search it.

## Search Past Events

`memory/history.jsonl` is JSONL format — each line is a JSON object with `cursor`, `timestamp`, `content`.

- For broad searches, start with `grep(..., path="memory", glob="*.jsonl", output_mode="count")` or the default `files_with_matches` mode before expanding to full content
- Use `output_mode="content"` plus `context_before` / `context_after` when you need the exact matching lines
- Use `fixed_strings=true` for literal timestamps or JSON fragments
- Use `head_limit` / `offset` to page through long histories
- Use `exec` only as a last-resort fallback when the built-in search cannot express what you need

Examples (replace `keyword`):
- `grep(pattern="keyword", path="memory/history.jsonl", case_insensitive=true)`
- `grep(pattern="2026-04-02 10:00", path="memory/history.jsonl", fixed_strings=true)`
- `grep(pattern="keyword", path="memory", glob="*.jsonl", output_mode="count", case_insensitive=true)`
- `grep(pattern="oauth|token", path="memory", glob="*.jsonl", output_mode="content", case_insensitive=true)`

## Important

- Prefer not to hand-edit `SOUL.md`, `USER.md`, or `memory/MEMORY.md` unless the user explicitly wants manual control.
- Dream may maintain those files when optional memory-maintenance runs are enabled, but the main runtime path should not assume Dream is always active.
- Users can inspect Dream activity with `/dream-log` when Dream-based maintenance is in use.
