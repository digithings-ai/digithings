# Gold technical composite (Plan 12: no-trend vote + honest labels) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace gold's time-trend valuation vote with a technical composite — trailing mean-reversion anchor (RollingZ rails) + oscillators + macro/dollar legs — fix the false "power law" labeling for non-BTC rails, and measure the new vote on fold-1 and the full gate — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Three small engine changes, all additive/default-preserving: (1) omit the valuation leg when its weight is 0 (mirroring the extras rule — today it null-poisons despite contributing nothing); (2) wire the `z` kwarg through the `rolling_z` selector branch (3 lines); (3) asset-aware display names for the valuation leg (per-risk-model map, BTC default unchanged). Gold v4 seed votes valuation 1.0 on rolling-z rails + m2/uup 0.5 + oscillators 0.25/0.25/0.25 with trend valuation at zero. No new indicators, no new legs, no bar changes.

**Tech Stack:** Python, Polars, Pydantic v2, pytest (`-m unit`), ruff (line length 100). Simulator-only compute.

**Spec:** Recon 2026-10-01 (same session, recorded as completed Task 0): `RollingZRiskModel(dates, price, *, window=90, z=1.0)` scores log-price vs trailing window, causal, rails low/med/high into the same `valuation_z` path (`rolling_z.py:27-91`; docstring names exactly this use case); selector has the branch but drops `z` (`providers.py:48-78`, `KNOWN_SDCA_RISK_MODELS:39-43`); sma_band overlap warning (same mean-reversion family — recorded, not resolved; the gate decides); oscillators `price_oscillators.py:151-337` (mtf blend behind `weekly_rsi`, macd kwargs partially ignored `:298`, all three wired `:699-734`, all zero-weighted in every gold seed; weekly-only/monthly-only variants available-but-unwired; NO trend/vol/drawdown functions anywhere — explicit absence); null-poison mechanics (`risk_index.py:84-88` always-enabled valuation + `composite_risk.py:53-55` ignore_nulls=False vs extras omission rule `indicator_catalog.py:498`); dead-compute inventory under valuation=0 (per-fold refits, seed rails, `--rails-variant` — all meaningless, none removed); current votes (v3 = valuation/m2/uup; v2deep adds walcl/be5y/nfci/ratios); correlation extension surface (TLT/TIP/CPER need full new-leg plumbing — explicitly OUT of this plan); label sites (`indicator_catalog.py:94-117`, `chart_series.py:21,141,165`).

## Global Constraints

