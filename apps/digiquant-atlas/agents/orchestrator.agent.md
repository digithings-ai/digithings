# Orchestrator Agent

## Role

Master pipeline driver for the digiquant-atlas research + digest flow. Coordinates segment skills and materializes outputs into Supabase (`daily_snapshots`, `documents`). **Authoritative instructions:** [`skills/orchestrator/SKILL.md`](../skills/orchestrator/SKILL.md).

## How runs are scheduled (preferred)

Use **Claude Cowork** tasks under [`cowork/tasks/README.md`](../cowork/tasks/README.md) — e.g. [`research-daily-delta.md`](../cowork/tasks/research-daily-delta.md), [`research-weekly-baseline.md`](../cowork/tasks/research-weekly-baseline.md), [`portfolio-pm-rebalance.md`](../cowork/tasks/portfolio-pm-rebalance.md). Then [`RUNBOOK.md`](../RUNBOOK.md) for publish + `run_db_first.py`.

## Trigger phrases

- "Run today's digest"
- "Full daily analysis"
- "Run the orchestrator pipeline for {DATE}"
- "Follow skills/orchestrator"

## Inputs (session start)

- [`skills/orchestrator/SKILL.md`](../skills/orchestrator/SKILL.md) — phase order and publish rules  
- `config/watchlist.md`, `config/preferences.md`, `config/investment-profile.md` (Track B)  
- Prior state from **Supabase** (`daily_snapshots`, `documents`) — not legacy flat-file memory  

## Segment skills (canonical paths)

Packages are always `skills/<slug>/SKILL.md`. Examples:

| Area | Slugs |
|------|--------|
| Alt data | `alt-sentiment-news`, `alt-cta-positioning`, `alt-options-derivatives`, `alt-politician-signals` |
| Institutional | `inst-institutional-flows`, `inst-hedge-fund-intel` |
| Macro | `macro` |
| Asset classes | `bonds`, `commodities`, `forex`, `crypto`, `international` |
| Equities | `equity` |
| Sectors | `sector-technology` … `sector-comms` (11 GICS) |
| PM / Track B | `market-thesis-exploration`, `thesis-vehicle-map`, `opportunity-screener`, `asset-analyst`, `deliberation`, `pm-allocation-memo`, `portfolio-manager` |

See [`docs/agentic/SKILLS-CATALOG.md`](../docs/agentic/SKILLS-CATALOG.md) for the full list.

## Outputs

Structured **JSON** published to Supabase per RUNBOOK; optional scratch under `data/agent-cache/` is gitignored.

## Example invocation

```
Read agents/orchestrator.agent.md for role.
Read skills/orchestrator/SKILL.md for phase order.
Execute today's Cowork task file (cowork/tasks/…) then RUNBOOK publish + validate steps.
```
