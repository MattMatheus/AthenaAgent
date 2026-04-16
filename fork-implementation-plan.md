# AthenaAgent Fork Implementation Plan

This plan translates [spec.md](/Users/foundry/AgenticDevelopment/Repos/trusted/AthenaAgent/spec.md) into concrete implementation work against the current fork state.

## Objectives

- Preserve the runtime core inherited from athena_agent.
- Remove product-oriented surfaces that are not part of the runtime mission.
- Reframe the project as a CLI-first agent runtime with cron, MCP, subagents, and workspace-centric operation.
- Replace broad implicit defaults with profile-driven configuration.
- Merge heartbeat behavior into cron via a supervisor job model.

## Current-State Summary

The current fork still looks like the upstream personal-assistant product:

- branding and metadata still say `athena_agent` / personal assistant
- CLI help and onboarding are product-oriented
- tool registration is hardcoded in the agent loop
- heartbeat and cron exist as separate recurring systems
- API, websocket bridge, and many chat channels are still present
- config and dependencies still reflect a broad consumer/messaging product surface

## Keep, Remove, Review

### Keep as core

- `athena_agent/agent/context.py`
- `athena_agent/agent/hook.py`
- `athena_agent/agent/loop.py`
- `athena_agent/agent/memory.py`
- `athena_agent/agent/runner.py`
- `athena_agent/agent/skills.py`
- `athena_agent/agent/subagent.py`
- `athena_agent/agent/tools/base.py`
- `athena_agent/agent/tools/cron.py`
- `athena_agent/agent/tools/filesystem.py`
- `athena_agent/agent/tools/mcp.py`
- `athena_agent/agent/tools/registry.py`
- `athena_agent/agent/tools/schema.py`
- `athena_agent/agent/tools/search.py`
- `athena_agent/agent/tools/shell.py`
- `athena_agent/agent/tools/spawn.py`
- `athena_agent/agent/tools/web.py`
- `athena_agent/config/`
- `athena_agent/cron/`
- `athena_agent/providers/`
- `athena_agent/session/manager.py`
- `athena_agent/utils/evaluator.py`
- `athena_agent/utils/gitstore.py`
- `athena_agent/utils/helpers.py`
- `athena_agent/utils/prompt_templates.py`
- `athena_agent/athena_agent.py`
- core tests for agent, tools, providers, config, cron, session, and MCP

### Remove or disable early

- `athena_agent/api/`
- `bridge/`
- most of `athena_agent/channels/`
- product/demo-oriented docs and templates
- broad channel test suite in `tests/channels/`
- websocket/API tests that only support removed product surfaces

### Freeze or review

- `athena_agent/heartbeat/`
- `athena_agent/agent/tools/notebook.py`
- Dream-related flows in `athena_agent/agent/memory.py`
- onboarding wizard paths in `athena_agent/cli/onboard.py`

## Phased Plan

## Phase 1: Rebrand and Reposition

Goal: change the project identity from personal assistant product to agent runtime.

Files to update:

- `README.md`
- `pyproject.toml`
- `athena_agent/cli/commands.py`
- `athena_agent/athena_agent.py`
- `athena_agent/__init__.py`
- `COMMUNICATION.md`
- `docs/`
- `athena_agent/templates/`

Tasks:

- rename user-facing project description to AthenaAgent or neutral runtime naming
- remove personal-assistant language from README, CLI help, and package metadata
- rewrite docs around agent runtime, MCP workspace, cron, and CLI operation
- remove consumer/community/chat-app centric marketing sections from README
- update examples so they show task execution and scheduled runtime usage

Deliverables:

- repo reads as an agent runtime, not a lifestyle assistant
- package metadata no longer advertises personal assistant framing
- CLI help text describes runtime/operator usage

Acceptance criteria:

- a new visitor can identify CLI, cron, MCP, and agent runtime as the core product
- no top-level docs describe the product primarily as a personal assistant

## Phase 2: De-productize Surfaces Without Touching Core Runtime

Goal: remove obvious product sprawl while keeping runtime internals intact.

Files and areas affected:

- `athena_agent/api/`
- `bridge/`
- `athena_agent/channels/`
- `tests/channels/`
- `tests/test_api_attachment.py`
- `docs/WEBSOCKET.md`
- channel/setup references in `README.md` and CLI docs
- dependency lists in `pyproject.toml`

Tasks:

- remove API server surface unless a runtime-facing reason to keep it appears
- remove websocket bridge and WhatsApp bridge packaging
- remove non-core chat channels first: email, slack, discord, feishu, qq, matrix, websocket, wecom, weixin, mochat, dingtalk
- keep Telegram only if deliberately retained as a thin optional surface; otherwise remove for first pass
- delete channel-specific docs and channel-specific tests
- trim dependencies that only exist for removed channel surfaces

