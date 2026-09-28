---
type: behavior-guide
title: digiquant Research and Portfolio
description: digiquant research and portfolio sub-graphs plus the dashboard backend — phases, edit-mode, attention plans, chain orchestration, and book scope.
tags: [digiquant, research, portfolio, dashboard]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-3cca7b16d985d38458390d9a
    resource: repo://digiquant/AGENTS.md
  - id: openwiki-source-8c11732820d0053e19298a82
    resource: repo://digiquant/src/digiquant/dashboard/attention_plan.py
  - id: openwiki-source-364e70bee0a0f26206456267
    resource: repo://digiquant/src/digiquant/dashboard/edit_mode/config.py
  - id: openwiki-source-1b05d5c09e956bce2b2e22cf
    resource: repo://digiquant/src/digiquant/dashboard/edit_mode/resolve.py
  - id: openwiki-source-53e73b847780419e4710564b
    resource: repo://digiquant/src/digiquant/dashboard/tenancy.py
  - id: openwiki-source-6088906826891f8e21b0be8a
    resource: repo://digiquant/src/digiquant/portfolio/graph.py
  - id: openwiki-source-cd70721f10bdd6e6c64ac824
    resource: repo://digiquant/src/digiquant/portfolio/phases/commit.py
  - id: openwiki-source-aead886b86e31de618b4af13
    resource: repo://digiquant/src/digiquant/portfolio/phases/direction.py
  - id: openwiki-source-8f5f7ae01a7df21f2186a118
    resource: repo://digiquant/src/digiquant/portfolio/phases/phase7e_risk_sizing.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# digiquant Research and Portfolio

digiquant runs two LangGraph sub-graphs — research (daily thesis production) and
portfolio (thesis-to-allocation deliberation) — composed by a chain
orchestrator, with a `dashboard/` backend serving persisted state to the
operator UI. One graph, one daily cadence: no lite forks, no monthly paths.
Cost control is the model tier (`DIGIQUANT_MODEL_TIER`) plus per-artifact edit
modes.

## Research sub-graph

`research/` produces the daily research thesis through a single compiled graph
(`build_research_graph`). The topology is:

1. **preflight** — loads config, prior context, and data-layer state (no LLM).
2. **preflight_reflect** (optional) — closed-loop reflection on prior
   `decision_log` rows, computing alpha vs SPY.
3. **triage** — evaluates which segments need regeneration today (baseline, delta,
   or monthly cadence).
4. **Phase 1–7** — `phase1_altdata` → `phase2_institutional` →
   `phase3_macro` → `phase4_assetclass` → `phase5_equities` (fan-out across
   sectors/segments) → `phase6_consolidate` → `phase7_synthesis`.
5. **publish_phase** (optional) — persists all research artifacts to Supabase.
   The chain orchestrator wires this *after* portfolio instead; standalone
   research runs append it directly.

Phase skills live under `research/skills/`; runbooks and deployment notes
under `research/docs/`. The research graph itself is built in
`digiquant/src/digiquant/research/graph.py` and accepts a minimal
`ResearchInput` contract.

## Portfolio sub-graph

`portfolio/phases/` implements `build_portfolio_phases_thesis()`, which
assembles a linear pipeline of phases that consume research output and produce
an allocation:

| Phase | Node | Role |
|-------|------|------|
| H1 | `portfolio/thesis/market-review` | Thesis review: re-score active theses; update status |
| H2 | `portfolio/thesis/market-exploration` | Market thesis exploration: discover new theses from macro + sector research |
| H3 | `portfolio/thesis/vehicle-map` | Vehicle map: map each thesis to candidate tickers |
| H4 | `portfolio/thesis/opportunity-screener` | Opportunity screener: build focus roster from held positions + thesis vehicles + technical candidates |
| — | `portfolio/coverage/director` | Coverage director (PM role): narrow screener roster to refresh/explore/skip buckets via LLM |
| H5 | `portfolio/analyst/*` | Per-ticker blinded analyst recommendation (fan-out) |
| H6 | `portfolio/deliberation/*` | Analyst↔PM cyclic deliberation per ticker (fan-out, max 6 rounds) |
| H7 | `portfolio/pm-direction` | PM direction memo — **direction, rank, and confidence only; no weights** (`PMDirectionMemo`) |
| H8 | `portfolio/risk-sizing` | Deterministic risk sizing via `size_portfolio` — the sole weight owner |
| H9 | `portfolio/commit-run` | Terminal `commit_run`: persist positions, decision_log, portfolio brief, risk policy snapshots, cost liquidity bundles, forecast lineage, sizing risk snapshots, and ledger append |

