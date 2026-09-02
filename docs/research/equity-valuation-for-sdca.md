# Equity valuation metrics for SDCA — sources, viability, verdict

Research spike for [#3176](https://github.com/digithings-ai/digithings/issues/3176) (SDCA v1 epic
[#3167](https://github.com/digithings-ai/digithings/issues/3167) / parent [#1078](https://github.com/digithings-ai/digithings/issues/1078)).
**Not an implementation issue.** No production `RiskModel` or equity SDCA strategy is shipped here.

Crypto SDCA positions *price inside fitted power-law rails*. Equities do not have a genesis date or a
decaying power law; they have earnings, rates, and sentiment. Applying `BtcPowerLawRiskModel` to SPY
would produce rails that look plausible and mean nothing. This note answers what “cheap” / “expensive”
can mean for equities, whether we can source it without lookahead, and whether the existing
`RiskModel` protocol still fits.

Throwaway check: [`equity_valuation_sdca_check.py`](equity_valuation_sdca_check.py) (Buffett
indicator from public FRED graph CSVs). CAPE event prints were read once from Shiller’s public
`ie_data.xls` (Yale, last saved 2023-09-17 in the copy fetched 2026-08-30) and are tabulated below;
that workbook is **not** committed.

## Verdict (read this first)

1. **Do not implement an equity SDCA `RiskModel` in the v1 pack.** A CAPE-percentile (or
   Buffett-percentile) driver would have distributed into the 2000 and 2021 highs — good — but would
   **not** have been in an accumulate band at the March 2020 low (CAPE still ~85th percentile of its
   full history) and was only *moderately* cheap in March 2009 (~25th percentile of the prior 50
   years, not a fire-sale). That fails the owner’s “would it have accumulated near 2009 and 2020
   lows?” test if the mapping is “position the valuation metric in its own long-run distribution,”
   which is the closest analogue of crypto rails.
2. **The existing `RiskModel` protocol can still fit equities**, but only if rails are **implied
   fair-price bands** (e.g. CAPE band × trailing real EPS), not a time-power-law of SPY, and only
   with a **second, faster indicator** in `compute_composite_risk()` (credit / ERP). Raw CAPE-as-z
   is the wrong sibling abstraction; a second protocol is not required if we keep “price vs rails.”
3. **Scope boundary: broad index ETFs (SPY / VTI) only.** Single-name fundamentals are a different
   product (per-company PE, filings, survivorship). Do not file that.
4. **Do not file v1 implementation issues from this spike.** File later, and only if the owner
   still wants index SDCA after reading the 2020 miss. Recommended follow-up bodies are at the
   bottom (this session cannot `gh issue create`).

## Candidate metrics

| Metric | Source | Cadence | History | License / ToS | PIT handling | Role vs rails |
|---|---|---|---|---|---|---|
| CAPE (Shiller P/E10) | Yale `ie_data.xls` (academic). **Not on FRED.** Do not scrape MULTPL. | Monthly | 1871– | Shiller posts it for research; not a registered adviser; no redistribution-as-product claim. Human review before we *depend* on a monthly pull. | Earnings lag 1–2 quarters; CPI is revised. There is **no ALFRED vintage**. Impose a publication lag (e.g. use month *t−2* CAPE on day *t*) and never “fill forward” a restated E. | Slow valuation. Map to implied price rails (CAPE band × real EPS), **not** to a time-power-law. |
| Trailing / forward PE | Trailing: from prices + GAAP/operating EPS (paid vendor or delayed free). Forward: FactSet / Bloomberg consensus. | Daily / quarterly | Trailing: decades if vendor; forward: ~30y, vendor. | Paid. **Human gate** before a new vendor. | Consensus forward PE is revised continuously — classic lookahead if you use the final number on a past date. | Inferior to CAPE for a multi-decade SDCA book. Skip until a PIT vendor exists. |
| Buffett (mkt cap / GDP) | **FRED first.** Construct `NCBEILQ027S` (nonfinancial corporate equities, $ millions, quarterly) / `GDP` ($ billions, SAAR). World Bank `DDDM01USA156NWDB` is the same idea annually, last obs **2020** — too lagged to drive a daily strategy. | Quarterly (GDP: advance / second / third + annual revisions) | 1947– | [FRED ToS](https://fred.stlouisfed.org/legal/): free with attribution; API key required for the JSON API. Graph CSV is public. | **This is the lookahead trap.** Using today’s GDP vintage on 2009-03-31 is not what a 2009 actor saw. Use ALFRED (`realtime_start` = `realtime_end` = as-of). `macro_ingest.fred_observations_to_rows` already *stores* `realtime_start` but `fetch_fred_series()` does **not** request vintages — current ingest is latest-vintage. | Slow valuation / regime. Bad as a *daily* rail by itself: COVID Q2 2020 **GDP collapse in the denominator made the ratio look *more expensive*** right as equities bottomed. |
| Equity risk premium (CAPE earnings yield − 10y) | CAPE (above) + FRED `DGS10` (already in `macro_series.yaml`) | Daily rate × monthly CAPE | 1962– (10y); CAPE 1881– | Same as legs. | `DGS10` is a daily close, low revision risk. CAPE lag still applies. ERP **must not** mix a revised CAPE with a contemporaneous yield without the lag. | Rate-aware valuation. **This is the metric that makes 2020 look cheap** when raw CAPE does not (see table). Prefer ERP (or CAPE-implied price *and* a rates overlay) over raw CAPE percentile. |
| HY OAS (ICE BofA) | FRED `BAMLH0A0HYM2` — **already in** `digiquant/src/digiquant/olympus/atlas/config/macro_series.yaml` and the daily FRED ingest. MCP `digiquant_get_macro_series` reads the *ingested* Supabase table, not live FRED. | Daily | 1996– | ICE via FRED. Graph CSV without an API key returned only ~3 years in this session; full history needs `FRED_API_KEY` (already used by `fetch_fred`). | Spreads are not revised like GDP, but the series can be restated. Still prefer ALFRED for backtests. | **Regime filter / composite indicator**, not a valuation rail. Closest existing pattern: M2 liquidity’s indicator vote (`indicators/m2_signals.py`) feeding a precomputed parquet. |
| Put/call (CBOE) | CBOE daily market statistics; historical usually **paid**. Not on FRED. | Daily | 1990s– (vendor) | Proprietary. Scraping the public delayed page is fragile and likely ToS-hostile. **Human review required** before any dependency. | Same-day sentiment; little revision, but definition changes (equity-only vs total, inverted ETF effects). | Sentiment overlay in the composite, **never** a `RiskModel` rail. |

**FRED-first rule, applied:** anything we can already ingest (`DGS10`, `BAMLH0A0HYM2`, `GDP`,
`NCBEILQ027S`) is worth more than a slightly better series behind a scrape. CAPE is the one
non-FRED exception that is still justified (longest cheap/rich history, academic, no scrape).
Forward PE and put/call fail the FRED-first test and need a human-gated vendor if they are ever
pursued.

## Level vs rails — does `RiskModel` fit?

`RiskModel` is a structural protocol: `rails(dates) -> DataFrame[low, median, high]`. The engine
then calls `valuation_z_score(price, low, median, high)` and maps that z into `[0, 100]` risk.
Crypto fills those rails with quantile regressions of *price on log calendar time*.

Equities can reuse the **protocol** in one of two ways:

| Approach | How rails are produced | Fits `RiskModel`? | Verdict |
|---|---|---|---|
| A. Time-power-law of SPY | Same code path as BTC | Yes, mechanically | **Reject.** An index has no genesis, no decaying adoption curve. Rails would be a fitted trend that overfits one bull market. |
| B. Implied fair-price bands | `low/median/high_price = (CAPE_q10 / CAPE_q50 / CAPE_q90 reversed) × trailing real EPS`, or ERP bands × a yield | Yes | **Accept if we ever build this.** Price is still positioned inside rails. Cadence of the bands is monthly/quarterly; daily SDCA must not pretend the band moved today. |
| C. Metric-as-z (CAPE percentile → z, skip price) | New protocol `valuation_z(dates)` | No | **Do not add a sibling protocol in v1.** Composite risk already accepts any z-series via `IndicatorWeight`. If we ever want CAPE-as-z, it is an *indicator*, not a new `RiskModel`. |

**Recommendation:** keep `RiskModel`. If index SDCA is built later, implement approach **B** (implied
price rails from CAPE or ERP) plus HY OAS as a second `IndicatorWeight`, mirroring M2’s vote rather
than stuffing credit into the rails. Do not copy `BtcPowerLawRiskModel` onto SPY.

A daily decision reading a quarterly series must hold the last *published* band constant through the
quarter and size trades off *price vs that frozen band* (plus the daily credit overlay). That is
honest; interpolating GDP across days is not.

## Cadence mismatch and point-in-time

| Hazard | What goes wrong | How to avoid |
|---|---|---|
| GDP / market-cap revisions | BEA restates GDP for years. A 2026 vintage of 2009-Q1 GDP is not what was on the tape in 2009. | ALFRED: for each as-of date `d`, fetch observations with `realtime_start=d&realtime_end=d`. The existing ingest stores `meta.realtime_start` but does not *request* vintages — extend `fetch_fred_series` if this ever becomes production. |
| Earnings lag | CAPE’s E10 includes reports that were not out on day 1 of the month. | Use CAPE as of month-end *minus a lag* (two months is conservative). Never peek at a restated E. |
| COVID denominator | Nominal GDP fell in 2020-Q2; Buffett = cap / GDP **rose** in the official quarterly print (`NCBEILQ027S/GDP` ≈ 129% in 2020-Q1 → **173% in 2020-Q2** on current vintage). A Buffett-driven SDCA would have read “more expensive” through the crash. | Do not use Buffett as a daily or even intra-quarter signal. If used at all, pair with a high-frequency spread and treat GDP as a *regime prior* updated on release dates only. |
| `digiquant_get_macro_series` | Returns the last `lookback` ingested rows from Supabase — operator diagnostic, not a PIT backtest feed. | Backtests must read a vintage-aware store, not this MCP tool. |
| FRED graph CSV | Convenient, no API key, **current vintage only**, and some ICE series truncate to ~3 years without a key. | Fine for a spike; not a production path. Production stays `fetch_fred` + `FRED_API_KEY`. |

## Historical plausibility (2000 / 2009 / 2020 / 2021)

Numbers below are **current-vintage** (the spike’s own warning). CAPE from Shiller `ie_data.xls`
through 2023-09. Buffett = `(NCBEILQ027S / 1000) / GDP * 100` from FRED graph CSVs fetched
2026-08-30. ERP ≈ `100/CAPE − DGS10` on the nearest 10y close. Percentiles are of the full available
history of that series (CAPE from 1881; Buffett from 1947-Q4).

| Event | CAPE | CAPE pctile (full / 50y trail) | Buffett % | Buffett pctile | 10y % | ERP (pp) | Would a *slow valuation* SDCA accumulate / distribute? |
|---|---:|---:|---:|---:|---:|---:|---|
| 2000-03 (dot-com high) | 43.22 | 99.8 / 99.5 | 163 (Q1) | 93 | 6.20 | **−3.9** | **Distribute.** Both CAPE and ERP agree. |
| 2009-03 (GFC low) | 13.32 | 31.5 / 24.5 | 69 (Q1) | 46 | 2.89 | **+4.6** | **Weak accumulate.** CAPE is cheap vs 2000, not vs 1982. Buffett is only median. ERP is the cleanest “cheap” signal. |
| 2020-03 (COVID low) | 24.82 | **85.1 / 66.7** | 129 (Q1) then **173 (Q2)** | 82 → 94 | 0.76 | **+3.3** | **CAPE/Buffett miss.** A long-run CAPE-percentile rail would still be in a “rich / above mid” band. ERP is the metric that flips to cheap because yields collapsed. HY OAS (not fully re-fetched here; ICE graph CSV was last-3-years without a key) is the fast confirmation — March 2020 is a known ~11% print vs ~3% in 2021. |
| 2021-12 (post-COVID high) | 38.30 | 98.5 / 95.8 | 219 (Q4) | 99 | 1.52 | **+1.1** | **Distribute on CAPE/Buffett.** ERP is only mildly rich because yields were still low — a CAPE-only reader is more aggressive here than an ERP reader. |

**Honest result:** the owner’s test is only half-passed.

- Tops (2000, 2021): a slow US-equity valuation metric **would** have been in a distribute region.
- 2009: it would have been *less greedy*, not a fire-sale accumulate, unless ERP (or credit) is in
  the composite.
- 2020: **CAPE-driven SDCA would not have bought the dip.** That is the finding, not a footnote.
  A crypto-style “price vs long-run corridor” is exactly the mapping that fails here, because the
  corridor (CAPE’s own history) still said “expensive” while the *rate-aware* gap said “cheap” and
  the *credit* gap said “panic.”

So if index SDCA is ever built, the composite must include a rate-aware or credit leg. CAPE-only is
not a strategy; it is a secular-valuation overlay.

## Which assets

| Universe | Viable? | Why |
|---|---|---|
| SPY / VTI (broad US) | Plausible **after** a follow-up that solves PIT + composite (CAPE/ERP + HY OAS) | One CAPE, one Buffett, one 10y, one HY series. Same rails for the index and for an ETF that tracks it. |
| Other developed index ETFs (EFA, VXUS) | Later | Need local CAPE / local rates / local credit. FRED coverage is US-centric. |
| Single stocks | **No for v1 or v2** | Per-name PE, point-in-time fundamentals, delistings. Not a `RiskModel` swap; it is a data platform. |

Recommend the boundary: **US broad-index ETFs only**, and not until the 2020 miss is addressed in
the design (ERP and/or HY OAS in the composite, ALFRED for GDP).

## Existing wiring to reuse (no new production code here)

- FRED ingest: `digiquant/src/digiquant/data/prices/macro_ingest.py` (`fetch_fred`,
  `FRED_OBS_URL`). Manifest: `digiquant/src/digiquant/olympus/atlas/config/macro_series.yaml`
  already lists `DGS10` and `BAMLH0A0HYM2`.
- Operator read: MCP `digiquant_get_macro_series` → Supabase `macro_series_observations`
  (latest window, not vintages).
- Composite pattern: `strategies/sdca/composite_risk.py` (`IndicatorWeight` +
  `compute_composite_risk`) and M2’s `indicators/m2_signals.py` vote. Equity SDCA should add
  indicators here, not a second engine.
- Crypto-side analogue: on-chain valuation is [#1086](https://github.com/digithings-ai/digithings/issues/1086),
  equally “do not cargo-cult the BTC power law.”

## Recommended issues (not filed this session)

`gh` is read-only in this environment. Do **not** treat these as filed. Copy into GitHub only if
the owner agrees after reading the 2020 result.

### Do not file

- Equity `RiskModel` / `spy_sdca` / `vti_sdca` settings entries as part of SDCA v1.
- Single-stock SDCA.
- Put/call as a rail.
- Applying `BtcPowerLawRiskModel` (or #3175’s generic log-time fit) to SPY.

### Optional later — infrastructure, not a strategy

```text
Title: [agent] ALFRED-vintage option on FRED ingest (GDP and slow macros)

Goal: fetch_fred_series can request realtime_start=realtime_end=as_of so a backtest never
sees a revised GDP figure that did not exist on that date. Store vintage in
macro_series_observations.meta (realtime_start is already a field). Do not change the
default daily ingest’s “latest vintage” behaviour until a consumer needs PIT.

Out of scope: any SDCA strategy, any new FRED series.
```

### Optional later — only if the owner still wants index SDCA

```text
Title: [agent] Index SDCA for SPY/VTI — implied-price rails from CAPE/ERP + HY OAS overlay

Depends on: ALFRED ingest (above), SDCA v1 crypto path already published.

Design constraints from docs/research/equity-valuation-for-sdca.md:
- RiskModel approach B (implied fair-price bands), never a time-power-law of SPY.
- Composite must include a rate-aware or credit leg; CAPE-only failed March 2020.
- Publication lag on CAPE; GDP/Buffett is a regime prior, not a daily rail.
- Universe: SPY/VTI only.

Acceptance: a historical check (PIT) that reports 2000 / 2009 / 2020 / 2021 honestly,
including a miss if it still misses.
```

## Session evidence

- FRED graph CSV (no API key): `GDP` 1947-01-01–2026-04-01; `NCBEILQ027S` 1945-10-01–2026-01-01;
  `DGS10` 1962-01-02–2026-08-27; `DDDM01USA156NWDB` 1975–2020 only; `BAMLH0A0HYM2` truncated to
  2023-08-29–2026-08-27 without a key; `SP500` on FRED is a ~10-year licensed window.
- `FRED_API_KEY` was unset in this environment; production ingest remains the right full-history
  path.
- Shiller `ie_data.xls` fetched from `http://www.econ.yale.edu/~shiller/data/ie_data.xls` (HTTP 200,
  last saved 2023-09-17). Event CAPE values in the table are from the `Data` sheet column “P/E10 or
  CAPE.”
