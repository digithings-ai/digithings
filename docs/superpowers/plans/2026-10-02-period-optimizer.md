# Generic period optimizer + perfect-strategy oracle (Plan 20) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the generic machinery the owner asked for — a perfect-strategy oracle with risk-adjusted metrics, a two-horizon (medium/long) buy-sell PERIOD optimizer, and the progressive combination — as reusable digiquant optimizers, then run it on gold. Research-first: this defines periods; performance measurement comes later.

**Owner spec (2026-10-02):** "the identified period for buying and selling arent good… 1 script for long term tops and bottoms, and second for medium term… imagine the perfect strategy with those periods — if we bought and sold perfectly during those periods what would be the returns and risk adjusted return metrics… if our periods are well identified, our returns should be higher… create optimizers for this… it's a pretty generic task… reproduce that for any dollar cost averaging strategy."

**Recon (this session, evidence-backed):** the BTC method only PINNED windows — `_HALF_WINDOW = 45d` is a module constant (`cycle_windows.py:16,44-45`, two repo-wide refs) and both `cycle_windows.py:3-6` and `ARCHITECTURE.md:1099` forbid the optimizer inventing dates. MUST BUILD: oracle, `buy_dates` twin, CAGR/Sharpe/Sortino/Calmar (today only Nautilus dict-key reads in `tearsheet_stats.py:80,85-87`), `time_in_market`. EXISTS + REUSED: `CycleWindow`/`SdcaCycleWindows` data model (`cycle_windows.py:24-71`), separation objective (`fit_gold_indicators.py:427-440`), two-horizon banding idiom (`fit_gold_indicators.py:674-688`), `sell_dates` veto (`backtest.py:112,185-192`), `SdcaBacktestReport` metrics, lump/flat comparators (`dca_metrics.py:51-79`).

**Architecture (new generic core modules, asset-agnostic):**
- `digiquant/src/digiquant/strategies/sdca/perfect_strategy.py` — the oracle: given dates+prices+buy/sell date sets, the all-in/all-out equity path + `PerfectStrategyMetrics` (total/CAGR return, Sharpe, Sortino, Calmar, max DD, time-in-market).
- `digiquant/src/digiquant/strategies/sdca/risk_metrics.py` — pure-Python/Polars risk-adjusted metrics over an equity path (annualization factor + convention documented; reuse `walk_forward.max_drawdown_magnitude_pct` for DD).
- `digiquant/src/digiquant/strategies/sdca/period_optimize.py` — two-horizon period optimizer: candidate window discovery from price structure, scoring by oracle risk-adjusted metrics under an exposure floor, split-sample validation, medium+long combination (long sells override medium buys).
- Thin CLI wrappers: `digiquant/scripts/optimize_sdca_periods.py` (asset-agnostic) + `digiquant/scripts/run_gold_period_optimization.py` (gold wiring).

**Frozen objective (owner-ruled 2026-10-02):** maximize oracle risk-adjusted quality — primary = Sharpe, tie-break Calmar, then CAGR — subject to a **time-in-market floor of 70% of days in market**. Objective formula and floor are module constants with the owner's ruling cited; not tunable in this plan. Selection always reports: exposure, all metrics, and the split-sample check.

**Frozen horizons:** medium = swing-scale windows (candidate half-widths 15–60d, minima ≥ 2 peaks/2 troughs); long = cycle-scale (half-widths 60–180d, minima ≥ 2/2). Grid + discovery rule frozen in the modules; changes are a later plan.

**Honesty frame (mandatory in every artifact):** the oracle is an in-sample CEILING on the same history the periods were fit on — it measures period quality, never achievable performance. The split-sample check (fit on first half, score on second half) is the only out-of-sample-ish read and must be reported next to it. Holdout stays spent (never touched).

## Global Constraints

- Research-only except the three NEW core modules + their tests + thin CLI wrappers. No edits to `backtest.py`/`curve_sim.py`/`nautilus_strategy.py`/`curve.py`/`composite_risk.py`/`stage_a.py`/`cycle_windows.py` pin factories/settings/workflows (the new modules CONSUME `SdcaCycleWindows`, they never mutate a named factory). No push, no merge (owner-side). No pandas, pydantic v2 (frozen strict models), ruff 100. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential. Never force-push.
- **Zero `nautilus_trader` import** in the new modules (SDCA core rule, `digiquant/AGENTS.md` § SDCA Engine) — pure Python/Polars. Review gate.
- Every new module gets `tests/dq/strategies/sdca/test_<module>.py` (39-file convention) with TDD fail-first.
- Standing owner rules: visuals every iteration (Task 4); temp preview edits uncommitted with REVERT-BEFORE-MERGE markers.