Deliverables:

- significantly smaller non-runtime surface area
- leaner dependency set
- reduced test matrix focused on runtime behavior

Acceptance criteria:

- the repo can be understood without learning a chat-platform matrix
- removed surfaces are absent from docs, config defaults, and packaging

## Phase 3: Introduce Tool Profiles

Goal: replace hardcoded broad tool registration with config-driven profiles.

Primary files:

- `athena_agent/agent/loop.py`
- `athena_agent/agent/tools/registry.py`
- `athena_agent/config/schema.py`
- `athena_agent/config/loader.py`
- `tests/tools/test_tool_registry.py`
- new tests for profile-driven registration

Tasks:

- refactor `_register_default_tools()` into profile-aware registration
- define built-in profiles:
  - `core`
  - `research`
  - `orchestrator`
  - `scheduled`
  - `mcp_first`
- make notebook, spawn, web, cron, and MCP tools opt-in by profile
- ensure subagents can receive explicit tool profiles
- keep safe defaults for filesystem and shell restrictions

Suggested initial profile mapping:

- `core`: read/write/edit/list/glob/grep/exec
- `research`: `core` + web search/fetch
- `orchestrator`: `core` + spawn
- `scheduled`: `core` + cron + optional spawn
- `mcp_first`: `core` + MCP + optional web

Deliverables:

- tool registration behavior is explicit and inspectable
- agent modes can choose appropriate tool exposure

Acceptance criteria:

- default runtime no longer registers every tool implicitly
- config can select a profile for interactive and scheduled runs

## Phase 4: Simplify Config Around Runtime Concerns

Goal: make config reflect the forked product shape instead of the upstream product matrix.

Primary files:

- `athena_agent/config/schema.py`
- `athena_agent/config/loader.py`
- `athena_agent/config/paths.py`
- `athena_agent/cli/onboard.py`
- `athena_agent/cli/commands.py`
- `tests/config/`

Tasks:

- reduce channel-heavy and gateway-heavy config prominence
- add runtime-oriented config sections:
  - runtime
  - agent defaults
  - tool profiles
  - providers
  - MCP servers
  - scheduler
  - optional surfaces
- deprecate dedicated heartbeat config
- reduce default provider complexity while preserving abstraction
- keep strong migration logic so existing configs do not break abruptly
- simplify onboarding or replace it with a smaller runtime bootstrap flow

Deliverables:

- cleaner config schema aligned with the spec
- fewer defaults that imply multi-channel consumer usage

Acceptance criteria:

- a default config is understandable as an operator/developer runtime config
- heartbeat is no longer presented as a separate primary subsystem

## Phase 5: Merge Heartbeat Into Cron

Goal: make cron the only recurring execution subsystem.

Primary files:

- `athena_agent/cron/types.py`
- `athena_agent/cron/service.py`
- `athena_agent/heartbeat/service.py`
- `athena_agent/agent/tools/cron.py`
- `athena_agent/agent/loop.py`
- `athena_agent/utils/evaluator.py`
- `tests/cron/`
- `tests/agent/test_heartbeat_service.py`

Tasks:

- extend cron payloads beyond `agent_turn`
- add `supervisor_turn` payload support
- model supervisor jobs with fields such as:
  - `source_kind`
  - `source_ref`
  - `decision_mode`
  - `decision_prompt`
  - `execution_prompt`
  - `notify_policy`
  - `session_key`
  - `keep_recent_messages`
  - `deliver_target`
- preserve useful heartbeat patterns:
  - phase-1 triage
  - phase-2 full execution
  - post-run evaluation
  - stable recurring session context
  - bounded retained history
- migrate notification gating onto cron supervisor runs
- deprecate heartbeat service, then remove it after parity is proven

Deliverables:

- one recurring execution model
- richer cron jobs supporting agent and supervisor behavior

Acceptance criteria:

- scheduled supervisor jobs can skip, run, evaluate, and persist run history
- heartbeat is unnecessary as a separate subsystem

## Phase 6: MCP-First Workspace Integration

Goal: make MCP, especially Obsidian MCP, a normal operating surface.

Primary files:

- `athena_agent/agent/tools/mcp.py`
- `athena_agent/agent/context.py`
- `athena_agent/agent/memory.py`
- `README.md`
- `docs/MEMORY.md`
- new MCP/Obsidian docs if needed

Tasks:

