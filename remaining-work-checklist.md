# AthenaAgent Remaining Work Checklist

This checklist captures what is still open from [fork-implementation-plan.md](/Users/foundry/AgenticDevelopment/Repos/trusted/AthenaAgent/fork-implementation-plan.md) after the major runtime fork work already completed.

## 1. Finish Heartbeat Demotion

- [x] Treat `scheduler.supervisor` as the only canonical recurring-work config.
- [x] Keep `gateway.heartbeat` load-only for compatibility, but stop mirroring new scheduler defaults back into legacy config objects.
- [x] Reduce direct runtime references to `HeartbeatService` until it is clearly just a legacy adapter.
- [ ] Decide whether `athena_agent/heartbeat/` stays for one transition period or is removed entirely.

## 2. Simplify Legacy Config Surface

- [x] Shrink the prominence of `channels`, `gateway`, and `api` in [athena_agent/config/schema.py](/Users/foundry/AgenticDevelopment/Repos/trusted/AthenaAgent/athena_agent/config/schema.py).
- [x] Keep migration compatibility for old config files, but only write back runtime-first sections by default.
- [x] Audit onboarding and status/help output for any remaining legacy config framing.

## 3. Demote Dream and Notebook Further

- [x] Decide whether Dream remains an optional subsystem or is removed from the default runtime path.
- [x] If retained, mark Dream as optional/experimental in CLI help, docs, and config wording.
- [ ] Decide whether notebook editing remains as an opt-in profile-only tool or is removed.
- [x] Trim default docs/examples so the main runtime story does not rely on Dream or notebook behavior.

## 4. Finish MCP-First Workspace Story

- [x] Add a dedicated MCP workspace guide, ideally with an Obsidian-oriented workflow.
- [x] Tighten memory docs so the three layers stay explicit:
- [x] runtime session memory
- [x] durable internal agent memory
- [x] external workspace memory through MCP

## 5. Final Test and CI Boundary Cleanup

- [ ] Prune tests that only protect retained-for-compatibility behavior once removal decisions are made.
- [ ] Revisit [.github/workflows/ci.yml](/Users/foundry/AgenticDevelopment/Repos/trusted/AthenaAgent/.github/workflows/ci.yml) so CI clearly centers runtime, scheduler, tools, providers, sessions, and MCP.
- [ ] Re-run the full suite in a Python 3.11+ environment with project dependencies installed once the local venv is fixed.

## 6. Nice-to-Have Final Cleanup

- [ ] Decide whether the internal Python package should stay `athena_agent` indefinitely for compatibility or be renamed in a later breaking change.
- [ ] Sweep remaining code comments/docstrings that still describe the old product architecture rather than the runtime-focused fork.
