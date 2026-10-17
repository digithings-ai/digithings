# Gold cycle windows + Stage-A calibration (Plan 18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Do for gold what the BTC build did first: pin target buying/selling windows from documented cycle history, then calibrate indicator weights to best fit those windows (Stage-A cycle overlap), then judge the calibrated vote on behavior (oscillation) AND benchmarks (both) — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Standing facts:** All prior gold votes were fitted by walk-forward curve search, never to the cycle — result: 34 sell fills in 16 years. Owner direction 2026-10-02: expect visible buy↔sell oscillation; windows first, indicators calibrated to fit. Baseline oscillation: 34 sell fills / 16yr ≈ 2/yr (reselect diagnostic). No-trend steer holds (no time-trend fits; cycle windows are date pins, not regressors).

**Architecture:** Reuse the landed Stage-A machinery (`SdcaCycleWindows`, `optimize_stage_a_weights`, parsimony rule), then the landed two-stage fit (`regularized_weight_params` frozen into the walk-forward gate). New code: gold cycle profile only. New runs: Stage-A search (in-sample, reported as such) + Stage-B gate (the judge). New weights must clear BOTH the behavior bar (oscillates visibly more than baseline) and the benchmark bar to matter.

**Pre-registered cycle pins (documented history, frozen here):** highs 2008-03-17 (~$1033 pre-GFC top), 2011-09-06 (~$1920 secular top), 2020-08-07 (~$2070 covid high), 2026-09-29 (current run high, incomplete top — standard practice, btc_v1 does the same with 2025); lows 2008-10-24 (~$680 GFC washout), 2015-12-17 (~$1050 bear bottom), 2022-10-21 (~$1620 dip). Windows ±45d mirroring btc_v1. Rationale documented, dates from published market history + our own measured event table (mayer report) — no tuning (pins are history, not parameters).

**Oscillation bar (behavioral, reported not gated):** fills/yr and sell-days/yr vs the 34/16yr baseline — expect a multiple, exact factor reported. Benchmark bar (gated): mean OOS beats flat AND lump, feasible everywhere, sens ≤ 2.0 (same as ever). Tension disclosed: oscillation frequency trades against lump-beating in a bull — both numbers reported, no hiding.

## Global Constraints

- Research-only. No live-trading paths, no Supabase push, no merge/push (owner-side). No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.
- New production code: cycle profile ONLY. No engine/curve/composite/backtest/nautilus/providers/settings/preset/provenance/workflow edits. Any need = STOP with NEEDS_CONTEXT.
- Stage-A search is IN-SAMPLE — labeled as such in every artifact; it selects nothing shippable. Only the Stage-B gate judges. Holdout stays spent (ABSENT, stated).
- Frozen: pins above (±45d), parsimony rule (fewer extras then higher valuation on ties), benchmark bar. No generic_valuation/log fits.
- Standing owner rules: every iteration ships visuals (tearsheet + charts); temp preview edits stay uncommitted with REVERT-BEFORE-MERGE markers.

---

