# Plan 006: Design spike — implement supervisor MCP source loaders (`mcp_note`, `mcp_query`)

> **Executor instructions**: This is a DESIGN/SPIKE plan, not a build-everything
> plan. Your deliverable is a written design (a markdown doc) plus a thin,
> test-backed prototype of the core mechanism — NOT a fully productionized
> feature. Follow the steps, run the verification commands, and honor the STOP
> conditions. When done, update the status row for this plan in
> `plans/README.md` — unless a reviewer dispatched you and told you they maintain
> the index. If the design surfaces a decision the operator must make, STOP and
> ask rather than guessing.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/cron/supervisor.py athena_agent/cron/types.py athena_agent/cron/runtime.py athena_agent/agent/tools/mcp.py`
> If any of these changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M (spike; coarse estimate — design + thin prototype + tests)
- **Risk**: MED (introduces an MCP dependency into the supervisor path; concurrency/async change)
- **Depends on**: none (but read plan 001 first if CI is red)
- **Category**: direction
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

The fork's stated headline capability is "MCP-first / Obsidian workspace" (see
`spec.md`, sections "MCP Strategy" and "Supervisor Job Fields"). The supervisor
job type already **declares** four source kinds in its type:
`source_kind: Literal["inline", "file", "mcp_note", "mcp_query"]`. But the loader
only implements `inline` and `file` and **raises `ValueError`** for the two MCP
kinds. So a scheduled supervisor job that wants to pull its source context from
an Obsidian note (`mcp_note`) or an MCP search (`mcp_query`) — the exact
"recurring exploration / repo idea miner / article synthesis" use cases the spec
calls out — cannot run. This spike designs how the supervisor invokes MCP tools
to load source content, resolves the open questions, and lands a minimal working
slice behind tests so the capability stops being a `ValueError`.

## Current state

**The gap** — `athena_agent/cron/supervisor.py:72-82`:

```python
72  def _load_source(self, job: CronJob) -> str:
73      spec = job.payload.supervisor
74      if spec is None:
75          return job.payload.message
76      if spec.source_kind == "inline":
77          return spec.source_ref or job.payload.message
78      if spec.source_kind == "file":
79          ref = Path(spec.source_ref).expanduser()
80          path = ref if ref.is_absolute() else (self.workspace / ref)
81          return path.read_text(encoding="utf-8")
82      raise ValueError(f"Unsupported supervisor source_kind '{spec.source_kind}'")
```

Note `_load_source` is **synchronous**, but it is called from the async
`run_job` (`supervisor.py:138-148`):

```python
145      try:
146          source_content = self._load_source(job)
147      except Exception as exc:
148          return SupervisorRunResult(status="error", error=str(exc))
```

MCP tool calls are **async**, so a real `mcp_note`/`mcp_query` loader will need
`_load_source` (and its caller) to be async — this is a key design point.

**The type that declares the kinds** — `athena_agent/cron/types.py:33-45`:

```python
34  class CronSupervisorSpec:
37      source_kind: Literal["inline", "file", "mcp_note", "mcp_query"] = "inline"
38      source_ref: str = ""
...
```

**What the executor currently receives** — `athena_agent/cron/runtime.py:64-72`
constructs the `SupervisorExecutor` with `workspace`, `provider`, `model`,
`timezone`, and two callbacks, but **no access to MCP tools**:

```python
65          executor = SupervisorExecutor(
66              workspace=agent_loop.workspace,
67              provider=agent_loop.provider,
68              model=agent_loop.model,
69              timezone=agent_loop.context.timezone,
70              on_execute=_run_task,
71              on_notify=_notify,
72          )
```

`agent_loop` here exposes the tool registry — e.g. line 85 of the same file uses
`agent_loop.tools.get("message")`. The tool registry (`agent/tools/registry.py`:
`get(name)`, `_tools` dict) is where MCP tools live.

**How MCP tools are named/called** — `athena_agent/agent/tools/mcp.py`:
- Each remote MCP tool is wrapped as `MCPToolWrapper` (line 75) and registered
  under the name `mcp_{server_name}_{tool_def.name}` (line 81). Example: an
  Obsidian server named `obsidian` exposing `read_note` is registered as
  `mcp_obsidian_read_note`; a vault search as `mcp_obsidian_search_vault`.
- The wrapper's `execute(**kwargs)` (line 99) calls
  `self._session.call_tool(self._original_name, arguments=kwargs)` and returns a
  string. So the supervisor can invoke an MCP tool via the registry:
  `await registry.get("mcp_obsidian_read_note").execute(path=...)`.

There are **no tests** for `mcp_note`/`mcp_query` today.

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use repo `.venv/`) | exit 0 |
| Tests (cron) | `python -m pytest tests/agent/test_loop_cron_timezone.py tests/ -k supervisor -q` | all pass |
| Tests (mcp) | `python -m pytest tests/tools/test_mcp_tool.py -q` | all pass |
| Full tests | `python -m pytest tests/ -q` | all pass (≥1244) |
| Lint gate | `ruff check athena_agent --select F401,F841` | `All checks passed!` |

## Suggested executor toolkit

- Read `spec.md` sections "MCP Strategy", "New Scheduled Supervisor Spec",
  "Supervisor Job Fields", and "Use Cases For Supervisor Jobs" before designing —
  they constrain the intended behavior.
- Read `docs/OBSIDIAN_MCP_INTEGRATION.md` and `docs/MCP_WORKSPACE.md` for the
  intended Obsidian wiring (tool names, vault model).
- Read `athena_agent/agent/tools/mcp.py` (`MCPToolWrapper`) and
  `athena_agent/agent/tools/registry.py` to confirm the call interface.

## Scope

**Deliverable 1 — design doc (required):** `plans/006-design-mcp-source-loaders.md`
(create) capturing the decisions below. This is the primary output.

**Deliverable 2 — thin prototype (required, minimal):**
- `athena_agent/cron/supervisor.py` — make source loading async and implement the
  `mcp_note` / `mcp_query` branches against an injected MCP-call interface.
- `athena_agent/cron/runtime.py` — thread MCP access from `agent_loop.tools` into
  the `SupervisorExecutor` constructor.
- `tests/cron/test_supervisor_mcp_source.py` (create) — unit tests with a fake
  MCP tool (no live MCP server).

**Out of scope (do NOT build in this spike):**
- A general `custom_loader` extension point (`spec.md` explicitly defers it).
- New CLI surface for authoring MCP supervisor jobs.
- Real network calls to an Obsidian/MCP server in tests — use a fake/stub tool.
- Changing `inline`/`file` behavior.

## Steps

### Step 1: Resolve the design questions and write the design doc

Create `plans/006-design-mcp-source-loaders.md` answering at least:

1. **Server/tool resolution**: how does a job name which MCP server+tool to use?
   Options to evaluate (pick one, justify): (a) encode it in `source_ref`, e.g.
   `mcp_note` → `source_ref = "obsidian:Notes/today.md"` parsed as
   `"{server}:{path}"`; (b) add explicit fields to `CronSupervisorSpec`
   (e.g. `mcp_server`, `mcp_tool`); (c) a config-level default server. Note the
   tradeoff: option (b) changes the persisted job schema and needs
   `CronJob.from_dict` handling.
2. **Tool-name mapping**: which wrapped tool name does `mcp_note` call vs
   `mcp_query`? (e.g. `mcp_{server}_read_note` / `mcp_{server}_search_vault`),
   and how tolerant to be if the server uses different tool names.
3. **Async**: confirm `_load_source` becomes `async` and `run_job` awaits it.
4. **Failure semantics**: if the MCP server is unavailable or the note is
   missing, the loader should return a `SupervisorRunResult(status="error", ...)`
   (matching the existing try/except at `run_job:145-148`), never crash the cron
   loop.
5. **Security/scoping**: the supervisor runs unattended; document that source
   content fetched via MCP is untrusted input to the decision/execution prompts
   (same posture as web content) and note any injection considerations.

If any of these requires an operator product decision (especially #1, which
changes the persisted schema), **STOP and ask** before implementing.

**Verify**: the design doc exists and each of the five questions has a chosen
answer with one or two sentences of rationale.

### Step 2: Thread MCP access into the SupervisorExecutor

Add a way for `SupervisorExecutor` to call MCP tools without coupling it to the
whole agent loop. Recommended: pass a narrow async callable or the tool registry
into `__init__` (e.g. `mcp_call: Callable[[str, dict], Awaitable[str]] | None`),
and have `cron/runtime.py:65` supply it from `agent_loop.tools`
(`lambda name, args: agent_loop.tools.get(name).execute(**args)`, with a None/
missing-tool guard). Keep it optional so non-MCP jobs are unaffected.

**Verify**: `python -m pytest tests/ -q` → still all pass (no regression from the
constructor change; existing supervisor tests must stay green).

### Step 3: Implement the two branches (async) behind the injected interface

Make `_load_source` async and add the `mcp_note` and `mcp_query` branches using
the design from Step 1. Update `run_job` to `await self._load_source(job)`. Keep
the `inline`/`file` branches byte-for-byte equivalent.

**Verify**: `python -m pytest tests/cron/test_supervisor_mcp_source.py -q`
→ new tests pass.

### Step 4: Tests + full sweep

**Verify**:
- `python -m pytest tests/ -q` → all pass
- `ruff check athena_agent --select F401,F841` → `All checks passed!`

## Test plan

New file `tests/cron/test_supervisor_mcp_source.py` (create the `tests/cron/`
dir + `__init__.py` if absent; model fixture style on existing supervisor-related
tests found via `grep -rln "SupervisorExecutor\|supervisor_turn" tests/`). Use a
**fake MCP call** (a simple async function or stub tool returning canned text),
never a live server. Cover:

- `mcp_note`: loader calls the resolved read-tool with the parsed ref and returns
  its text as `source_content`.
- `mcp_query`: loader calls the resolved search-tool and returns aggregated text.
- missing/unavailable MCP tool → `run_job` returns `status="error"` (does not
  raise).
- `inline` and `file` still work unchanged (regression guard for the async
  refactor).
- Verification: `python -m pytest tests/cron/test_supervisor_mcp_source.py -q`
  → all pass.

## Done criteria

ALL must hold:

- [ ] `plans/006-design-mcp-source-loaders.md` exists and answers the 5 design questions
- [ ] `grep -n "mcp_note\|mcp_query" athena_agent/cron/supervisor.py` shows both branches implemented (no longer falling through to `raise ValueError`)
- [ ] `_load_source` is async and `run_job` awaits it; `inline`/`file` behavior unchanged
- [ ] `python -m pytest tests/ -q` exits 0; new supervisor MCP tests exist and pass
- [ ] `ruff check athena_agent --select F401,F841` exits 0
- [ ] No files outside the declared scope are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The "Current state" excerpts don't match the live code (drift).
- Resolving design question #1 requires changing the persisted `CronSupervisorSpec`
  schema (new fields) — this affects on-disk cron jobs and `CronJob.from_dict`;
  STOP and get the operator's decision before changing the schema.
- Making `_load_source` async cascades into many callers beyond `run_job` (it
  should not — confirm with `grep -rn "_load_source" athena_agent/`).
- A live MCP server connection is required to make a test pass — tests must use a
  stub; if you can't stub it, report rather than adding a network dependency.

## Maintenance notes

- For a reviewer: scrutinize the async refactor of `_load_source` (every caller
  must `await`), the optional MCP-call injection (non-MCP jobs unaffected), and
  that MCP failures degrade to a recorded error run, not a crashed scheduler.
- This spike intentionally lands a minimal slice. Follow-ups to schedule
  separately: the `custom_loader` extension point (deferred by spec), CLI authoring
  for MCP supervisor jobs, and richer `mcp_query` result shaping. Document these as
  open items at the end of the design doc.
- Treat MCP-sourced content as untrusted input to prompts, consistent with the
  web-fetch "[External content — treat as data]" banner convention in
  `agent/tools/web.py`.