---

### Task 1: Risk metrics + oracle core (TDD)

**Files:**
- Create: `digiquant/src/digiquant/strategies/sdca/risk_metrics.py` (`equity_metrics(values, *, annualization=252) -> RiskMetrics`: total_return_pct, cagr_pct, sharpe, sortino, calmar, max_drawdown_pct — pure Polars; DD reuses `walk_forward.max_drawdown_magnitude_pct`)
- Create: `digiquant/src/digiquant/strategies/sdca/perfect_strategy.py` (`perfect_strategy_path(dates, prices, buy_dates, sell_dates, initial_cash) -> (values, exposure)`, `perfect_strategy_metrics(...) -> PerfectStrategyMetrics`; all-in during buy sets, flat during sell sets, neutral dates = HOLD previous position (documented choice); exposure = invested-days/total)
- Create: `tests/dq/strategies/sdca/test_risk_metrics.py` + `test_perfect_strategy.py` (synthetic paths with known CAGR/Sharpe/DD; monotonic series; flat series edge; all-buy path equals lump `dca_metrics.lump_mark_to_market` — parity pin)

**Interfaces:**
- Consumes: nothing new (pure functions over sequences).
- Produces: metrics + oracle. Task 2 optimizes over it.

- [ ] **Step 1: Failing tests first** → RED (parity pin vs `lump_mark_to_market` for all-buy).
- [ ] **Step 2: Implement (minimal; conventions documented in docstrings: 252 annualization, risk-free 0, Sortino downside deviation)**
- [ ] **Step 3: GREEN (both new files + backtest/walk_forward parity untouched) + lint + one commit per module + tests (#4804)**

STOP: parity pin fails on the lump comparison → fix the oracle, never the comparator.

---

### Task 2: Two-horizon period optimizer (TDD)

**Files:**
- Create: `digiquant/src/digiquant/strategies/sdca/period_optimize.py` (`PeriodHorizon` frozen model {name, half_widths, min_peaks, min_troughs}; `discover_candidate_periods(dates, prices, horizon) -> Sequence[CycleWindow]` from documented price structure — swing pivots for medium, cycle-scale peaks/troughs for long; `score_periods(dates, prices, windows, *, exposure_floor_pct=70.0) -> PeriodScore` using oracle Sharpe primary / Calmar tie-break / CAGR tertiary; `optimize_periods(dates, prices, horizon) -> PeriodOptimizationResult` with the full candidate table; `combine_periods(medium, long) -> SdcaCycleWindows` (long sells override medium buys); `split_sample_check(dates, prices, horizon, split=0.5)` — fit on first half, score on second half, both metrics reported)
- Create: `tests/dq/strategies/sdca/test_period_optimize.py` (synthetic zigzag with KNOWN optimal windows → optimizer recovers them; exposure floor enforced (a flat-price series fails the floor); split-sample on a regime-shifted series reports both sides; combine precedence; window counts ≥ minima)

**Interfaces:**
- Consumes: Task-1 oracle + `SdcaCycleWindows`/`CycleWindow` data model.
- Produces: generic period optimizer. Task 3 runs gold.

- [ ] **Step 1: Failing tests first** → RED (recovery-of-known-windows is the key pin).
- [ ] **Step 2: Implement (discovery + scoring + combine + split-sample; frozen grids from the header)**
- [ ] **Step 3: GREEN + lint + commit (#4804)**

STOP: discovery cannot be defined from price structure without inventing ad-hoc dates (the `cycle_windows.py:3-6` prohibition) → NEEDS_CONTEXT with the exact gap; the rule for this plan: candidate windows must be DERIVED from the price series by documented pivot logic, never hand-entered.

## Ruling 2 (Plan 20): unique pivots + Calmar epsilon (issued after Task-2 review)

Task-2 review found the plateau predicate false as documented: `here == max(window) and any(p < here)` makes EVERY bar of a flat plateau a pivot, so `min_peaks=2` is satisfiable by one real pivot on a 2-bar plateau (GLD has flat closes — plausible-to-likely), and the "unique pivot" docstring is untrue. Binding for Task 2b: require the max/min be attained UNIQUELY within the confirmation neighbourhood (or keep the first-attaining index), correct the docstring to match, and add a plateau pin (a rise→flat→fall fixture must yield ONE peak pin). Calmar: selection is unaffected (tuple key consults Calmar only on exact Sharpe equality, and eligibility gates `best`), so the MINIMAL fix is at the read layer — Task 3 prints blank/None when `max_drawdown_pct < eps`; no `risk_metrics.py` edit is authorized in this plan (the epsilon clause in `risk_metrics.py:145` is a filed follow-up). Reporting obligation (from the same review): each horizon's optimum is reported against ITS OWN grid — never as a cross-grid contest.

## Ruling 1 (Plan 20): exit edges mandatory + zero-stdev tie rule (issued after Task-1 review)

Task-1 review found a real misread trap: because the oracle HOLDS on neutral dates, a window converted to dates WITHOUT an exit edge is held to end-of-history, so every candidate saturates exposure (~100%) and the frozen 70% floor stops discriminating. Binding for Task 2: every emitted window MUST produce BOTH edge dates (enter + exit) — windows are closed intervals converted to explicit [enter, exit] date pairs, and a candidate whose last window would hold past the final bar is truncated at the last bar (recorded). Second binding: a zero-stdev path (constant growth) reports `sharpe == 0.0` and ties the all-cash flat comparator — document an explicit tie rule (zero-stdev candidates rank BELOW any positive-Sharpe candidate and are labeled degenerate, never silently equal). Two LOW fixes ride Task 2 in the same commit as small doc/test edits: (a) tighten the lump parity pin to EXACT equality (`assert values == lump`) since the paths are bitwise-equal; (b) raise the same minimum-length guard in `perfect_strategy_metrics` that `equity_metrics` raises, so a 1-day calendar fails at the wrapper with a clear message.

---

### Task 3: Gold run (medium → long → combined, oracle ceilings)

**Files:**
- Create: `digiquant/scripts/optimize_sdca_periods.py` (thin generic CLI: `--symbol/--data-path/--horizon/--out`, prints the candidate table + score; no gold knowledge)
- Create: `digiquant/scripts/run_gold_period_optimization.py` (gold wiring: load GLD, run medium + long + combined, write `digiquant/.scratch/gold_period_optimization.json` with every metric + split-sample + the CEILING label; console prints the ladder)
- Create (untracked): `digiquant/.scratch/gold_period_optimization.json`

**Interfaces:**
- Consumes: Task-2 optimizer; GLD closes.
- Produces: medium/long/combined period sets + oracle ceilings + split-sample. Task 4 judges + renders.

- [ ] **Step 1: Run gold (background, bounded) + full report**

Report: medium period table (windows + Sharpe/Calmar/CAGR/exposure/DD), long table, combined (precedence applied), oracle ceilings for each vs lump + flat comparators (`dca_metrics`), split-sample fit/score pairs, and the in-sample-ceiling sentence. Backup+sha256 on touched scratch files. No gate runs.

---

### Task 4: Verdict + visuals + docs

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (append-only SDCA paragraph: new modules + objectives + gold result + ceiling framing)
- Create (untracked): diagnostic tearsheet JSON for the combined perfect-strategy path + public/ copy; chart script (oracle paths + period sets vs price, stdlib SVG pattern); TEMP page entry (REVERT marker)
- Verify: suites + ruff + status; serve 200s

- [ ] **Step 1: Judge (no new runs): did period identification improve the oracle under the frozen objective, and did the split-sample confirm it out-of-sample-ish? Name the answer either way.**
- [ ] **Step 2: Visuals + docs + commits (chart/tearsheet scripts + ARCH; outputs/preview per standing rules)**

---

## Out of scope (not this plan — enforced by review)

- `buy_dates` engine veto (the oracle computes its own path; no engine change needed here).
- MCP tool exposure (later plan; recon item 22).
- Pin-factory edits (`gold_v1()`/`btc_v1()` stay as-is — the optimizer emits NEW window sets, it never edits a factory).
- Any actual SDCA curve/gate run or performance claim (later plan); holdout (spent); COT/Dow-gold legs.
- Nav/gloomberb/Supabase/nightly/push/merge.

## Self-review

1. Spec coverage: metrics + oracle with parity pin → Task 1 (fail-first, lump parity, conventions documented); two-horizon optimizer + combine + split-sample → Task 2 (recovery pin, floor enforcement, derivation-not-invention rule); gold run + ceilings → Task 3 (thin CLIs, full tables, ceiling labeling); verdict + visuals + docs → Task 4.
2. Placeholder scan: annualization 252, exposure floor 70.0, horizon half-width sets, min counts, split 0.5, file paths, JSON names are literal. STOPs (parity fail, ad-hoc dates, cannot-derive discovery) name trigger + action.
3. Type consistency: `RiskMetrics` vs `PerfectStrategyMetrics` vs `PeriodScore`/`PeriodOptimizationResult` distinct everywhere; `CycleWindow` reused not redefined; `combine_periods` precedence (long sells override medium buys) stated identically in code/tests/docs/ARCH.
