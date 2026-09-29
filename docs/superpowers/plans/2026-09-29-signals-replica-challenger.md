# Signals-Replica Challenger — spec (2026-09-29)

Goal (owner-stated): learn from the Railway production signals app
(`sdca-signals-automation`), beat it on an identical backtest, and make our
aggregate valuation index more resilient. Source unavailable; reimplement from
UI spec, flag every assumption with `ASSUMPTION[Sn]` in code + here.

## 1. Production behavior (from UI fetch, no source)

- Composite Risk with Q1/Q99 rails, median, Z-score; bands 0–25 Buy, 25–50
  Accumulate, 50–75 Trim, 75–100 Sell.
- 4 indicator votes, equally weighted: Asymmetric Tail Curvature (price);
  Sharpe (realized P/L, 14d EMA); Cost Basis P/L Ratio (7d EMA); Onchain Risk
  Composite (7d EMA). Composite tab + Accum/Dist backtest driven by composite.
- Curve: X = Composite Risk %, Y = % traded per day. Positive = % of current
  cash bought; negative = % of current BTC sold. No Z-gate, no tranches.
- Backtest outputs: portfolio vs lump sum, avg daily rate, cash reserve incl.
  sells, max DD (DCA and buy&hold).

## 2. Mapping onto our engine (verified via codebase explores)

- Curve mechanics: `AccumDistCurve` (`curve.py:59`, 21 nodes at RISK_NODES) +
  `size_trade` (`backtest.py:85`) + `run_backtest` (`backtest.py:108`) ARE the
  production semantics. No new backtester; replica feeds these a new risk
  series and node set.
- Blend: `compute_composite_risk` (`composite_risk.py:66`) with four
  `IndicatorWeight(..., weight=1.0)` gives equal votes + `risk = 50 − z·50/3`.
- EMA legs: `causal_ema_smooth` (`composite_risk.py:50`).
- Rails: `BtcPowerLawRiskModel(...).rails_full(dates)` → q01/q50/q99, then
  `power_law_z_score(price, q01, q50, q99)` for literal Q1/Q99 z
  (default `rails()` is q10/q95 — do NOT use for the replica).
- Feeds: `data/price-history/BTC-USD.csv`; Bitview parquets
  (`data/onchain/bitview/*.parquet`: mvrv, asopr_24h, puell_multiple,
  rhodl_ratio); CoinMetrics `btc_AdrActCnt.parquet`. No cost-basis feed
  exists; no realized-P/L series exists.

## 3. The four replica votes (assumptions flagged)

- **S1 — Tail curvature (price). Formula unknown.** Proxy: rolling-window tail
  asymmetry of log returns = (mean upside tail − mean downside tail magnitude)
  over 252d, causal rolling-z (90d) to [-3,3], cheap=+3. Document as proxy.
- **S2 — Sharpe (realized P/L, 14d EMA). Denominator ambiguous** (book P/L vs
  price returns?). Proxy: Sharpe of daily log returns over 90d window
  (annualized, rf=0), sign-flipped (high Sharpe = rich = negative z),
  then 14d EMA smooth. Flag sign convention as assumption.
- **S3 — Cost Basis P/L Ratio (7d EMA). Circularity risk: book-dependent.**
  Two readings: (a) onchain realized-price/MVRV-style network cost basis;
  (b) the DCA book's own avg cost vs price (curve-dependent → index depends
  on curve being evaluated). Decision: implement (a) first using Bitview MVRV
  as the network cost-basis ratio (log, sign-flipped rolling-z, 7d EMA),
  because a curve-dependent index cannot serve as a fixed baseline. Record (b)
  as rejected-with-reason; revisit only if owner says production means (b).
- **S4 — Onchain Risk Composite (7d EMA). Constituents unknown.** Proxy:
  equal-weight blend of the four catalog onchain z legs
  (mvrv/asopr/puell/rhodl, existing 365d-window legs) + 7d EMA smooth.
  Reuse `build_onchain_composite_z` semantics where possible.

## 4. Default-curve problem (unknown production default nodes)

Production's default 21-node curve is unknown. Do NOT invent one and claim
parity. Fair comparison protocol instead: run the SAME curve-search budget on
both indexes (replica composite vs our cycle-4/live index) over identical
data/windows, compare winners. Searches use `search_wide_knee_curve_feasibility_aware`
or the robust variant; report both raw (production-style: full-history
in-sample vs lump) and gated (our walk-forward OOS vs flat) numbers.

## 5. Comparison + gate

- New script `scripts/run_replica_comparison.py`: builds replica risk series,
  runs both systems on identical dates/prices/cash, prints portfolio-vs-lump,
  vs-flat-DCA, max DDs, deployment. Defines `beats_production_oos` as the
  challenger gate (candidate OOS vs-flat minus replica OOS vs-flat > 0 on the
  same folds).
- Resilience read-out: per-vote attribution (drop-one-vote sensitivity on the
  replica composite) vs our index's drop-one-indicator sensitivity, to direct
  the "harden our index" step.

## 6. Module layout (new code, TDD per repo bar)

- `strategies/sdca/signals_replica.py` — four vote builders + composite
  assembler, all `ASSUMPTION[Sn]`-tagged; reuses composite_risk/rails/catalog
  primitives, no forks.
- `tests/dq/strategies/sdca/test_signals_replica.py` — vote ranges [-3,3],
  equal-weight math, EMA causality (no lookahead), Q1/Q99 rail usage.
- No preset/settings changes. No live-trading paths. Research-only.

## 7. Open promotion state (parked, not lost)

Commit `9cef6d5b8` (WIP): presets.json + provenance updated for cycle-4.
Still open: RESEARCH_STATE Current-best step 6, sdca unit tests. Resume only
if the replica comparison vindicates cycle-4.
