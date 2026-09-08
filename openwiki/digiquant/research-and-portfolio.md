---
type: behavior-guide
title: digiquant Research and Portfolio
description: digiquant research and portfolio sub-graphs plus the dashboard backend — phases, edit-mode, attention plans, and book scope.
tags: [digiquant, research, portfolio, dashboard]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-3cca7b16d985d38458390d9a
    resource: repo://digiquant/AGENTS.md
  - id: openwiki-source-5b646b68ffe0cd0431a31bfb
    resource: repo://digiquant/src/digiquant/portfolio/docs/PORTFOLIO_SUBGRAPH.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiquant Research and Portfolio

Beyond the backtest pipeline, digiquant runs two LangGraph sub-graphs —
research (daily thesis production) and portfolio (thesis-to-allocation
deliberation) — with a `dashboard/` backend serving persisted state to
the operator UI. One graph, one daily cadence: no lite forks, no monthly
paths; cost control is the model tier plus per-artifact edit modes.

## Research sub-graph

`research/` (graph, phases, state, schemas, Supabase IO, telemetry)
produces the daily thesis: data gathering, sector/segment analysis,
forecast calibration with outcome tracking, attribution, and a digest for
the dashboard. Phase skills live under `research/skills/`; runbooks and
deployment notes under `research/docs/`.

## Portfolio sub-graph (H1–H9)

`portfolio/phases/` implements `build_portfolio_phases_thesis`: thesis
review → market exploration → vehicle map → opportunity screen → blinded
per-ticker analysis (fan-out) → analyst↔PM deliberation → PM direction
memo (**no weights**) → risk sizing → `commit_run` terminal. H7 emits a
`PMDirectionMemo` only; H8 sizes; H9 commits — no parallel materializers.
Grounding and phase blinding wire through `build_grounding`; new phases
extend `build_portfolio_phases_thesis`.

## Dashboard backend

`dashboard/` serves the operator UI: replay, performance returns,
research corpus/retrieval, instrument metadata, tenancy, overlay, and
learning modules. The **edit-mode** pattern (`dashboard/edit_mode/`:
`resolve_edit_mode` at node entry) triages each artifact to
`skip` (shallow-carry prior, zero LLM), `edit` (skill-driven
`DocumentPatch` merge), or `full` (rewrite) — priors resolve to the
latest published row before the run date, with stale gaps forcing `full`.
Attention plans publish shadow-only (`off`/`shadow` never actuate).
Tests: `pytest tests/dq/dashboard/ tests/dq/research/ tests/dq/portfolio/
-m unit -v`.

## Book scope

Group A reads/writes (`positions`, `nav_history`, `position_events`,
`portfolio_metrics`) pin `workspace_id` — omitted means house; overlay
uses explicit IDs. The dashboard's `houseBook()` mirrors this server-side.
Views and fail-closed rules live in [Dashboard Operator Views](/openwiki/dashboard/operator-views.md).
