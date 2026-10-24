# Long-term-first period model + graded medium overlay (Plan 21) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Rebuild the period model the way the owner specified — long-term windows first as the primary regime, then medium-term windows added GRADUALLY and calibrated, with unhit windows abandoned and indicators matched to the final windows — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Owner direction (2026-10-02):** "Focus on long-term windows and gradually incorporate medium-term windows. Ensure that the indicators are matched with the identified windows to target long-term opportunities more effectively. Adjust the frequency of medium-term windows as needed. Identify and abandon windows that do not get hit, and gradually calibrate the medium-term windows."

**Why this supersedes Plan 20's failure mode:** Plan 20 built period sets from EVERY swing pivot, so flat time between windows pinned exposure at ~55% regardless of width (1.49pp spread across the whole medium grid — pivot DENSITY, asset-independent). Few wide secular windows invert that: flat time = peak windows only, so the frozen 70% floor becomes reachable and meaningful. Plan 20's oracle, metrics and split-sample machinery are reused as-is.

**Architecture:** two new period-model functions in `period_optimize.py` (the existing disjoint-pair discovery is left intact for the earlier record) — `select_long_term_periods(dates, prices, *, max_peak_days_pct=25.0, min_peaks=2, min_troughs=2)` (prominence-ranked cycle pivots, truncated to a small set so peak-window days stay ≤ 25% of the calendar) and `grade_medium_overlay(dates, prices, long_windows, medium_candidates, *, exposure_floor_pct=70.0)` (adds medium windows ONE AT A TIME, ranked; keeps an addition only if oracle Sharpe strictly improves AND exposure ≥ floor AND the window is HIT; abandons unhit windows with the reason recorded; stops at the first non-improvement). Hit test: `window_is_hit(dates, prices, window, *, min_move_pct)` — the window contains a real move of at least `min_move_pct` (frozen: 15.0 long, 10.0 medium), i.e. it caught something instead of being decoration. Indicator matching reuses the landed separation metric: each fitted indicator scored against the FINAL window set.

**Frozen objective (owner-ruled, unchanged from Plan 20):** oracle Sharpe primary / Calmar tie-break / CAGR tertiary, time-in-market floor 70%. Exposure floor NOT relaxed (Plan 20 review: relaxing to ~55% after seeing the data is exactly the backward-fitting that broke earlier gold work). Half-width grids unchanged (long 60–180d, medium 15–60d); only the SELECTION changes (prominence-ranked + few).

**Honesty frame:** every oracle number is an in-sample ceiling on the same history used to select the windows; the split-sample check (with its known 1-bit OOS defect, filed) is reported beside it. Holdout stays spent. Ceilings lose to buy-and-hold at ~55% exposure (Plan 20); the whole point of the long-first model is to test whether that flips as exposure rises.

## Global Constraints

- Research-only except edits INSIDE `period_optimize.py` (additive: new functions + tests; existing discovery untouched) and the two existing thin CLI scripts. No edits to `risk_metrics.py` / `perfect_strategy.py` / engine / settings / workflows. No push, no merge. No pandas, pydantic v2 frozen strict, ruff 100, zero nautilus imports. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential. Never force-push.
- New public functions get TDD fail-first pins + stay in `__all__`.
- Standing owner rules: visuals every iteration (Task 5); temp preview edits uncommitted with REVERT-BEFORE-MERGE markers.

---

