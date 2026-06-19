# Olympus MVP Daily Delta — collapse graph, fix continuity

**Epic:** [#930](https://github.com/digithings-ai/digithings/issues/930) · **Branch:** `task/930-olympus-mvp-delta` (off `module/digiquant`) · **PR target:** `module/digiquant`
**Date:** 2026-06-19 · **Author:** Chris Stefan (+ Claude)

## Problem (from epic #930)

Jun 17–19 prod delta runs cost **147 LLM calls / 726s / $11.95** each, produced three unrelated books (SPY/XLP/IJR → SHY/XLK → BIL) with flat NAV, and the published digest diverged from the materialized `positions`. The learning loop was empty.

## Goal

One daily delta path that **evolves** the paper book, publishes **one** brief aligned to final post-7E weights, and costs **<20 LLM calls** (~$1 on the cheap tier).

## Scope

**In (11 issues, one branch):**
- Hermes execution: #936, #934, #933, #931, #932, #937, #935
- Atlas / continuity: #927, #928, #929, #925

**Out:**
- #924 thesis-first entry — **deferred** until 3 stable delta days (epic "Scope — Out" + handoff).
- #926 OpenRouter open-weight JSON benchmark — **split** to its own branch (investigation, not a behavior change).

## Branch & PR strategy

- Single branch `task/930-olympus-mvp-delta`, **one commit per issue** (clean attribution, reviewable).
- PR into `module/digiquant`; body: `Fixes #925 #927 #928 #929 #931 #932 #933 #934 #935 #936 #937` (closes epic #930 once all 11 land; #924 deferred, #926 split noted in body).
- `make score` + full `tests/dq` + repo-wide ruff (pinned **0.15.18** to match CI) green before PR.

## Folded-in items (reconciliation, approved 2026-06-19)

Beyond the 11 issues, the design-doc sweep surfaced four items folded into this branch:

1. **Correlation fix in #934** — phase7e vol-targeting uses a hard-stubbed `corr=None` → ρ=1.0 → systematically over-raises cash (audit §6.5). Likely the *mechanism* behind "PM 65% invested → 7E BIL 30%". Fold a real/saner correlation estimate into the sizer as part of #934.
2. **Early-exit on zero-stale delta** (new Wave 4 guard, from ADR-0019 §3.4) — when triage finds nothing stale, write a `no-op delta` diagnostics row and skip Hermes entirely.
3. **ADR-0020** — record the Hermes-lite collapse + PM/7E split + commit_run as a canonical ADR **superseding ADR-0019's "Hermes always re-runs, it's cheap" premise** (invalidated by Jun-19 forensics). Written first, as the design authority + novel-architecture human gate.
4. **Small audit cleanups** — `AnalystPayload.risks` wired (not hard-`""`) in #931; dead PM-waterfall fallbacks (`portfolio-manager`, `pm-allocation-memo` — human-session prompts incompatible with automated use, audit §9) neutralized in #934/#937.

## Current-state grounding (verified 2026-06-19)

- **#937** — `prior_analyst_gaps` already injected in `phase7d_pm.py` (#859); only `pm-rebalance-decision/SKILL.md` lacks the doc/guardrail. → SKILL-only.
- **#927** — `_enforce_research_only_boundary` already zeros `portfolio_recommendations` (#859 digest merge). Remaining: today-only `_bodies()` filter + trade-verb strip in `actionable_summary`.
- **#933/#931** — `phase7cd_debate.py` exists; no gating/lite/`phase7c_unified`/`AnalystPayload` symbols yet (net-new).
- **#932** — `chain.py` ends on `publish_phase` and already imports `portfolio_materialize`; `commit_run` merges the two.

## Plan — 4 waves (dependency-ordered)

Each wave is independently testable. Criticals (#936, #934) land in waves 1–2 so early stop still ships the P0s. Order reorders the handoff's "then" list for dependency soundness (#933 before #931; #934 before #932).

### Wave 0 — Architecture record (first)
- **ADR-0020 `docs/adr/0020-olympus-mvp-daily-delta.md`** — record the three architecture decisions (Hermes-lite collapse, PM direction-only / 7E sole sizer, `commit_run` terminal write) and the delta cost contract (≤20 calls). Mark **ADR-0019 "Superseded in part by ADR-0020"** (its delta premise that Hermes always re-runs is invalidated). This is the novel-architecture human gate (CLAUDE.md) — review before code lands.

### Wave 1 — Continuity foundation
- **#936 (crit) held-ticker focus slate invariant** — `candidates.py` (`select_focus_tickers`), `chain.py`.
  - Hard invariant: every `prior_book` ticker appears in phase7c fan-out (or explicit carry path with `prior_analyst_gaps`). Build focus list **after** preflight hydrates `prior_book` from Supabase. Warn-log if a held ticker is ever skipped.
  - Tests: unit (prior book {SPY,IJR,XLP} → all three in fan-out even if low technical score); integration in `test_chain_atlas_then_hermes.py`.
- **#937 wire `prior_analyst_gaps` into PM skill** — `pm-rebalance-decision/SKILL.md`.
  - Document the input; require PM to treat gaps as valid analyst context; forbid exiting held names solely for slate absence when a gap entry exists. Snapshot test asserts template includes `prior_analyst_gaps`.

### Wave 2 — Sizing authority + debate reduction
- **#934 (crit) PM direction-only + 7E sole sizer** — `phase7d_pm.py`, `phase7e_risk_sizing.py`, `pm-rebalance-decision/SKILL.md`, `ARCHITECTURE.md`.
  - PM emits direction/ranks/rationale (weights advisory only); 7E reads PM direction + analyst conviction + debate delta → final `recommended_portfolio`. Respect #874 calibration floors (aggressive ≠ zero equities). Published `pm-rebalance` carries `pm_intent` + `sized_portfolio` (or single post-7E book with sizing footnotes).
  - **Fold (correlation):** replace phase7e `corr=None`/ρ=1.0 stub with a real or saner default correlation in vol-targeting (compute pairwise from `price_technicals` where available; sane equity default otherwise). Test: correlated book no longer over-raises cash vs ρ=1.0 baseline.
  - **Fold (PM waterfall):** neutralize the dead `portfolio-manager` / `pm-allocation-memo` human-session fallbacks so automated runs can't reach bash-command prompts.
  - Tests: PM proposes 5 names → 7E output documented; notes match landed book.
- **#933 debate gating — skip 7CD when analysts agree** — `phase7cd_debate.py`, `hermes/docs/ARCHITECTURE.md`.
  - Before 7CD: tight 4-axis agreement (stance spread, `|conviction_score| ≤ threshold`) **or** held ticker with unchanged `prior_analyst` → emit deterministic `DebateSummary(neutral, delta=0)` with 0 LLM calls. Always full debate when `|conviction_score| ≥ 3`, stance includes `sell`, or `prior_analyst` materially changed. Flag `HERMES_DEBATE_GATING=1` (default on for delta). Telemetry: gated-vs-full counts.
  - Tests: agreement → 0 calls; disagreement → full 7CD.

### Wave 3 — Structural collapse + terminal write
- **#931 Hermes lite graph** — `graph.py`, new `phase7c_unified`, `AnalystPayload` schema, `ARCHITECTURE.md` ×2.
  - `build_hermes_phases_lite` (or `OLYMPUS_HERMES_LITE=1`): `phase7c_unified` (1 call/ticker) → `phase7d_pm` (no risk agg/cons debate) → skip Phase 9 LLM. Delta path skips 7CD via gating (#933). Collapse 4-axis join into one `AnalystPayload` (backward-compatible publish keys). A/B harness in `atlas/testing/simulator.py`.
  - **Fold (risks):** wire `AnalystPayload.risks` from the unified analyst's bear case instead of hard-`""` (materialize reads it as an invalidation fallback).
  - Tests: N=8 focus tickers → ≤10 Hermes LLM nodes on lite path.
- **#932 `commit_run` terminal phase** — `chain.py` (`build_commit_phase`), `ARCHITECTURE.md`.
  - After 7E: upsert `positions`/`nav_history`/`theses` then publish `pm-rebalance` + `run_summary` from the **same final weights**. Idempotent `decision_log` append on `(run_date, ticker)`. Move `persist_pending` out of Phase 9 into commit. Fail-closed: abort publish if sized book fails coherence checks.
  - Tests: 7E changes PM weights → published `recommended_portfolio` == `positions`.

### Wave 4 — Cost + Atlas research/triage
- **#935 shared context diet** — `_node_factory.py`, `atlas/docs/RUNBOOK.md`, `docs/atlas/token-budget.md`.
  - Phase-aware context: delta omits 5-snapshot history (inject `bias_row` + changed segments only); per-phase `data_layer` allowlist; analyst gets ticker-scoped context, PM portfolio-scoped. Target ≥30% avg prompt-token drop on simulator delta vs Jun 19. Test asserts context byte budget.
  - **Fold (stale doc):** refresh `token-budget.md` — it still documents Gemini→Grok routing, predating the OpenRouter `OLYMPUS_MODEL_TIER` work merged in #859. Update routing + per-phase budgets to current reality.
- **#927 today-only digest + strip trade verbs** — `phase7_synthesis.py`.
  - `_bodies()` returns only `payload.source == "today"`; `_enforce_research_only_boundary` rewrites/rejects trade verbs in `actionable_summary`. Integration test: carried-segment delta → smaller digest prompt; published snapshot watchlist language only.
- **#928 Phase2 institutional circuit-breaker** — `preflight.py`, phase2 nodes.
  - Preflight `institutional_data_available`; delta skips `inst-*` (deterministic absent stub) when false ≥3 consecutive runs; baseline always runs Phase2; diagnostics show skipped/carried + zero search spend.
- **#929 triage rules for alt nodes** — triage config, phase1.
  - `alt-onchain-positioning`: carry/skip when preflight Hyperdash injection unchanged. `alt-ai-portfolios`: baseline-only regen unless `AI_PORTFOLIOS_DELTA=1`. Guard test: `evaluate()` segment count == compiled graph.
- **#925 deliberation carry + MCP `query_data`** — loaders, `mcp_server.py`, phase7cd phase_inputs.
  - `load_prior_deliberation_summaries` + 7CD `prior_deliberation` phase_input for held tickers. MCP tool(s) wrapping `query_data` with the same table allowlist as in-process agents (`positions`, `nav_history`, `theses`, `documents`). Delta triage skip for held tickers with unchanged prior stance. Unit tests per loader + triage gate.
- **Fold — delta early-exit guard** (ADR-0019 §3.4) — `chain.py` / `run_atlas_then_hermes`. After triage (depends on #928/#929), if zero segments are stale: write a `no-op delta` `atlas_run_diagnostics` row and return **without invoking Hermes**. Test: zero-stale triage → Hermes never built, diagnostics row marked no-op.

## Verification / exit gates (epic acceptance)

Run on `atlas/testing/simulator.py` after wave 3, re-confirm after wave 4:
- [ ] 3 consecutive delta days: ≤2 position exits without risk breach / regime shift.
- [ ] Operator brief weights == `positions` within tolerance.
- [ ] Delta run: **≤20 LLM calls, ≤180s, ≤$1.50** on `OLYMPUS_MODEL_TIER=cheap`.
- [ ] `decision_log` idempotent on retry; resolved lessons in PM `past_context`.
- [ ] Unit: prior book + unchanged conviction → no full book rewrite.

## Risks & notes

- Heavy shared-file contention across waves (`ARCHITECTURE.md`, `pm-rebalance-decision/SKILL.md`, `phase7cd_debate.py`, `chain.py`) — mitigated by sequential single-branch commits (no parallel conflict).
- Duplicates closable once #932/#934 land: #874–#904 (per handoff). Mark #876/#878/#880/#882 (commit_run) and #884/#885 (lite/carry) as the relevant waves merge.
- ADR-0015 (Atlas vs Hermes boundary) and `digiquant/ARCHITECTURE.md` continuity contract are the authority for research-only vs allocator split.

## Reconciliation appendix (design-corpus sweep, 2026-06-19)

**Superseded / historical (do NOT re-implement here):**
- `hermes/docs/HERMES_SUBGRAPH.md` + `WAVE2_UNIT_SPECS.md` — the Wave-2 thesis-first deliberation subgraph (thesis review → exploration → vehicle map → screener → cyclic deliberation → allocation memo). Designed, **never wired, skills deleted** (WS4a note). This is the blueprint for deferred **#924** — revive from here when 3 stable delta days are met; do not redesign.
- ADR-0019 (unified workflow / incremental doc-patch) — premise "Hermes always re-runs, it's cheap" is invalidated; superseded in part by ADR-0020 (this branch). Its workflow-consolidation half (single `atlas.yml`) belongs to the separate workflow-audit epic **#321**, not here.

**Explicitly out of scope — tracked, not forgotten:**
- PR **#771** (HUMAN GATE, open) + **#904** — `portfolio_metrics` / `position_attribution` crons. Audit's "highest-impact gap" but it's dashboard analytics, not delta cost/continuity. Leave for the held PR.
- `fed_odds` unlit (**#778**); `OLYMPUS_POSITION_RISK_FIELDS` off; `atlas_run_health` view (migration 041, held); `#893` triage-breakdown persistence (overlaps #928 diagnostics — consider closing as dup when #928 lands).
- Grandparent vision: **#726** (hedge-fund-in-a-box 3-pillar) — this epic is one slice of it.

**Doc fixes folded into waves:** `token-budget.md` routing refresh (#935); ADR-0019 supersede note (Wave 0).
