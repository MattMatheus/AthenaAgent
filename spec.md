# Nanobot Fork Spec

## Goals

Build a fork of `athena_agent` into a general-purpose agent runtime for task-focused agents, not a personal assistant product.

The fork should preserve:
- strong agent infrastructure
- scheduling and autonomous recurring work
- subagents
- MCP as a first-class extension surface
- file/workspace-oriented operation
- enough flexibility to support exploration loops, research, implementation, and synthesis

The fork should remove or de-emphasize:
- multi-channel product sprawl
- "personal life" framing
- prepackaged assistant/demo personas
- broad consumer-style surfaces that do not contribute to the runtime core

The fork should support:
- interactive task agents
- scheduled supervisor/exploration agents
- external human/agent workspace through Obsidian MCP
- optional Telegram later, without making messaging central

## Product Positioning

This fork is not:
- a personal assistant
- a life-management bot
- a multi-channel consumer messaging product

This fork is:
- an agent runtime
- a scheduler for recurring agent work
- a substrate for specialized agents
- a tool/MCP/skill-enabled execution environment

Working name:
- `athena_agent-core`
- or a new project name if cleaner conceptual separation is desirable later

## Core Principles

- Prefer optionality over premature deletion.
- Remove product clutter before removing infrastructure.
- Preserve strong primitives even if not used on day one.
- Make capabilities modular and profile-driven instead of globally enabled by default.
- Treat MCP as a normal operating surface, not an add-on.
- Keep recurring background work as a first-class runtime concern.

## In Scope

- core agent loop
- tools and tool registry
- skills
- memory/sessioning
- scheduler
- supervisor jobs
- subagents
- MCP
- workspace/file-based operation
- optional web access
- CLI-first usage
- optional Telegram later

## Out of Scope

- email
- broad chat platform matrix
- personal-assistant defaults
- demo/product personas
- wide end-user onboarding flows
- broad built-in communication surfaces unless later justified

## Retained Nanobot Subsystems

Keep as core:

- `agent/loop.py`
- `agent/runner.py`
- `agent/context.py`
- `agent/memory.py`
- `agent/skills.py`
- `agent/hook.py`
- `agent/subagent.py`
- `agent/tools/base.py`
- `agent/tools/schema.py`
- `agent/tools/registry.py`
- `agent/tools/filesystem.py`
- `agent/tools/search.py`
- `agent/tools/shell.py`
- `agent/tools/mcp.py`
- `session/manager.py`
- `cron/service.py`
- `cron/types.py`
- `utils/prompt_templates.py`
- `utils/helpers.py`
- `utils/gitstore.py`
- `utils/evaluator.py`
- `athena_agent.py`

Keep, but not necessarily as default-enabled:

- `agent/tools/web.py`
- `agent/tools/spawn.py`
- `agent/tools/cron.py`
- provider flexibility beyond the minimum set
- notebook tool only if a later use case proves it valuable

## Subsystems To Remove First

These should be removed early because they are clearly product-oriented rather than core runtime value:

- most of `channels/`
- `api/`
- websocket/bridge surfaces
- most onboarding/setup wizard behavior
- assistant/product/demo-facing docs and templates that imply lifestyle use
- built-in skills that are really showcase/demo clutter rather than reusable primitives

Likely keep only:

- CLI
- maybe Telegram later

## Subsystems To Keep For Now

These should remain until proven unnecessary:

- subagents
- MCP
- scheduler
- web tools
- tool schema/validation
- hooks
- session management
- provider abstraction
- execution sandboxing/restrictions

## Subsystems To Demote or Replace

- `heartbeat`
  - replace as a subsystem
  - preserve its useful pattern inside cron
- notebook tool
  - demote for now because Obsidian MCP is the preferred human/agent workspace
- Dream
  - do not treat as core product behavior
  - either disable initially or later reframe as exploration/distillation infrastructure

## Runtime Modes

The fork should support two first-class runtime modes.

### 1. Interactive Agent Mode

- invoked via CLI
- handles direct tasks
- uses selected tool profile
- may use sessions/memory
- may use subagents
- MCP available

### 2. Scheduled Supervisor Mode

- invoked by cron
- runs recurring jobs
- may perform triage before full execution
- may run long-horizon exploration
- may write to Obsidian via MCP
- may promote outputs into durable memory/artifacts

These should share the same core runtime rather than being separate products.

## Tooling Model

Adopt explicit tool profiles rather than "register everything."

Suggested built-in profiles:

### `core`

- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `glob`
- `grep`
- `exec`

### `research`

