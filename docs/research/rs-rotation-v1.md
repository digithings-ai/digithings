# Relative-strength asset rotation — Phase 0 design note (#1084)

**Status:** Phase 0 research spike (chosen v1) + Phase 1 long-only implementation map.
**Seeds:** DigiVault theory map; optimizer epic #1079; SDCA RS-driven risk hook #1082; macro regime gate #1085.

## Literature map (compact)

| Tradition | Claim | Practical takeaway |
|-----------|--------|-------------------|
| Cross-sectional momentum (Jegadeesh–Titman; Asness et al.) | Relative winners continue over ~3–12 months | Rank the *pool*, do not pick by absolute return alone |
| Time-series / absolute momentum (Moskowitz–Ooi–Pedersen) | Asset’s own trend filters crashes | Hold cash when the “best” name is still falling |
| Dual momentum (Antonacci) | Relative *and* absolute | v1 gate: long only if trailing absolute return > 0 |
| Risk-adjusted momentum | Return / vol dampens lottery names | Prefer risk-adj score for crypto alts with fat tails |
| Skip window | Recent month often mean-reverts | Drop the last ~1 week (crypto) / ~1 month (equity) from the lookback |
| Rebalance / turnover | Monthly (equity) or weekly (crypto) trades off signal decay vs costs | v1: weekly; costs deferred to #1079 |
| Correlation-aware universe | Low-corr sleeves improve rotation edge | v1 uses a fixed crypto pool; pool selection is Phase 2+ |
| Regime overlay | Risk-off → cut gross | Optional consumer of `MacroLiquidityModel.risk_on` (#1085); Phase 2+ default-on |

## Chosen v1 (Phase 1)

**Signal.** For each asset on each day \(t\):

1. **Lookback** \(L=90\) trading days ending at \(t - S\), with **skip** \(S=7\).
2. **Absolute return** \(R = P_{t-S}/P_{t-S-L} - 1\).
3. **Vol** = stdev of daily simple returns over the same window (floor \(\varepsilon\)).
4. **Risk-adjusted score** \(= R / \max(\sigma, \varepsilon)\).
5. **Absolute gate** — asset *qualifies* iff \(R > 0\) (dual-momentum cash rule).
6. **RS rank** — among assets with a finite score that day, rank by risk-adjusted score (1 = strongest). Missing history → null score, not ranked.

**Look-ahead.** `skip_days` is required ≥ 1 so the signal never uses the same bar’s close that the rotator trades on.

**Portfolio.** Long-only top-\(N\) (default \(N=1\)) equal-weight among *qualifying* names; **cash** when none qualify. Rebalance every \(R_b=7\) calendar days on the ranking grid. No shorts, no spreads, no vol targeting in v1.

**Benchmarks (CI harness, not published `BacktestResult`).** Equal-weight always-invested (same rebalance cadence) and buy-&-hold equal initial sleeves (no rebalance). Nautilus remains the sole published engine; the Polars harness documents allocation math the same way SDCA/`backtest_regime_gate` do.

**Regime (#1085).** Phase 1 exposes an *optional* `risk_on` overlay: when false/null, force cash. Phase 2+ can default it on for expansion-only rotation. Weight/window search stays with #1079.

## Explicitly deferred (Phase 2+)

- Long/short + spread/pairs legs
- Volatility targeting / risk-parity sleeve weights
- Correlation-aware pool construction
- Turnover / transaction-cost objective in optimize
- Publishing a live digiquant.io book / `--push-supabase`

## Module map

| Piece | Path |
|-------|------|
| Ranker (shared RS signal) | `digiquant/indicators/rs_ranker.py` |
| CI rotation backtest | `digiquant/strategies/rotation/backtest.py` |
| Nautilus long-only rotator | `digiquant/strategies/rotation/nautilus_strategy.py` |
| Architecture | `digiquant/ARCHITECTURE.md` § RS rotation |

## References (seed list)

- Jegadeesh & Titman (1993), *Returns to Buying Winners…*
- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*
- Antonacci, *Dual Momentum Investing*
- Asness, Moskowitz & Pedersen (2013), *Value and Momentum Everywhere*
- (Internal) #1078 master composition; #1085 macro-liquidity gate; #1082 SDCA RS risk hook
