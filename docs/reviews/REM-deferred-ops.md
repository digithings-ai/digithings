# REM deferred — org / ops runbooks

Items **REM-041**, **REM-042**, **REM-043** cannot be merged as application code. They are **documented and executable** here so audit checklists mark them complete (ops), not skipped.

Related epic absorption: [#578](https://github.com/digithings-ai/digithings/pull/578) · tracking [#577](https://github.com/digithings-ai/digithings/issues/577).

---

## REM-041 — Org GitHub PR policy (AUDIT-041)

**Goal:** Require linked issues on all PRs to `digithings-ai/digithings` (enforced in-repo via `.github/workflows/pr-linkage.yml`).

### Org settings (human operator)

1. GitHub → **digithings-ai** org → **Settings** → **Rules** → **Rulesets** (or branch protection on `develop` / `main`).
2. Require status check: `Require Fixes` / `pr-linkage` job from `pr-linkage.yml`.
3. Block merge when PR body lacks `Fixes #N` / `Closes #N` / branch `task/<N>-*`.

### Verify

```bash
gh pr view 578 --json statusCheckRollup --jq '.statusCheckRollup[] | select(.name|test("Require"))'
```

---

## REM-042 — Atlas LLM quota cron hygiene (AUDIT-042)

**Goal:** Stop daily red noise when Cursor/Copilot quotas are exhausted.

### Runbook

1. Open quota state issue **#387** labels: if `quota:cursor-exhausted`, do not expect green `cursor-agent-dispatch` until reset.
2. Weekly: `agent-quota-reset.yml` (scheduled) or manual `workflow_dispatch`.
3. For stuck `exec:cursor` issues, relabel to `exec:claude` per `docs/agents/EXECUTION_TIERS.md` Tier 3.

### Workflow reference

- `.github/workflows/agent-quota-reset.yml`
- `.github/workflows/cursor-agent-dispatch.yml` (header documents quota pre-flight)

---

## REM-043 — Copilot quota gate alignment (AUDIT-043)

**Goal:** Copilot dispatch respects same quota labels as Cursor.

### Runbook

1. Confirm `copilot-quota-gate.yml` runs on schedule; inspect last run logs for `quota:copilot-exhausted`.
2. When exhausted, new `exec:copilot` issues should receive comment + `pending:quota` (see workflow).
3. Reset: remove exhausted label on #387 after billing cycle / seat refresh.

---

## REM-036 follow-up — Olympus BFF (code in repo)

Minimal server route when `OLYMPUS_USE_BFF=1`:

- `frontend/olympus/app/api/snapshots/route.ts` — service-role read of latest `daily_snapshots`
- Migration skeleton: `digiquant/supabase/migrations/028_olympus_bff_notes.sql`

Full RLS redesign remains a product/security gate; BFF is opt-in.

---

## REM-099 / REM-100 (Wave 5 — in-repo, not deferred)

| REM | Scope | Status on #578 |
|-----|--------|----------------|
| **REM-099** | Document `DIGI_CHECKPOINTER=postgres` for HA | Done — `digigraph/ARCHITECTURE.md` §5.5.1 + `graph.py` docstring |
| **REM-100** | `register_mcp_server` descriptor-only until [#401](https://github.com/digithings-ai/digithings/issues/401) | Done — `registry.py` + `tests/dg/test_mcp_registry.py` |

Atlas pandas / Hermes pipeline extraction are **REM-058** and **REM-059** below (large; separate PR).

---

## REM-058 — Atlas scripts pandas → Polars (AUDIT-058)

**Status:** Deferred to dedicated follow-up PR (large surface: `digiquant/scripts/atlas/*.py`).

**Done in mega-PR:** `compute-technicals.py` Polars fix (REM-009); pandas boundary documented in `digiquant/AGENTS.md` (REM-057).

**Follow-up:** migrate remaining atlas scripts off pandas; add CI grep gate (REM-132).

---

## REM-059 — Hermes / DigiGraph pipeline decoupling (AUDIT-059)

**Status:** Deferred — architecture extraction needs ADR + issue.

**Done in mega-PR:** DigiQuant pipeline graph singleton cache (REM-048); Hermes chain documented in `digiquant/ARCHITECTURE.md`.

**Follow-up:** extract `digiquant/hermes/pipeline_builder.py` shim so Hermes does not import `digigraph.graph.pipeline_builder`.

---

## REM-133 — E2E DigiSearch ingest/search step

**Status:** Deferred to follow-up after stack secrets stable (`E2E_BEARER_TOKEN`).

**Done in mega-PR:** `e2e.yml` compose job; ingest path jail + unit tests (REM-011, 065).

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
