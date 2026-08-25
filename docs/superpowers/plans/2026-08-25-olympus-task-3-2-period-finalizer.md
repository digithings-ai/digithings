# Olympus Phase 0 Task 3.2 — EOD period accounting finalizer (#2597)

Mini-plan for the worktree `task/2597-persist-eod-holdings-periods-nav`.

## Goal

Persist one coherent EOD accounting period from authoritative ledger fills + marks so
job order cannot alter daily metrics meaning (`OLY-REV-007`, `OLY-REV-008`).

## Delivered

1. `digiquant/src/digiquant/olympus/accounting/io.py` — append-only persist,
   `select_final_period`, child repair, supersession.
2. `digiquant/scripts/atlas/finalize_period_accounting.py` — assemble → compute →
   persist; `--date` / `--dry-run` / `--shadow`; cold-ledger decline (exit 3).
3. `refresh_performance_metrics.py` prefers finalized period day return.
4. Shadow step ahead of metrics in `pipeline-atlas-metrics.yml` (`continue-on-error`).
5. Tests in `tests/dq/atlas/test_finalize_period_accounting.py`.
6. `SCHEMA.md` + `ARCHITECTURE.md` finalizer / provisional-vs-final notes.

## Follow-ups (not this PR)

- Drop `continue-on-error` after shadow window passes acceptance metric.
- Task 3.3 lookback vs realized naming; Task 3.4 curated public views.
- Cron densification of eligible cutover days (shadow reconcile every eligible day).
