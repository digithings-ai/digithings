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
