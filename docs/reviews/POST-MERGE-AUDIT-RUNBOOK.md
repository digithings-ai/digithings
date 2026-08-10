# Post-merge audit runbook (REM-136, REM-137)

After [#578](https://github.com/digithings-ai/digithings/pull/578) merges to `develop`, operators run this checklist **without an agent**. Epic: [#577](https://github.com/digithings-ai/digithings/issues/577).

---

## REM-136 — Watch cron health (7 days)

| Workflow | Expect | Check |
|----------|--------|-------|
| `enforce-project-assignment.yml` | Daily green | Actions → filter workflow name |
| `project-fields-coverage.yml` | Daily green | Same |
| `provider-review.yml` | Weekly green | Sunday 00:00 UTC |
| `digiquant-prices.yml` | Weekday intraday + EOD | Market hours |
| `agent-backlog-snapshot.yml` | Weekly or documented defer | See [`REM-deferred-ops.md`](./REM-deferred-ops.md) REM-041 |
| `stack-smoke.yml` | Nightly `/healthz` | REM-128 |

If a workflow fails, use [`ci-triage`](../agents/CI_CONVENTIONS.md) or `scripts/dry_run_workflows.sh` for local replay hints.

---

## REM-137 — Close epic and children

1. Confirm PR body lists completed `REM-*` rows and deferred items link to [`REM-deferred-ops.md`](./REM-deferred-ops.md).
2. On merged PR: verify `Fixes #577` closed the epic (or close manually with summary comment).
3. Close absorbed child issues (#580–#585) with “Absorbed in #578” if still open.
4. Update [Project #1](https://github.com/orgs/digithings-ai/projects/1) status to **Done** for #577.

---

## Maintainer gate (REM-108–110)

Same commands as implementation plan §5.5:

```bash
make test-unit && make test-baseline
make doc-check && python3 scripts/agents_init.py --check
ruff check . && ruff format --check .
make score
cd frontend/digichat && npm run lint && npm run test && npm run build
cd frontend/olympus && npm run lint && npm run test && npm run build
```

Optional stack: `make up && make test-e2e` or green `e2e.yml` on `develop`.
