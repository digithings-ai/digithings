# SDCA Composite-Index Smoothing + Tiered Response Curve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Smooth the SDCA composite valuation index's remaining spikiness (a cadence-broadcast step-function bug shared by 4 oscillator functions, plus a discontinuous blend multiplier), give the response curve a mid-tier knee so medium-risk signals move allocation ~50% while true extremes still hit 100%, re-weight the full 17-indicator `SURVIVING_INDICATORS` pool jointly with the new tiered curve search space, and wire a standing periodic self-optimization cycle so SDCA keeps re-testing itself against this bar going forward. Together these are the direct answer to Chris's 2026-09-25 directive ("adjust our SDCA strategy building to kind of build on top of [the reference dashboard]... have our SDCA system optimize itself over time, periodically, and include more indicators and have more self-adjustment... optimize buying and selling curves... adjust the plan so that we could at least match this SDCA reference in performance terms") — the direct successor to the accept/reject/new-lever decision point recalibration-v1 Round 4 left open (see Prior Art below). Tearsheet/presentation work is explicitly out of scope for this plan, per Chris's own framing ("we'll deal with how we want to present it in the tier sheet later").

**Architecture:** Three independent library-level fixes/extensions (`price_oscillators.py` smoothing + blend continuity, `curve_shape.py` tiered `rate_at()`, `curve_optimize.py`/`curve_optimize_feasibility.py` search-space plumbing) land first with full TDD coverage, each backward-compatible with every existing caller. A new roughness-diagnostic module quantifies indicator smoothness before/after. A driver script reweights the canonical 17-name pool against the smoothed index and tiered curve search together, gated by the standing walk-forward accept protocol — it writes only to `.scratch/`/untracked local files, never `settings.json` or `RESEARCH_STATE.md`'s validated-candidate section. A final periodic-cycle driver wraps that same machinery (plus the already-shipped ablation/baseline-comparison machinery from the pearl-plan) into a repeatable, state-persisting cycle, invoked on a standing self-paced loop.

**Tech Stack:** Python, polars, pydantic v2 (frozen/strict models throughout), pytest (`pytest.mark.unit`, class-based grouping, `pl.Series`/`pytest.approx`).

**Spec:** `docs/superpowers/specs/2026-09-25-sdca-index-smoothing-tiered-curve-design.md`