### Task 1: Gold cycle profile (pins + test)

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/cycle_windows.py` (add `gold_v1()` mirroring `btc_v1()` structure — read it first; documented peaks/troughs above, ±45d)
- Modify: `tests/dq/strategies/sdca/test_asset_profile.py` or the cycle-windows test home (grep first — extend, don't create): gold profile resolves, windows sane (ordered, non-overlapping, within GLD history 2004+, peak/trough counts match pins)

**Interfaces:**
- Consumes: pre-registered pins.
- Produces: `gold_v1()` profile. Task 2 searches against it.

- [ ] **Step 1: Failing test first (profile resolves with the pinned dates)**

Expect FAIL (no gold profile). Then implement (data entry only — no logic). GREEN: containing file FULL + engine subset green. Ruff clean. Commit (#4804).

---

### Task 2: Stage-A overlap search (in-sample, reported as such)

**Files:**
- Create (untracked): `digiquant/.scratch/gold_stage_a.json` (winner weights + separation score + full ranking + parsimony log)
- Modify: NONE (use the shipped `optimize_stage_a_weights` / `stage_a_search_names` path — read-first which entry point fits a research run: MCP helper `digiquant_fit_sdca_weights` vs direct `fit_sdca_weights_from_cache`; no new harness)

**Interfaces:**
- Consumes: `gold_v1()`; GLD cache + staged extras (generic technicals + gold plugins + real_rate — search every extra WITH DATA via `search_names_with_data`-equivalent; read-first the exact call).
- Produces: ranked weights + separation. Task 3 characterizes, Task 4 judges.

- [ ] **Step 1: Read-first (entry point + search-names + objective definition)**

Record: exact function + args used, what `search_names_with_data` includes for gold (list it — real_rate present?), the overlap objective formula (mean peak-window risk minus trough-window risk + band fractions per ARCH), parsimony rule site. STOP: entry point needs engine changes (NEEDS_CONTEXT).
- [ ] **Step 2: Run + report (no commits, output untracked)**

Run the search (background if slow; wall + exit recorded). Report: winner weights (full vector), separation score, top-5 ranking, parsimony decisions (what dropped and why), per-extra data availability (anything skipped for no-data), and the IN-SAMPLE label (one explicit sentence). No weight is adopted anywhere — nothing to commit.

---

## Ruling 1 (Plan 18): two-vote characterization + gating (issued after Task-2 review)

Task-2 review FLAGGED the steer interaction: the winner (valuation-only) rides frozen generic_valuation/log_quadratic trend rails — the in-sample trend fit voting for itself. Diagnostic use is legitimate; a trend-rails vote can NEVER be promoted for gold under the standing no-trend steer. Therefore Task 3 characterizes TWO votes, both read from the EXISTING ranking (no new search): (V1) the winner as specified, diagnostic behavior reference; (V2) the best valuation-free combo (all valuation weight 0 — the steer-compliant candidate; report its separation gap vs V1 honestly, however large). Task 4 gates BOTH through the identical Stage-B machinery (two evaluations, no new fitting): V1 promotion-BARRED by steer (measurement only — quantifies how much separation is the trend fit itself); V2 judged against the full BEHAVIOR-BEATS-BOTH bar. If V2 is unidentifiable from the persisted ranking → STOP with NEEDS_CONTEXT (exact gap), no re-search.

### Task 3: Behavior characterization (oscillation vs baseline)

**Files:**
- Create: `digiquant/scripts/build_gold_stagea_diagnostic_tearsheet.py` ONLY IF the existing diagnostic builders can't render a weights-only-different vote (read one first — if a `--weights`/`--seed` seam serves, reuse with zero edits and record that; mirror otherwise)
- Create (untracked): diagnostic JSON + oscillation chart (fills/yr + sell-days/yr + risk-band occupancy vs the 34/16yr baseline; stdlib SVG pattern) + public/ copies

**Interfaces:**
- Consumes: Task-2 winner weights; reselect curve HELD CONSTANT (isolates the vote change — state that); full-history curve-sim (diagnostic, labeled).
- Produces: behavior verdict (oscillates Y/N + multiple over baseline) + full-history vs flat/lump (diagnostic context, NOT gate claims).

- [ ] **Step 1: Build vote + backtest (frozen curve, new weights) + charts + serve-200s**

Risk index from the calibrated weights (same construction as v4 seed — reuse, don't rebuild); backtest with the reselect curve; charts: risk with buy/sell fills + fills-per-year bars. Serve checks (relaunch dev EXACTLY as before if down).
- [ ] **Step 2: Report behavior (no gate claims) + commit script if created (output untracked)**

Separation achieved, fills/yr + sell-days/yr vs baseline, diagnostic flat/lump (labeled diagnostic). If it does NOT oscillate more → NEGATIVE on behavior, stop (no gate — record why).

---

### Task 4: Stage-B gate (frozen Stage-A weights — the judge)

**Files:**
- Modify: NONE expected (freeze via `regularized_weight_params` as `strategy_params` `*_weight` keys per ARCH two-stage fit — read-first the exact mechanism; if a script edit is needed to pass weights through, minimal diff + STOP check that grid/gates/folds/objective are otherwise untouched)
- Create (untracked): `digiquant/.scratch/gold_curve_search_stagea.json` (+ stdout log)

**Interfaces:**
- Consumes: Task-2 weights (regularized per `regularize.py` — read-first whether regularization applies before freezing; record either way); same space/bars/geometry/objective/mask/causal loop as v6.
- Produces: gate record (vs_flat + vs_lump per fold + frontier-both + sens). Task 5 judges.

- [ ] **Step 1: Read-first (weight-freeze seam) + run (background, ~40s class) + FULL table**

Backup+sha256 discipline on all touched scratch files. Record wall + exit + winner shape + per-fold flat/lump/deployed/dd/feasible + sens + neighbor key + means + both beats flags + frontier-both + mask-day stats + holdout-absence.
- [ ] **Step 2: Lint + commit (seam edit if any; outputs untracked)**

---

### Task 5: Verdict + visuals + docs (no new runs)

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (append-only SDCA paragraph: pins, Stage-A winner + separation, behavior multiple, gate verdict, disclosures)
- Verify: relevant suites + ruff + status.
- Visuals: gate-outcome charts + diagnostic tearsheet served per standing rule (page entry ONLY on BEATS-BOTH).

- [ ] **Step 1: Judge (behavior AND benchmarks)**

BEHAVIOR-BEATS-BOTH requires: fills/yr multiple over baseline (visible oscillation — state the factor) AND mean OOS beats flat AND lump AND feasible everywhere AND sens ≤ 2.0. Name every failed condition on NEGATIVE. No re-runs, no re-freezing.
- [ ] **Step 2: Visuals + docs + verify + commits (ARCH; scripts if created; outputs/preview per standing rules)**

---

## Out of scope (not this plan — enforced by review)

- Pin changes after seeing results (history doesn't move).
- Weight/space/objective/mask/threshold tuning; re-selection; sens re-runs; holdout (spent).
- Engine/curve/composite/backtest/nautilus/providers/settings/presets/provenance/workflows edits (profile-only plan).
- New indicators/legs (search covers the existing catalog incl. real_rate; nothing new coded).
- Nautilus enablement, broker paths, Supabase, nightly, credentials, merge.

## Self-review

1. Spec coverage: pins + test → Task 1 (fail-first, data-entry-only); shipped-path Stage-A search with in-sample labeling → Task 2 (read-first entry point + search-names + objective + parsimony, no commits); frozen-curve behavior characterization + oscillation multiple → Task 3 (reuse-or-mirror builder, charts, serve proofs, behavior NEGATIVE stops the plan); frozen-weight Stage-B gate → Task 4 (read-first freeze seam, full table + frontier + mask stats); verdict on both bars + visuals + docs → Task 5.
2. Placeholder scan: pin dates, ±45d, file paths, JSON names, commands, bars are literal. STOPs name trigger + action. Brief guesses at seams are VERIFY-FIRST.
3. Type consistency: `gold_v1()` vs `btc_v1()`/`eth_research_v1()` naming; `gold_stage_a.json` / `gold_curve_search_stagea.json` / `build_gold_stagea_diagnostic_tearsheet.py` identical everywhere; Stage-A (in-sample fit) vs Stage-B (walk-forward judge) never conflated in language.