- `core`
- `web_search`
- `web_fetch`

### `orchestrator`

- `core`
- `spawn`

### `scheduled`

- `core`
- `cron`
- optional `spawn`

### `mcp_first`

- `core`
- MCP tools
- optional web

Tool registration should be driven by config/profile, not hardcoded broad defaults.

## MCP Strategy

MCP is a first-class core capability.

Use MCP for:
- Obsidian vault access
- external knowledge/workspace interaction
- human/agent shared notes
- future system integrations

Design assumptions:
- Obsidian MCP can replace much of the built-in notebook/document interface
- internal runtime memory is still useful for execution continuity
- durable human-facing knowledge artifacts should often live in Obsidian rather than internal files alone

Implication:
- design memory and outputs with an "internal runtime memory + external MCP workspace" split

## Memory Model

Memory should be split conceptually into at least three layers.

### 1. Runtime Session Memory

- short-term execution continuity
- per-session history
- bounded and compactable

### 2. Durable Agent Memory

- facts or distilled patterns the agent should retain
- likely file-backed
- scoped to agent/domain, not "user personality"

### 3. External Workspace Memory

- human/agent shared notes
- idea archives
- evolving concepts
- source material
- lives in Obsidian via MCP

Do not center the system on "learning me as a person."
Center it on:

- task/domain context
- project context
- durable insights
- exploration outputs

## Skills Model

Keep athena_agent's skill mechanism.

Desired behavior:

- skills are reusable instructions/capability modules
- summaries load by default
- full skill bodies load progressively when needed
- skills can be local and domain-specific
- skills can reference MCP workflows, tool patterns, repo patterns, and exploration routines

Skills should be treated as:

- agent operating procedures
- domain playbooks
- reusable execution recipes

Not as:

- demo gimmicks
- roleplay personas

## Subagents

Subagents remain a core capability.

Desired uses:

- bounded parallel work
- specialized side tasks
- exploration branches
- research vs implementation split
- candidate generation vs evaluation split

Constraints:

- subagents should use explicit tool profiles
- subagent results should return cleanly to the parent
- subagent use should be intentional, not default

## Scheduling Model

Cron becomes the sole scheduler.

There should not be two parallel recurring-execution systems.
Heartbeat should be absorbed into cron.

Cron should support:

- one-shot jobs
- interval jobs
- cron-expression jobs
- protected system jobs
- manual trigger
- run history
- status/error tracking

This stays close to current `CronService`, with an expanded execution model.

## Heartbeat Replacement

Heartbeat as a separate subsystem is deprecated.

Replace it with a cron-based supervisor pattern.

Current heartbeat's useful ideas to preserve:

- cheap phase-1 triage/decision step
- full phase-2 execution only when needed
- optional post-run notification evaluation
- stable recurring session context
- bounded retained session history

What goes away:

- standalone `HeartbeatService`
- dedicated heartbeat loop
- special branding around `HEARTBEAT.md`
- dedicated heartbeat config block as a primary subsystem

## New Scheduled Supervisor Spec

Introduce a cron-supported supervisor execution mode.

Current cron payload kinds are too simple. Expand them so cron jobs can express richer behavior.

Suggested payload model:

- `agent_turn`
- `supervisor_turn`
- optionally `system_event` remains as a protection marker, or is separated from execution kind

Suggested `supervisor_turn` behavior:

1. Load source context
2. Run decision/triage prompt with a lightweight model/config if configured
3. If result is `skip`, record skipped run
4. If result is `run`, construct execution task
5. Run full agent loop
6. Apply notify policy
7. Persist run results and session state

## Supervisor Job Fields

A supervisor job should support fields like:

- `source_kind`
  - `inline`
  - `file`
  - `mcp_note`
  - `mcp_query`
  - `custom_loader` later if needed

- `source_ref`
  - path or MCP identifier

- `decision_mode`
  - `always_run`
  - `llm_gate`
  - `rule_gate` later if useful

- `decision_prompt`
  - prompt for triage step

- `execution_prompt`
  - full prompt template

- `notify_policy`
  - `always`
  - `never`
  - `evaluate`

- `session_key`
  - stable recurring session name

- `keep_recent_messages`
  - bounded recurring history

- `deliver_target`
  - optional delivery surface if needed later

## Use Cases For Supervisor Jobs

- exploration walk every 30 minutes
- repo idea miner every 6 hours
- article synthesis pass daily
- backlog triage or concept clustering
- follow-up experiment dispatcher
- stale-task/failed-run monitor

## Exploration Loop Support

