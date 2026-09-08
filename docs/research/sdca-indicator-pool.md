# SDCA BTC v1 indicator pool

Research note (not production code). Date: 2026-08-30.

This note inventories what digiquant already has, proposes a **small BTC v1
candidate pool** for the composite that turns Strategic-DCA accumulate / dead /
distribute on and off, and records how each series should become a z-score
`compute_composite_risk` can blend. It does **not** implement extras, change
weights, touch live-trading, or publish a tearsheet.

Parallel work: `cursor/sdca-composite-weights-af6c` is already wiring
`extra_indicators` + weight optimize (`m2`, `rs_eth`, `dxy`). This note must
not race that branch. Do not edit `risk_index.py`, walk-forward, or optimize
from this research.

Related issues: [#3167](https://github.com/digithings-ai/digithings/issues/3167)
(epic), [#3174](https://github.com/digithings-ai/digithings/issues/3174)
(weights + curve optimize), [#3175](https://github.com/digithings-ai/digithings/issues/3175)
(generic crypto rails), [#1084](https://github.com/digithings-ai/digithings/issues/1084)
(RS rotation), [#1086](https://github.com/digithings-ai/digithings/issues/1086)
(on-chain valuation), [#3176](https://github.com/digithings-ai/digithings/issues/3176)
(equity spike — research only; **no CAPE `RiskModel` in v1**).

---

## Normalized intent

### Goal

Aggregate valuation is a **weighted blend of long-horizon sub-indicators**.
That aggregate is the only thing that should drive the DCA curve. After a
pool exists, digiquant optimize searches **weights** and the **entry/exit
curve**. Publishing to the digiquant.io strategy library with a **larger
signal delay** is later — not this note.

### Requirements

1. Long-term indicators, not day-trade noise.
2. Price-based technicals are in scope: weekly RSI, weekly MACD, other slow oscillators.
3. BTC/crypto on-chain valuation belongs in the **candidate** pool (MVRV, NUPL, Puell, SOPR, …).
4. Stocks (put/call, CAPE, macro-per-asset) are **later per-asset research**, not v1.
5. Each series must become a `[-3, 3]` z (cheap = +, rich = −) for
   `compute_composite_risk`.
6. Weekly vs daily alignment must be causal (no lookahead).
7. Do not add new paid APIs.
8. Do not publish, `--push-supabase`, or change delay now.

### Constraints / guardrails

- Polars only; Pydantic v2; digi names lowercase in prose.
- No live-trading paths.
- No equity CAPE `RiskModel` in v1 ([#3176](https://github.com/digithings-ai/digithings/issues/3176)).
- Do not treat five transforms of the same daily close as independent votes.
- Do not race the composite-weights implementer.

### Scope boundary

- **In scope:** inventory, BTC v1 include/defer list, z-mapping and resample
  rules, on-chain feasibility, throwaway weekly-oscillator correlation vs
  `valuation_z`.
- **Out of scope:** production extras, optimize, walk-forward, `risk_index.py`
  edits, site publish, delay changes, live trading, stocks implementation.

---

## Inventory (what digiquant already has)

| Piece | Where | SDCA-relevant fact |
|---|---|---|
| Power-law rails → `valuation_z` | [`btc_power_law.py`](../../digiquant/src/digiquant/strategies/sdca/btc_power_law.py), [`valuation.py`](../../digiquant/src/digiquant/strategies/sdca/valuation.py) | Primary indicator. Cheap = +3, rich = −3. `#3173` real coefficients live on a parallel branch; develop still has the synthetic example. |
| Composite blend | [`composite_risk.py`](../../digiquant/src/digiquant/strategies/sdca/composite_risk.py) | Weight-normalized average of enabled z series. **Any enabled null nulls the day** — no partial blend. |
| Risk parquet glue | [`risk_index.py`](../../digiquant/src/digiquant/strategies/sdca/risk_index.py) | `build_risk_index(..., extra_indicators=None, valuation_weight=1.0)`. Hook already exists; do not edit it here. |
| History cache | [`history_cache.py`](../../digiquant/src/digiquant/data/prices/history_cache.py) | Flat CSV `data/price-history/<TICKER>.csv`. Same store as `digiquant_fetch_coinbase_ohlcv`. |
| Coinbase daily OHLCV | [`fetch_coinbase.py`](../../digiquant/scripts/fetch_coinbase.py) | BTC/ETH/SOL daily via CCXT. This environment's BTC cache: 2015-07-20 → 2026-08-29 (4059 bars). |
| Daily technicals | [`technicals.py`](../../digiquant/src/digiquant/data/prices/technicals.py) | RSI(7/14/21), MACD(12,26,9), SMA 20/50/**200**, `% vs SMA200`, **zscore vs SMA200**. **Daily only** — no weekly resample. |
| Bar-by-bar RSI | [`oscillators.py`](../../digiquant/src/digiquant/indicators/oscillators.py) | Nautilus `rsi_momentum` path. Not a batch weekly series. |
| M2 vote (separate strategy) | [`m2_signals.py`](../../digiquant/src/digiquant/indicators/m2_signals.py), [`m2_liquidity.py`](../../digiquant/src/digiquant/strategies/m2_liquidity.py) | Five sub-indicators on **M2 ROC**, including RSI and MACD **of M2**, not of BTC. Expects a precomputed parquet. Planned `digiquant.data.m2` **never landed**. |
| FRED ingest | [`macro_ingest.py`](../../digiquant/src/digiquant/data/prices/macro_ingest.py), [`macro_series.yaml`](../../digiquant/src/digiquant/research/config/macro_series.yaml) | Free FRED + Yahoo FX. Stores `realtime_start` in row meta. **`M2SL` is not in the default YAML** (research skills still mention it). Present and useful: `DTWEXBGS` (broad USD), `WALCL` (Fed assets, weekly), HY/IG OAS, VIX, yields. |
| Relative strength | [`relative_strength.py`](../../digiquant/src/digiquant/data/prices/relative_strength.py) | Sector ETF vs **SPY**. Not BTC/ETH. RS-driven SDCA risk is [#1084](https://github.com/digithings-ai/digithings/issues/1084) / leftover #1082 item 4. |
| On-chain in-repo | [`hyperdash.py`](../../digiquant/src/digiquant/data/onchain/hyperdash.py) | Hyperliquid **perp cohort positioning** (smart vs rekt). Snapshot overlay for research, fail-soft, **not** a long MVRV/NUPL history. |
| ETF “flows” | [`etf_flows.py`](../../digiquant/src/digiquant/data/prices/etf_flows.py) | Dollar-volume z + OBV **proxy**. Explicitly not IBIT creations. Too noisy / not valuation. |
| Signal delay (publish) | `apply_signal_delay` in `generate_tearsheets.py`, tearsheet schema 1.2 | Calendar-day truncation already exists. **Do not change delay or `--push-supabase` now.** |
| In-flight extras | `cursor/sdca-composite-weights-af6c` | Named extras **`m2` / `rs_eth` / `dxy`** plus `causal_rolling_z` / `align_to_dates`. Treat those names as reserved. |

research ops docs list Glassnode / CryptoQuant as **paid** research sources
([`data-sources.md`](../../digiquant/src/digiquant/research/docs/ops/data-sources.md)).
That is a directory, not an ingest.

---

## Collinearity rule

A vote is only worth blending if it can disagree with power-law `valuation_z`
on a cycle-relevant horizon. Transforms of the **same daily close** (daily RSI,
daily MACD, ROC, `% vs SMA200`, Mayer = price / 200w SMA, subsidy-only
“Puell”) are not independent just because the formula differs.

Empirical check on Coinbase BTC daily 2015-07-20 → 2026-08-29, real `#3173`
coefficients (not committed here; loaded at research-time from the fit
branch). Sign convention: cheap / oversold = `+z`. Pearson *r* on overlapping
non-null days:

| Pair | r | n | Read |
|---|---|---|---|
| `valuation_z` vs weekly RSI z | **+0.365** | 3962 | Related, not a duplicate |
| `valuation_z` vs weekly MACD-hist z | **+0.066** | 3647 | Nearly orthogonal |
| `valuation_z` vs Mayer-like 200w z | **+0.843** | 2303 | **Near-duplicate — do not add** |
| `valuation_z` vs daily RSI z | +0.092 | 4046 | Independent but **day-trade horizon** |
| weekly RSI z vs weekly MACD z | **+0.654** | 3647 | Oscillators overlap with each other |
| weekly RSI z vs daily RSI z | +0.537 | 3962 | Same family, different cadence |

Throwaway script: [`sdca_weekly_oscillator_corr.py`](sdca_weekly_oscillator_corr.py).
Plot: `/opt/cursor/artifacts/sdca-indicator-pool-weekly-corr.png`.

**Why weekly RSI/MACD are not redundant with power-law z.** Power-law z is
*distance from a fitted secular corridor in log-time*. Weekly RSI/MACD are
*momentum of weekly closes*. They can be oversold while price is still rich vs
the corridor (correction inside a bubble) and overbought while still cheap
(early bull). The 0.37 / 0.07 correlations are the quantitative version of
that. Mayer / 200w SMA is the opposite: another slow trend-distance of the
same close, *r* = 0.84 with `valuation_z` — drop it.

Caveat on weekly MACD z: a 2y rolling-z of the histogram **saturates at ±3**
during trend extensions. If MACD is included, prefer a longer window, a rank
z, or a raw histogram mapped through a tanh — do not ship the clipped 104-week
z as-is.

---

## Recommended BTC v1 set (no new vendors)

Small pool. Implement from data already in-repo or already fetchable with
existing free clients (Coinbase OHLCV, FRED). Let `#3174` / the in-flight
weight optimizer shrink overlap.

| # | Name | Include? | Source | Horizon | Why |
|---|---|---|---|---|---|
| 1 | `valuation` | **yes (primary)** | Power-law rails × Coinbase close | Secular | Already wired. |
| 2 | `weekly_rsi` | **yes (new)** | Weekly Wilder RSI(14) of Coinbase weekly close | Cycle / months | Long-horizon technical; only moderately correlated with rails. |
| 3 | `weekly_macd` | **yes, second oscillator** | Weekly MACD(12,26,9) histogram of weekly close | Cycle / months | Almost orthogonal to `valuation_z`; overlaps RSI (*r* ≈ 0.65) so **do not equal-weight** with RSI as two independent votes. |
| 4 | `m2` | **yes, do not re-implement here** | FRED `M2SL` (add to YAML; client already exists) | Months, lagged | Liquidity, not a close transform. In-flight extra name `m2`. |
| 5 | `dxy` | **optional 5th** | FRED `DTWEXBGS` already in YAML (or Yahoo `DX-Y.NYB`) | Months | Inverse USD. In-flight extra name `dxy`. Inverse sign: strong dollar = −z (risk-off for BTC). |

**One liquidity series, not two.** `WALCL` (Fed assets, weekly, already ingested)
is the same liquidity family as M2 over cycles. Prefer `M2SL` to match the
existing M2 strategy thesis; do not also vote `WALCL`.

**`rs_eth`:** in-flight as a named extra. It is *relative* BTC vs ETH, not
absolute valuation. Useful later with [#1084](https://github.com/digithings-ai/digithings/issues/1084);
keep weight at 0 for BTC v1 until RS research exists. Needs the ETH Coinbase
cache (`ETH-USD` is already in `fetch_coinbase.py` `SYMBOLS`).

### Explicitly not v1 (price-derived duplicates or wrong horizon)

- Mayer multiple / 200-week SMA distance / daily `zscore_200` / `% vs SMA200`.
- Daily RSI, daily MACD, ROC(5/10/21), stochastic, Bollinger %b of price.
- Subsidy-only “Puell” (constant issuance × price / 365d MA ≈ another SMA
  distance of close). True Puell needs miner **fees**.
- Crypto Fear & Greed (dropped from default ingest, `#328`; sentiment, short).
- Hyperdash cohort divergence (perp positioning, not valuation; wrong horizon).
- Volume/OBV ETF proxy.

---

## On-chain valuation (candidate pool, **defer** — [#1086](https://github.com/digithings-ai/digithings/issues/1086))

These are the right *kind* of series (stock/flow of coin cost basis, not
another close transform). They need a vendor decision and an ingest. **Do not
add a paid API.** Do not scrape Look Into Bitcoin without a human ToS review
(already flagged on #1086).

| Metric | What it measures | Independence vs close / rails | Feasibility (checked 2026-08-30) | v1 |
|---|---|---|---|---|
| **MVRV** (market / realized cap) | How far cap sits vs on-chain cost basis | **Independent** — realized cap is not a function of close alone | **Coinmetrics community** `CapMVRVCur` returned without an API key; history from **2010-07-18**. `CapRealUSD` is **forbidden** on the community plan (MVRV ratio is available; the legs are not). BGeometrics `GET https://bitcoin-data.com/v1/mvrv` is free but **last 4 years only** (here: 2022-08-30 → 2026-08-29) and the free plan **forbids commercial publishing**. Glassnode / CryptoQuant: paid (already listed in research ops docs). | Defer. Best free path for #1086: Coinmetrics `CapMVRVCur`. Community data is CC-licensed — **legal review before any digiquant.io publish**. New vendor even if unpaid. |
| **MVRV-Z** | MVRV standardized vs its own history | Same series as MVRV | Compute **our** causal rolling/expanding z from `CapMVRVCur`. Do not buy Glassnode's z. | Defer; **this** is the z to blend, not raw MVRV and MVRV-Z as two votes. |
| **NUPL** | (market − realized) / market = `1 − 1/MVRV` | **Monotone transform of MVRV** | Coinmetrics community: **forbidden** without credentials. | Defer; **do not** add NUPL alongside MVRV. |
| **Puell** | Daily miner USD revenue / 365d MA | True Puell (with fees) spikes at tops independently; subsidy-only ≈ SMA of price | No free long history verified. BGeometrics has an endpoint under the 4y free cap. | Defer until a fee-inclusive series exists. |
| **SOPR / aSOPR** | Realized profit ratio on spent coins (flow) | Related at cycle extremes, not a stock duplicate of MVRV | Coinmetrics community: **forbidden**. BGeometrics `/v1/sopr` = 4y free. | Defer; if #1086 lands MVRV, SOPR is the next *flow* vote, not a second stock vote. |
| LTH/STH MVRV, RHODL, realized price | Holder-cohort splits of the same realized-cap idea | Nested in MVRV | Paid / 4y-free | Defer. |

**#1086 v1 on-chain recommendation (when that issue is executed):** ingest
Coinmetrics community `CapMVRVCur` only, map to one `mvrv_z` indicator, fall
back to valuation-only when the feed is down (composite null rule currently
**cannot** fall back per indicator — see below). Do not also ingest NUPL.
Human review of CC license vs commercial tearsheets before publish.

Hyperdash stays an research overlay, not an SDCA vote.

---

## Stocks / put-call / macro (later)

[#3176](https://github.com/digithings-ai/digithings/issues/3176) is the equity
spike. **No CAPE `RiskModel` in BTC v1.** Put/call, Buffett indicator, ERP,
single-stock fundamentals are per-asset research after crypto SDCA is
measurable. FRED already has legs that note will care about (`GDP`, credit
OAS, VIX) — do not wire them into `btc_sdca` “just because they exist.”

---

## How each series becomes a z `compute_composite_risk` can blend

Convention (already in [`valuation.py`](../../digiquant/src/digiquant/strategies/sdca/valuation.py)):
**cheap / buy = +3, rich / sell = −3**, clipped to `[-3, 3]`.

| Series | Raw | z mapping | Nulls |
|---|---|---|---|
| `valuation` | log-space position in rails | already `[-3, 3]` | null if any rail/price null |
| `weekly_rsi` | Wilder RSI(14) on weekly close, in `[0, 100]` | `(50 − RSI) / 50 × 3`, clip | null until 14 weekly bars |
| `weekly_macd` | weekly MACD histogram | causal trailing z of **−hist**, long window (or rank/tanh — see saturation note) | null until EMA warmup + z window |
| `m2` | M2SL level or ROC | causal rolling z of **+ROC** (accelerating liquidity = +z / buy), matching the in-flight `m2_liquidity_z` tests | null until ROC + window; **also null before publication** (below) |
| `dxy` | `DTWEXBGS` | causal rolling z of **−level** (strong dollar = −z) | same |
| future `mvrv_z` | `CapMVRVCur` | causal expanding or very long rolling z of **−MVRV** (high MVRV = rich = −z). Expanding mean of MVRV is the usual “MVRV-Z” cousin. | null until min history |

Do not pass raw RSI (0–100) or raw MVRV (~0.5–5) into the blend — the
composite assumes comparable z units.

**Null rule interaction.** Today, one enabled extra that is null on a day
nulls **all** risk that day. A sparse on-chain series would therefore
*disable trading* whenever Glassnode/Coinmetrics gaps. Until
`compute_composite_risk` gains an explicit “skip-missing” mode (out of
scope here, and would be a behaviour change), extras must be **dense** after
warmup (weekly oscillators and FRED forward-fill qualify; 4-year-only
BGeometrics does not).

---

## Weekly vs daily: resample rules (no lookahead)

BTC trades every calendar day. Use **ISO weeks** (Polars `dt.truncate("1w")`,
Monday-aligned): one weekly bar = **last daily close of that week**.

1. Compute RSI/MACD **only** on that weekly close series.
2. Broadcast back to daily with `join_asof(..., strategy="backward")` on
   `week_end`. A Wednesday sees last week's completed bar, never the
   in-progress week's Friday/Sunday close.
3. Do not use `technicals.py`'s daily RSI(14) as a stand-in for weekly RSI(14)
   — different horizon (empirical *r* = 0.54 between those two z series).
4. Coinbase's **today** daily bar is incomplete until UTC EOD; the fetch path
   already has `--through-yesterday`. Research/backtest should drop an
   unfinished week the same way.

### Macro alignment (M2 / DXY) — publication, not period date

FRED `M2SL` is **monthly** and revised. The ingest writes `obs_date` = period
date and stashes `realtime_start` in meta
([`fred_observations_to_rows`](../../digiquant/src/digiquant/data/prices/macro_ingest.py)).
Aligning M2 to BTC on `obs_date` **is lookahead** (you would use September M2
on 1 September, before FRED published it).

Required:

- As-of join daily BTC dates to M2 on **publication date** (`realtime_start` /
  vintage), then forward-fill.
- Do **not** apply the PineScript M2 strategy's 86-day “lead” as a forward
  shift of unpublished prints. That overlay is a chart trick; a live/backtest
  SDCA vote may only read already-released M2.
- `DTWEXBGS` is daily; still as-of on the last available print (weekends/holidays).

`M2SL` is missing from [`macro_series.yaml`](../../digiquant/src/digiquant/research/config/macro_series.yaml).
Adding it is an ingest one-liner with the existing FRED client — not a new
vendor. The `digiquant.data.m2` module from the 2026-06 plan was never merged;
SDCA should not wait on that whole M2 strategy fetcher.

---

## Publish + extra delay — explicitly later

Public tearsheets already support `signal_delay_days` (schema 1.2, `#1462`)
and SDCA's risk parquet is built from the delayed frame (`#3170`). Slow
valuation systems can use a **larger** delay than the Slappers when that
publish path is executed.

**Not now:** no `--push-supabase`, no delay-flag change, no digiquant.io
library entry from this note. Deal with delay when the strategy is actually
published ([#3167](https://github.com/digithings-ai/digithings/issues/3167)
definition of done).

---

## Suggested implementation order (for whoever is not the weights agent)

1. Finish in-flight extras plumbing (`m2` / `dxy` / weights simplex) on the
   composite-weights branch — **this note does not do that**.
2. Add `weekly_rsi` + `weekly_macd` as catalog extras computed from the
   existing Coinbase cache (same `history_cache.py` path as the power-law
   fit). Unit-test: causal week as-of, sign convention, warmup nulls.
3. Add `M2SL` to the FRED YAML; align on `realtime_start`.
4. Let `#3174` optimize weights **and** curve shape on `{valuation, weekly_rsi,
   weekly_macd, m2}` with a prior that RSI and MACD are **not** two full votes.
5. File/execute [#1086](https://github.com/digithings-ai/digithings/issues/1086)
   for a single `mvrv_z` from Coinmetrics community `CapMVRVCur` after license
   review. Only then consider SOPR as a *flow* add-on.
6. Publish + delay: later. Live trading: never from this workstream without
   the human gate.

---

## Open questions (left unresolved on purpose)

- Exact MACD z mapping (long rolling z vs rank vs tanh) given saturation.
- Whether the optimizer is allowed to turn weekly MACD's weight to 0 (likely
  yes — that is the point of a simplex).
- Coinmetrics community CC license vs commercial tearsheets — human.
- Vintage FRED vs “lag N calendar days” as a simpler publication proxy for
  M2SL if vintage rows are messy.

None of these block the v1 **price** extras (weekly RSI/MACD) or the
already-in-flight M2/DXY wiring.
