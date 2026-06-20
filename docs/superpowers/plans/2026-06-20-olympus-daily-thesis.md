# Olympus Daily Thesis + Edit-Mode — Implementation Plan

> **For agentic workers:** Read the design spec first. TDD per task. One commit per task with `Fixes #930`.

**Goal:** One daily Olympus workflow — Atlas research with edit-mode continuity → thesis-aware Hermes (H1–H9) → `commit_run` — cost controlled by model tier + per-artifact `skip`/`edit`/`full`, not graph forks.

**Architecture:** Single branch `task/930-olympus-mvp-delta` → PR into `module/digiquant`. **One graph topology** per [`2026-06-20-olympus-daily-thesis-design.md`](../specs/2026-06-20-olympus-daily-thesis-design.md) (owner decisions §17).

**Tech stack:** Python 3.12, Pydantic v2, Polars, LangGraph, LiteLLM, Supabase, pytest.

**Tracking:** GitHub [#930](https://github.com/digithings-ai/digithings/issues/930) — absorbs [#924](https://github.com/digithings-ai/digithings/issues/924) thesis-first scope.

**Implementation briefs:** [`briefs/atlas-orchestrator-scope.md`](briefs/atlas-orchestrator-scope.md) · [`briefs/hermes-scope.md`](briefs/hermes-scope.md)

---

## Workflow map (execution order)

Steps use **path-style titles** (domain / area / task) instead of numbered phases. Run top-to-bottom unless noted.

| Order | Step title | What it delivers |
|------:|------------|------------------|
| 0 | [`docs/adr-and-tracking`](#docsadr-and-tracking) | Revert #931, amend ADR, spec/plan green |
| 1 | [`foundation/edit-mode`](#foundationedit-mode) | `resolve_edit_mode`, `DocumentPatch`, merge library — **done** |
| 2 | [`atlas/research/edit-mode`](#atlasresearchedit-mode) | Triage + segments + bias + digest edit paths |
| 3 | [`orchestrator/daily-cadence`](#orchestratordaily-cadence) | `--cadence daily`, drop baseline/delta/monthly — **done** |
| 4 | [`tools/research-retrieval`](#toolsresearch-retrieval) | `query_research`, `query_portfolio`, blinding — **done** (grounding wire-up with Hermes) |
| 5 | [`hermes/thesis/market-and-roster`](#hermesthesismarket-and-roster) | H1–H4 + skills + thesis_io — **done** |
| 6 | [`hermes/portfolio/analyst-deliberation`](#hermesportfolioanalyst-deliberation) | H5–H6 — **done** |
| 7 | [`hermes/portfolio/direction-and-sizing`](#hermesportfoliodirection-and-sizing) | H7–H8 — **done** |
| 8 | [`hermes/portfolio/commit-run`](#hermesportfoliocommit-run) | H9 terminal — **done** |
| 9 | [`learning/preflight-and-beliefs`](#learningpreflight-and-beliefs) | Daily reflect; beliefs on-demand |
| 10 | [`ci/simulator-gates`](#cisimulator-gates) | Quiet-day budget, continuity tests |
| 11 | [`docs/olympus-topology-sync`](#docsolympus-topology-sync) | **Final step** — all docs match shipped graph |

**Daily graph reference (runtime nodes, not plan steps):**  
`atlas/preflight` → `atlas/triage` → `atlas/research/segment/*` → `atlas/research/consolidate` → `atlas/research/digest` → `hermes/thesis/*` → `hermes/portfolio/*` → `hermes/portfolio/commit-run`

---

## Global constraints

- Polars only; Pydantic v2; ruff 0.15.18; `make score` + `make doc-check` before PR.
- No live-trading paths. No `OLYMPUS_HERMES_LITE` or second Hermes graph builder.
- **First action:** revert uncommitted #931 lite-graph work on this branch (`graph.py`, `phase7c_analyst.py`, `test_hermes_lite.py`, simulator lite path, `ARCHITECTURE.md` lite paragraph).

---

## docs/adr-and-tracking

**Spec:** preamble, §12. Parallel with early code prep where safe.

- [x] **Revert** uncommitted #931 lite-graph changes (see Global constraints).
- [x] Amend ADR-0020 (or ADR-0021): edit-mode continuity + thesis-aware Hermes supersedes lite/collapse + baseline/delta graph forks.
- [x] Update #930 issue body to reference this plan + Jun-20 spec; close #924 as merged.
- [x] Apply spec review fixes (§3.6, §11.2–§11.3, prior-date semantics) — see Jun-20 design spec.
- [x] `make doc-check` green.

---

## foundation/edit-mode

**Module:** `digiquant.olympus.edit_mode` · **Spec:** §4–§5, §17 #1–#3.

- [x] `resolve_edit_mode`, `DocumentPatch`, `merge_document_patch` (wrap `apply_ops`).
- [x] `ArtifactEditOutput` = `DocumentPatch | FullArtifactBody` (model-initiated full rewrite).
- [x] `OLYMPUS_STALE_FULL_DAYS` env (default 7); `prior_date` field aligned with `document-delta.schema.json`.
- [x] `fetch_prior_document` / `query_research` tool stubs + tests.
- [x] Tests: no prior → full; quiet → skip; stale + prior → edit; gap > `OLYMPUS_STALE_FULL_DAYS` → full (`tests/dq/olympus/test_edit_mode.py`, 14 passed).

---

## atlas/research/edit-mode

**Spec:** §6, §13.1 (Atlas A1–A4). **Scope:** [`briefs/atlas-orchestrator-scope.md`](briefs/atlas-orchestrator-scope.md) — depends on `foundation/edit-mode`.

- [x] `atlas/triage`: `regenerate` → `edit` signal when prior exists (`triage_decision_to_signal`: carry→quiet/skip, regenerate→stale/edit); drop `run_type == "delta"` gates; always compile triage in `graph.py`.
- [x] `atlas/research/segment/*` (`_node_factory`): edit branch + `merge_document_patch` (macro `macro-edit.md` pilot; more `*-edit.md` verticals pending).
- [x] **`phase5_equities`:** equity node → `build_segment_node` (done); sector swarm nodes → `build_segment_node` (done).
- [x] `atlas/research/consolidate` (`phase6_consolidate`): bias row edit/carry + `document_deltas` on field changes.
- [x] `atlas/research/digest` (`phase7_synthesis`): digest edit merge + fallback to full synthesis.
- [x] Dual publish: materialized row + `document_delta` audit (`publish_phase`, `document_deltas` state).
- [x] Remaining vertical `*-edit.md` skills (equity, crypto, sectors/health-care, …).
- [x] Remove `run_type` gate on triage — daily-only rules (`triage.py` always-on).
- [x] Deprecate `--run-type` in `chain.py` CLI (shim with warnings; `monthly` rejected).
- [x] Deprecate `monthly` run path (§17 #4).

---

## orchestrator/daily-cadence

**Spec:** §14, §17 #4. **Scope:** [`briefs/atlas-orchestrator-scope.md`](briefs/atlas-orchestrator-scope.md). **Run after Atlas triage edits, before `tools/research-retrieval` and Hermes** — both touch `chain.py` / `graph.py`.

- [x] `hermes/chain.py`: `--cadence daily` + `--refresh-scope`; deprecated `--run-type` shim (`monthly` rejected).
- [x] `atlas/graph.py`: single daily topology; monthly branch removed.
- [x] `.github/workflows/olympus.yml`: daily cron + `workflow_dispatch` `refresh_scope`.
- [x] Simulator: daily-only; monthly short-circuit removed.
- [x] `refresh_scope` → `force_full_rewrite` in segment/digest nodes.

---

## tools/research-retrieval

**Spec:** §6.1, §17 #9.

- [x] `query_research` — documents + digest, `as_of_date` / prior_published fallback (`research_retrieval/`).
- [x] Extend `query_data` (prices/technicals) — existing MCP shape retained.
- [x] `query_portfolio` — phase-scoped blinding (§6.1 table).
- [x] Wire via `build_grounding` on Hermes H1–H7 (`build_thesis_grounding` + phase blinding).

---

## hermes/thesis/market-and-roster

**Spec:** §7–§8, §13.2 (H1–H4). Absorbs #924. **Scope:** [`briefs/hermes-scope.md`](briefs/hermes-scope.md). **Own PR (4a)** — do not combine with portfolio steps. **Prereqs:** `foundation/edit-mode`, `orchestrator/daily-cadence`, `tools/research-retrieval`, migration 025 (thesis fields).

- [x] Migration `025_thesis_daily_fields.sql` — §7.1 thesis fields + tests.
- [x] `build_hermes_phases_thesis()` scaffold; `build_hermes_graph()` cutover; legacy 7C→9 strangler tail; lite builder gone.
- [x] `hermes/thesis/market-review` (H1): LLM + edit-mode + `thesis_io` persist.
- [x] `hermes/thesis/market-exploration` (H2): LLM + edit-mode.
- [x] `hermes/thesis/vehicle-map` (H3): LLM + `thesis_vehicles` writers.
- [x] `hermes/thesis/opportunity-screener` (H4): deterministic roster + runtime gate → 7C fan-out.
- [x] **Create** skills: `thesis`, `market-thesis-exploration`, `thesis-vehicle-map`, `opportunity-screener` (`*-full.md` / `*-edit.md`).
- [x] Wire migration 024/025 tables (`theses`, `thesis_vehicles`); `test_thesis_criteria` (§16).
- [x] `build_grounding` + `RESEARCH_TOOLS` phase blinding.

---

## hermes/portfolio/analyst-deliberation

**Spec:** §9–§10, §10.6 (H5–H6). **Scope:** [`briefs/hermes-scope.md`](briefs/hermes-scope.md) PR **4b**. **Own PR.**

- [x] `hermes/portfolio/asset-analyst` (H5): unified `AnalystPayload` per ticker; vehicle-local thesis; edit-mode + fingerprint (#925).
- [x] **Create** `asset-analyst` skill (`*-full.md` / `*-edit.md`).
- [x] Ticker fingerprint skip/edit (`#925`) for H5/H6.
- [x] `hermes/portfolio/deliberation` (H6): PM↔analyst loop; `deliberation` skill; carried summary on skip.
- [x] Remove `phase7cd_debate.py` + 4-axis specialist path from graph (`phase7c`/`phase7cd` deleted).

---

## hermes/portfolio/direction-and-sizing

**Spec:** §11.2 (H7–H8). **Scope:** [`briefs/hermes-scope.md`](briefs/hermes-scope.md) PR **4c**. **Own PR.**

- [x] `hermes/portfolio/pm-direction` (H7): `PMDirectionMemo` — direction + rank only; `pm-direction` skills.
- [x] `hermes/portfolio/risk-sizing` (H8): 7E in-graph; sole weight owner → `phase_hermes.sized_book`.
- [x] Removed `build_phase7d` risk debaters + chain-terminal 7E; `test_pm_no_weights` + 7E memo regression.

---

## hermes/portfolio/commit-run

**Spec:** §11.3 (H9). **Scope:** [`briefs/hermes-scope.md`](briefs/hermes-scope.md) PR **4d**. **Own PR.** Blocks merge of portfolio track.

- [x] `hermes/portfolio/commit-run` (H9, #932): replaces chain-terminal materialize; H9 in-graph booking + brief + decision_log.

---

## learning/preflight-and-beliefs

**Spec:** §11.1, §17 #10.

- [x] `learning/preflight-reflect`: daily (unchanged on Atlas graph).
- [x] `learning/beliefs-distillation`: `refresh_scope=beliefs` or backlog > `OLYMPUS_BELIEFS_BACKLOG` (20); migration 043; `beliefs-distillation` skill.
- [x] Confirm phase9 evolution LLM removed from daily chain (H1–H9 only).

---

## ci/simulator-gates

- [x] Workflow + CLI alignment with `orchestrator/daily-cadence` (`olympus.yml` tests lock `--cadence daily`).
- [x] Simulator: `LlmCallTelemetry`, quiet-day budget (≤22), patch-ratio gate; `test_quiet_day` + 3-day continuity scaffold.
- [x] #926 benchmark (optional parallel branch) — gates cheap-tier default for edit-mode schemas.

---

## docs/olympus-topology-sync

**Final implementation step — blocks PR.** **Spec:** §13–§14. Run after all code steps above are green. Every doc describing Olympus topology, CLI, cadence, or operator runbooks must match the shipped graph.

### Component architecture (required)

- [x] `digiquant/ARCHITECTURE.md` — one daily graph; edit-mode; model tier only; no lite/7CD/4-axis prose.
- [x] `digiquant/AGENTS.md` — thesis-first Hermes + `edit_mode` extension patterns.
- [x] `digiquant/src/digiquant/olympus/hermes/docs/ARCHITECTURE.md` — H1–H9 path map, `PMDirectionMemo`, deliberation sub-graph, `commit_run`.
- [x] `digiquant/src/digiquant/olympus/hermes/docs/AGENTS.md` — extension checklist (§9–§11).
- [x] `digiquant/src/digiquant/olympus/atlas/docs/AGENTS.md` — triage `skip`/`edit`/`full`, segment edit-mode.
- [x] `digiquant/src/digiquant/olympus/atlas/docs/agentic/ARCHITECTURE.md` — Atlas→Hermes handoff, retrieval tools.

### Operator + runbooks

- [x] `digiquant/src/digiquant/olympus/atlas/docs/RUNBOOK.md` — daily cadence, `refresh_scope`, edit-mode fold, beliefs on-demand.
- [x] `digiquant/src/digiquant/olympus/atlas/docs/DEPLOYMENT.md` — `OLYMPUS_MODEL_TIER`, `OLYMPUS_STALE_FULL_DAYS`.
- [x] `digiquant/src/digiquant/olympus/atlas/docs/agentic/WORKFLOWS.md` — remove monthly/baseline/delta workflows.
- [x] `docs/LOCAL_STACK.md` — stack-local Olympus commands if referenced.

### ADRs + data model

- [x] `docs/adr/0020-olympus-mvp-daily-delta.md` — thesis-first + edit-mode canonical.
- [x] `docs/adr/0015-atlas-vs-hermes.md` — terminal = `commit_run`.
- [x] `digiquant/supabase/SCHEMA.md` — `theses` / `thesis_vehicles` / deliberation tables.

### Historical / secondary (update or redirect)

- [x] `digiquant/src/digiquant/olympus/hermes/docs/HERMES_SUBGRAPH.md` — implemented topology or redirect.
- [x] `digiquant/src/digiquant/olympus/hermes/docs/WAVE2_UNIT_SPECS.md` — align H-path names or redirect to Jun-20 spec.
- [x] `digiquant/src/digiquant/olympus/atlas/docs/DESIGN-DECISIONS.md` — supersede Jun-19 dual-graph decisions.
- [x] `docs/olympus/OLYMPUS_ARCHITECTURE_AUDIT.md` — superseded banner or refresh.

### Gate

- [x] `make doc-check` green.
- [x] Grep sweep: no authoritative doc mandates `OLYMPUS_HERMES_LITE`, `run_type=baseline|delta`, `phase7cd`, or monthly cron as **current** behavior.

---

## Test mapping (spec §16)

| Test | Plan step |
|------|-----------|
| `test_resolve_edit_mode`, `test_merge_document_patch` | `foundation/edit-mode` |
| `test_segment_edit_e2e`, `test_digest_edit` | `atlas/research/edit-mode` |
| cadence CLI + workflow smoke | `orchestrator/daily-cadence` |
| retrieval tool contract tests | `tools/research-retrieval` |
| `test_thesis_criteria`, H1–H4 graph smoke | `hermes/thesis/market-and-roster` |
| `test_analyst_edit`, `test_deliberation_*`, fingerprint skip | `hermes/portfolio/analyst-deliberation` |
| `test_pm_no_weights`, 7E sizing regression | `hermes/portfolio/direction-and-sizing` |
| `commit_run` coherence + idempotency (#932) | `hermes/portfolio/commit-run` |
| `test_quiet_day` | `ci/simulator-gates` |
| `preflight_reflect` + beliefs on-demand | `learning/preflight-and-beliefs` |
| doc link + stale-topology grep gate | `docs/olympus-topology-sync` |

---

## Verification (before PR)

- [x] Daily sim: thesis-aware graph + edit-mode; model tier = cheap.
- [x] Published brief weights == `positions` (post-7E).
- [x] Held tickers never dropped (#936).
- [x] **`docs/olympus-topology-sync` complete** (all items checked).
- [ ] `tests/dq` + ruff + `make score` + `make doc-check` green.

---

## Completed prerequisites (from Jun-19 — do not redo)

#936, #937, #933 (bridge only — remove with `hermes/portfolio/deliberation`), #934 (partial), #935, #927, #928, #929, ADR-0020 (amend in `docs/adr-and-tracking` before `hermes/thesis/market-and-roster`).
