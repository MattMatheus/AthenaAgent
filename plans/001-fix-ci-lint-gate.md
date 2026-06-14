# Plan 001: Green the CI lint gate by removing three unused imports

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/cli/commands.py athena_agent/cron/runtime.py athena_agent/cron/supervisor.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

CI (`.github/workflows/ci.yml`) runs `ruff check athena_agent --select F401,F841`
as a hard gate before the test job. Three unused imports currently fail that
gate, so **CI is red on `main`**: every push/PR is blocked at lint, and a
"verify before push" workflow can't get a green signal. Removing three import
lines restores the gate with zero behavior change.

## Current state

The CI lint command and its three failures (confirmed by running
`ruff check athena_agent --select F401,F841`, output: "Found 3 errors"):

- `athena_agent/cli/commands.py:23` — module-level `from loguru import logger`
  is unused. The functions that need `logger` re-import it locally:

  ```python
  20              pass
  21
  22  import typer
  23  from loguru import logger          # <-- unused at module scope
  24  from prompt_toolkit import PromptSession, print_formatted_text
  ```

  The only real uses are a **function-local** re-import at line 540 and its uses
  at lines 562/564:

  ```python
  540      from loguru import logger     # local import — the real one in use
  ...
  562          logger.enable("athena_agent")
  564          logger.disable("athena_agent")
  ```

  So deleting line 23 is safe — `logger` is still defined where it is used.

- `athena_agent/cron/runtime.py:5` — `Any` imported but never used:

  ```python
  5  from typing import TYPE_CHECKING, Any
  ```

- `athena_agent/cron/supervisor.py:7` — `Any` imported but never used:

  ```python
  7  from typing import TYPE_CHECKING, Any, Awaitable, Callable
  ```

`ruff --diff` (preview only, do NOT apply blindly — make the edits yourself per
the Steps) confirms exactly these three removals and nothing else.

Repo convention: ruff is the only linter; config lives in `pyproject.toml`
under `[tool.ruff]` (line-length 100, `select = ["E","F","I","N","W"]`,
`ignore = ["E501"]`). The CI gate narrows to `F401,F841` only.

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use the repo's existing `.venv`: `.venv/bin/python`, `.venv/bin/ruff`) | exit 0 |
| Lint (CI gate) | `ruff check athena_agent --select F401,F841` | `All checks passed!`, exit 0 |
| Tests     | `python -m pytest tests/ -q` | `1244 passed` (or more), exit 0 |

(If a `.venv/` exists at repo root, prefer `.venv/bin/ruff` and
`.venv/bin/python -m pytest` — dev deps are already installed there.)

## Scope

**In scope** (the only files you should modify):
- `athena_agent/cli/commands.py`
- `athena_agent/cron/runtime.py`
- `athena_agent/cron/supervisor.py`

**Out of scope** (do NOT touch):
- Any other ruff finding. `ruff check athena_agent` (full config) reports ~43
  issues; the CI gate is only `F401,F841`. Do not run `--fix` across the repo
  or touch E/W/I/N findings — that widens the diff and risks unrelated change.
- The function-local `from loguru import logger` at `commands.py:540` — keep it.

## Git workflow

- Branch: `advisor/001-fix-ci-lint-gate`
- One commit. Message style follows the repo's conventional-commit log
  (e.g. `chore: remove unused imports to fix ruff F401 CI gate`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Remove the unused module-level logger import

In `athena_agent/cli/commands.py`, delete line 23 (`from loguru import logger`).
Do not touch the local import at line ~540.

**Verify**: `ruff check athena_agent/cli/commands.py --select F401,F841` → `All checks passed!`

### Step 2: Remove unused `Any` from cron/runtime.py

In `athena_agent/cron/runtime.py:5`, change
`from typing import TYPE_CHECKING, Any` to `from typing import TYPE_CHECKING`.

**Verify**: `ruff check athena_agent/cron/runtime.py --select F401,F841` → `All checks passed!`

### Step 3: Remove unused `Any` from cron/supervisor.py

In `athena_agent/cron/supervisor.py:7`, change
`from typing import TYPE_CHECKING, Any, Awaitable, Callable` to
`from typing import TYPE_CHECKING, Awaitable, Callable`.

**Verify**: `ruff check athena_agent/cron/supervisor.py --select F401,F841` → `All checks passed!`

### Step 4: Full gate + test sweep

**Verify**:
- `ruff check athena_agent --select F401,F841` → `All checks passed!`
- `python -m pytest tests/ -q` → all pass (≥1244)

## Test plan

No new tests — this is a pure lint fix with no behavior change. The existing
suite is the regression guard: it must remain green (≥1244 passed). The lint
gate itself is the acceptance check.

## Done criteria

ALL must hold:

- [ ] `ruff check athena_agent --select F401,F841` exits 0 (`All checks passed!`)
- [ ] `python -m pytest tests/ -q` exits 0, all tests pass
- [ ] `git diff --stat` shows exactly 3 files changed, 3 deletions/edits, no additions of new logic
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at lines `commands.py:23`, `cron/runtime.py:5`, `cron/supervisor.py:7`
  doesn't match the excerpts above (drift since this plan was written).
- After removing `commands.py:23`, `ruff` reports `logger` as **undefined**
  (F821) anywhere — that means a use of the module-level import exists that this
  plan didn't account for. Stop and report.
- Removing an `Any` import causes a test or import error (it should not — both
  are genuinely unused).

## Maintenance notes

- For a reviewer: confirm the diff is only import removals; no logic touched.
- Follow-up (explicitly out of scope): the full `ruff check athena_agent` reports
  ~43 E/W/I/N issues. If the team wants the broader gate, that is a separate,
  larger plan (decide whether to widen the CI `--select` list and clean up).