### Task 1: Long-term selection + hit test (TDD)

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/period_optimize.py` (additive: `window_is_hit(...)`, `select_long_term_periods(...)`, + models `HitTest`, `LongTermSelection`)
- Modify: `tests/dq/strategies/sdca/test_period_optimize.py` (extend)

**Interfaces:**
- Consumes: existing pivot discovery (`discover_candidate_periods`) + oracle/metrics.
- Produces: a small secular window set + hit verdicts. Task 2 overlays medium.

- [ ] **Step 1: Failing tests first (TDD)**

Pins: (a) hit test — a window containing a 20% drop is hit at 15%, a window containing 3% is NOT (both directions, exact threshold behavior); (b) selection on a synthetic series with 3 clear secular cycles returns exactly 3 peak + 3 trough windows with peak-window days ≤ `max_peak_days_pct` of the calendar (assert the constraint holds, not just that it returns something); (c) selection respects `min_peaks/min_troughs` (a series with too few pivots → `None` + reason, never a relaxed minimum); (d) prominence ranking is deterministic (same input → same set). → RED.
- [ ] **Step 2: Implement additively** (existing `discover_candidate_periods` / `score_periods` / `combine_periods` / `split_sample_check` untouched — prove by diff)
- [ ] **Step 3: GREEN (extended file + full sdca suite unmodified-green) + lint + ONE commit (#4804)**

STOP: the additive edit would require touching existing functions → NEEDS_CONTEXT.

## Ruling 1 (Plan 21): half-width parameter + calendar guard (issued after Task-1 review)

Task-1 review found the long half-width is not a parameter (pinned to `min(LONG_HALF_WIDTHS)`=60d — the widest medium-grid member; "long" rests on provenance + cadence + the ≤25% cap). Re-running the gold ladder per width is expensive, and widening is qualitative (it can drop `n_peaks` below `MIN_PEAKS` into refusal), so the width must be settable up-front. Binding before Task 2: `select_long_term_periods(..., half_width_days: int | None = None)` (default = current `min(LONG_HALF_WIDTHS)`, behavior byte-preserved), carried in `LongTermSelection` so a run is self-describing; plus a clean minimum-calendar guard (clean `ValueError`, never `IndexError`). Two carry-forwards for Task 3: `peak_days_pct` and `trough_days_pct` are SEPARATE quantities (the cap is per kind) — only peak days bound the exposure floor; and the report must state whether the trailing pivot entered the set on a to-end-of-calendar bound.

### Task 1b: half-width parameter + guard (TDD)

---

### Task 2: Graded medium overlay (TDD)

**Files:**
- Modify: `period_optimize.py` (additive: `grade_medium_overlay(...)` + `OverlayGrade` model) + its test file

**Interfaces:**
- Consumes: Task-1 long set; medium candidates from the existing discovery; oracle + floor.
- Produces: the graded ladder + kept/abandoned lists with reasons.

- [ ] **Step 1: Failing tests first**

Pins: (a) an improving overlay is kept and the ladder shows it; (b) a NON-improving addition is abandoned with the reason recorded and the ladder STOPS there (no skipping ahead); (c) an UNHIT medium window is abandoned before scoring (reason = `unhit`, with the observed max move quoted); (d) exposure floor enforced per step (a step that breaches it is abandoned, reason = `exposure`); (e) deterministic ordering (ties → shorter window, then date). → RED.
- [ ] **Step 2: Implement + GREEN + lint + commit (#4804)**

---

### Task 3: Gold run — long-first ladder (no new machinery)

**Files:**
- Modify: `digiquant/scripts/run_gold_period_optimization.py` (add a `--long-first` mode; existing mode preserved for the Plan-20 record)
- Create (untracked): `digiquant/.scratch/gold_period_ladder.json`

**Interfaces:**
- Consumes: Tasks 1–2; GLD closes.
- Produces: pure-long ceiling, then the graded ladder (each step's windows, exposure, Sharpe/Calmar/CAGR/DD, keep/abandon reason), plus lump/flat comparators + split-sample.

- [ ] **Step 1: Run + report** (background, bounded; backup+sha256 on touched scratch files)

Console + JSON: long set (window dates + kinds + hit verdicts), pure-long oracle metrics + exposure, the overlay ladder step by step, the kept set, comparators, the exposure trajectory (the key column: does it climb toward the floor?), and the ceiling sentence.

---

## Ruling 2 (Plan 21): long-side hit test + coverage constraint (issued after Task-3 review)

Task 3 ran clean but exposed the real mechanism, and the review corrected the framing twice. MECHANISM: `_derive_edges` emits actions only at window ENTERS (buys at trough enters, sells at peak enters); a trough is already held until the next peak's enter, so exposure is NOT destroyed by edge construction — it is destroyed by a COVERAGE HOLE: 12 of 15 selected peaks sit in 2006-2013 + 2026, and after `long_peak_20130321` the next selected window is `long_trough_20200319` — a ~2236-business-day flat run (6 hold blocks, gaps 329/126/25/2236/1030). MEDIUM defect (owner-intent drift): the hit test only gated medium additions, so 5 long windows at 9.25-14.50% moves are kept — the owner's "abandon windows that do not get hit" was unqualified. Task 3b (new task, `period_optimize.py` only, TDD, additive): (1) hit-test every prominence-ranked LONG candidate at the frozen 15.0 BEFORE it consumes the per-kind day budget, so freed budget admits the next hit pin; dropped pins + observed moves recorded in `LongTermSelection`; (2) add a COVERAGE CONSTRAINT using only existing knobs — a calendar segment between selected trough windows must contain at least one selected trough, enforced by swapping the lowest-prominence selected PEAK in that segment for the best hit trough available there (cap still enforced, minima still never relaxed); (3) pins for both, plus a regression pin that defaults are unchanged for a series where no swap or drop is needed. Frozen 25% cap and 70% floor stay; this is in-sample selection and stays labeled that way. Task-3 numbers in `gold_period_ladder.json` are the PRE-FIX record — the fix changes them, and the post-fix run is a new JSON (no overwriting the filed one).

## Ruling 3 (Plan 21): coverage-first trough budget (owner-ruled 2026-10-03)

Task 3b proved the coverage swap inadmissible inside the frozen cap: trough budget is exhausted (GLD 1369/1374 trough days) and the seven hit troughs in the worst ~1509-day gap need 1458–1490 days; kinds are capped independently, so no peak drop funds a trough. OWNER RULING: fund coverage by RE-RANKING the trough walk — coverage first, prominence second, cap UNCHANGED. Binding implementation: within the per-kind trough budget, first place ONE hit trough per uncovered calendar segment (longest gap first, earliest tie, best hit trough by prominence in that segment), THEN fill the remaining trough budget by prominence as before; peaks follow their existing prominence walk. If coverage-first placements exhaust the budget and leave a segment uncovered, that segment is recorded (`uncovered_segments`) — never fudged. New record fields: coverage placements (segment, pin, observed move) and any prominence troughs displaced to fund coverage, so the cost is visible. No cap/floor/minimum change.

### Task 3b: Long-side hit test + coverage constraint (TDD, additive)

**Files:** `digiquant/src/digiquant/strategies/sdca/period_optimize.py` (additive inside `select_long_term_periods` + `LongTermSelection` fields) + its test file.

**Steps:** failing tests FIRST (an unhit prominent long candidate is dropped in favor of the next hit pin and the drop is recorded with its observed move; a segment with no selected trough triggers the swap; the cap and minima still hold after a swap; defaults unchanged where no swap/drop is needed) → RED → implement → GREEN + suite + ruff → ONE commit (#4804).

### Task 4: Indicator matching against the final windows

**Files:**
- Modify: `digiquant/scripts/run_gold_period_optimization.py` (add the matching pass; reuses `fit_gold_indicators` separation + the final window set — no new metric)

**Interfaces:**
- Consumes: Task-3 final window set; the fitted-indicator table.
- Produces: per-indicator separation vs the FINAL windows (which indicators actually align with the secular regime the strategy will trade).

- [ ] **Step 1: Run + report** — the matched table (indicator | fitted params | separation vs final windows | verdict), with the in-sample label.

---

### Task 5: Verdict + visuals + docs

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (append-only SDCA paragraph: long-first model, hit test, graded overlay, gold ladder result, indicator match, Plan-20 supersession note)
- Create (untracked): chart script (ladder: exposure + Sharpe per step, windows vs price, kept/abandoned markers; stdlib SVG) + public/ copies + serve-200 proofs; diagnostic tearsheet JSON + TEMP page entry ONLY if the verdict is selectable
- Verify: suites + ruff + status

- [ ] **Step 1: Judge (no new runs): did the long-first model reach the exposure floor, did the ladder improve on pure-long, and did the ceilings' Sharpe vs buy-and-hold flip as exposure rose? Name each answer.**
- [ ] **Step 2: Visuals + docs + commits (chart script + ARCH; JSON/preview per standing rules)**

---

## Out of scope (not this plan — enforced by review)

- Relaxing the exposure floor or any frozen threshold after seeing results (Plan 20 review precedent).
- Fixing `split_sample_check`'s 1-bit OOS side or `risk_metrics`' Calmar epsilon (both filed follow-ups).
- Any SDCA curve/gate run or performance claim (periods first, per owner); holdout (spent).
- New indicators/legs; MCP exposure of the new functions (later plan); pin-factory edits.

## Self-review

1. Spec coverage: long selection + hit test → Task 1 (fail-first incl. constraint-holds + too-few-pivots + determinism pins, additive-only diff); graded overlay → Task 2 (improve/stall/unhit/floor/determinism pins); gold ladder → Task 3 (exposure trajectory headline, backup discipline); indicator matching → Task 4 (reuse landed separation, no new metric); verdict + visuals + docs → Task 5.
2. Placeholder scan: `max_peak_days_pct=25.0`, `min_move_pct` 15.0 long / 10.0 medium, exposure floor 70.0, file paths, JSON names are literal. STOPs (non-additive edit, unrelaxable constraint) name trigger + action.
3. Type consistency: `window_is_hit` / `select_long_term_periods` / `grade_medium_overlay` / `HitTest` / `LongTermSelection` / `OverlayGrade` / `gold_period_ladder.json` identical in plan, code, tests, report, ARCH; "long-first, medium gradual" language consistent everywhere.
