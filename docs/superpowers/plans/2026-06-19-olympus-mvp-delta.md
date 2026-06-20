# Olympus MVP Daily-Delta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task is executed by a fresh subagent that **reads the listed files first, then does TDD** (failing test → minimal impl → green → ruff/score → commit). This plan gives the contract + test intent + acceptance per task; the executing subagent writes the line-level code against the real APIs.

**Goal:** Make the Olympus daily delta evolve the paper book, publish one coherent brief aligned to final post-7E weights, and cost <20 LLM calls (~$1) — by collapsing the Hermes graph, gating debate, fixing the sizer, and merging the terminal write.

**Architecture:** Single integration branch `task/930-olympus-mvp-delta` → one PR into `module/digiquant` (+ a separate `#926` benchmark branch/PR). Dependency-ordered waves. Hermes core (W1–W3) is sequential/orchestrator-led (shared `chain.py`/`state.py`/`phase7*`/`ARCHITECTURE.md`); isolated work (ADR, docs, Atlas W4, #925, #926) fans out to parallel worktree subagents. Behavior changes ship behind flags; **baseline keeps the full graph; the lite/collapse path is OFF-by-default for delta until #926 validates cheap-tier JSON reliability.**

**Tech Stack:** Python 3.12, Pydantic v2, Polars (never pandas), LangGraph, LiteLLM, Supabase, pytest. Source of truth for the "what": [`docs/superpowers/specs/2026-06-19-olympus-mvp-delta-design.md`](../specs/2026-06-19-olympus-mvp-delta-design.md).

## Global Constraints

- Polars only (never pandas); Pydantic v2; strict typing; ruff line-length 100; **ruff pinned 0.15.18** (matches CI — see `.venv/bin/python -m pip install 'ruff==0.15.18'`; invoke ruff/pytest via `.venv/bin/python -m …`, the wrapper shebangs are stale).
- Every task ends green on: `.venv/bin/python -m pytest <touched suites> -q`, `.venv/bin/python -m ruff check <paths>` + `ruff format --check <paths>`, and (per PR) `make score` ≥ thresholds (Sec 8 / Qual 8 / Opt 7 / Acc 9) + `make doc-check`.
- One commit per task, conventional-commit subject + `#<issue>` + `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Never touch live-trading paths (system is paper-only). No new external service deps.
- CI lanes that gate the PR: `atlas-graph / tests` (ruff dq paths + pytest), `digigraph / test` (ruff digigraph/src), `ruff-and-scripts` (lint all src+tests), `digiquant / test`, `score`, `doc-links + agents-init`.

---

## Execution order & parallelization map

```
W0  ADR-0020 ............................. PARALLEL (subagent A) — doc only
W1  #936 → #937 .......................... SEQUENTIAL (orchestrator) — candidates/chain + PM skill
W2  #934 → #933 .......................... SEQUENTIAL — phase7d/7e + SKILL + phase7cd
W3  #931 → #932 → early-exit ............. SEQUENTIAL — graph/state/chain (highest blast radius)
W4  #935 ∥ #927 ∥ #928 ∥ #929 ∥ #925 ..... PARALLEL (subagents B–F) — disjoint Atlas/cost files
#926 benchmark .......................... PARALLEL, SEPARATE BRANCH/PR (subagent G)
```
Rule: W1<W2<W3 are strictly ordered (shared files + behavioral dependency). W4 tasks touch disjoint files (`_node_factory.py` vs `phase7_synthesis.py` vs `preflight.py`/phase2 vs triage/phase1 vs loaders/mcp) and run in parallel worktrees, integrated onto `task/930` after each returns green. The early-exit guard lands last in W3 (needs W4 triage signals reliable → its ticker-level half may be split to a W4 follow-up commit if triage changes land first).

---

## Wave 0 — Architecture record (parallel, do first)

### Task 0: ADR-0020 + supersede ADR-0019
**Files:** Create `docs/adr/0020-olympus-mvp-daily-delta.md`; Modify `docs/adr/0019-unified-atlas-workflow.md` (status line), `docs/adr/README.md` (index).
**Contract:** ADR records 3 decisions — (1) Hermes-lite collapse (1 analyst + 1 PM + deterministic 7E on delta), (2) PM direction-only / 7E deterministic feasible-set sizer, (3) `commit_run` terminal write from final weights — plus the delta cost contract (≤20 calls) and the OFF-by-default sequencing rule. Cite the spec + audit §6.5 (correlation) + ADR-0015 boundary.
- [ ] Write ADR-0020 (follow the `0000-template.md` shape; Status: Accepted).
- [ ] Edit ADR-0019 Status → "Superseded in part by [ADR-0020]" with one-line reason (Hermes-cheap premise invalidated by Jun-19 forensics).
- [ ] Add ADR-0020 to `docs/adr/README.md` index.
- [ ] `make doc-check` green; commit `docs(adr): ADR-0020 Olympus MVP daily-delta (#930)`.
**Acceptance:** doc-check OK; ADR-0019 shows the supersede note. **This is the human-gate artifact — surfaced for user validation at PR review.**

---

## Wave 1 — Continuity foundation (sequential)

### Task 1 — #936 held-ticker focus-slate invariant
**Files:** Modify `hermes/candidates.py` (`select_focus_tickers`), the chain/graph caller that builds the focus list (`hermes/chain.py` / `hermes/graph.py` — locate the `select_focus_tickers` call), `hermes/docs/ARCHITECTURE.md`. Test: `tests/dq/hermes/test_candidates.py`, `tests/dq/hermes/test_chain_atlas_then_hermes.py`.
**Contract:** Focus list is built **after** preflight hydrates `prior_book`; holdings passed as `holdings=holdings_from_prior_book(state.prior_context.prior_book)` (not the stale `portfolio.json`/CLI path). Add a hard invariant: every `prior_book` ticker appears in the 7C fan-out (or an explicit carry path tagged `prior_analyst_gaps`); **warn-log if a held ticker is ever absent** (should never happen).
- [ ] Failing test: prior book {SPY, IJR, XLP} with low technicals → `select_focus_tickers(...)` includes all three; held ticker absent → warning logged.
- [ ] Wire hydrated `prior_book` holdings into the focus call; add invariant + warn-log.
- [ ] Integration test in `test_chain_atlas_then_hermes.py`: held IJR survives a delta fan-out.
- [ ] pytest + ruff green; update ARCHITECTURE.md focus-list note; commit `fix(hermes): held tickers always in 7C focus slate (#936)`.
**Acceptance:** held names never dropped from fan-out; warn-log on the impossible case.

### Task 2 — #937 wire prior_analyst_gaps into PM skill
**Files:** Modify `hermes/skills/pm-rebalance-decision/SKILL.md`. Test: a skill-template snapshot test under `tests/dq/hermes/` (assert the input is documented).
**Contract:** Add `prior_analyst_gaps` to the Inputs list (held tickers missing fresh analyst output, with carried prior summaries); strengthen the existing line-44 rule to reference it: PM must treat a gap entry as valid analyst context and must **not** exit a held name solely for `analyst_payloads` absence when a gap entry exists.
- [ ] Failing snapshot test: PM skill body contains `prior_analyst_gaps`.
- [ ] Edit SKILL.md: add the input + the explicit no-exit-on-gap rule.
- [ ] Test green; commit `docs(hermes): document prior_analyst_gaps in PM skill (#937)`.
**Acceptance:** snapshot asserts the input present; rule explicit.

---

## Wave 2 — Sizing authority + debate (sequential)

### Task 3 — #934 PM direction-only + 7E deterministic feasible-set sizer (+ correlation, +turnover, +waterfall)
**Files:** Modify `hermes/skills/pm-rebalance-decision/SKILL.md` (remove the sizing instructions — Phase B step 3 / min-max / round-to-5% — PM now emits direction + conviction rank + rationale only); `hermes/phases/phase7d_pm.py`; `hermes/phases/phase7e_risk_sizing.py` (becomes sole sizer); a new `hermes/sizing.py` (or extend `hermes/turnover.py`) for the covariance + sizer recipe; `digiquant/ARCHITECTURE.md`. Tests: `tests/dq/hermes/test_phase7e_risk_sizing.py`, `tests/dq/hermes/test_sizing.py`, new `tests/dq/hermes/test_covariance.py`.
**Contract (the sizer recipe — spec §Research-informed refinements):** 7E owns all magnitudes. Inputs: PM direction/ranks + analyst conviction + debate delta + prior book. Pipeline: EWMA vols (λ≈0.94, ≤63d) → Ledoit-Wolf shrinkage-to-constant-correlation (≤252d) → clip ρ∈[−0.95,0.99] → PSD-repair (shrink-to-identity on neg eigenvalue) → thin-history asset-class bucket fallback (blend by obs count) → recombine `Σ=D·R*·D` → inverse-vol base → bounded conviction tilt (≤½-Kelly) → optional ERC nudge → vol-target gross lever (capped ≤1.0) → per-name/asset-class/cash caps (respect #874 floors). No-trade bands (≈20% rel + 5% abs, rebalance-to-edge). Cash = residual. Published `pm-rebalance` carries `pm_intent` + `sized_portfolio`. Neutralize dead `portfolio-manager`/`pm-allocation-memo` fallbacks.
- [ ] Failing test (covariance): ρ=1.0 stub replaced — an equity/bond book gets diversification credit; portfolio vol < the ρ=1.0 value; matrix is PSD; thin-history (<40 obs) falls back to buckets.
- [ ] Failing test (over-cashing regression): a correlated multi-name book no longer parks the majority in one bond ETF vs the ρ=1.0 baseline.
- [ ] Implement `hermes/sizing.py` covariance + layered sizer (numpy/Polars; ~PSD repair via eigenvalue check).
- [ ] Failing test (authority): PM proposes 5 ranked names (no weights) → 7E emits the sized book; landed `positions` == published `sized_portfolio`.
- [ ] Edit PM SKILL.md to direction-only; wire `phase7d_pm.py` to emit ranks; `phase7e` to size; remove dead waterfall fallbacks.
- [ ] Failing test (turnover band): within-band drift → hold; breach → trade-to-edge.
- [ ] pytest (hermes) + ruff + score green; update `digiquant/ARCHITECTURE.md` allocator section; commit `feat(hermes): PM direction-only + 7E deterministic sizer with correlation+turnover (#934)`.
**Acceptance:** over-cashing regression passes; PM emits no weights; book == published sized_portfolio; bands control turnover. **Highest-value task — get the covariance recipe right.**

### Task 4 — #933 debate gating
**Files:** Modify `hermes/phases/phase7cd_debate.py`, `hermes/docs/ARCHITECTURE.md`. Test: `tests/dq/hermes/test_phase7cd_debate.py`.
**Contract:** Before 7CD: tight 4-axis agreement (stance spread + `|conviction|≤thr`) OR held ticker w/ unchanged `prior_analyst` → deterministic `DebateSummary(neutral, delta=0)`, 0 LLM calls. Always full debate when `|conviction|≥3`, stance includes sell, or prior_analyst materially changed. Flag `HERMES_DEBATE_GATING=1` (default on for delta). Gate on the agreement signal (not self-reported confidence). When debate runs: anonymize bull/bear identities; allow a heterogeneous bear model. Telemetry: gated-vs-full counts into diagnostics.
- [ ] Failing test: agreement → 0 LLM calls, deterministic summary; disagreement (|conv|≥3 or sell) → full 7CD path invoked.
- [ ] Implement the gate + anonymization + counts.
- [ ] pytest + ruff green; ARCHITECTURE.md note; commit `feat(hermes): debate gating — skip 7CD on agreement (#933)`.
**Acceptance:** rubber-stamp → 0 calls; real disagreement → full debate; counts recorded.

---

## Wave 3 — Structural collapse + terminal write (sequential, highest blast radius)

### Task 5 — #931 Hermes lite graph (+AnalystPayload.risks)
**Files:** Modify `hermes/graph.py` (add `build_hermes_phases_lite` / `OLYMPUS_HERMES_LITE`), `hermes/phases/phase7c_analyst.py` (new `phase7c_unified` 1-call path; wire `AnalystPayload.risks` from bear case, not hard-`""`), `hermes/state.py` if needed, `atlas/testing/simulator.py` (A/B harness), `digiquant/ARCHITECTURE.md` + `hermes/docs/ARCHITECTURE.md`. Tests: `tests/dq/hermes/test_phase7c_specialists.py`, new `tests/dq/hermes/test_hermes_lite.py`.
**Contract:** `build_hermes_phases_lite` (flag/`OLYMPUS_HERMES_LITE=1`, **OFF by default**): `phase7c_unified` (1 call/ticker, one flat `AnalystPayload` schema — keep it flat for cheap-model reliability) → `phase7d_pm` (no risk agg/cons debate) → skip Phase 9 LLM. Delta path skips 7CD via #933 gating. Backward-compatible publish keys. A/B harness compares lite vs full call counts.
- [ ] Failing test: N=8 focus tickers on the lite path → ≤10 Hermes LLM nodes; `AnalystPayload.risks` non-empty when bear case exists.
- [ ] Implement unified analyst + lite builder + simulator A/B.
- [ ] pytest + ruff + score green; ARCHITECTURE×2 updated; commit `feat(hermes): lite graph collapse — unified analyst + deterministic 7E (#931)`.
**Acceptance:** lite path ≤10 nodes for N=8; baseline unchanged (full graph); flag OFF by default.

### Task 6 — #932 commit_run terminal phase
**Files:** Modify `hermes/chain.py` (`build_commit_phase` replacing the separate publish→materialize→digest tail), `digiquant/ARCHITECTURE.md`. Tests: `tests/dq/hermes/test_portfolio_materialize.py`, new `tests/dq/hermes/test_commit_run.py`.
**Contract:** After 7E: one `commit_run` upserts `positions`/`nav_history`/`theses` then publishes `pm-rebalance` + `run_summary` from the **same final weights**. Idempotent `decision_log` append on `(run_date, ticker)`. Move `persist_pending` out of Phase 9 into commit (Phase 9 LLM optional/deferred). Fail-closed: abort publish if the sized book fails coherence checks. **Preserve the cheap learning-loop resolver (`preflight_reflect`) — only the Phase-9 improvement-proposals artifact goes dark on delta.**
- [ ] Failing test: 7E changes PM weights → published `pm-rebalance.recommended_portfolio` == `positions`; re-run same `(run_date,ticker)` → decision_log not duplicated; incoherent book → publish aborted.
- [ ] Implement `build_commit_phase`; rewire chain terminal tail.
- [ ] pytest + ruff + score green; ARCHITECTURE.md chain diagram; commit `feat(olympus): commit_run terminal write from final weights (#932)`.
**Acceptance:** brief == positions; decision_log idempotent; fail-closed on incoherence; preflight_reflect intact.

### Task 7 — delta early-exit + per-ticker fingerprinting (fold)
**Files:** Modify `hermes/chain.py` / `run_atlas_then_hermes`, `atlas/triage.py` or the focus/fingerprint layer. Test: new `tests/dq/hermes/test_delta_early_exit.py`.
**Contract:** (a) run-level — zero stale segments → write `no-op delta` diagnostics row, return without invoking Hermes; (b) ticker-level — fingerprint each focus ticker's inputs (price move, news hash, prior stance); unchanged → carry prior thesis with 0 LLM calls; changed → patch-not-regen where feasible.
- [ ] Failing test: zero-stale triage → Hermes never built, no-op row written; unchanged ticker → no analyst call, carried thesis.
- [ ] Implement guards (run-level first; ticker-level may land as a follow-up commit after W4 triage).
- [ ] pytest + ruff green; commit `feat(olympus): delta early-exit + per-ticker fingerprint carry (#930)`.
**Acceptance:** no-op delta skips Hermes; unchanged tickers cost 0 calls.

---

## Wave 4 — Cost + Atlas research/triage (PARALLEL subagents, disjoint files)

### Task 8 — #935 shared context diet (+token-budget.md)
**Files:** `atlas/phases/_node_factory.py`, `atlas/docs/RUNBOOK.md`, `docs/atlas/token-budget.md`. Test: `tests/dq/atlas/test_phase_tool_flags.py` (+ new context-budget assertion).
**Contract:** Phase-aware context: delta omits 5-snapshot history (inject `bias_row` + changed segments only); per-phase `data_layer` allowlist; analyst gets ticker-scoped context, PM portfolio-scoped. Target ≥30% avg prompt-token drop on simulator delta. Refresh `token-budget.md` to OpenRouter `OLYMPUS_MODEL_TIER` reality (drop the Gemini→Grok text). Preserve stable→volatile cache ordering.
- [ ] Failing test: delta context byte budget below a threshold; per-phase allowlist honored.
- [ ] Implement diet; update RUNBOOK + token-budget.md.
- [ ] pytest + ruff green; commit `perf(atlas): shared-context diet for delta (#935)`.

### Task 9 — #927 today-only digest + strip trade verbs
**Files:** `atlas/phases/phase7_synthesis.py`. Test: `tests/dq/atlas/test_phase67.py` / `test_phase7_synthesis_regime_fed.py`.
**Contract:** `_bodies()` returns only `payload.source == "today"` (parity with `_body()`); `_enforce_research_only_boundary` rewrites/rejects trade verbs (overweight/underweight/reduce exposure) in `actionable_summary`; published snapshot watchlist-language only, `portfolio_recommendations` empty (already zeroed).
- [ ] Failing test: carried-segment delta → digest prompt smaller; trade verbs stripped from actionable_summary.
- [ ] Implement; commit `fix(atlas): today-only digest inputs + strip trade verbs (#927)`.

### Task 10 — #928 Phase2 institutional circuit-breaker
**Files:** `atlas/phases/preflight.py`, `atlas/phases/phase2_institutional.py`, diagnostics. Test: `tests/dq/atlas/test_phase12.py` / new.
**Contract:** Preflight flag `institutional_data_available` from ingest/prior publish; delta skips `inst-*` (deterministic absent stub) when false ≥3 consecutive runs; baseline always runs Phase2; diagnostics show skipped/carried + zero search spend when skipped.
- [ ] Failing test: flag false ≥3 runs on delta → inst-* skipped, stub emitted, zero search; baseline → runs.
- [ ] Implement; commit `perf(atlas): Phase2 institutional circuit-breaker on delta (#928)`.

### Task 11 — #929 triage rules for alt nodes
**Files:** `atlas/triage.py` (+ `_default_rules`), `atlas/phases/phase1_altdata.py`. Test: `tests/dq/atlas/test_phase_tool_flags.py` / new triage test.
**Contract:** `alt-onchain-positioning` carries/skips when preflight Hyperdash injection unchanged; `alt-ai-portfolios` baseline-only regen unless `AI_PORTFOLIOS_DELTA=1`; guard test: `evaluate()` segment count == compiled graph.
- [ ] Failing test: delta with unchanged onchain → carried; ai-portfolios → baseline-only.
- [ ] Implement; commit `perf(atlas): triage rules for alt-onchain + alt-ai-portfolios (#929)`.

### Task 12 — #925 deliberation carry + MCP query_data
**Files:** `atlas/data/` loaders (`load_prior_deliberation_summaries`), `digiquant/.../mcp_server.py`, `hermes/phases/phase7cd_debate.py` (phase_inputs). Test: new loader + MCP tool tests.
**Contract:** `load_prior_deliberation_summaries` + 7CD `prior_deliberation` phase_input for held tickers (slim excerpts, not full dump); MCP tool(s) wrapping `query_data` with the same table allowlist as in-process agents (`positions`,`nav_history`,`theses`,`documents`); delta triage skip for held tickers w/ unchanged prior stance.
- [ ] Failing tests: loader returns slim prior deliberation; MCP tool enforces allowlist; triage skip on unchanged stance.
- [ ] Implement; commit `feat(hermes): deliberation carry + MCP query_data (#925)`.

> **W4 note:** Tasks 9–11 touch disjoint Atlas phase files; Task 8 (`_node_factory`) and Task 12 (`phase7cd_debate` phase_inputs) may lightly overlap W2/W3 edits — integrate Task 8/12 *after* W3 lands to avoid churn, or assign them to the orchestrator.

---

## Separate — #926 open-weight JSON reliability benchmark (own branch/PR)

### Task 13 — #926 benchmark (branch `task/926-openweight-json-benchmark`)
**Files:** new `scripts/atlas/benchmark_openweight_json.py` (or `digiquant/scripts/`), results doc. No pipeline-behavior change.
**Contract:** Benchmark strict-JSON adherence of cheap OpenRouter open-weight models (Qwen 3.x, Mistral Small, DeepSeek, Llama, Gemma) against the load-bearing Olympus schemas (analyst, PM). Methodology from spec: `json_schema` strict where supported, verify `supported_parameters=structured_outputs` per provider, 3-layer parse→heal→retry, keep schemas flat. Produce a ranked reliability table → informs which cheap model the lite path uses, and **gates flipping the collapse default-on.**
- [ ] Implement benchmark harness; run against a small schema set; write results doc.
- [ ] commit + PR `feat(olympus): open-weight JSON reliability benchmark (#926)`.
**Acceptance:** ranked table of model × schema-compliance; recommendation for the cheap tier.

---

## Verification / exit gates (whole branch, before PR)

Run on `atlas/testing/simulator.py` after W3, re-confirm after W4:
- [ ] Delta run on simulator: **≤20 LLM calls, ≤180s, ≤$1.50** on `OLYMPUS_MODEL_TIER=cheap` (lite path ON in the sim only).
- [ ] Operator brief weights == `positions` within tolerance.
- [ ] `decision_log` idempotent on retry; resolved lessons reach PM `past_context` (cheap resolver intact).
- [ ] Prior book + unchanged conviction → no full rewrite (turnover bands hold).
- [ ] Full `tests/dq` + `tests/dg` green; repo-wide ruff 0.15.18 clean; `make score` ≥ thresholds; `make doc-check` OK.
- [ ] Baseline path unchanged (full graph, lite OFF by default).

## Final passes (after PRs filed, before merge)

- [ ] `simplify` skill + `code-review` skill on the diff (deslop).
- [ ] pr-review-toolkit subagents (code-reviewer, silent-failure-hunter, pr-test-analyzer) on the PR.
- [ ] Flag `/code-review ultra` for the user to trigger (billed, user-only).
- [ ] **STOP — await user validation for every merge.**

## Self-review (spec coverage)

- #925✓(T12) #927✓(T9) #928✓(T10) #929✓(T11) #931✓(T5) #932✓(T6) #933✓(T4) #934✓(T3) #935✓(T8) #936✓(T1) #937✓(T2); folds: correlation✓(T3) turnover✓(T3) waterfall✓(T3) risks✓(T5) early-exit✓(T7) ADR✓(T0) token-budget✓(T8) #926✓(T13). Deferred: #924 (post 3 stable delta days). Follow-ups (file as issues, not built here): model cascade, FINCON/ContestTrade learning loop, regime MA tilt, net-of-cost reporting.
