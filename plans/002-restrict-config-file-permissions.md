# Plan 002: Write the config file with owner-only permissions (0600)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/config/loader.py`
> If `loader.py` changed since this plan was written, compare the "Current
> state" excerpt against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

`save_config()` writes `~/.athena-agent/config.json` with no explicit file mode,
so the file is created under the process umask — typically `0644`
(world-readable) on Unix. That file holds **plaintext provider API keys and
OAuth tokens** (the `providers` section, plus search-provider keys like Brave/
Tavily/Kagi/Jina). On any multi-user host, every local user can read those
credentials. The fix is to create the file (and its parent directory) with
owner-only permissions. Because any credential already written to a
world-readable file should be considered exposed, the remediation also includes
**rotating** keys that were stored before this fix.

> **Security handling rule for the executor**: never print, echo, log, or paste
> the *contents* of `config.json` or any credential value into commits, test
> fixtures, comments, or your report. Refer to credentials by location and type
> only (e.g. "the provider api_key field"). Tests in this plan use dummy values
> you invent, never a real key.

## Current state

`athena_agent/config/loader.py:64-78` — the only config writer. No `os.chmod`,
and `mkdir` sets no mode:

```python
64  def save_config(config: Config, config_path: Path | None = None) -> None:
...
72      path = config_path or get_config_path()
73      path.parent.mkdir(parents=True, exist_ok=True)
74
75      data = config.model_dump(mode="json", by_alias=True)
76
77      with open(path, "w", encoding="utf-8") as f:
78          json.dump(data, f, indent=2, ensure_ascii=False)
```

- `get_config_path()` (same file, lines 23-27) defaults to
  `Path.home() / ".athena-agent" / "config.json"`.
- `save_config` is the single chokepoint: onboarding and config-edit flows all
  route writes through it, so fixing it here covers every writer.
- Imports already present at top of file: `import json`, `import os`,
  `from pathlib import Path` (line 4 is `import os` — confirm it is imported;
  it is used by `_env_replace`).

Repo convention: standard-library only for this kind of utility; no helper
wrapper exists for secure file writes, so inline `os.chmod` is appropriate and
matches the file's existing direct-`open`/`mkdir` style.

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use repo `.venv/`) | exit 0 |
| Tests (this area) | `python -m pytest tests/config/ -q` | all pass |
| Full tests | `python -m pytest tests/ -q` | all pass (≥1244) |
| Lint gate | `ruff check athena_agent --select F401,F841` | `All checks passed!` |

## Scope

**In scope** (the only files you should modify):
- `athena_agent/config/loader.py`
- `tests/config/test_config_loader_permissions.py` (create)

**Out of scope** (do NOT touch):
- The config schema (`athena_agent/config/schema.py`) and migration logic.
- Session/data directory permissions under the workspace — a real but separate
  concern; note it in Maintenance notes, do not fix it here.
- Any change to *what* is stored in config (do not start moving secrets to a
  keyring/env — that is a larger design change, out of scope).

## Git workflow

- Branch: `advisor/002-restrict-config-file-permissions`
- Commit message style (conventional commits, matching the repo log):
  `fix(config): write config.json with 0600 permissions`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Restrict the parent directory and the file mode in `save_config`

Edit `save_config()` in `athena_agent/config/loader.py` so that:

1. The parent directory is created/tightened to `0700` (owner-only). Use a
   try/except around the chmod so a pre-existing dir with other contents doesn't
   hard-fail on platforms where chmod is a no-op.
2. The file is chmod'd to `0600` immediately after writing.

Target shape (adapt to surrounding style; keep `os` imported):

```python
def save_config(config: Config, config_path: Path | None = None) -> None:
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass  # best-effort on platforms without POSIX perms

    data = config.model_dump(mode="json", by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort (e.g. Windows)
```

Rationale for best-effort `try/except`: `os.chmod` has limited/odd semantics on
Windows; failing the whole save because perms couldn't be set would be a
regression. On POSIX it works and is the security win.

**Verify**: `python -m pytest tests/config/ -q` → all pass (existing config
tests still green after the edit).

### Step 2: Add a regression test for the file mode

Create `tests/config/test_config_loader_permissions.py`. Model its structure on
the existing config tests (e.g. `tests/config/test_config_paths.py` for how they
build a `Config` and a `tmp_path` config file). The test must:

- Skip on non-POSIX (`@pytest.mark.skipif(os.name == "nt", reason="POSIX perms")`).
- Call `save_config(Config(), config_path=tmp_path / "config.json")`.
- Assert the file mode is `0o600`:
  `assert stat.S_IMODE((tmp_path / "config.json").stat().st_mode) == 0o600`.
- Assert the parent dir mode is `0o700` when `save_config` created it.

Use a freshly-constructed `Config()` (or one with a dummy/fake api_key string you
invent) — never a real credential.

**Verify**: `python -m pytest tests/config/test_config_loader_permissions.py -q`
→ test(s) pass on this (POSIX) host.

### Step 3: Full sweep

**Verify**:
- `python -m pytest tests/ -q` → all pass (≥1245 now)
- `ruff check athena_agent --select F401,F841` → `All checks passed!`

## Test plan

- New file `tests/config/test_config_loader_permissions.py`:
  - happy path: file written → mode is `0o600`.
  - parent dir created by `save_config` → mode is `0o700`.
  - (optional) overwriting an existing config keeps `0o600`.
- Pattern source: `tests/config/test_config_paths.py` (Config construction +
  `tmp_path` usage).
- Verification: `python -m pytest tests/config/ -q` → all pass including the new
  test(s).

## Done criteria

ALL must hold:

- [ ] `python -m pytest tests/ -q` exits 0; the new permissions test exists and passes
- [ ] `grep -n "os.chmod" athena_agent/config/loader.py` shows the file gets `0o600` and the dir `0o700`
- [ ] `ruff check athena_agent --select F401,F841` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] The commit/PR text recommends **rotating** any provider/search API keys
      that were previously saved to a world-readable config (documented, not done
      by the executor)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `save_config` no longer matches the "Current state" excerpt (drift).
- You discover an additional config writer that bypasses `save_config` (search:
  `grep -rn "config.json\|model_dump" athena_agent/ | grep -i write`) — if a
  second writer exists, the perms fix must cover it too; report before expanding
  scope.
- The chmod approach breaks an existing test in a way a best-effort `try/except`
  doesn't resolve.

## Maintenance notes

- For a reviewer: confirm the chmod runs *after* the write (a chmod before the
  open is undone by the create), and that the `try/except` doesn't mask a real
  POSIX failure (it only guards `OSError`, which is the cross-platform concern).
- Deferred (separate plan if wanted): apply the same owner-only treatment to the
  workspace `sessions/` directory and any other on-disk store that may contain
  conversation data or tokens. `config/paths.py` is the place to start.
- Credential rotation is an operational follow-up the maintainer must perform for
  any environment where a config was written before this fix landed.
