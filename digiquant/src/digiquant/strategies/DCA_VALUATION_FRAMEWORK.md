# DCA valuation framework: dual-timeframe design

Design philosophy for the valuation/composite-risk indicator that drives a
dollar-cost-averaging strategy's buy/sell rate. Scoped beyond BTC-SDCA on
purpose: this is how Chris wants every DCA strategy's valuation indicator
built, not a BTC-only note. The concrete implementation today lives under
`sdca/` because SDCA is the only DCA strategy that exists yet (see
"Generalizing beyond SDCA" below) — nothing here is BTC-specific in principle.

## The mental model

Manually timing a DCA strategy means looking at a price chart and marking two
different kinds of zone:

- **Long-term zones** — the extremities. Major cycle bottoms and tops. Rare,
  wide, high-conviction. You'd want to be maximally aggressive here.
- **Medium-term zones** — the more frequent local pullbacks and rallies inside
  a cycle. Common, narrower, lower-conviction. You'd want to nibble here —
  small, progressive size, not a full commitment.

A good system separates these two judgments, tunes each against the
turning points it's meant to catch, and then combines them so that:
small/progressive sizing triggers in medium-term zones, and sizing becomes
aggressive only at long-term extremities. Each half should also work
*alone* — a medium-term-only trader, a long-term-only trader, and a combined
trader should all be able to plug into the same underlying valuation
machinery, just with different thresholds/curves on top of it.

That's the target architecture. The sections below map it onto what's
already built, what's missing, and the concrete next steps.

## What's already built (this is closer to the target than it looks)

**1. Per-indicator dual-timeframe blending already exists.**
`price_oscillators.agreement_scaled_blend()` (`sdca/price_oscillators.py:376`)
blends a long-term leg and a medium-term leg of the *same* indicator: weighted
average of the two, amplified when they agree in sign, damped when they
conflict. Four of the composite's indicators already use it —
`rsi_confluence_z` (weekly/daily), `macd_confluence_z` (weekly/daily),
`sma_band_confluence_z` (90d/20d), and `rs_eth_confluence_z` in
`sdca/indicator_catalog.py:` (90d/30d) — plus the anchor indicator itself,
`power_law_confluence_z` (whole-history/180d trend), per `sdca/risk_index.py`.
This is *within-indicator* timeframe fusion, not yet a strategy-level split —
see "The gap" below.

**2. Hand-picked long-term zones already exist, as data, not folklore.**
`sdca/cycle_windows.py` is exactly "look at the chart and mark the areas by
eye," formalized: `SdcaCycleWindows.btc_v1()` pins five documented BTC cycle
extremes (2017 peak, 2018 trough, 2021 peak, 2022 trough, 2025 peak, ±45 days
each) as `CycleWindow` peak/trough ranges. `stage_a.py`'s
`cycle_overlap_score()` scores a candidate weight set by how well the
composite's accumulate/distribute bands (risk ≤35 / ≥80) overlap those
windows — i.e. it already optimizes indicator weights to make the long-term
system's bottoms/tops line up with the marked extremities. This is Stage 1 of
the user's plan, already implemented, but note `weight_search.py:1-7`
documents that cycle overlap is currently kept only as a *diagnostic* — the
weight-selection path that actually ships uses in-sample backtest return
instead. Reconciling those two objectives is part of the next-steps list.

**3. Real smoothing now exists** (added this session,
`sdca/composite_risk.py:compute_composite_risk`). Before this change, the
*only* noise-reduction knob was `rolling_window`, and that is not smoothing —
it's a rolling z-score re-normalization against a trailing distribution, and
it can *amplify* a sudden move (a spike away from a quiet recent regime reads
as more extreme, not less). There was no true moving-average damping anywhere
in the pipeline, which is exactly the "quite volatile... spiky" complaint.
`smoothing_window` (opt-in, default `None`, off) is a causal rolling mean
applied to the final `composite_z`, after any rolling re-normalization —
genuine noise reduction, composable with everything above it. Threaded
through `build_risk_index()` as `composite_smoothing_window` /
`composite_smoothing_min_samples`. Tests: `test_composite_risk.py::TestCompositeSmoothing`.

## The gap

Nothing above operates at the *strategy* level. Today there is exactly one
composite risk index and one curve (`AccumDistCurve`) mapping it to a trade
rate — a single system, not two pluggable ones. Specifically missing:

- **No medium-term cycle-window set.** `cycle_windows.py` only has long-term
  pins. There's no equivalent "these are the medium-term pullback/rally zones"
  data to optimize a medium-term indicator set against.
- **No second, medium-term-tuned weight set.** Stage A optimizes one
  `SdcaCompositeWeights` against the long-term windows. There's no sibling
  process producing a second weight set tuned to catch medium-term turns.
- **No combination layer.** Even with two composites in hand, nothing today
  takes "medium-term risk" and "long-term risk" as two separate inputs and
  produces a rate that's small/progressive in the middle and aggressive at
  the extremes. `curve.py`'s `AccumDistCurve` is a single risk→rate map.
- **No long-only / medium-only / combined switch.** The three-configuration
  pluggability the user described doesn't exist as a strategy-level knob.

## Proposed next steps, in order

1. **Done this session:** true composite smoothing
   (`composite_risk.py`/`risk_index.py`, tested). Unblocks running the rest of
   this plan without the index being needlessly noisy first.
