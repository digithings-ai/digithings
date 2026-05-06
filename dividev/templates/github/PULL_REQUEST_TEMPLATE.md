## Linked issue

<!--
Every PR must trace to a backlog issue.
Either use a branch named  task/<N>-<slug>  (created by `make task ISSUE=N`),
or add a line below:  Fixes #123   (also accepts Closes / Resolves).
-->

Fixes #

---

## Component

<!-- Check all that apply -->
{{COMPONENT_CHECKBOXES}}
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

Score honestly against the rubrics in `dividev/docs/scoring/`. Do not check a box unless you fully satisfy the criterion.

### Security (target ≥ {{SCORE_SECURITY}}/10)
- [ ] No secrets in code (no API keys, tokens, private keys hardcoded)
- [ ] No PII in logs or traces (no raw prompts, bearer tokens, personal data)
- [ ] Input validation at system boundaries (typed models on all HTTP/CLI inputs)
- [ ] No injection vectors (no `eval`, f-string SQL, unguarded `subprocess` with user input)
- [ ] Auth checks on new routes / endpoints
- [ ] Fail-closed on missing auth config
- [ ] No new unreviewed network exposure (new bound ports, public endpoints)
- [ ] Least-privilege secret access (new secrets documented in `.env.example`)
- [ ] No debug backdoors in production paths
- [ ] Sensitive paths not touched without human gate (if touched, box below checked)

**Security score: __ / 10**

---

### Quality (target ≥ {{SCORE_QUALITY}}/10)
- [ ] Typed interfaces everywhere (no `Any` without justification)
- [ ] Linter clean (`ruff check . && ruff format --check .` or equivalent passes)
- [ ] Tests added or updated for changed behavior
- [ ] No orphaned code (removed symbols cleaned from exports and callers)
- [ ] Files stay focused (no file > 400 lines, no function > 60 lines without justification)
- [ ] Errors are structured (error envelope or typed error model, not raw strings)
- [ ] ARCHITECTURE.md updated (new modules, endpoints, env vars reflected)
- [ ] No backward-compat hacks left unfixed

**Quality score: __ / 10**

---

### Optimization (target ≥ {{SCORE_OPTIMIZATION}}/10)
- [ ] No N+1 patterns (bulk/batch used where applicable, no per-item HTTP calls in loops)
- [ ] No synchronous blocking in async paths
- [ ] Token / data efficiency (summaries in prompts, not full payloads)
- [ ] Result caching where stable (with appropriate TTL)
- [ ] No redundant computation in hot paths

**Optimization score: __ / 10**

---

### Accuracy (target ≥ {{SCORE_ACCURACY}}/10)
- [ ] Matches ARCHITECTURE.md spec (endpoints, models, flow order correct)
- [ ] Error paths handled, not silenced (no bare `except: pass`)
- [ ] API contracts unchanged or versioned (breaking changes use `/v2/` path)
- [ ] Test assertions are meaningful (specific values checked, not just `is not None`)
- [ ] No regression in existing tests (`make test-unit` passes with zero failures)

**Accuracy score: __ / 10**

---

## Testing Evidence

```
# Paste output of: make test-unit (and linter if code change)

```

---

## Documentation Updated

- [ ] `{component}/ARCHITECTURE.md` updated (interface or behavior changed)
- [ ] `{component}/AGENTS.md` updated (new patterns or anti-patterns discovered)
- [ ] Root `AGENTS.md` updated (if cross-cutting rule changed)

---

## Human Gate

> If any box below is checked, this PR **requires human review** before merge.

- [ ] Auth or cryptographic code modified
- [ ] Sensitive / live-trading paths modified
- [ ] New external service dependency introduced
- [ ] New network exposure (new bound port or public endpoint)
- [ ] Novel architecture pattern not described in any existing ARCHITECTURE.md
- [ ] Score below threshold on any dimension

**Is human review required?** Yes / No
