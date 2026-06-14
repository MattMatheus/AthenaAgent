# Plan 004: Cache the tiktoken encoder instead of rebuilding it per call

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/utils/helpers.py`
> If `helpers.py` changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

`estimate_prompt_tokens()` and `estimate_message_tokens()` each call
`tiktoken.get_encoding("cl100k_base")` **on every invocation**.
`get_encoding` is not free — it loads/initializes the BPE encoder. These
functions run on hot paths: `estimate_message_tokens` is called once per message
while picking a consolidation boundary, and token estimation runs every turn to
decide compaction. Rebuilding the encoder per message turns an O(1) setup into
O(n) redundant setups per consolidation pass. Caching the encoder at module
scope (it is stateless and safe to share) removes that waste with a one-line
accessor and no behavior change to the token counts themselves.

## Current state

`athena_agent/utils/helpers.py`:

- Line 13: `import tiktoken`
- `estimate_prompt_tokens()` rebuilds the encoder at line 298:

  ```python
  297      try:
  298          enc = tiktoken.get_encoding("cl100k_base")
  299          parts: list[str] = []
  ...
  328          return len(enc.encode("\n".join(parts))) + per_message_overhead
  329      except Exception:
  330          return 0
  ```

- `estimate_message_tokens()` rebuilds it again at line 365:

  ```python
  361      payload = "\n".join(parts)
  362      if not payload:
  363          return 4
  364      try:
  365          enc = tiktoken.get_encoding("cl100k_base")
  366          return max(4, len(enc.encode(payload)) + 4)
  367      except Exception:
  368          return max(4, len(payload) // 4 + 4)
  ```

Both wrap the encoder use in `try/except` and fall back gracefully, so the cached
accessor must preserve that fallback behavior (if encoder construction fails, the
existing `except` branches handle it).

Repo convention: `helpers.py` is a stdlib-style utility module; a module-level
cached factory using `functools.lru_cache` matches its plain-function idiom. Do
not introduce a class.

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use repo `.venv/`) | exit 0 |
| Tests (utils) | `python -m pytest tests/utils/ -q` | all pass |
| Full tests | `python -m pytest tests/ -q` | all pass (≥1244) |
| Lint gate | `ruff check athena_agent --select F401,F841` | `All checks passed!` |

## Scope

**In scope** (the only files you should modify):
- `athena_agent/utils/helpers.py`
- `tests/utils/test_token_encoder_cache.py` (create)

**Out of scope** (do NOT touch):
- The token-counting *logic* (which fields are counted, the `+4` overheads, the
  per-message framing). Output counts must be byte-identical to before.
- `estimate_prompt_tokens_chain` and any provider-side token counters.
- Splitting `helpers.py` into submodules (a separate, larger refactor).

## Git workflow

- Branch: `advisor/004-cache-tiktoken-encoder`
- Commit message style (conventional commits): `perf(helpers): cache cl100k_base tiktoken encoder`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a module-level cached encoder accessor

In `athena_agent/utils/helpers.py`, add near the top (after the imports; ensure
`functools` is imported — add `import functools` if absent):

```python
@functools.lru_cache(maxsize=1)
def _get_cl100k_encoder():
    """Return a process-wide cached cl100k_base tiktoken encoder."""
    return tiktoken.get_encoding("cl100k_base")
```

Placing the `get_encoding` call inside the cached function (not at import time)
keeps the existing `try/except` fallback meaningful: if tiktoken can't build the
encoder, the call still raises inside the `try` blocks at the call sites and the
fallback runs.

**Verify**: `python -c "from athena_agent.utils import helpers; e1=helpers._get_cl100k_encoder(); e2=helpers._get_cl100k_encoder(); print(e1 is e2)"`
→ prints `True` (same cached object).

### Step 2: Use the cached accessor at both call sites

- Replace `enc = tiktoken.get_encoding("cl100k_base")` at line ~298 with
  `enc = _get_cl100k_encoder()`.
- Replace `enc = tiktoken.get_encoding("cl100k_base")` at line ~365 with
  `enc = _get_cl100k_encoder()`.

Leave the surrounding `try/except` and all counting logic untouched.

**Verify**: `grep -n 'tiktoken.get_encoding' athena_agent/utils/helpers.py`
→ returns **only** the line inside `_get_cl100k_encoder` (one match), not the two
former call sites.

### Step 3: Add a test, then full sweep

Create `tests/utils/test_token_encoder_cache.py` (see Test plan), then:

**Verify**:
- `python -m pytest tests/ -q` → all pass (≥1245)
- `ruff check athena_agent --select F401,F841` → `All checks passed!`

## Test plan

New file `tests/utils/test_token_encoder_cache.py`. Model style on an existing
small util test such as `tests/utils/test_abbreviate_path.py`. Cover:

- **Identity / caching**: `helpers._get_cl100k_encoder() is helpers._get_cl100k_encoder()`
  returns the same object.
- **Counts unchanged**: assert `estimate_message_tokens({"role":"user","content":"hello world"})`
  and `estimate_prompt_tokens([...])` return the same integers as the current
  implementation. The robust way: compute the expected value from
  `tiktoken.get_encoding("cl100k_base").encode(...)` in the test itself and assert
  equality (this pins behavior without hardcoding a magic number).
- **Fallback path still safe**: monkeypatch `helpers._get_cl100k_encoder` to raise,
  call `estimate_message_tokens` with non-empty content, and assert it returns the
  documented fallback `max(4, len(payload)//4 + 4)` (i.e. it does not propagate the
  exception). Note: clear the lru_cache (`helpers._get_cl100k_encoder.cache_clear()`)
  in any test that monkeypatches, to avoid cross-test contamination.
- Verification: `python -m pytest tests/utils/test_token_encoder_cache.py -q`
  → all pass.

## Done criteria

ALL must hold:

- [ ] `python -m pytest tests/ -q` exits 0; new cache test exists and passes
- [ ] `grep -c 'tiktoken.get_encoding' athena_agent/utils/helpers.py` returns `1`
- [ ] Token counts for representative inputs are unchanged (asserted in the test)
- [ ] `ruff check athena_agent --select F401,F841` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The call sites at `helpers.py:298` / `:365` don't match the excerpts (drift).
- A token-counting test elsewhere in the suite changes its expected value after
  your edit — that means counts shifted; they must not. Stop and report.

## Maintenance notes

- For a reviewer: confirm the only behavioral change is *when* the encoder is
  built (once, cached), not *how* counts are computed.
- `lru_cache(maxsize=1)` keeps one encoder for the process lifetime. If a second
  encoding is ever needed, parameterize the cache by encoding name rather than
  adding a second uncached call site.
- Deferred (separate, larger plan): `agent/memory.py`'s consolidation re-tokenizes
  every message each round; once this cache lands, that cost drops sharply, but
  memoizing per-message token counts on the message dict is a further optimization
  if profiling still shows it hot.