- ensure MCP remains available as a core capability
- document Obsidian MCP as the preferred external workspace pattern
- clarify the three memory layers:
  - runtime session memory
  - durable agent memory
  - external workspace memory
- update examples and prompts so durable, human-facing artifacts can live in Obsidian

Deliverables:

- MCP is treated as core, not add-on
- memory and workspace docs reflect internal vs external persistence clearly

Acceptance criteria:

- docs show MCP as a standard path for workspace interaction
- the runtime story does not depend on internal notebook/document systems

## Phase 7: Demote Notebook and Dream

Goal: keep optionality without treating non-core subsystems as default behavior.

Primary files:

- `athena_agent/agent/tools/notebook.py`
- `athena_agent/agent/loop.py`
- `athena_agent/agent/memory.py`
- `README.md`
- config defaults and tests touching notebook or Dream

Tasks:

- disable notebook tool by default
- remove notebook from default docs and examples
- move Dream out of the main product narrative
- keep code only if low-cost, stable, and clearly optional
- mark both subsystems as under review until justified by runtime use cases

Deliverables:

- cleaner runtime defaults
- less conceptual clutter around non-core features

Acceptance criteria:

- default runtime path does not depend on notebook or Dream
- docs present them as optional or experimental if retained

## Phase 8: Rebuild the Test and Dependency Boundary

Goal: make the repository validate the forked runtime, not the original product breadth.

Primary files:

- `pyproject.toml`
- `tests/agent/`
- `tests/cron/`
- `tests/tools/`
- `tests/providers/`
- `tests/config/`
- CI config in `.github/workflows/ci.yml`

Tasks:

- remove tests for deleted channels and deleted API/websocket behavior
- add tests for:
  - tool-profile registration
  - supervisor cron payload execution
  - heartbeat-to-cron migration behavior
  - MCP-first workflows where practical
- trim optional dependencies and CI setup to match the new runtime surface

Deliverables:

- a smaller, more relevant test suite
- CI aligned with the fork’s mission

Acceptance criteria:

- CI primarily validates runtime, scheduling, tools, providers, sessions, and MCP
- removed product surfaces are not represented in CI or dependency defaults

## Recommended Execution Order

1. Phase 1: rebrand and docs reset
2. Phase 2: remove channels, API, bridge, and related tests/dependencies
3. Phase 3: implement tool profiles
4. Phase 4: simplify config and onboarding
5. Phase 5: merge heartbeat into cron
6. Phase 6: finalize MCP-first docs and workspace flows
7. Phase 7: demote notebook and Dream
8. Phase 8: clean CI, dependencies, and remaining tests

## Dependency Notes

- Phase 2 should come before major config cleanup so removed surfaces do not keep shaping schema decisions.
- Phase 3 is the architectural prerequisite for clean runtime modes.
- Phase 5 should wait until config and tool exposure are clearer, because supervisor jobs need explicit runtime/tool behavior.
- Phase 8 should be continuous, but the final cleanup belongs after the runtime boundary stabilizes.

## Risks and Mitigations

### Risk: Tool profile refactor destabilizes agent behavior

Mitigation:

- preserve a compatibility profile during migration
- add regression tests before deleting broad registration logic

### Risk: Heartbeat removal drops useful recurring behavior

Mitigation:

- implement `supervisor_turn` first
- port heartbeat semantics into cron before deleting service code

### Risk: Channel removal leaves dead references across config/docs/tests

Mitigation:

- remove by vertical slices: code, tests, docs, dependencies, config references
- use search-driven cleanup passes after each deleted surface

### Risk: Config migration becomes noisy

Mitigation:

- keep migration adapters in place for at least one transition period
- deprecate first, delete second

## First Concrete Milestone

The first milestone should include:

- rebranded README and package metadata
- removal of API/bridge/most channels
- docs reframed around CLI runtime, MCP, cron, and subagents
- notebook and heartbeat marked under review, not core

This gives the fork a new identity quickly without risking the runtime core too early.

## Second Concrete Milestone

The second milestone should include:

- profile-driven tool registration
- config simplification
- supervisor cron payload design and implementation
- heartbeat deprecation path

This is the point where the fork stops merely looking different and starts operating according to the new architecture.

## Definition of Success

The fork is successful when:

- direct interactive agent work still functions reliably
- scheduled recurring jobs work reliably
- supervisor-style cron jobs can gate, execute, and evaluate
- subagents still work
- MCP remains a first-class capability
- Obsidian MCP fits naturally as a human/agent workspace
- the repo no longer feels centered on personal assistant or chat-platform product goals
- core capability is preserved while product clutter is materially reduced