Your 30-minute high-temperature autonomous idea walks should be a first-class supported pattern.

The runtime should support a scheduled exploration job with:

- fixed cadence
- separate model configuration if desired
- source pool from files/MCP
- divergent prompt style
- structured outputs
- recurring session continuity if helpful
- ability to write outputs to Obsidian

Exploration jobs should be treated as normal supervisor jobs, not as a magical special system.

## Notification/Evaluation Model

Keep `evaluate_response(...)` as a reusable background-task notification gate.

Use it for:

- cron jobs
- supervisor jobs
- maybe subagent result surfacing later

Default behavior:

- safe-by-default notify on failure of evaluator
- configurable policy per job

## Config Philosophy

Config should be simplified and made more modular.

High-level config areas:

- runtime
- agent defaults
- tool profiles
- providers
- MCP servers
- scheduler
- optional surfaces

De-emphasize:

- huge cross-channel config surface
- end-user consumer setup complexity

Likely config changes:

- reduce default enabled providers
- remove or deprecate dedicated heartbeat config
- move recurring supervisor definitions into cron/job config
- make tool availability profile-based

## Provider Strategy

Do not remove provider abstraction, but reduce default complexity.

Suggested first retained provider set:

- OpenAI-compatible provider
- Anthropic provider

Optional keep-for-now:

- Codex provider
- GitHub Copilot provider

All others:

- keep only if low-cost to retain or useful
- otherwise demote from default config and docs before deleting

The goal is not to destroy flexibility, only to reduce default surface.

## CLI Strategy

CLI remains first-class.

CLI should support:

- direct task execution
- status
- cron job inspection/management
- triggering scheduled jobs
- running supervisor jobs manually
- loading specific tool profiles
- selecting agent mode/profile cleanly

CLI should not feel like a consumer chatbot shell first.
It should feel like an operator/developer agent runtime.

## Telegram Strategy

Telegram is optional and not core.
Do not design the runtime around it.
If kept later:

- it should be a thin surface adapter
- no broader implication that multi-channel messaging is a core product goal

## Notebook Tool Decision

Current status:

- deprioritized
- not core
- likely removed or disabled by default

Reason:

- Obsidian MCP is the preferred human/agent workspace
- notebook functionality is likely redundant

Only keep if:

- it offers workflow value not covered by Obsidian MCP
- it is very cheap to retain

## Phased Implementation Plan

### 1. Fork and Rebrand

- create fork
- update project identity and docs
- change framing from personal assistant to agent runtime

### 2. De-productize Without Over-Pruning

- remove broad channel/documentation/product surfaces
- retain runtime subsystems
- keep optionality

### 3. Make Tool Registration Profile-Driven

- stop broad implicit default registration
- add explicit tool profiles

### 4. Merge Heartbeat Into Cron Conceptually

- deprecate heartbeat subsystem
- add supervisor job execution mode to cron
- preserve triage/evaluate patterns

### 5. MCP-First Workspace Integration

- ensure Obsidian MCP works cleanly in core workflows
- document MCP as primary external workspace pattern

### 6. Simplify Config and Provider Defaults

- reduce default provider clutter
- remove heartbeat config as a distinct concept
- keep cron and supervisor config paths

### 7. Reassess Dream and Notebook

- disable by default
- only reintroduce/reframe if they prove useful

## Acceptance Criteria

The fork is successful when:

- the runtime still supports direct interactive agent work
- scheduled recurring agent jobs work reliably
- supervisor-style scheduled jobs can gate, execute, and evaluate
- subagents still work
- MCP remains first-class
- Obsidian MCP can serve as a normal human/agent workspace
- the codebase no longer feels centered on "personal assistant product"
- multi-channel/product clutter is materially reduced
- no major core capability is lost by over-pruning

## Non-Goals

- achieving the smallest possible codebase immediately
- deleting every unused feature upfront
- reinventing the whole runtime from scratch before learning from the fork
- forcing all persistence into one memory model
- treating external workspace and internal runtime memory as the same thing

## Immediate Next Step

Fork `athena_agent`, then do a first iteration with these concrete changes:

1. Remove/de-emphasize most channels and product-facing surfaces.
2. Keep cron, subagents, MCP, memory, sessions, skills, and core tools intact.
3. Freeze notebook and heartbeat as "under review."
4. Implement or spec `supervisor_turn` under cron.
5. Reframe docs/config around agent runtime, scheduled supervisor jobs, and MCP workspace.

After that first pass, do a second-pass spec for:

- exact tool profiles
- cron payload schema changes
- how the exploration walk should be modeled operationally