- Research-only except the three engine changes (omission fix, selector kwarg, display param), which are additive/default-preserving and BTC-safe by construction (BTC always votes valuation>0 on power-law rails with default display — proven by unmodified-green suites, not asserted).
- No trend fits for gold anywhere in this plan: no generic_valuation/log_linear/log_quadratic rails on any gold calendar (seed, folds, or holdout). The v4 seed resolves `rolling_z`, period.
- The sma_band overlap is disclosed, not resolved: rolling anchor + sma_band vote the same family. If the gate shows redundancy damage, that's a finding, not a plan failure.
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 1: Valuation-omission fix + rolling-z selector kwarg + tests

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/risk_index.py` (omit valuation leg at weight 0 — read `:73-88` first)
- Modify: `digiquant/src/digiquant/strategies/sdca/providers.py` (add `rolling_z` kwarg — read `:39-78` first)
- Modify: `tests/dq/strategies/sdca/test_risk_index.py` (omission test) + whichever test file covers the selector (grep `resolve_sdca_risk_model` in tests/ first — extend, don't create)

**Interfaces:**
- Consumes: recon line map.
- Produces: extras-only votes with full (null-free) coverage; selectable rolling-z width. Tasks 3–4 consume both.

- [ ] **Step 1: Write the failing tests**

Omission test (in test_risk_index.py — read its fixtures/imports first, mirror them): build a risk index over a calendar where the valuation z is null for the first K days (any rails with early nulls — reuse the file's existing rails fixture if it has nulls, else construct valuation z with leading Nones) with weights valuation=0.0 + m2-like extra 1.0 (use the file's existing extra-vector pattern); assert composite is non-null on days the extra is non-null (i.e. valuation contributes no null mask). Expect FAIL (null-poisoned today).

Selector test: `resolve_sdca_risk_model("rolling_z", dates=..., price=..., rolling_z=2.0)` returns a model whose rails spread is wider than default (compare high/low width at a fixed date > 2× the z=1.0 width — approximately, ratio ≈ 2.0 within 5%); plus `rolling_z` absent → z stays 1.0 (defaults-unchanged). Expect FAIL (TypeError on unknown kwarg — verify that failure shape; if the selector swallows kwargs, STOP with NEEDS_CONTEXT quoting the branch).

- [ ] **Step 2: Run to verify both fail**

Run: `.venv/bin/python -m pytest <touched test files> -m unit -q`
Expected: FAILs as specified (null mask present; TypeError-or-reported shape).

- [ ] **Step 3: Implement (two minimal edits, nothing else)**

1. `risk_index.py`: in the valuation-leg construction, mirror the extras rule — when the passed valuation weight is 0 (read how weight arrives at `:73-88` first: parameter name/shape), SKIP building/appending the valuation IndicatorWeight (do not append-then-zero; omission must remove both the vote AND the null mask). Docstring line stating the rule parity with `build_extra_indicators`.
2. `providers.py`: add keyword-only `rolling_z: float = 1.0` (validate `> 0` like the model does — mirror the model's own error, don't invent a new one) and pass `z=rolling_z` in the rolling_z branch ONLY. All other branches byte-untouched.
STOP branches: weight arrives in a shape that makes omission ambiguous (then NEEDS_CONTEXT, don't restructure); selector branch shape differs from recon (NEEDS_CONTEXT).

- [ ] **Step 4: Run to verify green + BTC-path suites unmodified-green**

Run: touched test files + `test_walk_forward.py` + `test_valuation.py` + `test_providers.py` (find the real selector-test filename via grep — use it, not my guess) + engine subset `-m unit -q`.
Expected: all green; nothing outside the touched files modified (`git diff --stat` check).

- [ ] **Step 5: Lint + commit (two commits, one per edit + its tests)**

Ruff check + format-check touched files.
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/risk_index.py <risk-index test>
git commit -m "Omit zero-weight valuation leg from risk blend (#4804)"
git add digiquant/src/digiquant/strategies/sdca/providers.py <selector test>
git commit -m "Wire rolling-z width through risk-model selector (#4804)"
```

---

