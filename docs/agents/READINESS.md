# Readiness — repo-health panel

`make readiness` prints this table. Advisory only: it measures the repo for
housekeeping shifts. It never gates, never fails (exit 0 always), never
auto-merges, and is never a PR pre-flight. If you want the 4-dimension PR
rubric, that is `make score` — a different tool measuring diffs, not the repo.

## Bands

`healthy` / `watch` / `sick` invite judgment; there is no composite score
(composites invite gating). Thresholds live as constants at the top of
`scripts/readiness.py`:

| Constant | Sick when | Healthy when |
|---|---|---|
| `STALE_DAYS = 90` | — (defines stale) | — |
| `WATCH_MISSING_LABELS = 5` | >5 open issues missing `priority:`/`component:` | none missing |
| `WATCH_STALE = 15` | >15 stale open issues | none stale |
| `WATCH_FAILURES = 3` | >3 scheduled failures in 7d | none |
| `WATCH_STUCK_DAYS = 7` / `HEALTHY_STUCK = 3` | >3 stuck `agent-task` | none stuck (≤3 → watch) |
| `WATCH_MODULE_BEHIND = 50` / `HEALTHY_MODULE_BEHIND = 5` | any `module/*` >50 behind | all within 5 |
| `WATCH_RELEASE_AGE = 30` / `HEALTHY_RELEASE_AGE = 7` | oldest release PR >30d | none open, or oldest ≤7d |
| `WATCH_DOC_CANDIDATES = 3` | >3 drift candidates or any ADR dupes | none (ADR gaps alone → watch — gaps are often benign) |

The label keep-list is the bare-minimum set from the 2026-09 simplification
(#3533): `component:*`, `priority:*`, `reviewed:*`, `autorelease:*`, plus
`agent-task`, `automerge-agent/docs`, `bug`, `ci:failure`, `client-pilot`,
`epic`, `provider-review`, `security:finding`. Anything else is drift.

## First-run bootstrap checklist (manual, not computed)

Not computed — curated. The computed row 8 below ("Bootstrap essentials")
checks file presence only. An agent shift should verify these by hand when
bootstrapping fails, not on every run:

- [ ] Fresh clone + `cp .env.example .env` + provider key → `make stack-local` serves all ports
- [ ] `make test-baseline` green on a clean checkout in under 5 minutes
- [ ] `make task ISSUE=N` cuts a worktree from current `origin/develop` (see #2547)
- [ ] `.env.example` lists every variable the stack actually reads (no tribal `.env` entries)
- [ ] Node 22 / Python 3.12+ pins match between CI and AGENTS.md

## Dashboard artifact

`make readiness-html` renders this table as a self-contained page at
`dist/readiness.html` (gitignored build output — regenerate, don't commit) and
opens it locally. No external assets: works from `file://`, printable, and
safe to attach to a bot report. Bots should quote
`make readiness ARGS=--format=json` for the machine-readable numbers and link
the artifact for the human.

## Computed table

Do not hand-edit between the markers — `make readiness-write` owns it.

<!-- readiness:begin -->

_Last computed: 2026-09-04 12:23 UTC via `make readiness` (advisory only)._ 

| # | Dimension | Value | Band |
|---|-----------|-------|------|
| 1 | Backlog hygiene | 137 open (4 missing labels, 0 stale, 7 epics) | watch |
| 2 | Label-set integrity | 28 labels (0 unexpected) | healthy |
| 3 | Docs freshness | 5 drift candidates, 0 dupes, 0 gaps (27 ADRs) | sick |
| 4 | Ops health | 29 failed runs / 12 workflows, 4 open ci:failure | sick |
| 5 | Dispatch health | 76 agent-task {'cursor': 68, 'claude': 8}, 0 stuck | healthy |
| 6 | Branch routing health | 12 module branches, worst behind=1572 | sick |
| 7 | Release discipline | 1 open release PRs, oldest 1d | healthy |
| 8 | Bootstrap essentials | 4/4 essentials present | healthy |

<!-- readiness:end -->

## Reference

- Tier framework: `docs/agents/EXECUTION_TIERS.md`
- Automation index: `docs/agents/HOUSEKEEPING.md`
- Script: `scripts/readiness.py` · Tests: `tests/scripts/test_readiness.py`