**Prior Art:** See [Prior Art (Already Completed)](#prior-art-already-completed) below — the pearl-plan's band-crossing fix, baseline-relative evaluator, re-score, and iterative-ablation machinery, and the recalibration-v1 workstream's Rounds 1-4, visualizations, comparison-set expansion, and blend attempts, are all already shipped, tested, and executed against real data. This plan does not re-build or re-run any of it — Tasks 1-7 are net-new work on top of it, and Task 8 reuses it.

**Reference:** `docs/superpowers/research/2026-09-25-sdca-reference-site-analysis.md` (analysis of the composite-index accumulation/distribution dashboard Chris named as SDCA's original inspiration) and see [Reference-Site Parity Target](#reference-site-parity-target) below for how its performance is translated into DigiQuant's own walk-forward-OOS methodology.

## Global Constraints

- Never write `settings.json` or `RESEARCH_STATE.md`'s "Current best validated candidate" section without Chris's explicit accept.
- Diagnostic/driver scripts write only to `.scratch/` or untracked local files under `apps/digiquant-web/public/strategies/`; any new diagnostic slug must be distinct from `btc_sdca` and from the already-used set (`btc_sdca_round1..4`, `btc_sdca_round8`, `btc_sdca_validated_baseline`, `btc_sdca_live_settings`, `btc_sdca_task93_round2/3`, `btc_sdca_blend1/2/3`).
- `beats_flat_dca_oos=True` may only be reported if actually true and gate-passed (full walk-forward table + stable sensitivity check).
- Every task must keep `tests/dq/strategies/sdca/` green (`uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`).
- Every change to a function with existing callers must be additive/backward-compatible: existing call sites must produce byte-identical output after the change (verified by the existing test suite continuing to pass unmodified).
- Commit after each task with the standing attribution footer:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
  ```

---

## Prior Art (Already Completed)

Both cited below are shipped, tested (`uv run pytest ../tests/dq/strategies/sdca/ -q` → 585 passed, 38 skipped, all skips environmental), and already executed against real cached data. Neither is re-planned or re-run by this document; they're recorded here so this plan is self-contained and no reader has to re-derive lineage from `RESEARCH_STATE.md`.

**The pearl-plan (post-mortem follow-up, `~/.claude/plans/delightful-riding-pearl.md`), Phases 0-5 — all shipped:**
- *Phase 0 (housekeeping):* `RESEARCH_STATE.md` log entries and `indicator_catalog.py`'s "Phase B" cross-references are resolved and consistent.
- *Phase 1 (band-crossing bug):* `quantile_rails.py`'s `rearrange_non_crossing()`/`detect_crossings()` (identity-preserving clamp, replacing the old row-wise `np.sort()` that could silently splice a different quantile's curve into a mislabeled slot) are landed and shared by `btc_power_law.py`'s `_evaluate_rails()`.
- *Phase 2 (baseline-relative evaluator):* `curve_shape.risk50_linear_reference_curve()` and `baseline_evaluator.py` (`BaselineComparison`, `WalkForwardBaselineComparison`, `compare_to_baseline()`, `run_sdca_walk_forward_vs_baseline()`) are landed — the machinery Task 7 and Task 8 below both reuse for gating.
- *Phase 3 (re-score):* `scripts/run_baseline_relative_rescore.py` ran against real data. Under fixed rails and baseline-relative scoring, the previously-reported validated baseline (`power_law=1.0, m2=0.5, dxy=0.5`) scores only **+21.73%** duration-weighted OOS (down from a stale +84.90%), **loses** to the risk50-linear baseline (`beats_baseline_oos=False`, -0.76%), and fails the sensitivity-stability check.
- *Phase 4 (iterative ablation):* `ablation.py` (`run_ablation_rounds()`, `AblationRoundResult`, `AblationRunResult`) ran 8 rounds via `scripts/run_iterative_ablation.py`. Best result — **Round 8**: `m2=1.0, rs_eth=0.1, onchain_asopr=0.1, fear_greed=0.1, weekly_monthly_rsi=0.1` (`power_law=0.0`) — **+52.01%** duration-weighted OOS, `beats_flat_dca_oos=True` **and** `beats_baseline_oos=True` (+9.13% over the risk50-linear baseline), the first candidate to clear that bar. But `sensitivity.stable=False` and OOS fold 1 (2019-09-12→2022-01-14) is still infeasible.

**The "SDCA recalibration v1" workstream (2026-09-24/25, `RESEARCH_STATE.md` lines ~792-1121) — also shipped:**
- *M2/RSI z-score smoothing fix* (commit `4e05eda9c`) — landed same day as, but ~2 hours before, the Round 8 tearsheet Chris reviewed; his "spiky index" feedback was on a stale run (see the spec's own grounding note). Post-fix roughness: mean |Δrisk| 1.03pts, p99 4.37, but a tail persists (17/3137 days >5pt) — this is exactly what Tasks 1-3 below finish.
- *Round 3* (`curve_optimize_feasibility.search_wide_knee_curve_multi_window_robust`, commit `30c79b920`): worst-case scoring across full-history + fold-IS windows. Mean OOS +1.91% (down from Round 2's +3.53%); fold 2 flipped positive but fold 1 regressed to -29.49%. Root cause: expanding IS windows are dominated by 2015-2017 explosive history, so the search proxy can't reward later-regime robustness. **Not promoted.**
- *Round 4* (dead-zone-width sweep, `curve_optimize.sweep_dead_zone_width`): a structural negative result — the sweep always re-selects Round 2's original width (30.0); no safe non-leaking IS-only objective exists today that can reward a fold-1-specific fix. Round 2's shape re-evaluated: mean OOS +14.50%, fold 1 still -25.79%, `beats_flat_dca_oos=True`, `beats_baseline_oos=True` (+32.27%), but `sensitivity_stable` **could not be computed** (no `nautilus_trader`, no non-Nautilus evaluator). **Not promoted** — the coordinator explicitly stopped here and flagged the decision this plan now answers: accept the OOS-adjacency tradeoff, accept fold 1 as unfixable under curve-shape-only levers, or explore a different lever entirely.
- *3 blend attempts* (Round 8's index/curve × Task #93 Round 2's 17-indicator weighting) — all **rejected**: Approach 1 loses to flat DCA outright (-13.84%); Approach 2 barely beats it (+3.52%) with worse instability than Round 8; Approach 3 gets closest to Round 8's magnitude (+41.57%, `beats_baseline_oos=True`) but with more than double Round 8's instability.
- *North-star oracle ceiling* (`scripts/run_oracle_ceiling.py`, 2026-09-11, non-causal benchmark, never a trading candidate): $148,330 (+14,733.0%) vs lump-sum $17,340 (+1,634.0%) vs flat DCA $4,791 (+379.1%), 61.8% max drawdown. Useful as an upper bound on what curve-shape optimization alone can achieve on this exact price history — not a target this plan claims to hit.
- *Visualization pass and comparison-set expansion* (round 1-4 diagnostic tearsheets, `apps/digiquant-web/app/strategies/sdca-recalibration/page.tsx`, validated-baseline/live-settings/task93-round2/3 diagnostic pages) — out of this plan's scope (tearsheet/presentation work, explicitly deferred by Chris), listed here only so a reader knows it already exists.

**What this means for this plan:** the "explore a different lever" branch of Round 4's stall is exactly Components 1-3 of the spec this plan implements (index smoothing, tiered curve, full-pool reweight) — chosen because curve-shape-only search (Rounds 2-4) had already been shown to plateau, and because Chris's own round-8 review (even though on a stale run) pointed at index roughness and curve granularity as the next lever, not another curve-shape sweep. Task 8 below is the "periodically" and "more self-adjustment" half of Chris's directive, layered on top of both bodies of prior art.

## Reference-Site Parity Target

The reference dashboard's headline backtest (+276,476% vs +26,062% lump-sum, -62.6% vs -83.2% max drawdown) is a **single whole-history 2015-2026 backtest**, not walk-forward-OOS-gated — it was never tested against held-out windows the way every DigiQuant SDCA candidate is. Literally matching that number isn't a meaningful target: it isn't apples-to-apples with the stricter standard SDCA is already held to, and no candidate in either body of prior art above has been evaluated against a non-walk-forward whole-history backtest at all.

The working definition of parity for this plan, used by Task 7 Step 5 and Task 8's gating:

1. **Fold-level, not just aggregate, wins.** `beats_flat_dca_oos=True` on the duration-weighted mean **and** on every individual OOS fold — directly targeting the two folds (2019-09-12→2022-01-14, 2022-01-15→2024-05-19) that have failed under every technique tried so far (pearl-plan Phase 4, recalibration-v1 Rounds 2-4, all 3 blends). A candidate that only wins in aggregate while losing in real sub-periods is not functionally matching what the reference dashboard demonstrates (positive performance shown across its whole displayed history, not just on average).
2. **Drawdown discipline in the same spirit as the reference's -62.6% vs -83.2%** — realized max drawdown materially below flat-DCA's own, not just a better return.
3. **Sensitivity-stable** — the existing neighbor-perturbation check (`sensitivity.stable=True`), since an unstable candidate isn't a real result regardless of its headline number (both Round 8 and Round 4's re-evaluation cleared #1 or came close but failed this).

Report against this three-part bar explicitly, fold-by-fold, in every walk-forward table this plan produces — not just the single aggregate percentage `RESEARCH_STATE.md` has reported until now.

---

## Task 1: Fix `agreement_scaled_blend`'s sign-crossing discontinuity

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/price_oscillators.py:458-497`
- Test: `tests/dq/strategies/sdca/test_price_oscillators.py` (extend `TestAgreementScaledBlend`, ~line 548)

**Interfaces:**
- Consumes: nothing new — pure refactor of `agreement_scaled_blend(long_term_z: pl.Series, medium_term_z: pl.Series, *, long_term_weight: float, agreement_boost: float, disagreement_damp: float, name: str) -> pl.Series` (signature unchanged).
- Produces: same function, now continuous across the sign crossing. `rsi_confluence_z` and every other confluence function (unchanged, consumes this function as before).

- [ ] **Step 1: Write the failing test**

Add to `TestAgreementScaledBlend` in `tests/dq/strategies/sdca/test_price_oscillators.py`:

```python
def test_multiplier_continuous_across_sign_crossing(self) -> None:
    # Sweep medium_term_z across a sign crossing while long_term_z stays
    # fixed and positive; the multiplier (and hence the blended output)
    # must not jump — adjacent samples 0.05 apart differ by a small bound.
    long_term = pl.Series("lt", [1.5] * 41, dtype=pl.Float64)
    medium_values = [round(-1.0 + 0.05 * i, 4) for i in range(41)]
    medium_term = pl.Series("mt", medium_values, dtype=pl.Float64)
    blended = agreement_scaled_blend(
        long_term,
        medium_term,
        long_term_weight=0.6,
        agreement_boost=0.5,
        disagreement_damp=0.5,
        name="blend",
    ).to_list()
    deltas = [abs(blended[i] - blended[i - 1]) for i in range(1, len(blended))]
    assert max(deltas) < 0.1

def test_far_tail_behavior_matches_pre_fix_values(self) -> None:
    # Same-sign, strong agreement: multiplier -> 1 + agreement_boost.
    same_sign = agreement_scaled_blend(
        pl.Series("lt", [2.0]),
        pl.Series("mt", [2.0]),
        long_term_weight=0.6,
        agreement_boost=0.5,
        disagreement_damp=0.5,
        name="blend",
    ).to_list()
    base = 0.6 * 2.0 + 0.4 * 2.0
    assert same_sign[0] == pytest.approx(base * 1.5)
    # Opposite-sign, strong disagreement: multiplier -> disagreement_damp.
    opposite_sign = agreement_scaled_blend(
        pl.Series("lt", [2.0]),
        pl.Series("mt", [-2.0]),
        long_term_weight=0.6,
        agreement_boost=0.5,
        disagreement_damp=0.5,
        name="blend",
    ).to_list()
    base_opp = 0.6 * 2.0 + 0.4 * -2.0
    assert opposite_sign[0] == pytest.approx(base_opp * 0.5)
```

- [ ] **Step 2: Run tests to verify they fail (or verify the discontinuity)**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_price_oscillators.py -k TestAgreementScaledBlend -v` from `digiquant/`
Expected: `test_multiplier_continuous_across_sign_crossing` FAILS (current step function jumps by more than 0.1 at the crossing); `test_far_tail_behavior_matches_pre_fix_values` PASSES already (it's a regression guard, not a new behavior — confirms the fix must not move the tails).

- [ ] **Step 3: Replace the discontinuous branch with a continuous one**

In `price_oscillators.py`, replace the loop body inside `agreement_scaled_blend` (current lines ~467-489):

```python
            base = long_term_weight * float(lv) + medium_term_weight * float(mv)
            if lv == 0.0 or mv == 0.0:
                multiplier = 1.0
            elif (lv > 0) == (mv > 0):
                agreement_frac = min(abs(lv), abs(mv)) / max(abs(lv), abs(mv))
                multiplier = 1.0 + agreement_boost * agreement_frac
            else:
                multiplier = disagreement_damp
            blended.append(max(-3.0, min(3.0, base * multiplier)))
```

with:

```python
            base = long_term_weight * float(lv) + medium_term_weight * float(mv)
            denom = max(abs(lv), abs(mv))
            if denom == 0.0:
                multiplier = 1.0
            else:
                agreement_frac = min(abs(lv), abs(mv)) / denom
                if (lv > 0) == (mv > 0):
                    multiplier = 1.0 + agreement_boost * agreement_frac
                else:
                    multiplier = 1.0 - (1.0 - disagreement_damp) * agreement_frac
            blended.append(max(-3.0, min(3.0, base * multiplier)))
```

The old `lv == 0.0 or mv == 0.0` special case is now redundant: whichever branch is taken, `agreement_frac` is `0` whenever either leg is exactly zero (since `min(abs(lv), abs(mv)) == 0`), so both branches already reduce to `multiplier = 1.0` in that case — the `denom == 0.0` guard only remains necessary for the both-zero case, to avoid a `ZeroDivisionError`. At a sign crossing, `agreement_frac` continuously approaches `0` from both sides as one leg approaches zero, so `multiplier` continuously approaches `1.0` from both the agreement side (`1.0 + agreement_boost * 0`) and the disagreement side (`1.0 - (1.0 - disagreement_damp) * 0`) — no jump.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_price_oscillators.py -k TestAgreementScaledBlend -v` from `digiquant/`
Expected: all 5 tests PASS (3 pre-existing + 2 new).

- [ ] **Step 5: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green.

```bash
git add digiquant/src/digiquant/strategies/sdca/price_oscillators.py digiquant/../tests/dq/strategies/sdca/test_price_oscillators.py
git commit -m "$(cat <<'EOF'
fix(sdca): make agreement_scaled_blend's sign-crossing multiplier continuous

Same-sign agreement already tapered smoothly to 1.0 as legs disagreed;
opposite-sign disagreement was a flat constant with no analogous taper,
producing a kink at every sign crossing. Both branches now taper by the
same agreement_frac, matching behavior at the far tails exactly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 2: Smooth the 4 cadence-broadcast oscillator functions

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/price_oscillators.py` (import block ~line 1-30; `weekly_rsi_z` ~329-339, `monthly_rsi_z` ~342-352, and the MACD equivalents `weekly_macd_z` ~line 582, `monthly_macd_z` ~line 616)
- Test: `tests/dq/strategies/sdca/test_price_oscillators.py` (new smoothing regression tests, mirroring `test_m2_smooths_monthly_print_steps` in `test_indicator_catalog.py`)

**Interfaces:**
- Consumes: `causal_ema_smooth(values: pl.Series, *, half_life: float, min_samples: int = 1) -> pl.Series` from `digiquant.strategies.sdca.composite_risk`.
- Produces: `weekly_rsi_z`, `monthly_rsi_z`, `weekly_macd_z`, `monthly_macd_z` — same signatures, now EMA-smoothed after the `_asof_to_daily` step-broadcast. Confluence functions that consume these (`monthly_rsi_confluence_z`, `weekly_monthly_rsi_confluence_z`, MACD equivalents) are unaffected in signature — they inherit smoother inputs automatically.

- [ ] **Step 1: Write the failing tests**

Add to `tests/dq/strategies/sdca/test_price_oscillators.py`, a new class following the `TestNamedExtras`/M2 pattern:

```python
class TestCadenceBroadcastSmoothing:
    def test_weekly_rsi_z_smooths_weekly_print_steps(self) -> None:
        # A weekly RSI print that jumps hard between two weekly values should
        # ramp over multiple days, not step instantly, once broadcast to daily.
        n = 120
        dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=n - 1), "1d", eager=True)
        # Alternate a low-RSI and high-RSI regime every ~14 days so at least
        # one hard weekly-print transition falls inside the window.
        prices = [100.0 + (40.0 if (i // 14) % 2 == 0 else -40.0) * (i % 14) / 14 for i in range(n)]
        price_s = pl.Series("price", prices, dtype=pl.Float64)
        z = weekly_rsi_z(dates, price_s)
        deltas = [
            abs(a - b)
            for a, b in zip(z.to_list()[1:], z.to_list()[:-1], strict=True)
            if a is not None and b is not None
        ]
        assert deltas, "expected at least one non-null adjacent pair"
        assert max(deltas) < 3.0  # no single-day z jump as large as the pre-fix step

    def test_monthly_rsi_z_smooths_monthly_print_steps(self) -> None:
        n = 400
        dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=n - 1), "1d", eager=True)
        prices = [100.0 + (60.0 if (i // 30) % 2 == 0 else -60.0) * (i % 30) / 30 for i in range(n)]
        price_s = pl.Series("price", prices, dtype=pl.Float64)
        z = monthly_rsi_z(dates, price_s)
        deltas = [
            abs(a - b)
            for a, b in zip(z.to_list()[1:], z.to_list()[:-1], strict=True)
            if a is not None and b is not None
        ]
        assert deltas
        assert max(deltas) < 3.0

    def test_weekly_macd_z_smooths_weekly_print_steps(self) -> None:
        n = 120
        dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=n - 1), "1d", eager=True)
        prices = [100.0 + (40.0 if (i // 14) % 2 == 0 else -40.0) * (i % 14) / 14 for i in range(n)]
        price_s = pl.Series("price", prices, dtype=pl.Float64)
        z = weekly_macd_z(dates, price_s)
        deltas = [
            abs(a - b)
            for a, b in zip(z.to_list()[1:], z.to_list()[:-1], strict=True)
            if a is not None and b is not None
        ]
        assert deltas
        assert max(deltas) < 3.0

    def test_monthly_macd_z_smooths_monthly_print_steps(self) -> None:
        n = 400
        dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=n - 1), "1d", eager=True)
        prices = [100.0 + (60.0 if (i // 30) % 2 == 0 else -60.0) * (i % 30) / 30 for i in range(n)]
        price_s = pl.Series("price", prices, dtype=pl.Float64)
        z = monthly_macd_z(dates, price_s)
        deltas = [
            abs(a - b)
            for a, b in zip(z.to_list()[1:], z.to_list()[:-1], strict=True)
            if a is not None and b is not None
        ]
        assert deltas
        assert max(deltas) < 3.0
```

Add `from datetime import date, timedelta` to the test file's imports if not already present (check the existing import block first — if `date`/`timedelta` are already imported, skip this).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_price_oscillators.py -k TestCadenceBroadcastSmoothing -v` from `digiquant/`
Expected: FAIL (current step function jumps ≥3.0 in z-units on at least one of the synthetic regime transitions — this reproduces the exact structural bug identified in spec 2.1(b)).

If any test passes unexpectedly (the synthetic fixture didn't actually trigger a hard step), tighten the threshold or widen the regime swing until it reliably fails pre-fix — the fixture must reproduce the real bug, not just assert an arbitrary bound.

- [ ] **Step 3: Add named half-life constants and the smoothing pass**

In `price_oscillators.py`, add the import (alongside existing imports, ~top of file):

```python
from digiquant.strategies.sdca.composite_risk import causal_ema_smooth
```

Add named half-life constants near the top of the file, following the `_M2_SMOOTHING_HALFLIFE_DAYS` pattern (`indicator_catalog.py`) — weekly-cadence legs ramp faster than monthly-cadence legs, matching the spec's guidance that a weekly print should ramp faster than M2's monthly-tuned 5-day value:

```python
# Cadence-appropriate EMA half-lives for the weekly/monthly oscillator
# legs' as-of daily broadcast (_asof_to_daily is a pure step function —
# same structural pattern M2 had before its own smoothing fix). Weekly
# prints ramp faster than monthly prints; M2's 5.0-day value (tuned for
# a monthly print) is the reference point for the monthly legs here.
_WEEKLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS = 2.0
_MONTHLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS = 5.0
```

In `weekly_rsi_z`, wrap the final broadcast series with the smoothing pass before it's returned — find the line where `_asof_to_daily(...)` output becomes the function's return value (or is assigned to the z-series before return) and pipe it through:

```python
    daily_z = _asof_to_daily(dates, period_end, weekly_z)
    return causal_ema_smooth(
        daily_z, half_life=_WEEKLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS, min_samples=1
    )
```

(Match this to the function's actual local variable name for the `_asof_to_daily` result and its actual `name`/dtype handling — `causal_ema_smooth` returns a `pl.Series`, so if the original function renamed or cast the series after `_asof_to_daily`, apply the smoothing pass immediately after `_asof_to_daily` and before any such rename/cast, preserving the function's existing return contract exactly.)

Apply the same pattern to `monthly_rsi_z` (using `_MONTHLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS`), `weekly_macd_z` (using `_WEEKLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS`), and `monthly_macd_z` (using `_MONTHLY_OSCILLATOR_SMOOTHING_HALFLIFE_DAYS`) — each gets the smoothing pass inserted immediately after its own `_asof_to_daily(...)` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_price_oscillators.py -k "TestCadenceBroadcastSmoothing or TestNamedExtras" -v` from `digiquant/`
Expected: all PASS.

- [ ] **Step 5: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green — in particular, confluence-function tests (`rsi_confluence_z` consumers) still pass since smoothing only changes the legs' shape, not their sign or the confluence function's contract.

```bash
git add digiquant/src/digiquant/strategies/sdca/price_oscillators.py digiquant/../tests/dq/strategies/sdca/test_price_oscillators.py
git commit -m "$(cat <<'EOF'
fix(sdca): smooth weekly/monthly RSI+MACD's cadence-broadcast step function

_asof_to_daily is a pure backward as-of join -- a step function structurally
identical to M2's pre-fix monthly-print-step pattern. Only M2 got an EMA
smoothing pass in the prior round; these 4 functions (and every confluence
variant that consumes them) never did. Applies causal_ema_smooth with a
cadence-appropriate half-life (2.0d weekly, 5.0d monthly, matching M2's
tuned value) immediately after each function's as-of broadcast.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 3: Roughness diagnostic module + real-data script

**Files:**
- Create: `digiquant/src/digiquant/strategies/sdca/roughness.py`
- Create: `digiquant/scripts/run_indicator_roughness_diagnostic.py`
- Test: `tests/dq/strategies/sdca/test_roughness.py`

**Interfaces:**
- Consumes: `Z_TO_RISK_SCALE` from `digiquant.strategies.sdca.composite_risk`; for the script, `load_sdca_extra_z`/`load_sdca_ohlcv` from `digiquant.strategies.sdca.optimize`, `BtcPowerLawRiskModel`/`load_coefficients` from `digiquant.strategies.sdca.btc_power_law`, `power_law_confluence_z` from `digiquant.strategies.sdca.power_law_zscore`, and `SURVIVING_INDICATORS`/`EXTRA_WINDOWS`/`DEFAULT_DATA_PATH` from `digiquant.scripts.run_aggregate_reweight_full17_fixed_index` (reusing that script's already-established 17-indicator data-assembly pattern rather than re-deriving it).
- Produces: `IndicatorRoughness` (pydantic model), `compute_indicator_roughness(name: str, z: pl.Series) -> IndicatorRoughness`, `compute_pool_roughness(indicators: dict[str, pl.Series]) -> list[IndicatorRoughness]` — Task 2's before/after comparison and Component 3's reporting both read `IndicatorRoughness` fields directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/dq/strategies/sdca/test_roughness.py`:

```python
"""Tests for the per-indicator roughness diagnostic (#SDCA index smoothing)."""

from __future__ import annotations

import pytest
import polars as pl
from digiquant.strategies.sdca.composite_risk import Z_TO_RISK_SCALE
from digiquant.strategies.sdca.roughness import compute_indicator_roughness, compute_pool_roughness

pytestmark = pytest.mark.unit


class TestComputeIndicatorRoughness:
    def test_constant_series_has_zero_roughness(self) -> None:
        z = pl.Series("z", [1.0] * 50, dtype=pl.Float64)
        stats = compute_indicator_roughness("flat", z)
        assert stats.name == "flat"
        assert stats.n_days == 50
        assert stats.mean_abs_delta_risk == pytest.approx(0.0)
        assert stats.max_abs_delta_risk == pytest.approx(0.0)
        assert stats.spike_days_gt_2 == 0

    def test_step_function_produces_one_large_spike(self) -> None:
        # 30 days at z=0.0, one jump to z=3.0, 30 more days at z=3.0.
        z = pl.Series("z", [0.0] * 30 + [3.0] * 30, dtype=pl.Float64)
        stats = compute_indicator_roughness("step", z)
        expected_jump = 3.0 * Z_TO_RISK_SCALE
        assert stats.max_abs_delta_risk == pytest.approx(expected_jump)
        assert stats.spike_days_gt_2 == 1
        assert stats.spike_days_gt_5 == (1 if expected_jump > 5.0 else 0)
        # 58 zero-deltas + 1 nonzero delta out of 59 total deltas.
        assert stats.mean_abs_delta_risk == pytest.approx(expected_jump / 59.0)

    def test_ramp_has_no_spikes_above_its_per_step_delta(self) -> None:
        # Linear ramp from 0.0 to 3.0 over 30 days -- per-step delta is small
        # and constant, unlike the step function's single large jump.
        z = pl.Series("z", [round(3.0 * i / 29, 6) for i in range(30)], dtype=pl.Float64)
        stats = compute_indicator_roughness("ramp", z)
        per_step = (3.0 / 29) * Z_TO_RISK_SCALE
        assert stats.max_abs_delta_risk == pytest.approx(per_step, abs=1e-4)
        assert stats.spike_days_gt_2 == 0

    def test_nulls_are_dropped_before_differencing(self) -> None:
        # Leading nulls (e.g. a rolling window's warm-up) must not count as
        # a delta once real values begin.
        z = pl.Series("z", [None, None, 1.0, 1.0, 1.0], dtype=pl.Float64)
        stats = compute_indicator_roughness("warmup", z)
        assert stats.n_days == 3
        assert stats.max_abs_delta_risk == pytest.approx(0.0)

    def test_empty_series_returns_zeroed_stats(self) -> None:
        z = pl.Series("z", [], dtype=pl.Float64)
        stats = compute_indicator_roughness("empty", z)
        assert stats.n_days == 0
        assert stats.mean_abs_delta_risk == pytest.approx(0.0)


class TestComputePoolRoughness:
    def test_returns_one_entry_per_indicator_in_input_order(self) -> None:
        indicators = {
            "a": pl.Series("a", [0.0, 0.0], dtype=pl.Float64),
            "b": pl.Series("b", [0.0, 5.0], dtype=pl.Float64),
        }
        results = compute_pool_roughness(indicators)
        assert [r.name for r in results] == ["a", "b"]
        assert results[0].max_abs_delta_risk == pytest.approx(0.0)
        assert results[1].max_abs_delta_risk == pytest.approx(5.0 * Z_TO_RISK_SCALE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_roughness.py -v` from `digiquant/`
Expected: FAIL with `ModuleNotFoundError: No module named 'digiquant.strategies.sdca.roughness'`.

- [ ] **Step 3: Implement `roughness.py`**

Create `digiquant/src/digiquant/strategies/sdca/roughness.py`:

```python
"""Per-indicator day-over-day roughness diagnostic (composite-index smoothing).

Measures each indicator's z-series the same way the round-8 post-mortem
measured the composite risk output (mean/p95/p99/max |delta|, spike counts
above fixed thresholds) so individual indicators can be compared on the
same risk-point scale the composite output is judged on, before deciding
which ones (per spec 2.1(b)) still need a smoothing pass.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import Z_TO_RISK_SCALE

_SPIKE_THRESHOLDS_RISK_PTS = (2.0, 5.0, 10.0)


class IndicatorRoughness(BaseModel):
    """Day-over-day roughness for one indicator's z-series, in risk-point units."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    n_days: int = Field(ge=0)
    mean_abs_delta_risk: float = Field(ge=0.0)
    p95_abs_delta_risk: float = Field(ge=0.0)
    p99_abs_delta_risk: float = Field(ge=0.0)
    max_abs_delta_risk: float = Field(ge=0.0)
    spike_days_gt_2: int = Field(ge=0)
    spike_days_gt_5: int = Field(ge=0)
    spike_days_gt_10: int = Field(ge=0)


def _percentile(sorted_values: list[float], p: float) -> float:
    idx = min(len(sorted_values) - 1, int(round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]


def compute_indicator_roughness(name: str, z: pl.Series) -> IndicatorRoughness:
    """Day-over-day |delta z| * Z_TO_RISK_SCALE roughness for one indicator.

    Nulls are dropped before differencing so warm-up nulls (e.g. a rolling
    window's first `min_samples` days) never count as a delta.
    """
    values = [float(v) for v in z.to_list() if v is not None]
    n_days = len(values)
    deltas = [abs(values[i] - values[i - 1]) * Z_TO_RISK_SCALE for i in range(1, n_days)]
    if not deltas:
        return IndicatorRoughness(
            name=name,
            n_days=n_days,
            mean_abs_delta_risk=0.0,
            p95_abs_delta_risk=0.0,
            p99_abs_delta_risk=0.0,
            max_abs_delta_risk=0.0,
            spike_days_gt_2=0,
            spike_days_gt_5=0,
            spike_days_gt_10=0,
        )
    sorted_deltas = sorted(deltas)
    gt2, gt5, gt10 = _SPIKE_THRESHOLDS_RISK_PTS
    return IndicatorRoughness(
        name=name,
        n_days=n_days,
        mean_abs_delta_risk=sum(deltas) / len(deltas),
        p95_abs_delta_risk=_percentile(sorted_deltas, 0.95),
        p99_abs_delta_risk=_percentile(sorted_deltas, 0.99),
        max_abs_delta_risk=max(deltas),
        spike_days_gt_2=sum(1 for d in deltas if d > gt2),
        spike_days_gt_5=sum(1 for d in deltas if d > gt5),
        spike_days_gt_10=sum(1 for d in deltas if d > gt10),
    )


def compute_pool_roughness(indicators: dict[str, pl.Series]) -> list[IndicatorRoughness]:
    """One `IndicatorRoughness` per entry, in `indicators`' iteration order."""
    return [compute_indicator_roughness(name, z) for name, z in indicators.items()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_roughness.py -v` from `digiquant/`
Expected: all PASS.

- [ ] **Step 5: Write the real-data driver script**

Create `digiquant/scripts/run_indicator_roughness_diagnostic.py`:

```python
"""Per-indicator roughness diagnostic across the full 17 SURVIVING_INDICATORS
(SDCA index smoothing, 2026-09-25). Diagnostic only -- writes to .scratch/,
never settings.json or RESEARCH_STATE.md's validated-candidate section.

Run: uv run python scripts/run_indicator_roughness_diagnostic.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.roughness import compute_pool_roughness
from scripts.run_aggregate_reweight_full17_fixed_index import (
    DEFAULT_DATA_PATH,
    EXTRA_WINDOWS,
    SURVIVING_INDICATORS,
)

OUT_PATH = Path(".scratch/indicator_roughness_diagnostic.json")


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    )

    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None, extra_windows=EXTRA_WINDOWS
    )
    missing = [n for n in SURVIVING_INDICATORS if n != "power_law" and n not in extra_z]
    if missing:
        raise SystemExit(f"missing extra_z for: {missing} -- have {sorted(extra_z)}")

    pool = {"power_law": power_law_z, **{n: extra_z[n] for n in SURVIVING_INDICATORS if n != "power_law"}}
    results = compute_pool_roughness(pool)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps([r.model_dump() for r in results], indent=2))

    print(f"{'name':<22}{'mean':>8}{'p95':>8}{'p99':>8}{'max':>8}{'>2pt':>6}{'>5pt':>6}{'>10pt':>6}")
    for r in sorted(results, key=lambda r: r.max_abs_delta_risk, reverse=True):
        print(
            f"{r.name:<22}{r.mean_abs_delta_risk:>8.2f}{r.p95_abs_delta_risk:>8.2f}"
            f"{r.p99_abs_delta_risk:>8.2f}{r.max_abs_delta_risk:>8.2f}"
            f"{r.spike_days_gt_2:>6}{r.spike_days_gt_5:>6}{r.spike_days_gt_10:>6}"
        )
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the script against real cached data and eyeball the output**

Run: `uv run python scripts/run_indicator_roughness_diagnostic.py` from `digiquant/`
Expected: prints a 17-row table and writes `.scratch/indicator_roughness_diagnostic.json`. Confirm `weekly_rsi`/`monthly_rsi`/`weekly_macd`/`monthly_macd`/`weekly_monthly_rsi`/`weekly_monthly_macd` (Task 2's fix, already landed by this point) show materially lower `max`/`spike_days_gt_10` than before Task 2 — use this run's output as the "after" side of the before/after comparison spec 2.4 and the Gate section call for when reporting to Chris; capture a copy of the pre-Task-2 numbers (e.g. by re-running against a stashed pre-Task-2 checkout, or simply noting this step should logically run once before Task 2 and once after if a strict before/after diff is wanted — not required for this task's own completion, only for the eventual Chris-facing report in Task 7).

- [ ] **Step 7: Commit**

```bash
git add digiquant/src/digiquant/strategies/sdca/roughness.py digiquant/scripts/run_indicator_roughness_diagnostic.py digiquant/../tests/dq/strategies/sdca/test_roughness.py
git commit -m "$(cat <<'EOF'
feat(sdca): add per-indicator roughness diagnostic across SURVIVING_INDICATORS

Reuses run_aggregate_reweight_full17_fixed_index.py's established 17-name
data-assembly pattern (load_sdca_extra_z + power_law_confluence_z) rather
than re-deriving it. Reports day-over-day |delta z|*Z_TO_RISK_SCALE in the
same units as the round-8 post-mortem's composite-risk roughness table, so
individual indicators and the composite output are directly comparable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 4: Tiered `SdcaCurveShape`

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/curve_shape.py` (full file, 132 lines pre-change)
- Test: `tests/dq/strategies/sdca/test_curve_shape.py` (new `TestTieredSdcaCurveShape` class)

**Interfaces:**
- Consumes: nothing new.
- Produces: `SdcaCurveShape` gains 4 new fields — `buy_mid_knee_risk: float | None = None`, `buy_mid_curvature: float = 1.0`, `sell_mid_knee_risk: float | None = None`, `sell_mid_curvature: float = 1.0` — all with defaults, so every existing 6-kwarg construction site (`curve_optimize.py`, `risk50_linear_reference_curve`, `test_curve_shape.py`'s `_shape()` helper) is unaffected. `rate_at()`'s signature is unchanged; its behavior is now piecewise when the relevant mid-knee is set. Task 5 consumes the 4 new field names directly (`_MID_TIER_KEYS` tuple).

**Design note on spec ambiguity**: spec section 2.2 describes the piecewise ramp as "from the far knee toward the mid knee... from the mid knee to the extreme" (mid knee sits between the outer knee and the extreme, 0/100) but a later sentence in the same section says search bounds should keep "the mid knee always sits strictly between its side's outer knee and the risk-50 midpoint." These two descriptions place the mid knee on opposite sides of the outer knee. This plan resolves the ambiguity in favor of the piecewise description (mid knee between the outer knee and the extreme) since that is what makes `rate_at()`'s two segments well-defined and is restated as the actual algorithm ("ramp toward roughly half of max_rate," then "ramp the remaining half up to full max_rate") rather than a parenthetical aside about search bounds. The validator below enforces this reading.

- [ ] **Step 1: Write the failing tests**

Add to `tests/dq/strategies/sdca/test_curve_shape.py`, a new class:

```python
class TestTieredSdcaCurveShape:
    def test_defaults_recover_single_knee_behavior(self) -> None:
        baseline = _shape()
        tiered_but_collapsed = _shape()  # no mid-tier overrides -> both None
        for r in RISK_NODES:
            assert tiered_but_collapsed.rate_at(r) == pytest.approx(baseline.rate_at(r))

    def test_buy_mid_knee_reaches_half_of_max_rate(self) -> None:
        shape = _shape(buy_max_rate=20.0, buy_knee_risk=40.0, buy_mid_knee_risk=10.0)
        assert shape.rate_at(10.0) == pytest.approx(10.0)

    def test_sell_mid_knee_reaches_half_of_max_rate(self) -> None:
        shape = _shape(sell_max_rate=20.0, sell_knee_risk=60.0, sell_mid_knee_risk=90.0)
        assert shape.rate_at(90.0) == pytest.approx(-10.0)

    def test_buy_extreme_still_reaches_full_max_rate_when_tiered(self) -> None:
        shape = _shape(buy_max_rate=20.0, buy_knee_risk=40.0, buy_mid_knee_risk=10.0)
        assert shape.rate_at(0.0) == pytest.approx(20.0)

    def test_sell_extreme_still_reaches_full_max_rate_when_tiered(self) -> None:
        shape = _shape(sell_max_rate=20.0, sell_knee_risk=60.0, sell_mid_knee_risk=90.0)
        assert shape.rate_at(100.0) == pytest.approx(-20.0)

    def test_continuous_at_buy_mid_knee_boundary(self) -> None:
        shape = _shape(buy_max_rate=20.0, buy_knee_risk=40.0, buy_mid_knee_risk=10.0, buy_curvature=2.0, buy_mid_curvature=1.5)
        just_above = shape.rate_at(10.0 + 1e-6)
        just_below = shape.rate_at(10.0 - 1e-6)
        assert just_above == pytest.approx(just_below, abs=1e-4)

    def test_continuous_at_sell_mid_knee_boundary(self) -> None:
        shape = _shape(sell_max_rate=20.0, sell_knee_risk=60.0, sell_mid_knee_risk=90.0, sell_curvature=2.0, sell_mid_curvature=1.5)
        just_above = shape.rate_at(90.0 + 1e-6)
        just_below = shape.rate_at(90.0 - 1e-6)
        assert just_above == pytest.approx(just_below, abs=1e-4)

    def test_tiered_nodes_are_monotonic_non_increasing(self) -> None:
        shape = _shape(
            buy_max_rate=20.0, buy_knee_risk=40.0, buy_mid_knee_risk=15.0, buy_mid_curvature=2.0,
            sell_max_rate=20.0, sell_knee_risk=60.0, sell_mid_knee_risk=85.0, sell_mid_curvature=2.0,
        )
        nodes = shape.to_nodes()
        for a, b in itertools.pairwise(nodes):
            assert a >= b - 1e-9

    def test_buy_mid_knee_must_sit_strictly_inside_outer_knee(self) -> None:
        with pytest.raises(ValueError):
            _shape(buy_knee_risk=40.0, buy_mid_knee_risk=40.0)
        with pytest.raises(ValueError):
            _shape(buy_knee_risk=40.0, buy_mid_knee_risk=0.0)

    def test_sell_mid_knee_must_sit_strictly_inside_outer_knee(self) -> None:
        with pytest.raises(ValueError):
            _shape(sell_knee_risk=60.0, sell_mid_knee_risk=60.0)
        with pytest.raises(ValueError):
            _shape(sell_knee_risk=60.0, sell_mid_knee_risk=100.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_shape.py -k TestTieredSdcaCurveShape -v` from `digiquant/`
Expected: FAIL with `TypeError`/`ValidationError: extra fields not permitted` (the 4 new fields don't exist yet on `SdcaCurveShape`, whose `model_config = ConfigDict(frozen=True, strict=True)` rejects unknown kwargs by default under pydantic v2 unless `extra` is configured — confirm this is the actual failure mode, not a different error, before proceeding).

- [ ] **Step 3: Implement the tiered fields and piecewise `rate_at()`**

Rewrite `digiquant/src/digiquant/strategies/sdca/curve_shape.py`:

```python
"""Parametric SDCA curve shape — the authoring/optimization surface (#3169).

`SdcaCurveShape` is a compact, validated description of the remaining-book
accumulate/distribute rate as a function of composite risk (0-100). It
generates the 21-node `AccumDistCurve` the runtime actually consumes.

Mid-tier fields (buy_mid_knee_risk/buy_mid_curvature and the sell-side
equivalents) are optional: when unset, `rate_at()` uses the original
single-segment ramp unchanged. When set, the ramp from the outer knee to
the extreme is split into two segments, reaching `_MID_TIER_RATE_FRAC` of
`max_rate` at the mid knee and the full `max_rate` only at the extreme —
so a medium-risk signal produces a partial allocation change and only a
true extreme drives 100% investment/divestment.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.strategies.sdca.curve import RISK_NODES

_RATE_EPS = 1e-12
_MID_TIER_RATE_FRAC = 0.5


class SdcaCurveShape(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    buy_max_rate: float = Field(ge=0.0, le=100.0)
    buy_knee_risk: float = Field(gt=0.0, lt=100.0)
    sell_knee_risk: float = Field(gt=0.0, le=100.0)
    sell_max_rate: float = Field(ge=0.0, le=100.0)
    buy_curvature: float = Field(ge=1.0)
    sell_curvature: float = Field(ge=1.0)
    buy_mid_knee_risk: float | None = Field(default=None, gt=0.0, lt=100.0)
    buy_mid_curvature: float = Field(default=1.0, ge=1.0)
    sell_mid_knee_risk: float | None = Field(default=None, gt=0.0, lt=100.0)
    sell_mid_curvature: float = Field(default=1.0, ge=1.0)

    @model_validator(mode="after")
    def _enforce_shape_invariants(self) -> SdcaCurveShape:
        if not (self.buy_knee_risk < self.sell_knee_risk):
            raise ValueError(
                f"buy_knee_risk ({self.buy_knee_risk}) must be < sell_knee_risk ({self.sell_knee_risk})"
            )
        if self.sell_max_rate > 0.0 and self.sell_knee_risk >= 100.0:
            raise ValueError("sell_knee_risk must be < 100 when sell_max_rate > 0")
        if self.buy_mid_knee_risk is not None and not (0.0 < self.buy_mid_knee_risk < self.buy_knee_risk):
            raise ValueError(
                f"buy_mid_knee_risk ({self.buy_mid_knee_risk}) must sit strictly between "
                f"0 and buy_knee_risk ({self.buy_knee_risk})"
            )
        if self.sell_mid_knee_risk is not None and not (
            self.sell_knee_risk < self.sell_mid_knee_risk < 100.0
        ):
            raise ValueError(
                f"sell_mid_knee_risk ({self.sell_mid_knee_risk}) must sit strictly between "
                f"sell_knee_risk ({self.sell_knee_risk}) and 100"
            )
        self._assert_generated_invariants(self.to_nodes())
        return self

    def rate_at(self, risk: float) -> float:
        if risk < self.buy_knee_risk:
            return self._buy_rate(risk)
        if risk <= self.sell_knee_risk:
            return 0.0
        return self._sell_rate(risk)

    def _buy_rate(self, risk: float) -> float:
        if self.buy_mid_knee_risk is None:
            span = self.buy_knee_risk
            t = (self.buy_knee_risk - risk) / span
            return self.buy_max_rate * (t**self.buy_curvature)
        mid_rate = self.buy_max_rate * _MID_TIER_RATE_FRAC
        if risk >= self.buy_mid_knee_risk:
            span = self.buy_knee_risk - self.buy_mid_knee_risk
            t = (self.buy_knee_risk - risk) / span
            return mid_rate * (t**self.buy_curvature)
        span = self.buy_mid_knee_risk
        t = (self.buy_mid_knee_risk - risk) / span
        return mid_rate + (self.buy_max_rate - mid_rate) * (t**self.buy_mid_curvature)

    def _sell_rate(self, risk: float) -> float:
        if self.sell_mid_knee_risk is None:
            span = 100.0 - self.sell_knee_risk
            t = (risk - self.sell_knee_risk) / span
            return -self.sell_max_rate * (t**self.sell_curvature)
        mid_rate = self.sell_max_rate * _MID_TIER_RATE_FRAC
        if risk <= self.sell_mid_knee_risk:
            span = self.sell_mid_knee_risk - self.sell_knee_risk
            t = (risk - self.sell_knee_risk) / span
            return -(mid_rate * (t**self.sell_curvature))
        span = 100.0 - self.sell_mid_knee_risk
        t = (risk - self.sell_mid_knee_risk) / span
        return -(mid_rate + (self.sell_max_rate - mid_rate) * (t**self.sell_mid_curvature))

    def to_nodes(self) -> tuple[float, ...]:
        return tuple(self.rate_at(r) for r in RISK_NODES)

    def _assert_generated_invariants(self, nodes: tuple[float, ...]) -> None:
        for risk, rate in zip(RISK_NODES, nodes, strict=True):
            if self.buy_knee_risk <= risk <= self.sell_knee_risk:
                if abs(rate) > _RATE_EPS:
                    raise ValueError(f"dead-zone node at risk={risk} must be exactly 0, got {rate}")
        for a, b in zip(nodes, nodes[1:], strict=True):
            if b > a + _RATE_EPS:
                raise ValueError(f"generated nodes must be monotonic non-increasing: {a} then {b}")


def risk50_linear_reference_curve(max_rate: float, *, eps: float = 0.1) -> SdcaCurveShape:
    """Linear reference: buy below risk 50, sell above, single knee each side."""
    return SdcaCurveShape(
        buy_max_rate=max_rate,
        buy_knee_risk=50.0 - eps,
        sell_knee_risk=50.0 + eps,
        sell_max_rate=max_rate,
        buy_curvature=1.0,
        sell_curvature=1.0,
    )


__all__ = ["SdcaCurveShape", "risk50_linear_reference_curve"]
```

Note: the `_assert_generated_invariants` body above is reconstructed to match its documented behavior (dead-zone-exactly-zero + monotonic non-increasing) — before editing, open the current file and diff this reconstruction against the real body; if the real implementation differs in any structural way beyond variable naming, preserve the real logic exactly and only add the two new field declarations, the two new validator checks, and the piecewise `rate_at()`/`_buy_rate`/`_sell_rate` — do not replace working invariant-checking logic with this plan's reconstruction if they diverge.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_shape.py -v` from `digiquant/`
Expected: all PASS, including every pre-existing test in `TestSdcaCurveShapeNodes`, `TestSdcaCurveShapeConstruction`, `TestSdcaCurveShapePropertySweep`, `TestRisk50LinearReferenceCurve` unchanged.

- [ ] **Step 5: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green — in particular `curve_optimize.py`'s tests (which construct `SdcaCurveShape` with only the original 6 kwargs) are unaffected since all 4 new fields default to values that collapse to the original single-segment behavior.

```bash
git add digiquant/src/digiquant/strategies/sdca/curve_shape.py digiquant/../tests/dq/strategies/sdca/test_curve_shape.py
git commit -m "$(cat <<'EOF'
feat(sdca): add tiered mid-knee/curvature to SdcaCurveShape

buy_mid_knee_risk/buy_mid_curvature and the sell-side equivalents are new,
optional (default None/1.0) fields. When set, rate_at() ramps to ~50% of
max_rate at the mid knee and the remaining 50% from the mid knee to the
true extreme (risk 0/100) -- so a medium-risk signal now produces a
partial allocation change while true extremes still drive 100%
investment/divestment. Unset (the default), behavior is byte-identical to
the prior single-knee curve.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 5: Tiered search space in `curve_optimize.py`

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/curve_optimize.py` (`_SHAPE_KEYS` block ~line 71, `shape_from_bounds_ok` ~186, `params_from_shape` ~211, `round_shape_for_preset` ~215, `WIDE_KNEE_SEARCH_BOUNDS`/`WIDE_KNEE_COARSE_GRID` block ~450-466, `sample_wide_knee_curve_trials` ~469, `search_curve` ~666, new `search_wide_knee_curve_tiered` function after `search_wide_knee_curve` ~534)
- Test: `tests/dq/strategies/sdca/test_curve_optimize.py` (extend `TestSearchSpace`, `TestSampleWideKneeCurveTrials`; new `TestSearchWideKneeCurveTiered` class)

**Interfaces:**
- Consumes: `SdcaCurveShape`'s 4 new fields (Task 4).
- Produces: `_MID_TIER_KEYS: tuple[str, ...]`, `WIDE_KNEE_TIERED_SEARCH_BOUNDS: dict[str, tuple[float, float]]`, `WIDE_KNEE_TIERED_COARSE_GRID: dict[str, tuple[float, ...]]`, `search_wide_knee_curve_tiered(dates, prices, risk, *, initial_cash, frozen_weights, n_random=3000, seed=42, include_grid=True, bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS, grid=WIDE_KNEE_TIERED_COARSE_GRID, gates=None) -> CurveOptimizeResult` — Task 7's driver script calls this directly. `shape_from_bounds_ok`/`params_from_shape` gain an additive `extra_keys: tuple[str, ...] = ()` kwarg; `sample_wide_knee_curve_trials` gains an additive `extra_keys: tuple[str, ...] = ()` kwarg. Every existing caller of these 3 functions and of `search_curve`/`search_wide_knee_curve`/`round_shape_for_preset` is unaffected (default `extra_keys=()`, or a `params` dict that simply never contains the new keys).

- [ ] **Step 1: Write the failing tests**

Add to `tests/dq/strategies/sdca/test_curve_optimize.py`:

```python
class TestMidTierShapePlumbing:
    def test_params_from_shape_includes_mid_tier_when_present(self) -> None:
        shape = SdcaCurveShape(
            buy_max_rate=10.0, buy_knee_risk=35.0, sell_knee_risk=80.0, sell_max_rate=10.0,
            buy_curvature=1.0, sell_curvature=1.0, buy_mid_knee_risk=10.0, buy_mid_curvature=2.0,
        )
        params = params_from_shape(shape, extra_keys=_MID_TIER_KEYS)
        assert params["buy_mid_knee_risk"] == pytest.approx(10.0)
        assert params["buy_mid_curvature"] == pytest.approx(2.0)
        assert "sell_mid_knee_risk" not in params  # None on the shape -> omitted

    def test_params_from_shape_default_extra_keys_matches_pre_change_output(self) -> None:
        shape = published_curve_shape()
        assert params_from_shape(shape) == {k: float(getattr(shape, k)) for k in _SHAPE_KEYS}

    def test_shape_from_bounds_ok_validates_mid_tier_when_extra_keys_passed(self) -> None:
        params = {
            "buy_max_rate": 10.0, "buy_knee_risk": 35.0, "sell_knee_risk": 80.0,
            "sell_max_rate": 10.0, "buy_curvature": 1.0, "sell_curvature": 1.0,
            "buy_mid_knee_risk": 10.0, "buy_mid_curvature": 2.0,
        }
        assert shape_from_bounds_ok(
            params, bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS, extra_keys=_MID_TIER_KEYS
        )

    def test_shape_from_bounds_ok_rejects_mid_knee_outside_bounds(self) -> None:
        params = {
            "buy_max_rate": 10.0, "buy_knee_risk": 35.0, "sell_knee_risk": 80.0,
            "sell_max_rate": 10.0, "buy_curvature": 1.0, "sell_curvature": 1.0,
            "buy_mid_knee_risk": 34.9, "buy_mid_curvature": 2.0,  # collapses onto outer knee
        }
        assert not shape_from_bounds_ok(
            params, bounds={**WIDE_KNEE_TIERED_SEARCH_BOUNDS, "buy_mid_knee_risk": (1.0, 5.0)},
            extra_keys=_MID_TIER_KEYS,
        )

    def test_round_shape_for_preset_round_trips_mid_tier_fields(self) -> None:
        shape = SdcaCurveShape(
            buy_max_rate=10.0, buy_knee_risk=35.0, sell_knee_risk=80.0, sell_max_rate=10.0,
            buy_curvature=1.0, sell_curvature=1.0, buy_mid_knee_risk=10.049, buy_mid_curvature=1.951,
        )
        rounded = round_shape_for_preset(shape)
        assert rounded.buy_mid_knee_risk == pytest.approx(10.0)
        assert rounded.buy_mid_curvature == pytest.approx(2.0)


class TestSampleWideKneeCurveTrialsTiered:
    def test_distinct_mid_tier_trials_are_not_deduped_together(self) -> None:
        bounds = {**WIDE_KNEE_SEARCH_BOUNDS, "buy_mid_knee_risk": (2.0, 15.0), "buy_mid_curvature": (1.0, 3.0),
                  "sell_mid_knee_risk": (85.0, 98.0), "sell_mid_curvature": (1.0, 3.0)}
        grid = {**WIDE_KNEE_COARSE_GRID, "buy_mid_knee_risk": (5.0, 10.0), "buy_mid_curvature": (1.5,),
                 "sell_mid_knee_risk": (90.0,), "sell_mid_curvature": (1.5,)}
        trials = sample_wide_knee_curve_trials(
            n_random=0, include_grid=True, bounds=bounds, grid=grid, extra_keys=_MID_TIER_KEYS
        )
        mid_knee_values = {t["buy_mid_knee_risk"] for t in trials}
        assert mid_knee_values == {5.0, 10.0}


class TestSearchWideKneeCurveTiered:
    def test_search_wide_knee_curve_tiered_returns_feasible_result(self, tiny_frozen_index) -> None:
        dates, prices, risk, weights = tiny_frozen_index
        result = search_wide_knee_curve_tiered(
            dates, prices, risk,
            initial_cash=1000.0, frozen_weights=weights,
            n_random=20, seed=1, include_grid=False,
        )
        assert result.num_evaluations > 0
```

The `tiny_frozen_index` fixture referenced in `TestSearchWideKneeCurveTiered` must already exist in this test file (used by the pre-existing `TestSearchWideKneeCurve` class per the earlier grep of this file) — reuse it as-is; do not redefine it. If it does not exist under that exact name, use whatever fixture/helper `TestSearchWideKneeCurve`'s existing tests already use to build a small synthetic `(dates, prices, risk, weights)` tuple, matching that test's exact call pattern.

Add the needed imports to the test file's import block if not already present: `SdcaCurveShape` (likely already imported), `params_from_shape`, `shape_from_bounds_ok`, `round_shape_for_preset`, `_SHAPE_KEYS`, `_MID_TIER_KEYS`, `WIDE_KNEE_SEARCH_BOUNDS`, `WIDE_KNEE_COARSE_GRID`, `WIDE_KNEE_TIERED_SEARCH_BOUNDS`, `sample_wide_knee_curve_trials`, `search_wide_knee_curve_tiered`, `published_curve_shape`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_optimize.py -k "MidTier or Tiered" -v` from `digiquant/`
Expected: FAIL with `ImportError`/`AttributeError` (none of the new names exist yet) or `TypeError: unexpected keyword argument 'extra_keys'`.

- [ ] **Step 3: Implement the plumbing**

In `curve_optimize.py`, add near `_SHAPE_KEYS` (~line 78):

```python
_MID_TIER_KEYS = (
    "buy_mid_knee_risk",
    "buy_mid_curvature",
    "sell_mid_knee_risk",
    "sell_mid_curvature",
)
```

Replace `shape_from_bounds_ok` (~line 186-208):

```python
def shape_from_bounds_ok(
    params: dict[str, float | int | str],
    *,
    bounds: dict[str, tuple[float, float]] | None = None,
    extra_keys: tuple[str, ...] = (),
) -> bool:
    """True when params form a valid shape inside ``bounds`` (default ``CURVE_SEARCH_BOUNDS``).

    ``extra_keys`` optionally includes additional shape fields (e.g.
    ``_MID_TIER_KEYS``) from ``params`` when present -- absent from
    ``params`` or from ``extra_keys`` (the default), behavior is identical
    to the original 6-field-only check.
    """
    b = bounds if bounds is not None else CURVE_SEARCH_BOUNDS
    try:
        kwargs: dict[str, float] = {key: float(params[key]) for key in _SHAPE_KEYS}
        for key in extra_keys:
            value = params.get(key)
            if value is not None:
                kwargs[key] = float(value)
        shape = SdcaCurveShape(**kwargs)
    except (KeyError, TypeError, ValueError):
        return False
    for key, (lo, hi) in b.items():
        value = float(getattr(shape, key))
        if value < lo - 1e-9 or value > hi + 1e-9:
            return False
    return shape.sell_max_rate > 0.0
```

Replace `params_from_shape` (~line 211-212):

```python
def params_from_shape(shape: SdcaCurveShape, *, extra_keys: tuple[str, ...] = ()) -> dict[str, float]:
    out = {key: float(getattr(shape, key)) for key in _SHAPE_KEYS}
    for key in extra_keys:
        value = getattr(shape, key)
        if value is not None:
            out[key] = float(value)
    return out
```

Replace `round_shape_for_preset` (~line 215-224):

```python
def round_shape_for_preset(shape: SdcaCurveShape) -> SdcaCurveShape:
    """One-decimal published curve; re-validates dead zone / signs."""
    kwargs: dict[str, float] = {
        "buy_max_rate": round(shape.buy_max_rate, 1),
        "buy_knee_risk": round(shape.buy_knee_risk, 1),
        "sell_knee_risk": round(shape.sell_knee_risk, 1),
        "sell_max_rate": round(shape.sell_max_rate, 1),
        "buy_curvature": round(shape.buy_curvature, 1),
        "sell_curvature": round(shape.sell_curvature, 1),
    }
    for key in _MID_TIER_KEYS:
        value = getattr(shape, key)
        if value is not None:
            kwargs[key] = round(value, 1)
    return SdcaCurveShape(**kwargs)
```

In `search_curve` (~line 666-694), replace the trial-construction block:

```python
    for params in trials:
        try:
            kwargs: dict[str, float] = {
                "buy_max_rate": float(params["buy_max_rate"]),
                "buy_knee_risk": float(params["buy_knee_risk"]),
                "sell_knee_risk": float(params["sell_knee_risk"]),
                "sell_max_rate": float(params["sell_max_rate"]),
                "buy_curvature": float(params["buy_curvature"]),
                "sell_curvature": float(params["sell_curvature"]),
            }
            for key in _MID_TIER_KEYS:
                value = params.get(key)
                if value is not None:
                    kwargs[key] = float(value)
            shape = SdcaCurveShape(**kwargs)
        except (KeyError, TypeError, ValueError):
            continue
        ranked.append(score_shape_on_index(dates, prices, risk, shape, initial_cash, gates=g))
```

Add near `WIDE_KNEE_SEARCH_BOUNDS`/`WIDE_KNEE_COARSE_GRID` (~line 466, after the existing dicts):

```python
# Tiered search space: same base 6 dimensions as WIDE_KNEE_SEARCH_BOUNDS,
# plus a mid-tier knee/curvature per side. Per the design spec (2.2), the
# mid knee must sit strictly between its side's outer knee and the true
# extreme (0 for buy, 100 for sell) -- see SdcaCurveShape's validator,
# which rejects any draw outside that range regardless of these bounds.
WIDE_KNEE_TIERED_SEARCH_BOUNDS: dict[str, tuple[float, float]] = {
    **WIDE_KNEE_SEARCH_BOUNDS,
    "buy_mid_knee_risk": (2.0, 18.0),
    "buy_mid_curvature": (1.0, 4.0),
    "sell_mid_knee_risk": (82.0, 98.0),
    "sell_mid_curvature": (1.0, 4.0),
}

WIDE_KNEE_TIERED_COARSE_GRID: dict[str, tuple[float, ...]] = {
    **WIDE_KNEE_COARSE_GRID,
    "buy_mid_knee_risk": (5.0, 10.0, 15.0),
    "buy_mid_curvature": (1.0, 2.0),
    "sell_mid_knee_risk": (85.0, 90.0, 95.0),
    "sell_mid_curvature": (1.0, 2.0),
}
```

Replace `sample_wide_knee_curve_trials` (~line 469-498):

```python
def sample_wide_knee_curve_trials(
    *,
    n_random: int = 3000,
    seed: int = 42,
    include_grid: bool = True,
    bounds: dict[str, tuple[float, float]] = WIDE_KNEE_SEARCH_BOUNDS,
    grid: dict[str, tuple[float, ...]] = WIDE_KNEE_COARSE_GRID,
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, float]]:
    """Rerunnable trial list for the wide-knee curve fit (buy/sell knees free).

    ``extra_keys`` (e.g. ``_MID_TIER_KEYS``) extends both the sampled
    dimensions (when present in ``bounds``/``grid``) and the dedup key, so
    trials differing only in a mid-tier param are never silently collapsed.
    """
    seen: set[tuple[float, ...]] = set()
    out: list[dict[str, float]] = []
    dedup_keys = (*_SHAPE_KEYS, *extra_keys)

    def _add(params: dict[str, float]) -> None:
        if not shape_from_bounds_ok(params, bounds=bounds, extra_keys=extra_keys):
            return
        key = tuple(round(params[k], 6) for k in dedup_keys if k in params)
        if key in seen:
            return
        seen.add(key)
        out.append(params)

    if include_grid:
        names = list(grid)
        for combo in itertools.product(*(grid[n] for n in names)):
            _add(dict(zip(names, combo, strict=True)))
    rng = random.Random(seed)
    for _ in range(max(0, n_random)):
        drawn = {name: round(rng.uniform(lo, hi), 4) for name, (lo, hi) in bounds.items()}
        _add(drawn)
    return out
```

Add a new function after `search_wide_knee_curve` (~line 534):

```python
def search_wide_knee_curve_tiered(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    *,
    initial_cash: float,
    frozen_weights: SdcaCompositeWeights,
    n_random: int = 3000,
    seed: int = 42,
    include_grid: bool = True,
    bounds: dict[str, tuple[float, float]] = WIDE_KNEE_TIERED_SEARCH_BOUNDS,
    grid: dict[str, tuple[float, ...]] = WIDE_KNEE_TIERED_COARSE_GRID,
    gates: CurveOptimizeGates | None = None,
) -> CurveOptimizeResult:
    """Tiered-knee entry: fit buy/sell curves with a mid-tier knee/curvature
    per side, on a frozen index. Same evaluator and baseline as
    ``search_wide_knee_curve`` -- only the search-space dimensions differ.
    """
    trials = sample_wide_knee_curve_trials(
        n_random=n_random,
        seed=seed,
        include_grid=include_grid,
        bounds=bounds,
        grid=grid,
        extra_keys=_MID_TIER_KEYS,
    )
    return search_curve(
        dates,
        prices,
        risk,
        trials,
        initial_cash=initial_cash,
        baseline=published_curve_shape(),
        frozen_weights=frozen_weights,
        gates=gates,
        evaluator="curve_simulator",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_optimize.py -v` from `digiquant/`
Expected: all PASS, including every pre-existing test in `TestSearchSpace`, `TestSampleWideKneeCurveTrials`, `TestSearchWideKneeCurve` unchanged (their calls never pass `extra_keys`, so behavior is byte-identical).

- [ ] **Step 5: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green.

```bash
git add digiquant/src/digiquant/strategies/sdca/curve_optimize.py digiquant/../tests/dq/strategies/sdca/test_curve_optimize.py
git commit -m "$(cat <<'EOF'
feat(sdca): add tiered-knee search space to curve_optimize.py

shape_from_bounds_ok/params_from_shape gain an additive extra_keys param;
search_curve's shape construction now also reads _MID_TIER_KEYS from a
trial dict when present. New WIDE_KNEE_TIERED_SEARCH_BOUNDS/COARSE_GRID
and search_wide_knee_curve_tiered() give the tiered SdcaCurveShape (added
last commit) its own search entry point, fully additive -- every existing
caller of the touched functions defaults extra_keys=() and is unaffected.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 6: Extend `curve_optimize_feasibility.py`'s feasibility-aware search for the tiered space

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/curve_optimize_feasibility.py` (`search_wide_knee_curve_feasibility_aware`)
- Test: `tests/dq/strategies/sdca/test_curve_optimize_feasibility.py`

**Interfaces:**
- Consumes: `sample_wide_knee_curve_trials(..., extra_keys=...)`, `search_curve`, `WIDE_KNEE_TIERED_SEARCH_BOUNDS`, `WIDE_KNEE_TIERED_COARSE_GRID`, `_MID_TIER_KEYS` (all from Task 5).
- Produces: `search_wide_knee_curve_feasibility_aware` gains additive `bounds`/`grid`/`extra_keys` passthrough params (defaulting to today's non-tiered values), so Task 7 can call it with the tiered bounds/grid while every existing caller is unaffected.

- [ ] **Step 1: Read the current exact signature and body before writing the diff**

Before writing tests or code, run:

```bash
grep -n "^def search_wide_knee_curve_feasibility_aware" -A 60 digiquant/src/digiquant/strategies/sdca/curve_optimize_feasibility.py
```

Confirm the function's exact current parameter list and how it currently calls `sample_wide_knee_curve_trials`/`search_curve` internally (per the earlier ground-truth summary it wraps `search_wide_knee_curve`-style sampling with an added `MAX_DRAWDOWN_CAP_PCT` feasibility gate — confirm the exact call shape before editing, since this plan's Task 5 changed both of those functions' signatures additively and this task must thread the new `extra_keys`/tiered `bounds`/`grid` through the same way Task 5 did, matching this function's actual current structure rather than a guessed one).

- [ ] **Step 2: Write the failing test**

Add to `tests/dq/strategies/sdca/test_curve_optimize_feasibility.py` (match this file's existing fixture/import conventions, e.g. reuse whatever synthetic `(dates, prices, risk, weights)` fixture its existing tests already use):

```python
class TestSearchWideKneeCurveFeasibilityAwareTiered:
    def test_accepts_tiered_bounds_and_grid(self, tiny_frozen_index) -> None:
        dates, prices, risk, weights = tiny_frozen_index
        result = search_wide_knee_curve_feasibility_aware(
            dates, prices, risk,
            initial_cash=1000.0, frozen_weights=weights,
            n_random=20, seed=1, include_grid=False,
            bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
            grid=WIDE_KNEE_TIERED_COARSE_GRID,
            extra_keys=_MID_TIER_KEYS,
        )
        assert result.num_evaluations > 0

    def test_default_call_unaffected(self, tiny_frozen_index) -> None:
        # Existing non-tiered callers must see byte-identical behavior --
        # this is a regression guard, should already pass before Step 4.
        dates, prices, risk, weights = tiny_frozen_index
        result = search_wide_knee_curve_feasibility_aware(
            dates, prices, risk,
            initial_cash=1000.0, frozen_weights=weights,
            n_random=20, seed=1, include_grid=False,
        )
        assert result.num_evaluations > 0
```

- [ ] **Step 3: Run tests to verify the new one fails**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_optimize_feasibility.py -k Tiered -v` from `digiquant/`
Expected: `test_accepts_tiered_bounds_and_grid` FAILS with `TypeError: unexpected keyword argument 'bounds'` (or similar); `test_default_call_unaffected` PASSES already (pre-existing behavior, confirms the baseline to preserve).

- [ ] **Step 4: Thread the new params through**

Using the exact signature/body confirmed in Step 1, add `bounds`, `grid`, and `extra_keys` parameters to `search_wide_knee_curve_feasibility_aware`, defaulting to the function's current non-tiered values (`WIDE_KNEE_SEARCH_BOUNDS`, `WIDE_KNEE_COARSE_GRID`, `()`), and pass them through to its internal `sample_wide_knee_curve_trials(...)` call exactly as Task 5's `search_wide_knee_curve_tiered` does. Do not change the feasibility gate itself (`MAX_DRAWDOWN_CAP_PCT` or equivalent) — only the search-space plumbing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_curve_optimize_feasibility.py -v` from `digiquant/`
Expected: all PASS, including every pre-existing test.

- [ ] **Step 6: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green.

```bash
git add digiquant/src/digiquant/strategies/sdca/curve_optimize_feasibility.py digiquant/../tests/dq/strategies/sdca/test_curve_optimize_feasibility.py
git commit -m "$(cat <<'EOF'
feat(sdca): thread tiered search space through the feasibility-aware curve search

search_wide_knee_curve_feasibility_aware gains additive bounds/grid/
extra_keys params (defaulting to today's non-tiered values), so it can run
against WIDE_KNEE_TIERED_SEARCH_BOUNDS the same way
search_wide_knee_curve_tiered does. The feasibility gate itself (drawdown
cap) is unchanged; only the sampled search space is now configurable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Task 7: Full 17-indicator joint reweight + tiered curve search driver

**Files:**
- Create: `digiquant/scripts/run_full17_tiered_reweight.py`

**Interfaces:**
- Consumes: `SURVIVING_INDICATORS`/`EXTRA_WINDOWS`/`load_inputs`-style data assembly (from `run_aggregate_reweight_full17_fixed_index.py`, reused not duplicated), `search_wide_knee_curve_feasibility_aware(..., bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS, grid=WIDE_KNEE_TIERED_COARSE_GRID, extra_keys=_MID_TIER_KEYS)` (Task 6), `run_sdca_walk_forward`/duration-weighted fold mean (from `optimize.py`/`walk_forward.py`, reused unchanged per spec 2.3 item 3).
- Produces: a `.scratch/full17_tiered_reweight.json` report + printed walk-forward table. No new library code — this is a driver script only, matching the established convention (`run_aggregate_reweight_full17_fixed_index.py`, `run_baseline_relative_rescore.py`) of no dedicated pytest file for `scripts/run_*.py` drivers; correctness is validated by running it against real cached data, not by unit tests.

This task's exact reweight-search loop (grid/refine strategy over the 17-name pool) must reuse `run_aggregate_reweight_full17_fixed_index.py`'s existing `refined_window`/`run_parallel_scan`/`best_for_ratio`/`full_score`/`chunked` functions and `_aggregate_reweight_parallel` worker module as-is (per spec 2.3 item 1: "not sequentially blind" means the curve search must run against each candidate weighting inside the same loop, not as a separate after-the-fact pass) — before writing this script, read `run_aggregate_reweight_full17_fixed_index.py`'s `main()` (not yet read this session) in full to confirm the exact reweight loop shape and where to insert the tiered curve search call per iteration, since guessing this structure risks silently reproducing spec 2.3's explicitly-called-out anti-pattern (sequential blindness between reweight and curve search).

- [ ] **Step 1: Read `run_aggregate_reweight_full17_fixed_index.py`'s `main()` in full**

```bash
sed -n '188,400p' digiquant/scripts/run_aggregate_reweight_full17_fixed_index.py
```

Read the full `main()` body (and any helper it calls that Steps above haven't already covered) to establish the exact current reweight-search loop shape before writing this task's driver.

- [ ] **Step 2: Write the driver script**

Create `digiquant/scripts/run_full17_tiered_reweight.py`, structured as:

1. Reuse `load_inputs()` from `run_aggregate_reweight_full17_fixed_index` unchanged (imported, not copied) to assemble the 17-indicator z-series.
2. Reuse that module's coarse-grid + refine reweight search (`refined_window`, `run_parallel_scan`, `best_for_ratio`, `full_score`) unchanged for the weight-search half.
3. For the curve-search half, inside the same per-candidate-weighting loop (not a separate pass after weights are already fixed), call `search_wide_knee_curve_feasibility_aware(..., bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS, grid=WIDE_KNEE_TIERED_COARSE_GRID, extra_keys=_MID_TIER_KEYS)` against each candidate weighting's frozen index, so the reported winner is jointly the best (weights, tiered curve) pair, not weights optimized in isolation then a curve fit afterward.
4. Gate the final candidate through `run_sdca_walk_forward` (with `fold_weighting="duration"` if that param exists per the `delightful-riding-pearl.md` plan's Phase 2c — check whether it has already landed in `optimize.py` before using it; if not landed, use the default `fold_weighting` and note in the script's output that duration-weighting was unavailable) before writing any report.
5. Write output to `.scratch/full17_tiered_reweight.json` (never `settings.json`) and print a walk-forward table (`beats_flat_dca_oos`, sensitivity-stability, realized max drawdown) matching the standing report format from every prior round, plus the Task 3 roughness diagnostic's before/after numbers for context per the Gate section (spec section 4).

Because this script's exact body depends on `main()`'s real structure (read in Step 1, not yet known at plan-writing time), the executor writing this task must produce the actual code following that real structure — reusing the real function names/signatures confirmed in Step 1, not the illustrative names above.

- [ ] **Step 3: Run the script against real cached data**

Run: `uv run python scripts/run_full17_tiered_reweight.py` from `digiquant/`
Expected: completes without error, writes `.scratch/full17_tiered_reweight.json`, prints a walk-forward table. Do NOT write `settings.json` or touch `RESEARCH_STATE.md`'s validated-candidate section regardless of the result — this is diagnostic/research output for Chris's explicit accept/reject, per the standing gate.

- [ ] **Step 4: Run the full SDCA suite one more time and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green (this task adds no library code, so this is a final confirmation, not a new-behavior check).

```bash
git add digiquant/scripts/run_full17_tiered_reweight.py
git commit -m "$(cat <<'EOF'
feat(sdca): add joint 17-indicator reweight + tiered-curve search driver

Reuses run_aggregate_reweight_full17_fixed_index.py's reweight-search loop
and Task 6's feasibility-aware tiered curve search together, per-candidate-
weighting, so the reported result is a jointly-optimal (weights, tiered
curve) pair rather than weights fit blind to the curve shape. Diagnostic
only: writes .scratch/full17_tiered_reweight.json, never settings.json or
RESEARCH_STATE.md's validated-candidate section.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

- [ ] **Step 5: Report the result to Chris for explicit accept/reject**

Present the walk-forward table (`beats_flat_dca_oos`, sensitivity-stability, realized max drawdown), per-fold pass/fail against the [Reference-Site Parity Target](#reference-site-parity-target)'s 3-part bar, and the Task 3 roughness diagnostic's before/after comparison, per the spec's Gate section. Do not claim `beats_flat_dca_oos=True` unless the script's own gated output actually shows it. Wait for Chris's explicit accept before any `settings.json`/`RESEARCH_STATE.md` validated-candidate change — that write is explicitly out of scope for this plan.

---

## Task 8: Periodic self-optimization cycle driver

This is the "periodically... optimize itself... more self-adjustment" half of Chris's directive: a repeatable, state-persisting cycle script that alternates between indicator-pool ablation and tiered-curve search, gates each result against both flat DCA and the currently-published live config using the pearl-plan's already-shipped `baseline_evaluator`, and logs findings — never touching `settings.json` or the validated-candidate section. Task 9 (Operational Rollout, below) wires this into a standing loop.

**Files:**
- Create: `digiquant/scripts/run_periodic_self_optimization_cycle.py`
- Create: `digiquant/.scratch/periodic_cycle_state.json` (generated at first run, untracked — not committed)
- Modify: `digiquant/src/digiquant/strategies/sdca/RESEARCH_STATE.md` (append-only, "Immediate backlog" section — never lines 13-21)

**Interfaces:**
- Consumes: `ablation.run_ablation_rounds` (pearl-plan, `ablation.py:80`), `baseline_evaluator.run_sdca_walk_forward_vs_baseline` (pearl-plan, `baseline_evaluator.py:100`), `curve_optimize_feasibility.search_wide_knee_curve_feasibility_aware` (Task 6, gains tiered `bounds`/`grid`/`extra_keys`), `curve_optimize.published_indicator_weights`/`published_curve_shape` (existing, read the live `settings.json` config as the comparison baseline — **not** the stale validated-candidate section), `SURVIVING_INDICATORS`/`EXTRA_WINDOWS` (`run_aggregate_reweight_full17_fixed_index.py`), `WIDE_KNEE_TIERED_SEARCH_BOUNDS`/`WIDE_KNEE_TIERED_COARSE_GRID`/`_MID_TIER_KEYS` (Task 5).
- Produces: `.scratch/periodic_cycle_state.json` (round counter, cycle-type alternation, current indicator pool, best-seen candidate so far) and `.scratch/periodic_cycle_<UTC-timestamp>.json` per run (full result detail) — both untracked, never read by anything except this script's next invocation and the reporting step below.

Because this task's exact call shape depends on `ablation.run_ablation_rounds`'s and `baseline_evaluator.run_sdca_walk_forward_vs_baseline`'s real current signatures (both landed in the pearl-plan, prior to this plan's own planning pass, and not re-read in full during this planning session — only their names and one-line summaries were confirmed via signature grep), the executor must read them first rather than guess, exactly as Task 7 Step 1 already does for `run_aggregate_reweight_full17_fixed_index.py`. This is the same deliberate, narrow exception the Self-Review below calls out for Task 7.

- [ ] **Step 1: Read the exact signatures this task threads together**

```bash
grep -n "^def run_ablation_rounds" -A 30 digiquant/src/digiquant/strategies/sdca/ablation.py
grep -n "^def run_sdca_walk_forward_vs_baseline" -A 30 digiquant/src/digiquant/strategies/sdca/baseline_evaluator.py
grep -n "^def published_indicator_weights\|^def published_curve_shape" -A 15 digiquant/src/digiquant/strategies/sdca/curve_optimize.py
```

Confirm each function's exact parameter list, return type, and (for `published_indicator_weights`) whether Phase 3's one-line `"valuation"`-vs-`"power_law"` settings-key audit fix already landed — the pearl-plan write-up above records it as part of Phase 3, but confirm directly before relying on it, since this script's "current live config" baseline depends on reading the correct key.

- [ ] **Step 2: Define the cycle-state schema and write the failing state-transition test**

`.scratch/periodic_cycle_state.json` schema (a plain JSON file, not a pydantic model — it's diagnostic local state, not a library interface):

```json
{
  "cycle_count": 0,
  "next_cycle_type": "ablation",
  "ablation_pool_remaining": ["power_law", "m2", "rs_eth", "dxy", "onchain_mvrv", "onchain_asopr", "onchain_puell", "onchain_rhodl", "onchain_addr_ratio", "fear_greed", "weekly_monthly_rsi", "weekly_monthly_macd", "weekly_rsi", "weekly_macd", "sma_band", "monthly_rsi", "monthly_macd"],
  "best_seen": null
}
```

`next_cycle_type` alternates `"ablation"` / `"curve"` each run so both indicator-pool exploration and curve-shape exploration get regular attention rather than one starving the other. `ablation_pool_remaining` starts as `SURVIVING_INDICATORS` and is only reset (back to the full list) once it drops below 2 names, mirroring the pearl-plan's own ablation stop criterion. `best_seen` is `null` until some cycle's candidate clears `beats_flat_dca_oos=True` against the live-config baseline, then holds that candidate's full result dict — never a settings.json write, just a running memory of the best diagnostic result across cycles.

Add `tests/dq/strategies/sdca/test_periodic_cycle_state.py`:

```python
import json
from pathlib import Path

import pytest

from digiquant.strategies.sdca.periodic_cycle_state import (
    CycleState,
    load_cycle_state,
    save_cycle_state,
)


class TestCycleStateRoundTrip:
    def test_missing_file_returns_fresh_state_with_full_pool(self, tmp_path: Path) -> None:
        state = load_cycle_state(tmp_path / "periodic_cycle_state.json")
        assert state.cycle_count == 0
        assert state.next_cycle_type == "ablation"
        assert len(state.ablation_pool_remaining) == 17
        assert state.best_seen is None

    def test_save_then_load_round_trips_exactly(self, tmp_path: Path) -> None:
        path = tmp_path / "periodic_cycle_state.json"
        original = CycleState(
            cycle_count=3,
            next_cycle_type="curve",
            ablation_pool_remaining=("power_law", "m2", "dxy"),
            best_seen={"duration_weighted_oos_pct": 52.01, "beats_flat_dca_oos": True},
        )
        save_cycle_state(path, original)
        reloaded = load_cycle_state(path)
        assert reloaded == original

    def test_pool_below_two_resets_to_full_surviving_indicators(self, tmp_path: Path) -> None:
        path = tmp_path / "periodic_cycle_state.json"
        save_cycle_state(
            path,
            CycleState(cycle_count=5, next_cycle_type="ablation", ablation_pool_remaining=("power_law",), best_seen=None),
        )
        state = load_cycle_state(path)
        assert len(state.ablation_pool_remaining) == 17  # reset, not left at 1
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_periodic_cycle_state.py -v` from `digiquant/`
Expected: FAIL with `ModuleNotFoundError: No module named 'digiquant.strategies.sdca.periodic_cycle_state'`.

- [ ] **Step 4: Implement `periodic_cycle_state.py`**

Create `digiquant/src/digiquant/strategies/sdca/periodic_cycle_state.py`:

```python
"""Small persisted state for the periodic self-optimization cycle (Task 8).

Plain JSON, not a walk-forward interface -- read/written only by
run_periodic_self_optimization_cycle.py between successive invocations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from digiquant.strategies.sdca.indicator_catalog import SURVIVING_INDICATORS

CycleType = Literal["ablation", "curve"]


class CycleState(BaseModel, frozen=True):
    cycle_count: int
    next_cycle_type: CycleType
    ablation_pool_remaining: tuple[str, ...]
    best_seen: dict[str, object] | None


def load_cycle_state(path: Path) -> CycleState:
    if not path.exists():
        return CycleState(
            cycle_count=0,
            next_cycle_type="ablation",
            ablation_pool_remaining=tuple(SURVIVING_INDICATORS),
            best_seen=None,
        )
    raw = json.loads(path.read_text())
    pool = tuple(raw["ablation_pool_remaining"])
    if len(pool) < 2:
        pool = tuple(SURVIVING_INDICATORS)
    return CycleState(
        cycle_count=raw["cycle_count"],
        next_cycle_type=raw["next_cycle_type"],
        ablation_pool_remaining=pool,
        best_seen=raw.get("best_seen"),
    )


def save_cycle_state(path: Path, state: CycleState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.model_dump(), indent=2))
```

Confirm `SURVIVING_INDICATORS` is importable from `indicator_catalog.py` at that exact name (it is the canonical 17-name pool referenced throughout the pearl-plan and recalibration-v1 write-ups above) before relying on the import; if it instead lives in `run_aggregate_reweight_full17_fixed_index.py` as this plan's own earlier grounding noted, import it from there and adjust Task 5-7's cross-references accordingly (Task 7's own Step 1 already re-confirms this at execution time).

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest ../tests/dq/strategies/sdca/test_periodic_cycle_state.py -v` from `digiquant/`
Expected: PASS.

- [ ] **Step 6: Write the cycle driver script**

Using the exact signatures confirmed in Step 1, create `digiquant/scripts/run_periodic_self_optimization_cycle.py` structured as:

1. Load `CycleState` via `load_cycle_state(Path(".scratch/periodic_cycle_state.json"))`.
2. Read the current live-config baseline via `published_indicator_weights()` + `published_curve_shape()` (the actual current `settings.json`, not the stale validated-candidate section) — this is the comparison baseline for this cycle's `beats_baseline_oos` check, replacing Phase 3's now-known-stale +84.90% figure everywhere in this script's output.
3. If `state.next_cycle_type == "ablation"`: run one bounded ablation round via `run_ablation_rounds(...)` seeded with `state.ablation_pool_remaining` (using whatever round-budget parameter its real signature exposes, set to run exactly one round per invocation — this is a periodic *cycle*, not the pearl-plan's own up-to-8-round batch run), producing a new candidate weighting and an updated remaining pool.
4. If `state.next_cycle_type == "curve"`: run `search_wide_knee_curve_feasibility_aware(..., bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS, grid=WIDE_KNEE_TIERED_COARSE_GRID, extra_keys=_MID_TIER_KEYS)` (Task 6) against the current live-config weighting (or `state.best_seen`'s weighting if one exists and already clears the ablation gate), producing a new candidate tiered curve shape.
5. Gate the resulting candidate through `run_sdca_walk_forward_vs_baseline(...)` (pearl-plan) against the live-config baseline from Step 2, and report per-fold pass/fail against the [Reference-Site Parity Target](#reference-site-parity-target)'s 3-part bar (fold-level `beats_flat_dca_oos`, drawdown, sensitivity-stability) — not just the aggregate.
6. Flip `next_cycle_type` for the following invocation, increment `cycle_count`, update `ablation_pool_remaining` if this was an ablation cycle, update `best_seen` only if this cycle's candidate both `beats_flat_dca_oos=True` in aggregate-and-per-fold and improves on the previous `best_seen` (or there was none) — then `save_cycle_state(...)`.
7. Write full result detail to `.scratch/periodic_cycle_<cycle_count>.json` (never `settings.json`).
8. Append one dated line to `RESEARCH_STATE.md`'s "Immediate backlog" section (same format as existing numbered entries — additive only, never touches lines 13-21) summarizing: cycle number, cycle type, candidate params, duration-weighted OOS%, per-fold pass/fail, `beats_flat_dca_oos`, `beats_baseline_oos` (vs. live config), sensitivity-stability.
9. Print a one-line summary to stdout ending in either `"CANDIDATE CLEARS FULL PARITY GATE — needs Chris's explicit accept"` (all 3 parity-target criteria pass, both aggregate and every fold) or `"gate not cleared: <which criterion/fold failed>"` — this is the line the standing loop (Task 9 / Operational Rollout below) relays to Chris each cycle. Exit 0 regardless — this is a diagnostic research cycle, not a CI gate, so a not-yet-passing cycle is not a failure.

Because Steps 3-5's exact call shape depends on the real signatures from Step 1, the executor writes the actual code following that real structure — reusing the real parameter names confirmed there, not the illustrative call shapes above. This mirrors Task 7's own deferral for the same reason.

- [ ] **Step 7: Run the script once against real cached data**

Run: `uv run python scripts/run_periodic_self_optimization_cycle.py` from `digiquant/`
Expected: completes without error, writes `.scratch/periodic_cycle_state.json` and `.scratch/periodic_cycle_1.json`, appends one dated line to `RESEARCH_STATE.md`, prints the one-line gate summary. Confirm the appended `RESEARCH_STATE.md` line lands in "Immediate backlog" and that lines 13-21 are untouched (`git diff digiquant/src/digiquant/strategies/sdca/RESEARCH_STATE.md` — inspect the diff directly before committing).

- [ ] **Step 8: Run the full SDCA suite and commit**

Run: `uv run pytest ../tests/dq/strategies/sdca/ -q` from `digiquant/`
Expected: all green.

```bash
git add digiquant/src/digiquant/strategies/sdca/periodic_cycle_state.py digiquant/scripts/run_periodic_self_optimization_cycle.py digiquant/../tests/dq/strategies/sdca/test_periodic_cycle_state.py digiquant/src/digiquant/strategies/sdca/RESEARCH_STATE.md
git commit -m "$(cat <<'EOF'
feat(sdca): add periodic self-optimization cycle driver

run_periodic_self_optimization_cycle.py alternates ablation and tiered-
curve-search cycles, gates each candidate against the live settings.json
config (not the stale validated-candidate section) via the pearl-plan's
baseline_evaluator, reports fold-level pass/fail against the reference-
site parity target, and logs to RESEARCH_STATE.md's Immediate backlog.
State persists in .scratch/periodic_cycle_state.json (untracked). Never
writes settings.json or the validated-candidate section regardless of
result -- that stays gated on Chris's explicit accept.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsYpwKnGwkLp5CsU89bMfK
EOF
)"
```

---

## Operational Rollout: Standing Self-Optimization Loop

Not a coded task — this is the session-level action that wires Task 8's driver into Chris's Q1 answer ("Standing /loop in this session"). Perform this once Task 8 is committed and its Step 7 real-data run has produced a sane first cycle.

Invoke, in this session, the `loop` skill in **dynamic mode** (no fixed interval — the underlying walk-forward searches are compute-heavy and irregular in duration, so a self-paced loop fits better than a fixed cron cadence):

```
/loop From digiquant/, run `uv run python scripts/run_periodic_self_optimization_cycle.py`. Read its stdout summary and the RESEARCH_STATE.md line it appended. If the summary says a candidate clears the full parity gate, report the candidate and its walk-forward table to Chris explicitly and wait for his accept before touching settings.json or RESEARCH_STATE.md's validated-candidate section -- never write either automatically. Otherwise just report the one-line gate-not-cleared summary and continue. Keep tests/dq/strategies/sdca/ green throughout; if the cycle script itself errors, report the error and stop the loop rather than retrying blindly.
```

Per the `loop` skill's dynamic-mode mechanics: run the cycle now, then `ScheduleWakeup` with a `delaySeconds` chosen for the cycle's real observed duration (these are walk-forward searches over multi-year daily data — expect single-digit minutes to run, so a 1200-1800s fallback between cycles is appropriate; do not poll faster than the cycle itself completes), `prompt` set to this same `/loop ...` text verbatim so each firing re-enters the loop, and `noop: true` on cycles that don't clear the gate (routine — most won't), `noop: false` whenever a cycle updates `best_seen` or surfaces a gate-clearing candidate. Stop the loop (`ScheduleWakeup(stop: true)`) only if Chris asks, or if the cycle script starts erroring and needs a code fix first (i.e., it becomes an implementation task, not a loop iteration).

---

## Self-Review

**Spec coverage:**
- 1(prior, done) — not re-implemented, referenced as context only. ✓
- 1b (roughness diagnostic across all 17) — Task 3. ✓
- 1c (generalize `causal_ema_smooth` to flagged indicators, cadence-appropriate half-lives, named constants) — Task 2. ✓
- 1d (fix `agreement_scaled_blend` discontinuity, preserve far-tail behavior) — Task 1. ✓
- 2 (tiered `SdcaCurveShape` + search-bound updates) — Tasks 4, 5, 6. ✓ (ambiguity in the spec's own bound description explicitly resolved and documented in Task 4.)
- 3 (full 17-indicator pool re-weight, explicit `SURVIVING_INDICATORS`, joint not sequential, `EXTRA_WINDOWS` applied, standard walk-forward gate) — Task 7. ✓
- 4 (testing: smoothness diagnostic tests, per-indicator regression tests, blend-discontinuity tests, tiered-curve-shape tests including single-knee-recovery, full suite green throughout) — woven into every task's own test steps. ✓
- Gate (never writes `settings.json`/validated-candidate section, diagnostic output to `.scratch/`/untracked, reported for explicit accept) — stated in Global Constraints and enforced explicitly in Task 7 Step 5 and Task 8 Step 6.9. ✓

**Governing-directive coverage (Chris, 2026-09-25, beyond the spec's own scope):**
- "build on top of [the reference dashboard]" / "match this SDCA reference in performance terms" — Reference-Site Parity Target section translates this into a concrete, fold-level 3-part bar (not a placeholder "try to do well"), threaded explicitly into Task 7 Step 5 and Task 8 Step 6.5/6.9. ✓
- "optimize itself over time, periodically... more self-adjustment" — Task 8 (cycle driver) + Operational Rollout (standing `/loop`, per Chris's own Q1 answer: "Standing /loop in this session"). ✓
- "include more indicators" — already covered by Task 7 (full 17-`SURVIVING_INDICATORS` reweight) and kept alive going forward by Task 8's ablation half-cycles. ✓
- "optimize buying and selling curves" — already covered by Tasks 4-6 (tiered curve + search space) and kept alive going forward by Task 8's curve half-cycles. ✓
- "we'll deal with how we want to present it in the tier sheet later" (explicit scope exclusion) — no task in this plan touches tearsheet/presentation code; Prior Art section explicitly notes the existing diagnostic tearsheet pages as out-of-scope context only, not work this plan does or extends. ✓
- Fold the pearl-plan in (Chris's Q2 answer: "Fold it in now") — Prior Art section documents all of Phases 0-5 as already-shipped background, per the grounding this session did (file-existence checks, signature greps, and a full green 585-passed/38-skipped test run) rather than re-planning it as new work, which is what "fold it in" turned out to mean once grounded against real code state. ✓

**Placeholder scan:** Tasks 1-6 contain complete, concrete code for every step. Task 7 and Task 8 are the two tasks with an explicit "read first, then write following the real structure" step rather than fully pre-written code for their driver's core call sequence — Task 7 because `run_aggregate_reweight_full17_fixed_index.py`'s `main()` body wasn't read in full during this planning session, Task 8 because `ablation.run_ablation_rounds`'s and `baseline_evaluator.run_sdca_walk_forward_vs_baseline`'s exact signatures (both landed in the pearl-plan, prior to this plan's own planning pass) were only confirmed by name via signature grep, not read in full. Both are deliberate, narrow exceptions: each task specifies exactly what to read, why, and what the resulting script must do — not an open-ended "add appropriate logic" placeholder. Task 8's `CycleState` model, its state-file schema, its test file, and its RESEARCH_STATE.md-append/gate-summary/stdout-contract are all fully concrete. No other step in this plan has an unresolved placeholder.

**Type/signature consistency:** `_MID_TIER_KEYS` (Task 5) is used identically in Task 6, Task 7, and Task 8. `SdcaCurveShape`'s 4 new field names (Task 4) match `_MID_TIER_KEYS`'s string values exactly. `search_wide_knee_curve_tiered`'s signature (Task 5) mirrors `search_wide_knee_curve`'s existing signature exactly except for its `bounds`/`grid` defaults. `shape_from_bounds_ok`/`params_from_shape`/`sample_wide_knee_curve_trials` all gain the same `extra_keys: tuple[str, ...] = ()` convention across Tasks 5, 6, and 8's Step 6.4 curve-cycle call. `WIDE_KNEE_TIERED_SEARCH_BOUNDS`/`WIDE_KNEE_TIERED_COARSE_GRID` (Task 5) are consumed identically by Task 6, Task 7, and Task 8. `CycleState.ablation_pool_remaining` (Task 8) is seeded from the same `SURVIVING_INDICATORS` name set Task 7 explicitly passes to the reweight search, so both tasks agree on the canonical pool.

**Scope check:** All three spec components plus testing are covered by Tasks 1-7, matching the spec's own single-document scope (it was not decomposed into sub-project specs during brainstorming, and none of Components 1-3 is independently shippable without the others per Chris's original ask). Task 8 and the Operational Rollout section are a deliberate scope extension beyond the spec — required by Chris's 2026-09-25 chat directive (periodic self-optimization, folding in the pearl-plan) rather than by the spec document itself, and kept to exactly what that directive asked for: no tearsheet/presentation work, no auto-writes to `settings.json`, reuse of already-shipped machinery rather than new optimization primitives.
