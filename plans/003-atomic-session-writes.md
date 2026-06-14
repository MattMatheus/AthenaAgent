# Plan 003: Make session writes atomic (temp file + os.replace)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/session/manager.py`
> If `manager.py` changed since this plan was written, compare the "Current
> state" excerpt against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S-M
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

`SessionManager.save()` opens the session file with mode `"w"` (which truncates
immediately) and then writes the metadata line plus every message line in a
loop. If the process is interrupted mid-write — a crash, a `KeyboardInterrupt`,
an OOM kill, a cron job and an interactive run touching the same `session_key`,
or a disk-full error — the file is left **truncated or half-written**, losing the
entire session history (not just the new turn). Sessions are the agent's runtime
memory; corrupting one silently drops conversation continuity. The fix is the
standard atomic-write pattern: write to a temporary file in the same directory,
flush, then `os.replace()` it over the target. `os.replace` is atomic on both
POSIX and Windows, so a reader either sees the complete old file or the complete
new one — never a partial write.

## Current state

`athena_agent/session/manager.py:189-206` — the non-atomic write:

```python
189  def save(self, session: Session) -> None:
190      """Save a session to disk."""
191      path = self._get_session_path(session.key)
192
193      with open(path, "w", encoding="utf-8") as f:
194          metadata_line = {
195              "_type": "metadata",
196              "key": session.key,
197              "created_at": session.created_at.isoformat(),
198              "updated_at": session.updated_at.isoformat(),
199              "metadata": session.metadata,
200              "last_consolidated": session.last_consolidated
201          }
202          f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
203          for msg in session.messages:
204              f.write(json.dumps(msg, ensure_ascii=False) + "\n")
205
206      self._cache[session.key] = session
```

Supporting facts:

- `_get_session_path(key)` returns `self.sessions_dir / f"{safe_key}.jsonl"`
  (lines 109-112). `self.sessions_dir` is `ensure_dir(self.workspace / "sessions")`
  set in `__init__` (line 105). The temp file MUST be created in this same
  directory so `os.replace` stays on one filesystem (cross-device replace fails).
- Top-of-file imports already include `import json` and `from pathlib import Path`
  (lines 3-7). You will add `import os` (and `import tempfile` if you use it).
- The format is JSONL: first line is the metadata object, then one JSON object
  per message. Preserve this byte-for-byte so existing `load`/`list_sessions`
  (which read the metadata line first, lines ~161, ~221-224) keep working.

**Existing locking exemplar to match (for the optional Step 2)**: the cron store
uses `filelock` — `athena_agent/cron/service.py:12` (`from filelock import FileLock`)
and `:99` (`self._lock = FileLock(str(self._action_path.parent) + ".lock")`),
used as `with self._lock:` around load/merge/save (lines 175-195). `filelock` is
already a project dependency (`pyproject.toml`).

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use repo `.venv/`) | exit 0 |
| Tests (this area) | `python -m pytest tests/agent/test_session_manager_history.py -q` | all pass |
| Full tests | `python -m pytest tests/ -q` | all pass (≥1244) |
| Lint gate | `ruff check athena_agent --select F401,F841` | `All checks passed!` |

## Scope

**In scope** (the only files you should modify):
- `athena_agent/session/manager.py` (the `save()` method, plus imports)
- `tests/agent/test_session_manager_atomic_write.py` (create)

**Out of scope** (do NOT touch):
- The `Session` dataclass, `get_history`, `load`, `list_sessions`, or the
  consolidation/memory code. Only `save()` changes.
- The JSONL on-disk format — keep it identical. Readers depend on it.
- The append-based history store in `agent/memory.py` (`append_history`) — a
  different file, different plan if needed.

## Git workflow

- Branch: `advisor/003-atomic-session-writes`
- Commit message style (conventional commits): `fix(session): write sessions atomically via temp file + os.replace`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Replace the in-place write with an atomic temp-file write

Rewrite the body of `save()` so it serializes the full file content first (or
writes to a temp file handle), then atomically replaces the target. Keep the
exact JSONL output. Target shape:

```python
def save(self, session: Session) -> None:
    """Save a session to disk atomically (temp file + os.replace)."""
    path = self._get_session_path(session.key)

    metadata_line = {
        "_type": "metadata",
        "key": session.key,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata,
        "last_consolidated": session.last_consolidated,
    }
    lines = [json.dumps(metadata_line, ensure_ascii=False)]
    lines.extend(json.dumps(msg, ensure_ascii=False) for msg in session.messages)
    payload = "\n".join(lines) + "\n"

    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    self._cache[session.key] = session
```

Notes:
- The temp file is in the **same directory** as the target (via `path.with_name`),
  so `os.replace` is a same-filesystem atomic rename.
- `os.fsync` before replace guarantees the bytes are on disk before the rename;
  keep it (the cost is negligible at session-save frequency).
- The `finally` cleans up the temp file if `os.replace` failed; on success the
  temp no longer exists so `unlink` is skipped.
- Add `import os` to the imports at the top of the file.

**Verify**: `python -m pytest tests/agent/test_session_manager_history.py -q`
→ all pass (existing session round-trip tests still green).

### Step 2 (OPTIONAL — only if the operator asked for concurrency safety): add a file lock

Atomic replace already prevents *corruption* from concurrent writers (last writer
wins cleanly). A lock additionally serializes writers so one doesn't silently
overwrite another's newer state. If requested, wrap the write in a per-session
`FileLock` mirroring `cron/service.py`:

- Construct a lock path next to the session file: `str(path) + ".lock"`.
- `from filelock import FileLock` and `with FileLock(lock_path):` around the
  temp-write + replace.

If the operator did NOT ask for this, **skip Step 2** — atomicity is the
high-value, low-risk win and adding locking changes concurrency semantics.

**Verify (if done)**: `python -m pytest tests/agent/ -q` → all pass.

### Step 3: Add regression tests, then full sweep

Create `tests/agent/test_session_manager_atomic_write.py` (see Test plan), then:

**Verify**:
- `python -m pytest tests/ -q` → all pass (≥1245)
- `ruff check athena_agent --select F401,F841` → `All checks passed!`

## Test plan

New file `tests/agent/test_session_manager_atomic_write.py`. Model construction
on `tests/agent/test_session_manager_history.py` (it imports `Session`; build a
`SessionManager(workspace=tmp_path)`). Cover:

- **Round-trip**: save a session with several messages, reload it, assert
  messages and `last_consolidated` survive unchanged (format preserved).
- **No lingering temp files**: after `save()`, assert no `*.tmp` files remain in
  `manager.sessions_dir` (`list(manager.sessions_dir.glob("*.tmp")) == []`).
- **Overwrite preserves old file on failure**: monkeypatch `os.replace` to raise,
  call `save()` inside `pytest.raises`, and assert the *previously saved* file is
  still intact and fully loadable (this proves the write is non-destructive until
  the atomic swap).
- Verification: `python -m pytest tests/agent/test_session_manager_atomic_write.py -q`
  → all pass.

## Done criteria

ALL must hold:

- [ ] `python -m pytest tests/ -q` exits 0; new atomic-write tests exist and pass
- [ ] `grep -n "os.replace" athena_agent/session/manager.py` returns a match in `save()`
- [ ] `grep -n 'open(path, "w"' athena_agent/session/manager.py` no longer matches inside `save()` (the truncating in-place write is gone)
- [ ] The on-disk JSONL format is unchanged (round-trip test passes)
- [ ] `ruff check athena_agent --select F401,F841` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `save()` no longer matches the "Current state" excerpt (drift).
- Any existing session test fails after the change in a way that indicates the
  on-disk format changed (e.g. `load` can't parse the new file) — the format must
  stay identical.
- `os.replace` raises `OSError: [Errno 18] Invalid cross-device link` in tests —
  that means the temp file isn't in the same directory as the target; fix the
  temp path, do not switch to `shutil.move`.

## Maintenance notes

- For a reviewer: verify the temp file is same-dir, `os.replace` (not
  `os.rename` semantics across platforms differ — `os.replace` is the portable
  atomic one), and that `self._cache` is only updated on success.
- If session writes ever move to async, wrap the blocking write in
  `asyncio.to_thread` rather than reintroducing inline I/O on the event loop.
- Deferred: the same atomic pattern would benefit `agent/memory.py`'s
  `append_history`/`compact_history` and the cron store if they ever show
  corruption; not in scope here.