Grounding and phase blinding wire through `build_grounding` (in
`_node_factory.py`) and `_portfolio_grounding` (in `portfolio_common.py`).
New phases extend `build_portfolio_phases_thesis`. Direction must not emit
weights — sizing is the sole weight owner, and commit is the terminal; no
parallel `portfolio_materialize` phase is added on the daily path.

### Coverage director

Between screener and analyst, the coverage director (`phase_h4_b` in
implementation terms) is an LLM-driven PM decision node that buckets each
rostered ticker as `refresh` (reassessment needed), `explore` (new candidate
worth analyzing), or `skip` (rely on history — downstream carries prior with
zero LLM). The director proposes; `apply_coverage` disposes deterministically:
it can only narrow the screener roster, never widen it.

### Prerequisite snapshot

The direction phase accepts an optional `direction_prerequisite_snapshot` — a
research-state pin that freezes analyst/deliberation context for offline
consumption. This is wired via `wire_direction_phase_inputs` and the
`ResearchStateStore`.

## Chain orchestrator

The cron entry point is `digiquant.portfolio.chain.run_research_then_portfolio`
(`chain.py`). It composes:

```
ResearchInput → build_research_graph (no publish) → build_portfolio_graph → publish_phase
```

The chain accepts unified `ChainDeps` carrying `research` (preflight,
triage, preflight-reflect), `portfolio` (thesis–commit thesis path), and
shared `publish` deps. Phase 9 evolution LLM is off the daily graph; beliefs
distillation runs after publish via `run_beliefs_distillation_if_triggered`.

Stage gates (`stage_gates.py`) control cadence by pipeline stage (baseline
Sunday, delta Mon–Sat, monthly synthesis), with `MarketCalendarContext`
informing scheduling decisions.

## Dashboard backend

`dashboard/` serves the operator UI: replay, performance returns, research
corpus/retrieval, instrument metadata, tenancy, overlay, learning, and
attention plans.

### Edit-mode pattern

The edit-mode pattern (`dashboard/edit_mode/`) triages each artifact at node
entry via `resolve_edit_mode(artifact_key, run_date, prior_loader, triage,
force_full_rewrite)`:

- **`skip`** — shallow-carry the prior published row (zero LLM calls).
- **`edit`** — load the `*-edit.md` skill, produce a `DocumentPatch`, merge
  via `merge_document_patch`.
- **`full`** — load the `*-full.md` skill and produce a complete new body.

Prior resolution uses `prior_published(run_date, document_key)`: the latest
row with `date < run_date`, not just calendar yesterday. Staleness is measured
from `content_date` (the date content materially changed), not publish date,
so republishes don't reset the gap. When the gap exceeds
`DIGIQUANT_STALE_FULL_DAYS` (default 7), the mode is forced to `full`.

### Attention plans (shadow-only)

Attention plans (`dashboard/attention_plan.py`) produce typed pre-provider
attention decisions with stable refresh reasons. Planner mode is `off` or
`shadow` only — `enforce` is intentionally absent. The planner cannot expand a
screener roster or rewrite direction/sizing authority.

`attention_plan_graph.maybe_publish_attention_plan_shadow` (Track C,
glass-box #1945 / #2622) computes a WP13-class shadow plan beside incumbent
edit modes and upserts `document_key='attention-plan'` during the research
publish phase when triage ran and `DIGIQUANT_PLANNER_MODE` is `shadow`
(default). Never fabricate UI rows without a published document; never
actuate.

### Tests

```bash
pytest tests/dq/dashboard/ tests/dq/research/ tests/dq/portfolio/ -m unit -v
```

## Book scope

Group A reads/writes (`positions`, `nav_history`, `position_events`,
`portfolio_metrics`) must pin `workspace_id`. Omitted/`None`/blank means the
**house** workspace — `resolved_workspace_id()` delegates to
`house_workspace_id()`, and all queries filter through
`eq_house_workspace()`. Overlay passes an explicit workspace ID. The
dashboard's `houseBook()` (TypeScript, `lib/house-workspace.ts`) mirrors this
server-side. Never date-only scans: every Group A access must carry a
workspace-id filter.

Views and fail-closed rules live in [Dashboard Operator
Views](/openwiki/dashboard/operator-views.md).