2. **Reconcile the two weight-selection objectives** (`stage_a.py` cycle
   overlap vs `weight_search.py` backtest return) before building a second
   (medium-term) copy of the same machinery — building two of something whose
   selection criterion is already unsettled compounds the ambiguity. Concretely:
   decide whether cycle-overlap should gate/regularize the backtest search
   (e.g. as a constraint or tie-break) rather than stay a pure diagnostic.
3. **Define a medium-term `CycleWindow` set.** This is the one step that
   should not be fully automated — it's the "I'd look at the chart and mark
   it" judgment call the user described. Recommend: propose a first-pass
   candidate set algorithmically (e.g. swing highs/lows at a fixed lookback,
   tunable window width, distinct from the long-term pins) for review, rather
   than either hand-picking without a proposal or shipping an unreviewed
   automated set — mirrors how `cycle_windows.py`'s existing pins are curated,
   not mined.
4. **Done (2026-09-04):** medium-term Stage A pass, via the new
   `scripts/run_stage_a_cycle_overlap.py` (reuses `cycle_overlap_score()`/
   `optimize_stage_a_weights()` against both window sets, real BTC data). The
   two layers pick different composites, confirming the prediction above:
   - Long-term (`btc_v1()`, corrected 2025-10-06 peak): `power_law=1.0`
     wins outright (objective 64.2, spread 41.4pp); every extra hurts —
     forcing one in (`require_extras=True`) drops the objective to 58.4.
   - Medium-term (`btc_medium_term_v1()`, 75-pivot set): `power_law=0.0,
     sma_band=0.5` wins instead (objective 41.4, spread 24.2) — power-law's
     whole-history position is the wrong signal for turns this frequent;
     the fast/slow SMA-band confluence catches them better.
   Lower medium-term objective is expected, not a regression: its windows
   are far denser (757 trough-days + 748 peak-days vs. long-term's 182+273),
   so separating the two means is a harder problem by construction.
   This only answers the cycle-overlap objective, not the backtest-return
   one `weight_search.py` actually ships with — see step 2's still-open
   reconciliation question before treating either weight set as a candidate.
5. **Build the combination layer.** Recommended shape: two independent
   `IndicatorWeight` sets → two independent `compute_composite_risk()` calls →
   two risk scores (`risk_long`, `risk_medium`) → a combination function that
   sums a small-rate curve driven by `risk_medium` with a large-rate curve
   driven by `risk_long`, e.g. `rate = curve_medium(risk_medium) +
   curve_long(risk_long)` with `curve_medium`'s max rate well below
   `curve_long`'s. Two independent curves (not one 2D curve) keeps each
   system independently inspectable, testable, and pluggable per the next
   step.
6. **Expose three configurations sharing one kernel.** A medium-only system
   (`curve_medium` alone), a long-only system (`curve_long` alone, close to
   what exists today), and the combined system (both). Same underlying
   indicators, confluence blends, and cycle-window scoring; only the curve
   wiring differs. This is the "pluggable into two types of systems" ask.
7. **Validate each configuration** through the existing protocol
   (`RESEARCH_STATE.md`'s "Standard trial protocol": curve_simulator go/no-go,
   Nautilus walk-forward, tearsheet, compact metrics table, explicit accept
   before touching `settings.json`). Update `RESEARCH_STATE.md`'s backlog and
   "current best validated candidate" only on accept, per its existing rule.

Note step 2 of `RESEARCH_STATE.md`'s own backlog — "joint period re-tuning of
the five confluence indicators... never applied jointly" — is a prerequisite
this plan should absorb rather than duplicate: the medium-term windows in
step 3 are exactly what joint re-tuning of the *daily/fast* legs should be
scored against.

## Generalizing beyond SDCA

SDCA is currently the only DCA-family strategy in `strategies/` (siblings —
`bollinger_mr`, `ema_cross*`, `macd_trend`, `rsi_momentum`, `m2_liquidity` —
are trade-signal strategies, not accumulation strategies), but the valuation
kernel is already asset-generic, which is why this framework should stay
asset-agnostic too:

- `RiskModel` is a selector (`btc_power_law` / `generic_valuation` /
  `rolling_z`, `sdca/providers.py`) — `generic_valuation.py` fits per-asset
  log-price trend rails from that asset's own cached history, not BTC's.
- `SdcaAssetProfile` (`sdca/asset_profile.py`) already carries a per-asset
  `SdcaOscillatorSpec`, extra-indicator allowlist, and now (via
  `cycle_windows.eth_research_v1()`) a per-asset cycle-pin set — `btc_v1()`
  and `eth_research_v1()` are the existing pattern for "one more asset."
- The reusable, asset-agnostic kernel this framework depends on:
  `agreement_scaled_blend`, `causal_rolling_z`, the new smoothing step,
  `CycleWindow`/`SdcaCycleWindows`, and `cycle_overlap_score`. None of these
  reference BTC. A future non-BTC DCA strategy (or ETH-SDCA moving out of
  research-only status) should reuse all of it, supplying only its own
  `RiskModel`, `SdcaOscillatorSpec` windows, and cycle pins.

When a second DCA strategy is actually built, the long/medium/combined
curve-combination layer (step 5 above) belongs one level up from `sdca/` —
today it would be premature to extract, since there is only one caller.