### Task 2: Asset-aware valuation display names + tests

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (display map + function signature — read `:94-117` first)
- Modify: `digiquant/src/digiquant/strategies/sdca/chart_series.py` (call sites `:141,165` — pass-through only)
- Modify: tests covering `indicator_display_name` (grep first — extend, don't create)

**Interfaces:**
- Consumes: risk-model names (`btc_power_law`, `generic_valuation`, `rolling_z`).
- Produces: `indicator_display_name(name, *, model=None)` with BTC-default preservation. Tasks 3–4 + the shipped UI consume it.

- [ ] **Step 1: Write the failing tests**

In the covering test file: `indicator_display_name("valuation") == "power law"` (unchanged default — BTC safe); `indicator_display_name("valuation", model="rolling_z") == "mean reversion"`; `indicator_display_name("valuation", model="generic_valuation") == "valuation trend"`; unknown model falls back to default map (no KeyError); non-valuation names ignore `model`. Expect FAIL (no `model` kwarg).

- [ ] **Step 2: Run to verify it fails**

Expected: TypeError on unexpected keyword.

- [ ] **Step 3: Implement**

Per-model valuation labels, BTC default preserved exactly:
```python
_VALUATION_DISPLAY_BY_MODEL = {
    "btc_power_law": "power law",
    "generic_valuation": "valuation trend",
    "rolling_z": "mean reversion",
}

def indicator_display_name(name: str, *, model: str | None = None) -> str:
    """Chart/UI label for an indicator code id. `model` selects the valuation-leg label; default preserves BTC wording."""
    if name == "valuation" and model in _VALUATION_DISPLAY_BY_MODEL:
        return _VALUATION_DISPLAY_BY_MODEL[model]
    return INDICATOR_DISPLAY_NAMES.get(name, name.replace("_", " "))
```
`chart_series.py:141,165`: thread an optional model through from the caller IF the caller knows it (read the callers first — if the asset/risk-model isn't available at those sites without plumbing, pass nothing and record the gold-tearsheet follow-up explicitly instead of plumbing half the stack; the shipped UI can adopt the param when it knows the model).

- [ ] **Step 4: Run + lint + commit**

Suite green + ruff clean, then:
```bash
git add digiquant/src/digiquant/strategies/sdca/indicator_catalog.py digiquant/src/digiquant/strategies/sdca/chart_series.py <test file>
git commit -m "Asset-aware valuation display names (#4804)"
```

---

### Task 3: v4 technical seed (rolling anchor + oscillators + macro/dollar, trend zero)

**Files:**
- Create: `digiquant/scripts/run_gold_technical_index_v4.py` (standalone — do NOT extend the v2 seed script; the trend-seed lineage stays frozen and comparable)
- Create (untracked): `digiquant/.scratch/gold_seed_v4.json`
- Modify: NONE (no seed-file overwrites, no v1-v3 outputs touched)

**Interfaces:**
- Consumes: Task-1 omission fix + selector kwarg; staged CSVs (GLD/UUP/M2SL); oscillator precompute (weights-only enablement).
- Produces: v4 seed + coverage/null-footprint report. Task 4 gates it.

- [ ] **Step 1: Write the script (mirror the v2 seed structure, new vote)**

Read `run_gold_frozen_index_v2.py` fully first; mirror imports/flow/output shape with these deltas: rails via `resolve_sdca_risk_model("rolling_z", dates=date_s, price=price_s, rolling_window=90, rolling_z=1.0)` (window/z as literal constants with a comment: 90d matches the oscillator horizon family; sensitivity to these is a follow-up, not this task); weights `SdcaCompositeWeights(valuation=1.0, m2=0.5, uup=0.5, weekly_rsi=0.25, weekly_macd=0.25, sma_band=0.25)` (oscillator seed values: quarter-weight starters — the gate decides; rationale in docstring); NO generic_valuation import/fit anywhere in the file (grep-verify before running — a trend fit sneaking in fails review); extras via the established sources+vectors pattern; OUT `gold_seed_v4.json` with the same keys as v2 seeds plus `"rails": "rolling_z/90d/z1.0 trailing mean-reversion (no time trend)"` and `"trend_valuation": false`. Docstring states the sma_band overlap disclosure + the oscillator quarter-weight rationale.

- [ ] **Step 2: Run + tripwires (no gate yet)**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_technical_index_v4.py`
Expected: exit 0; coverage ≥ 95% of v1 (rolling warmup ≈ 90d vs M2 YoY warmup dominates anyway — assert, STOP if violated); buy-zone share + mean risk printed for the record; null footprint: ZERO nulls attributable to valuation (assert by construction — verify with a one-liner counting null-risk days before vs after masking valuation z; if valuation nulls still mask, the Task-1 fix didn't take — STOP, do not work around).

- [ ] **Step 3: Lint + commit the script (output untracked)**

Ruff clean, then:
```bash
git add digiquant/scripts/run_gold_technical_index_v4.py
git commit -m "Add gold technical (no-trend) seed v4 (#4804)"
```

---

### Task 4: v4 gate run (same space/bars/geometry, new vote + new rails)

**Files:**
- Modify: `digiquant/scripts/run_gold_curve_search.py` — ONLY IF the rails-variant factory cannot express a rolling-z fitter through the existing `--rails-variant` choices (read the factory first): add a `rolling90` choice mapping to the Task-3 fitter closure (same params: window 90, z 1.0). Grid/gates/folds/objective/weights UNTOUCHED — seed comes from `--seed-path gold_seed_v4.json` (existing flag).
- Create (untracked): `digiquant/.scratch/gold_curve_search_v4.json` (+ stdout log)

**Interfaces:**
- Consumes: v4 seed; landed gate machinery.
- Produces: v4 gate record. The comparison that matters: fold-1 vs v1/v3/B + sensitivity verdict.

- [ ] **Step 1: Wire the variant if needed (arg-only change, proven by diff)**

If the factory needs the choice: add it, prove with `git diff` that ONLY the factory mapping + choices list changed. If `--rails-variant` already generalizes (it takes fitter closures — check), use the existing seam with zero edits and record that.

- [ ] **Step 2: Run the v4 gate (background, ~40s class)**

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed_v4.json --rails-variant rolling90 > digiquant/.scratch/gold_curve_search_v4.stdout.log 2>&1
```

(copy-before-overwrite discipline.) Expected: exit 0. Record wall time + FULL table (winner shape — EXPECT it to differ from trend-era winners since the vote changed: shape-identity does NOT apply across votes, state that explicitly; per-fold OOS/dd/feasible, sensitivity maxΔ + worst-neighbor key, mean + beats_flat) + holdout-absence + the fold-1-vs-prior verdict (better/worse than −11.19/−11.16/−8.25?) + sensitivity verdict (stable? at what maxΔ?).

- [ ] **Step 3: Lint + commit (arg edit if any; output untracked)**

Ruff clean, then commit the arg edit only (message per brief pattern). If no edit was needed, no commit — record that.

---

### Task 5: Docs + verify + evidence log

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (rails passage: rolling-z anchor option + omission rule + display-param — append-only, touch nothing else; skip-with-note if passages absent)
- Verify: heavy suite + ruff + status.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: docs + evidence log (final report section: plan commits, v4 table + fold-1-vs-priors + sens verdict, sma-band overlap read (did it damage or help? cite the winner weights/dropout if visible), open items).

- [ ] **Step 1: ARCH append**

Grep the rails + catalog rows; append: rolling-z anchor semantics, `z` selector kwarg, omission rule (weight-0 valuation contributes neither vote nor null mask), display param with per-model labels. Nothing else.

- [ ] **Step 2: Full verification**

```bash
.venv/bin/python -m pytest tests/dq/strategies/sdca/test_risk_index.py tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_valuation.py tests/dq/strategies/sdca/test_providers.py tests/dq/strategies/sdca/test_indicator_catalog.py tests/dq/strategies/sdca/test_sdca_gold_uup.py -m unit -q
ruff check <touched files> && ruff format --check <touched files>
git status --short
```

(Expected: green — stash-prove any failure; #3173 test unmodified-green re-confirmed via `git diff --stat`; status shows plan commits + `??` staging only. NOTE: `test_providers.py` filename is recon-held — verify existence first, substitute the real selector-test path if different.)

- [ ] **Step 3: Commit docs**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Document no-trend vote: omission rule + rolling-z anchor (#4804)"
```

---

## Out of scope (not this plan — enforced by review)

- New indicators (trend/vol/drawdown functions don't exist — proposing them is a follow-up, not a drive-by).
- TLT/TIP/CPER legs (staged but unwired — declared scope since Plan 2).
- Oscillator weight search (quarter-weight starters; the gate measures, a search tunes later).
- Unwiring/disabling the sma_band overlap (disclosed; gate evidence first).
- Engine defaults, #3173 test, bars, promotion, nightly, credentialed runs, holdout (spent).

---

### Task 5: Causal rolling evaluation + v4 re-gate (added per Ruling 3)

**Context (why this task exists):** Task 4's v4 gate is VOID — IS-sliced per-fold evaluation starves the trailing window (1100/1100 null OOS rails → 0% deployed everywhere → −6.49% measures non-participation, not the vote). A trailing-window operator evaluated on a bare OOS slice has no history; the fix is giving the evaluation pre-history WITHOUT estimating any parameter on OOS (causal trailing computation is leak-free by construction — each output uses only inputs ≤ t).

**Files:**
- Modify: `digiquant/scripts/run_gold_curve_search.py` (`--out PATH` arg: output path derived from seed path or explicit flag; default = current fixed path — default-preserving footgun fix)
- Create or modify: the rolling evaluation wiring (gold-side script and/or small helper — options below; engine `score_trial_on_folds` + fitter protocol UNTOUCHED)
- Create: offline causal test (new file or appended to the gold uup/price-family test area — colocate sensibly)
- Create (untracked): `digiquant/.scratch/gold_curve_search_v4.json` (OVERWRITE of the void record — explicitly authorized: the current content measures nothing; backup + sha256 the void file first, record both hashes, then overwrite)

**Interfaces:**
- Consumes: v4 seed weights; `RollingZRiskModel`; `evaluate_sdca_trial_curve_sim`; fold objects from `make_walk_forward_folds` (read-only geometry).
- Produces: a valid v4 gate record (all folds trading). No grid/gates/folds/objective/weight changes.

**Steps:**

- [ ] **Step 1: Investigate the wiring (read-only, then choose i/ii/iii — record the choice with line evidence)**

(i) Static/precomputed-rails RiskModel in src (a test-side `StaticRiskModel` was spotted during review — check for a src equivalent): if one exists and accepts precomputed rails, precompute rolling rails on the FULL calendar once (causal op, zero estimated parameters), wrap per-fold OOS slices, score via the evaluator directly. (ii) Else gold-side fold loop: per fold, build the rolling model on `window_slice(dates, prices, is_start, oos_end)` (concatenated history — trailing inputs include OOS prices ≤ t, causally clean, nothing estimated), slice OOS rails, evaluate on OOS via `evaluate_sdca_trial_curve_sim`. (iii) If neither is clean without engine-protocol changes: STOP with NEEDS_CONTEXT (exact blockage) — the plan then closes with v4-unmeasurable recorded honestly, no hack.

- [ ] **Step 2: Causal test FIRST (offline, synthetic series — fails before the wiring, passes after)**

New test asserting the lookahead tripwire: rolling rails at date t computed on the full calendar EQUAL rails at t computed on the calendar truncated at t (same params) — for several t across a synthetic regime break. This proves the evaluation uses no future information regardless of wiring choice. Run → FAIL (or vacuous-pass with justification if the wiring makes truncation meaningless — no, it must be a real test: construct it so it exercises the chosen path; a vacuous pass fails review).

- [ ] **Step 3: Implement the wiring + `--out` + backup discipline**

Implement the chosen wiring (gold-side code only — engine `score_trial_on_folds`/fitter protocol untouched; the enforcement test never fires because the engine path isn't used for rolling folds — state that explicitly with the reasoning that no OOS parameter estimation occurs). Add `--out PATH` (default preserves current behavior). Backup discipline (mandatory, non-negotiable after the Task-4 footgun): sha256sum every scratch file the run could touch BEFORE running, re-verify after; paste both hash sets in the report.

- [ ] **Step 4: Re-run the v4 gate (background, ~40s class) + table**

Same vote (v4 seed), same space/bars/geometry, causal rolling evaluation. Record wall + exit + FULL table (winner shape — no identity expectation across votes, state that; per-fold OOS/deployed-net/peak/dd/feasible, sens maxΔ + neighbor key, mean + beats_flat) + fold-1-vs-priors (v1 −11.19 / v3 −11.16 / B −8.25) + sensitivity verdict + holdout-absence. The question: does the technical vote trade, and what does fold-1 read?

- [ ] **Step 5: Lint + tests + commit (wiring + test + --out; outputs untracked)**

Full relevant suite green + ruff clean, then commit (message per brief pattern). Report carries the table + the void-result correction (v4 verdict SUPERSEDES the Task-4 −6.49% non-result — say so explicitly so no reader cites the void number).

## Self-review

1. Spec coverage: omission + selector + tests → Task 1 (fail-first both, BTC-safe by unmodified-green); display param → Task 2 (BTC default preserved exactly, caller threading only if available); v4 seed + tripwires → Task 3 (no-trend grep gate, coverage + null-footprint asserts, standalone file); v4 gate → Task 4 (vote+rails delta only, shape-identity explicitly N/A across votes, fold-1 + sens verdicts required); docs + verify → Task 5.
2. Placeholder scan: signatures, weights, window/z values, commands, file paths, JSON names are literal. STOPs (ambiguous weight shape, swallowed kwargs, missing test home, factory mismatch, tripwire violation, absent passages) name trigger + action. The `--variant`/`--rails-variant` reuse is read-first, not assumed.
3. Type consistency: `rolling_z` kwarg vs `z` model param distinguished everywhere (selector kwarg `rolling_z`, model field `z`); `fit_lookback_days`-style naming not reused; `gold_seed_v4.json` / `gold_curve_search_v4.json` / `run_gold_technical_index_v4.py` identical in tasks and triggers; `mean reversion` / `valuation trend` labels identical in tests, code, and ARCH row.
