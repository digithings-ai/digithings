## Linked issue

<!--
Every PR must trace to a backlog issue on the Project board.
Either use a branch named  task/<N>-<slug>  (created by `make task ISSUE=N`),
or add a line below like:  Fixes #123   (also accepts Closes / Resolves).
CI check: .github/workflows/pr-linkage.yml
-->

Fixes #

---

## Component

<!-- Check all that apply -->
- [ ] digigraph
- [ ] digiquant
- [ ] digisearch
- [ ] digismith
- [ ] digiclaw
- [ ] digibase
- [ ] digikey
- [ ] digichat
- [ ] website / root docs
- [ ] config / infra

## Change Type

- [ ] feat — new capability
- [ ] fix — bug fix
- [ ] refactor — restructure without behavior change
- [ ] docs — documentation only
- [ ] test — tests only
- [ ] chore — build, CI, deps

## Summary

<!-- 2–4 sentences: what changed and why -->

---

## Self-Score Checklist

Agents: score honestly using `docs/scoring/`. Do not check a box unless you fully satisfy the criterion. Leave unchecked criteria with a note if they are N/A.

### Security (target ≥ 8/10) — [`docs/scoring/SECURITY.md`](docs/scoring/SECURITY.md)
- [ ] 1. No secrets in code (no API keys, tokens, PEM strings)
- [ ] 2. No PII in spans or audit logs (no raw prompts, bearer tokens, full doc bodies)
- [ ] 3. Input validation at system boundaries (Pydantic models on all HTTP/MCP/CLI inputs)
- [ ] 4. No injection vectors (no `eval`, `exec`, f-string SQL, unguarded `subprocess`)
- [ ] 5. Scope-checked auth (new routes use `digikey.integrations.service_middleware`)
- [ ] 6. Fail-closed on missing auth config (returns 503, not 200)
- [ ] 7. No new loopback exceptions (no `0.0.0.0` bind without SECURITY.md approval)
- [ ] 8. No live-trading path touched without human gate ← **triggers human review if checked**
- [ ] 9. Least-privilege secret access (new secrets in `.env.example` with comments)
- [ ] 10. No debug back-doors in production paths

**Security score: __ / 10**

---

### Quality (target ≥ 8/10) — [`docs/scoring/QUALITY.md`](docs/scoring/QUALITY.md)
- [ ] 1. Pydantic v2 everywhere (no v1 `@validator`, no bare `dict` return on public APIs)
- [ ] 2. Polars only — no pandas
- [ ] 3. Strict typing — no untyped `Any` without inline justification
- [ ] 4. Ruff clean (`ruff check . && ruff format --check .` passes)
- [ ] 5. Tests added or updated for changed behavior
- [ ] 6. No orphaned code (removed symbols cleaned from exports and callers)
- [ ] 7. Files stay focused (no file > 400 lines, no function > 60 lines without justification)
- [ ] 8. Errors are structured (`digibase` error envelope or Pydantic error model)
- [ ] 9. ARCHITECTURE.md updated (new modules, endpoints, env vars reflected)
- [ ] 10. No backward-compat hacks (no `_old_` vars, no `# TODO: remove` left unfixed)

**Quality score: __ / 10**

---

### Optimization (target ≥ 7/10) — [`docs/scoring/OPTIMIZATION.md`](docs/scoring/OPTIMIZATION.md)
- [ ] 1. LiteLLM caching used (all LLM calls through `digigraph/llm.py`)
- [ ] 2. Model mode respected (`get_model_for_mode()` used; no hardcoded model strings)
- [ ] 3. Polars lazy evaluation (`.scan_csv` + single `.collect()` at end of pipeline)
- [ ] 4. No N+1 patterns (bulk/batch endpoints used; no per-item HTTP calls in loops)
- [ ] 5. Embedding cache used (`BatchEmbedder` + `EmbeddingCache` wrappers)
- [ ] 6. Parallel-safe tools tagged (`parallel_safe` tag on stateless orchestrator tools)
- [ ] 7. No synchronous blocking in async routes (`asyncio.to_thread` for unavoidable blocking)
- [ ] 8. Token efficiency (summaries/briefs in prompts, not full doc bodies)
- [ ] 9. Result caching where stable (JWKS, orchestrator manifests cached with TTL)
- [ ] 10. Backtest performance target maintained (10M rows < 2s; DigiQuant changes only)

**Optimization score: __ / 10**

---

### Accuracy (target ≥ 9/10) — [`docs/scoring/ACCURACY.md`](docs/scoring/ACCURACY.md)
- [ ] 1. Matches ARCHITECTURE.md spec (endpoints, models, flow order correct)
- [ ] 2. Workflow state transitions correct (LangGraph nodes read/write correct fields)
- [ ] 3. Audit events emitted for state changes (`audit_log()` on new side-effecting ops)
- [ ] 4. DigiSmith spans carry required attributes (`workflow_id`, `request_id`, `session_id`)
- [ ] 5. Error paths handled, not silenced (no bare `except: pass`)
- [ ] 6. API contracts unchanged or versioned (breaking changes use `/v2/` path)
- [ ] 7. Strategy invariants preserved (Nautilus event lifecycle unchanged; DigiQuant only)
- [ ] 8. JWT scope contract unchanged (new routes use existing scope naming convention)
- [ ] 9. Test assertions are meaningful (specific values checked, not just `is not None`)
- [ ] 10. No regression in existing tests (`make test-unit` passes with zero failures)

**Accuracy score: __ / 10**

---

## Testing Evidence

```
# Paste output of: make test-unit (and ruff check if code change)

```

---

## Documentation Updated

- [ ] `{component}/ARCHITECTURE.md` updated (Module Map, Public API, or Configuration changed)
- [ ] `{component}/AGENTS.md` updated (new patterns or anti-patterns discovered)
- [ ] Root `AGENTS.md` or `CLAUDE.md` updated (if cross-cutting rule changed)

---

## Human Gate

> If any box below is checked, this PR **requires human review** before merge — do not label `automerge-docs`.

- [ ] Live-trading path modified (broker adapters, order submission, execution gates)
- [ ] Auth or crypto modified (DigiKey signing, JWT generation, scope enforcement)
- [ ] New JWT scope added to a protected route
- [ ] `DIGI_ALLOW_CODE_EXEC` gate modified
- [ ] New network exposure (`0.0.0.0` bind or new published port)
- [ ] New external service dependency introduced
- [ ] `SECURITY.md` changed
- [ ] Novel architecture pattern introduced (not described in any existing ARCHITECTURE.md)

**Is human review required?** Yes / No
