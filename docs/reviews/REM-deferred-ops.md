# REM deferred — org / ops runbooks

Items **REM-041**, **REM-042**, **REM-043**, **REM-036**, **REM-058**, and **REM-059** are **complete for audit #578** via this runbook plus in-repo artifacts (BFF route, pipeline shim, pandas allowlist). They are not application-code blockers.

Related: [#578](https://github.com/digithings-ai/digithings/pull/578) · [#577](https://github.com/digithings-ai/digithings/issues/577) · epic [#579](https://github.com/digithings-ai/digithings/issues/579).

---

## REM-041 — Org GitHub PR policy (AUDIT-041)

**Status:** done (ops/human gate documented) — in-repo enforcement is `pr-linkage.yml`; org ruleset is operator-owned.

**Goal:** Every PR to `digithings-ai/digithings` links a GitHub Issue (`Fixes #N` or `task/<N>-*` branch).

### Executable checklist (org admin)

- [ ] Open **digithings-ai** → **Settings** → **Rules** → **Rulesets** (or branch protection on `develop` / `main`).
- [ ] Add required status check: job name from `.github/workflows/pr-linkage.yml` (`Require Fixes` / `pr-linkage`).
- [ ] Enable “Require branches to be up to date” if your ruleset supports it.
- [ ] Confirm **Actions can create PRs** is enabled for `github-actions[bot]` if `agent-backlog-snapshot.yml` should open PRs (optional; bot may use PAT instead).

### Executable checklist (verify in repo)

- [ ] `test -f .github/workflows/pr-linkage.yml`
- [ ] Open a test PR without `Fixes #N` → linkage job fails.
- [ ] Open a test PR with `Fixes #577` on branch `task/577-*` → linkage job passes.

### Verify (CLI)

```bash
gh pr view 578 --json statusCheckRollup --jq '.statusCheckRollup[] | select(.name|test("Require|pr-linkage|linkage"))'
```

**Workflow headers:** `enforce-project-assignment.yml`, `agent-backlog-snapshot.yml` (when present).

---

## REM-042 — Atlas LLM quota cron hygiene (AUDIT-042)

**Status:** done (ops/human gate documented)

**Goal:** Daily workflows do not spam red failures when Cursor/Copilot quotas are exhausted.

### Executable checklist

- [ ] Open issue **#387** — note labels `quota:cursor-exhausted` / `quota:copilot-exhausted`.
- [ ] If exhausted: do **not** expect green `cursor-agent-dispatch` until reset; use Tier 3 relabel per `docs/agents/EXECUTION_TIERS.md`.
- [ ] Weekly: confirm `agent-quota-reset.yml` last run succeeded (`gh run list -w agent-quota-reset.yml -L 3`).
- [ ] Manual reset: `gh workflow run agent-quota-reset.yml` (or repo default dispatch).
- [ ] Stuck `exec:cursor` issues: relabel to `exec:claude` after quota reset.

### Verify

```bash
gh run list -w cursor-agent-dispatch.yml -L 5
gh run list -w agent-quota-reset.yml -L 3
```

**Workflow reference:** `.github/workflows/agent-quota-reset.yml`, `.github/workflows/cursor-agent-dispatch.yml` (header cites this runbook).

---

## REM-043 — Copilot quota gate alignment (AUDIT-043)

**Status:** done (ops/human gate documented)

**Goal:** Copilot dispatch respects the same quota labels as Cursor.

### Executable checklist

- [ ] Confirm `copilot-quota-gate.yml` is enabled on schedule.
- [ ] Inspect last run: `gh run view $(gh run list -w copilot-quota-gate.yml -L 1 --json databaseId -q '.[0].databaseId') --log-failed`
- [ ] When `quota:copilot-exhausted` on #387: new `exec:copilot` issues get comment + `pending:quota` (see workflow).
- [ ] After billing/seat refresh: remove exhausted label on #387.

### Verify

```bash
gh run list -w copilot-quota-gate.yml -L 5
```

---

## REM-036 — Olympus BFF (AUDIT-036)

**Status:** done — documented public-read threat model (REM-035) + optional BFF path in repo. Full RLS redesign remains a product/security gate.

**Goal:** Operators can host Olympus on Node with service-role reads instead of anon key in the browser bundle.

### In-repo artifacts

| Artifact | Purpose |
|----------|---------|
| `frontend/olympus/app/api/snapshots/route.ts` | `GET /api/snapshots` (service role) |
| `frontend/olympus/lib/snapshot-fetch.ts` | `NEXT_PUBLIC_OLYMPUS_USE_BFF=1` → fetch BFF |
| `frontend/olympus/examples/bff-snapshots-route.example.ts` | Mirror of route for static-export docs |
| `digiquant/supabase/migrations/028_olympus_bff_notes.sql` | BFF migration notes |
| `frontend/olympus/README.md` | Threat model + env table |

### Executable checklist (Node / dev hosting)

- [ ] Copy `frontend/olympus/.env.local.example` → `.env.local`.
- [ ] Set `NEXT_PUBLIC_SUPABASE_URL`, `OLYMPUS_SUPABASE_SERVICE_ROLE_KEY` (server-only).
- [ ] Set `NEXT_PUBLIC_OLYMPUS_USE_BFF=1`.
- [ ] Run `npm --workspace frontend/olympus run dev` (not static export).
- [ ] `curl -s http://localhost:3000/olympus/api/snapshots | jq .snapshot.date`

### Static export (digiquant.io)

- [ ] Leave `NEXT_PUBLIC_OLYMPUS_USE_BFF` unset — anon path via RLS `anon_read` (documented in README).

---

## REM-058 — Atlas scripts pandas boundary (AUDIT-058)

**Status:** done — formal allowlist in `digiquant/AGENTS.md` § Pandas allowlist; `compute-technicals.py` Polars date fix (REM-009). Full atlas migration deferred → [#579](https://github.com/digithings-ai/digithings/issues/579).

### Executable checklist (developer)

- [ ] Before adding `import pandas`, check the allowlist table in `digiquant/AGENTS.md`.
- [ ] New data paths: use Polars; do not expand pandas surface without updating the table.
- [ ] CI: `rg 'import pandas' digiquant/ --glob '!scripts/atlas/**'` should only hit allowlisted non-atlas paths.

### Follow-up (#579)

- [ ] Migrate `scripts/atlas/*.py` off pandas where pandas-ta permits.
- [ ] Add CI grep gate (REM-132).

---

## REM-059 — Hermes / DigiGraph pipeline decoupling (AUDIT-059)

**Status:** done (shim) — `digiquant.hermes.pipeline_builder` re-exports DigiGraph builder; Hermes entrypoints import the shim. Full copy/decouple deferred → [#579](https://github.com/digithings-ai/digithings/issues/579).

### In-repo artifacts

| Artifact | Purpose |
|----------|---------|
| `digiquant/src/digiquant/hermes/pipeline_builder.py` | Stable digiquant import path (Hermes) |
| `digiquant/src/digiquant/hermes/graph.py` | Imports shim |
| `digiquant/src/digiquant/hermes/chain.py` | Publish pass imports shim |
| REM-048 | DigiQuant quant pipeline graph singleton cache |

### Executable checklist (developer)

- [ ] New Hermes phase code: `from digiquant.hermes.pipeline_builder import NodeSpec, PipelinePhase, build_pipeline`
- [ ] Do not add new `digigraph.graph.research_agent` imports outside existing phase modules until #579.

### Follow-up (#579)

- [ ] Move builder implementation into digiquant and drop digigraph dependency from Atlas phases.

---

## REM-099 / REM-100 (Wave 5 — in-repo, not deferred)

| REM | Scope | Status on #578 |
|-----|--------|----------------|
| **REM-099** | Document `DIGI_CHECKPOINTER=postgres` for HA | Done — `digigraph/ARCHITECTURE.md` §5.5.1 + `graph.py` docstring |
| **REM-100** | `register_mcp_server` descriptor-only until [#401](https://github.com/digithings-ai/digithings/issues/401) | Done — `registry.py` + `tests/dg/test_mcp_registry.py` |

---

## REM-133 — E2E DigiSearch ingest/search step

**Status:** Deferred to follow-up after stack secrets stable (`E2E_BEARER_TOKEN`).

**Done in #578:** `e2e.yml` compose job; ingest path jail + unit tests (REM-011, 065).

**Follow-up:** extend `tests/test_e2e.py` with seed ingest + query hop when CI secret is configured.

---

## Wave 6 janitor (JAN-003–007, 015–016, 022–024)

**Done in #578 branch (gitignore / ops docs):**

| JAN | Item | Status |
|-----|------|--------|
| JAN-002 | `digiquant/tearsheet.html` removed from git | Done |
| JAN-004 | Root `data/` gitignored | Done |
| JAN-005 | `.remember/` gitignored | Done |
| JAN-006 | `.local_digikey.sqlite`, `/*.sqlite` gitignored | Done |
| JAN-007 | `dashboard-data.json` gitignored | Done |
| JAN-003 | Regenerate root `package-lock.json` (drop stale atlas workspaces) | Follow-up PR |
| JAN-014 | `projects/README.md` allowlist | **Human commit** (path blocked for agents) |
| JAN-008–011, 018–024 | Doc drift | Partial — see REM-111–126, 096, 084 |

---

## Post-merge (REM-136–137)

See [`POST-MERGE-AUDIT-RUNBOOK.md`](./POST-MERGE-AUDIT-RUNBOOK.md).
