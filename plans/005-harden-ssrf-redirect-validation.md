# Plan 005: Make redirect/SSRF validation fail-closed

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0587a85a..HEAD -- athena_agent/security/network.py athena_agent/agent/tools/web.py`
> If either file changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `0587a85a`, 2026-06-13

## Why this matters

The `web_fetch` tool fetches arbitrary URLs, many of which originate from
untrusted web content the agent is reading (a prime prompt-injection / SSRF
surface). SSRF protection lives in `security/network.py`. `validate_url_target`
correctly **fails closed** (blocks) when a hostname can't be resolved. But its
sibling `validate_resolved_url` — used to re-check the URL after redirects —
**fails open**: it returns "allow" when the redirect URL has no hostname and when
DNS resolution raises `gaierror`. An attacker who controls a fetched page can
redirect to a host that resolves to an internal address (e.g. cloud metadata at
`169.254.169.254`, `127.0.0.1`, RFC1918 ranges) and arrange for the
post-redirect re-resolution to fail or be hostname-less, slipping past the check.
Making `validate_resolved_url` fail-closed (consistent with
`validate_url_target`) closes the obvious bypass with a small, well-tested change.

This plan does the **fail-closed hardening only**. A deeper, separate hardening
(pin the connection to the exact validated IP to defeat DNS-rebinding TOCTOU
between validate and connect) is documented as a follow-up, not done here — it is
larger (custom httpx transport/resolver) and riskier.

## Current state

`athena_agent/security/network.py:81-110` — `validate_resolved_url`, with the two
fail-open branches marked:

```python
81  def validate_resolved_url(url: str) -> tuple[bool, str]:
82      """Validate an already-fetched URL (e.g. after redirect). Only checks the IP, skips DNS."""
83      try:
84          p = urlparse(url)
85      except Exception:
86          return True, ""                          # <-- fail-open on parse error
87
88      hostname = p.hostname
89      if not hostname:
90          return True, ""                          # <-- fail-open on missing hostname
91
92      try:
93          addr = ipaddress.ip_address(hostname)
94          if _is_private(addr):
95              return False, f"Redirect target is a private address: {addr}"
96      except ValueError:
97          # hostname is a domain name, resolve it
98          try:
99              infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
100         except socket.gaierror:
101             return True, ""                      # <-- fail-open on resolution failure
102         for info in infos:
103             try:
104                 addr = ipaddress.ip_address(info[4][0])
105             except ValueError:
106                 continue
107             if _is_private(addr):
108                 return False, f"Redirect target {hostname} resolves to private address {addr}"
109
110     return True, ""
```

For contrast, `validate_url_target` (same file, lines 46-78) already fails closed
on `gaierror` (line 67-68 returns `False, "Cannot resolve hostname: ..."`).

Callers in `athena_agent/agent/tools/web.py` (already wired, do not change the
wiring): the streamed image path (`:322-326`) and the readability path
(`:391-394`) both call `validate_resolved_url(str(r.url))` and block on `False`.
Making the function stricter automatically tightens both call sites.

Existing tests: `tests/security/test_security_network.py` already imports from
`athena_agent.security.network` and uses a `_fake_resolve` helper that returns a
`getaddrinfo` mock (see its top-of-file `_fake_resolve`). It currently imports
`configure_ssrf_whitelist, contains_internal_url, validate_url_target` — you will
add `validate_resolved_url` to that import.

## Commands you will need

| Purpose   | Command | Expected on success |
|-----------|---------|---------------------|
| Install   | `pip install -e ".[dev]"` (or use repo `.venv/`) | exit 0 |
| Tests (security) | `python -m pytest tests/security/ -q` | all pass |
| Tests (web tools) | `python -m pytest tests/tools/test_web_fetch_security.py -q` | all pass |
| Full tests | `python -m pytest tests/ -q` | all pass (≥1244) |
| Lint gate | `ruff check athena_agent --select F401,F841` | `All checks passed!` |

## Scope

**In scope** (the only files you should modify):
- `athena_agent/security/network.py` (the `validate_resolved_url` function only)
- `tests/security/test_security_network.py` (add cases)

**Out of scope** (do NOT touch):
- `validate_url_target`, `_is_private`, `_BLOCKED_NETWORKS`, `contains_internal_url`,
  or the whitelist logic — they already behave correctly.
- The `web.py` fetch wiring / redirect-following / `MAX_REDIRECTS`.
- Implementing IP-pinning / a custom httpx resolver — that is the deferred
  follow-up described in Maintenance notes, not this plan.
- The SSRF whitelist convention (`configure_ssrf_whitelist`) — honoring it is
  by-design.

## Git workflow

- Branch: `advisor/005-harden-ssrf-redirect-validation`
- Commit message style (conventional commits): `fix(security): fail closed in validate_resolved_url`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Flip the three fail-open branches to fail-closed

Edit `validate_resolved_url` in `athena_agent/security/network.py` so that:

1. URL parse failure → blocked: `return False, "Cannot parse redirect URL"`.
2. Missing hostname → blocked: `return False, "Redirect URL has no hostname"`.
3. `socket.gaierror` during resolution → blocked:
   `return False, f"Cannot resolve redirect target: {hostname}"`.

Leave the private-IP checks (lines 92-108) and the final
`return True, ""` (the allow path when all resolved IPs are public) exactly as
they are. Target shape for the three branches:

```python
    try:
        p = urlparse(url)
    except Exception:
        return False, "Cannot parse redirect URL"

    hostname = p.hostname
    if not hostname:
        return False, "Redirect URL has no hostname"
    ...
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            return False, f"Cannot resolve redirect target: {hostname}"
```

**Verify**: `python -m pytest tests/security/ tests/tools/test_web_fetch_security.py -q`
→ all pass. (If an existing test asserted the old fail-open behavior, see STOP
conditions — do not weaken your fix to satisfy it; report instead.)

### Step 2: Add regression tests for the fail-closed branches

In `tests/security/test_security_network.py`:
- Add `validate_resolved_url` to the existing import from
  `athena_agent.security.network`.
- Add tests (reuse the `_fake_resolve` mock pattern already in the file, patching
  `socket.getaddrinfo`):
  - redirect URL with no hostname (e.g. `"http:///path"`) → `ok is False`.
  - redirect host that raises `gaierror` → `ok is False`.
  - redirect host resolving to a private IP (e.g. `169.254.169.254`) → `ok is False`.
  - redirect host resolving to a public IP (e.g. `93.184.216.34`) → `ok is True`.
  - a literal private IP as the hostname (e.g. `"http://127.0.0.1/"`) → `ok is False`.

**Verify**: `python -m pytest tests/security/test_security_network.py -q`
→ all pass including the new cases.

### Step 3: Full sweep

**Verify**:
- `python -m pytest tests/ -q` → all pass
- `ruff check athena_agent --select F401,F841` → `All checks passed!`

## Test plan

- New cases in `tests/security/test_security_network.py` (pattern source: the
  same file's existing `validate_url_target` tests and `_fake_resolve` helper).
- Cover all three flipped branches (parse fail, missing host, gaierror) plus the
  private-IP-after-redirect block and the public-IP allow (to prove the change
  didn't make it block everything).
- Verification: `python -m pytest tests/security/ -q` → all pass.

## Done criteria

ALL must hold:

- [ ] `python -m pytest tests/ -q` exits 0; new fail-closed tests exist and pass
- [ ] `grep -n "return True" athena_agent/security/network.py` shows the ONLY
      `True` return in `validate_resolved_url` is the final all-public-IP allow
      (the three early fail-open `return True, ""` lines are gone)
- [ ] A redirect to a private/internal address or an unresolvable/hostname-less
      target is blocked (asserted by tests)
- [ ] `ruff check athena_agent --select F401,F841` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `validate_resolved_url` doesn't match the "Current state" excerpt (drift).
- An existing test asserts the OLD fail-open behavior (e.g. expects an
  unresolvable redirect to be allowed). Do NOT weaken the fix to pass it — report
  the conflict so a human can confirm the security change is intended.
- Flipping `gaierror` to fail-closed breaks a large number of unrelated
  web-fetch tests because they rely on hosts that don't resolve in the test env —
  report; the tests may need a `getaddrinfo` mock rather than the fix being wrong.

## Maintenance notes

- For a reviewer: confirm `validate_resolved_url` now mirrors
  `validate_url_target`'s fail-closed posture; the two should be consistent.
- **Deferred follow-up (separate plan, larger/riskier)**: this change still has a
  validate-then-reconnect TOCTOU window — `validate_url_target` resolves DNS, then
  httpx independently re-resolves and connects, so a rebinding host can return a
  public IP at validation time and a private IP at connect time. The robust fix is
  to resolve once, validate the IP, and pin httpx to connect to that exact IP
  (custom transport/resolver, with the original Host header preserved for TLS/SNI).
  Scope that separately; it touches `web.py`'s client construction and needs
  careful TLS handling.
- The blocklist in `_BLOCKED_NETWORKS` covers IPv4/IPv6 private + metadata ranges;
  keep it in sync if new cloud metadata ranges appear.
