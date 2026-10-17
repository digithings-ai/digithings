# Per-indicator window fitting + equal-weight selection (Plan 19) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Do what the owner asked, in the BTC order: for EVERY wired indicator, fit its z-transform (lookback window, growth horizon, oscillator params) to the pinned gold buy/sell windows, then select by equal-weight aggregate improvement (keep if the aggregate improves, drop if not) — then show the manipulated/z-scored series on a tearsheet and deliver the pass list.

**Owner spec (2026-10-02, verbatim intent):** "the way to know if an indicator is beneficial or not is just by equal weighing an aggregate index. And then if the aggregate index improves, we keep the indicator, if it doesn't we drop it… we could manipulate the underlying indicators, z scoring them, maybe scaling them differently, changing the time periods, etc… optimize the individual indicators, trying to fit it to the time periods first… going through all the indicators we've identified and have wired and trying to fit them to the time periods we determined to be buying and selling zone… then placing those indicators in the tearsheet so I could see how they've been manipulated and standardized in z scored. And give me a list of basically which indicators passed."

**Architecture (zero production edits):** every shipped z-function is already keyword-parameterized (`m2_liquidity_z(..., roc_days=, window=)`, `walcl_liquidity_z`, `uup_z`, `real_rate_z`, `gvz_z`, `hy_oas_z`, `ig_oas_z`, `breakeven_5y_z`, `nfci_z`, `gdx_gld_z`, `gld_slv_z`, oscillators via `SdcaOscillatorSpec` + `price_oscillator_z_vectors`). The fit harness CALLS them with different parameters (call-with-a-param, never reimplement math). Scoring reuses `gold_v1()` pins (±45d windows, landed 8510cbdf0) and the shipped overlap metric. Selection is greedy equal-weight forward selection from the no-trend anchor, in individual-fit-descending order (order frozen here so search noise can't pick the order).

**Frozen fit metric (pre-registered):** `separation = mean(z | peak windows) − mean(z | trough windows)`. All bars with valid z are in-sample; labeled in every artifact. This is calibration to pinned history — it fits windows, NOT weights on performance.

## Ruling 1 (Plan 19): metric sign CORRECTED + degenerate-oscillator rule (issued after Task-1 review adjudication)

The frozen sign was a CORRECTNESS BUG. Evidence: `composite_risk.py:57` `risk = 50 − composite_z×50/3` (high z = buy = cheap), and the shipped Stage-A objective `stage_a.py:88-99` `mean_risk(peaks) − mean_risk(troughs)` is algebraically `+(50/3)·(mean z|troughs − mean z|peaks)`. Correct definition (single, frozen from here): `separation = mean(z | trough windows) − mean(z | peak windows)`; `> 0` = votes cheap at bottoms. `abs()` is forbidden (would reward anti-correlated legs). Re-derivation: sign flip on the stored `mean_peak_z`/`mean_trough_z` — zero re-runs for separation; `sign_share` must be recomputed from raw z as (peak<0 / trough>0 shares) and is NOT recoverable by 1−x (dead-zone oscillators sit at exactly 0). Degenerate-oscillator rule: an indicator whose pass rests on |mean| ≤ 0.06 in every window (the dead-zone oscillators, `weekly_rsi`/`weekly_macd`) is recorded DEGENERATE-PASS — listed separately, never counted in the keep list without an explicit owner look. All 12 param sets change under the corrected metric; Task 2 must consume the corrected `best_*`, never the pre-correction report.

**Frozen grids:** level-z window ∈ {90, 180, 270, 378, 504, 756, 1260} (7); m2/walcl `roc_days` ∈ {90, 180, 365, 730} × window ∈ {180, 378, 756, 1260} (16); oscillators: read `price_oscillators.py` and `SdcaOscillatorSpec` fields first (VERIFY-FIRST — grid over rsi_length ∈ {14, 21} + internal windows it exposes; MACD fast/slow ∈ {(12,26),(8,34)} × z_window ∈ {90, 378}; sma_band sma_window ∈ {200, 378, 1000} × k ∈ {2, 3}). Tie-break: higher separation → SHORTER window (parsimony). Medium read = best with window ≤ 378; long read = best with window ≥ 504 (both reported per indicator).

**Selection rule (frozen):** base = equal-weight `{valuation: 1.0}` on rolling90/z1.0 rails (the no-trend anchor). Candidates = every indicator whose individual best-fit separation > 0, ordered by separation descending (frozen order). For each candidate: add at equal weight alongside all kept-so-far, recompute equal-weight aggregate separation; keep if aggregate separation STRICTLY improves, else drop (record the delta for every candidate — that table IS the deliverable). Report also the pure equal-weight-of-individual-passers aggregate as a cross-check (never used for selection). Grid 0/500 (hy/ig data starts 2023, last trough ends 2022-12-05 — provably unscoreable; listed, not silent).

## Global Constraints

- Research-only. ZERO production-code edits (scripts + tests + docs only). No engine/catalog/settings/workflow changes. No push, no merge (owner-side). No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential. Never force-push.
- Holdout stays spent (never touched). No gate runs in this plan (Stage-B judging is a later plan). No-trend steer: anchor is rolling90/z1.0; no trend rails here.
- Frozen: grids, metric, tie-breaks, selection order/rule, ±45d windows. Report deviations, don't invent.
- Standing owner rules: visuals on every iteration (Task 3 is the owner's explicit deliverable); temp preview edits uncommitted with REVERT-BEFORE-MERGE markers.

---

### Task 1: Fit harness + per-indicator fits (TDD on the metric)

**Files:**
- Create: `digiquant/scripts/fit_gold_indicators.py` (grid runner + `--fit` mode; pure functions `fit_indicator(...)`, `separation(z, windows)`, `indicator_grid(name)` VERIFY-FIRST against `price_oscillators.py`/`SdcaOscillatorSpec`; calls shipped z-functions only)
- Create: `tests/dq/strategies/sdca/test_gold_indicator_fitting.py` (metric tests via importlib, mirroring the Plan-12 script-import test pattern): synthetic z with known peak/trough means → exact separation; sign convention (positive = rich-at-tops); coverage/None handling; grid-completeness (every wired name has a grid; hy/ig produce empty-and-reason, not silent skip)
- Create (untracked): `digiquant/.scratch/gold_indicator_fits.json` (per indicator: full grid rows {params, separation, sign share, coverage}, best-medium, best-long, best overall)

**Interfaces:**
- Consumes: `gold_v1()` pins; `load_sdca_extra_sources` + GLD closes (verify the exact loader call for oscillator inputs); shipped z-functions.
- Produces: fits file. Task 2 selects; Task 3 renders.

- [ ] **Step 1: Failing tests first (metric + grid completeness)** → RED.
- [ ] **Step 2: Implement (calls shipped z-functions with params; no reimplementation; param grids exactly as frozen)**

STOP: a grid needs a NEW indicator math path → NEEDS_CONTEXT. STOP: an indicator's shipped signature doesn't accept the parameter → record + report (do not extend the catalog in this plan).
- [ ] **Step 3: Run (background if slow; wall + exit), lint, commit script + tests (#4804); output untracked**

Report: full fits table (name | best params | medium/long | separation | sign share | coverage), grid rows count per indicator, skip reasons.

---

### Task 2: Equal-weight selection (greedy, frozen order)

**Files:**
- Modify: `digiquant/scripts/fit_gold_indicators.py` (add `--select` mode reading the fits file + anchor; greedy loop; record every candidate's delta)
- Create (untracked): `digiquant/.scratch/gold_indicator_selection.json` (kept list with params, dropped list with deltas, aggregate series, cross-check aggregate)

**Interfaces:**
- Consumes: Task-1 fits; rolling90 anchor z (built with shipped `resolve_sdca_risk_model`/`build_risk_index` or the seed construction — reuse, read-first which is cleanest for an extras-only composite).
- Produces: the owner's keep/drop list. Task 3 renders it.

- [ ] **Step 1: Failing test for the greedy loop (synthetic z-vectors: keep-improver, drop-neutral, drop-hurter) → RED**
- [ ] **Step 2: Implement (rule verbatim: strict improvement → keep) + GREEN**
- [ ] **Step 3: Run, lint, commit (#4804); output untracked**

Report: kept/dropped table with deltas, aggregate separation trajectory, cross-check read.

---

### Task 3: OWNER DELIVERABLE — tearsheet + charts + pass list

**Files:**
- Create: `digiquant/scripts/build_gold_indicator_tearsheet.py` (per-owner: every fitted indicator's manipulated z-series as `indicator_curves` with the fitted params visible, buy/sell windows overlaid as markers, plus notes carrying the keep/drop table + the IN-SAMPLE label; mirror the v4/v5/v6 builders for schema shape)
- Create: `digiquant/scripts/plot_gold_indicator_fits.py` (multi-panel SVG: one panel per fitted indicator (z vs time + window markers), one aggregate panel; stdlib SVG pattern as established)
- Create (untracked): tearsheet JSON + public/ copies + chart SVGs
- Modify: `page.tsx` TEMP entry (REVERT-BEFORE-MERGE, uncommitted)

**Interfaces:**
- Consumes: Task-1+2 outputs.
- Produces: the owner's view + list. Verify: page/JSON/charts 200 (relaunch dev EXACTLY as before if down).

- [ ] **Step 1: Build + serve + verify**
- [ ] **Step 2: Lint + commit scripts (#4804); outputs/preview per standing rules**

Console + report MUST print the plain pass list (names + fitted params) — that is the owner's ask.

---

### Task 4: Docs + verify + close-out

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (append-only SDCA paragraph: metric, grids, per-indicator best fits, keep/drop table + deltas, IN-SAMPLE + holdout-absent labeling)
- Verify: suites + ruff + status

- [ ] **Step 1: ARCH + verify + commit (#4804)**

---

## Out of scope (not this plan — enforced by review)

- Production catalog/engine/settings/workflow edits (zero by construction).
- Stage-B gates / performance measurement (later plan; the owner explicitly wants fitting FIRST).
- Weight optimization of the aggregate (later plan, per owner).
- New indicators/legs not already wired; COT/Dow-gold (recon-listed only).
- Holdout, promotion, nightly, credentials, merge, push.

## Self-review

1. Spec coverage: metric+grid harness with tests → Task 1 (fail-first, shipped-call reuse, completeness incl. hy/ig reason); greedy equal-weight selection → Task 2 (frozen order/rule, every-candidate delta table, synthetic test); owner deliverable (tearsheet showing manipulation + z-scoring + windows; charts; pass list) → Task 3; docs + close-out → Task 4.
2. Placeholder scan: window grids, roc grid, file paths, JSON names, commands are literal; oscillator params VERIFY-FIRST (named sets to confirm against the real spec fields). STOPs name trigger + action.
3. Type consistency: `separation` metric name identical in code/tests/report/ARCH; `gold_indicator_fits.json` / `gold_indicator_selection.json` / `fit_gold_indicators.py` / `build_gold_indicator_tearsheet.py` / `plot_gold_indicator_fits.py` identical everywhere; "medium ≤378 / long ≥504" identical in plan, code, report.
