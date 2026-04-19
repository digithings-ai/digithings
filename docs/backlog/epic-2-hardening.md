# Epic #2 — Hardening (cold review) child-task breakdown

## Purpose

Epic [#2](https://github.com/digithings-ai/digithings/issues/2) is a Phase 2
production-readiness cold review of the entire monorepo after a stretch of
active feature development. Scope covers secrets handling, auth-path rate
limiting, CORS tightening, input validation at every HTTP trust boundary, a
dependency/CVE audit, sensible `httpx` timeout defaults, health-probe vs
status-endpoint separation, and documented threat-model coverage — all held to
the PR scoring gate (see [docs/scoring/](../scoring/README.md): Security ≥ 8,
Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9). The output is a set of small,
individually-mergeable PRs that close the residual gaps identified after the
platform-level controls already landed.

## Completed preconditions

Already in place and out of scope for this epic:

- **DigiKey RS256 JWTs + JWKS** protect DigiGraph, DigiQuant, and DigiSearch on
  non-exempt routes (see [SECURITY.md](../../SECURITY.md) §"Non-negotiable
  defaults" item 2). No legacy static `DIGI_API_KEY` fallback.
- **Scoped API keys** issued via DigiKey, with tenant-scope enforcement at the
  key layer.
- **Audit redaction** — every `audit.jsonl` writer routes through
  `digibase.audit.redact_mapping`; prompts, JWTs, API keys, and document bodies
  are stripped before persistence.
- **Claude Code guardrails** — `scripts/claude-hooks/` PreToolUse hooks block
  writes outside the repo root, pushes to non-origin remotes, and edits to
  protected paths off a `task-N-*` branch (see [AGENTS.md](../../AGENTS.md)).
- **Pre-push hook** — `scripts/hooks/pre-push.sh` (installed by
  `make hooks-install`) blocks non-origin pushes, `main` pushes without
  `ALLOW_MAIN_PUSH=1`, and live-trading-path pushes without a
  `Human-Approved-By:` trailer.
- **Loopback binding** — every Compose service binds `127.0.0.1` by default.

## Remaining sub-tasks

Each item below is sized for a single PR under ~120 lines of diff.

- [x] **Secrets-scan CI config.** Add a `gitleaks` (or `trufflehog`) GitHub
  Actions job running on every PR + on `develop` pushes. Ship a baseline
  allowlist for known fixtures under `tests/`. Fail the job on any new finding.
  — PR #68.
- [x] **Rate-limit middleware on auth paths.** Apply a per-IP token-bucket
  limiter to DigiKey's key-issuance and JWT-mint endpoints, and to DigiGraph's
  authenticated entry points. Default limits configurable via env; document in
  [SECURITY.md](../../SECURITY.md). — PR #70.
- [x] **CORS allowlist audit.** Enumerate every FastAPI app's CORS config
  (DigiGraph, DigiSearch, DigiQuant, DigiKey, DigiSmith, DigiChat BFF). Replace
  any `*` origin with an explicit allowlist driven by env. Add a unit test per
  service asserting disallowed origins are rejected. — PR #74.
- [x] **Pydantic v2 input validation at HTTP boundaries.** Sweep every
  `@app.post` / `@app.get` handler for untyped `dict` bodies or query params;
  replace with a Pydantic v2 model. Covers DigiGraph `/workflow`, DigiSearch
  query/ingest, DigiQuant backtest, and the DigiChat BFF proxy routes. — PR #72.
- [x] **Dependency-audit CI (`pip-audit`).** Add a scheduled + PR-triggered
  `pip-audit` job against each component's lockfile. Fail on `HIGH`/`CRITICAL`;
  warn on `MEDIUM`. Include Node audit for `digichat/` (`npm audit --omit=dev`).
  — PR #67.
- [x] **`httpx` timeout defaults.** Centralize an `httpx.Timeout(connect=5,
  read=30, write=10, pool=5)` helper in `digibase`; replace bare
  `httpx.AsyncClient()` constructions across components. Guarantees no
  unbounded hangs on upstream LLM or broker calls. — PR #73.
- [x] **`/healthz` vs `/v1/status` separation.** Carve a minimal
  auth-exempt `/healthz` returning `{"ok": true}` for liveness probes on every
  service; keep `/v1/status` (DigiSmith) for richer, still-secret-free
  diagnostics. Document the contract so load balancers stop pinging `/v1/status`.
  — PR #75.
- [x] **Documented threat model.** Expand [SECURITY.md](../../SECURITY.md)
  "Threat model" section into a STRIDE-style table — actor, asset, threat,
  mitigation, residual risk — cross-linked from [AGENTS.md](../../AGENTS.md)
  and the [security scoring rubric](../scoring/SECURITY.md). — PR #76.

All eight child tasks merged 2026-04-18 via PRs #67, #68, #70, #72, #73, #74,
#75, #76. Epic #2 closed.

> **Follow-up (tracked separately):** gitleaks full-history scan on develop
> reports 3 pre-existing leaks in the 77-commit history. Not introduced by this
> epic; needs its own remediation issue (baseline allowlist or history scrub).
