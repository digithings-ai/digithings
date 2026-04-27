---
name: market-bonds
description: Run bond market and interest rates analysis as part of the daily digest. Covers Treasury yields, yield curve, inflation breakevens, TIPS real yields, credit spreads, Fed expectations, and bond ETFs. Run as Phase 4A — output feeds into commodities, forex, REITs, and utilities analysis.
---

# Bonds & Rates Analysis Skill — v2

## Inputs
- `config/watchlist.md` (bonds section)
- `config/preferences.md`
- Macro regime output (rate path context)

## Data Layer

> DB-first: read the latest relevant snapshot data from Supabase (`daily_snapshots.snapshot` / `documents.payload`).

Supplement with `mcp_fred_*` tools for data not in the fetch files:
- **TIPS breakevens**: `mcp_fred_fred_series_observations` with `T10YIE` (10Y), `T5YIE` (5Y)
- **Real yields**: series `DFII10` (10Y TIPS real yield)
- **Credit spreads**: `BAMLH0A0HYM2` (HY OAS), `BAMLC0A0CM` (IG OAS)
- **Fed Funds**: `DFF` for current effective rate
- **5Y5Y forward**: `T5YIFR`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any Fed speech, credit market article, or sovereign debt news page URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Treasury Yields
- Current levels for: 2Y, 5Y, 10Y, 30Y
- Daily change in bps for each
- Are yields rising or falling? What's the catalyst?
- Which part of the curve is moving most?

### 2. Yield Curve Shape
- 2s10s spread: inverted / flat / steepening / normalized?
- Is the curve steepening or flattening? (bull or bear steepener/flattener?)
- Historical context: how does the current spread compare to recent weeks?
- What does the curve shape imply for recession risk / growth expectations?

### 3. Fed Watch
- Current Fed Funds Rate
- CME FedWatch: next meeting probabilities (cut / hold / hike)
- Any recent Fed speaker commentary
- Next FOMC date and whether it's a "live" meeting
- Where is the market pricing the terminal rate?

### 4. Credit Markets
- HYG (high yield) and LQD (investment grade) — price and spread direction
- HY OAS (option-adjusted spread) — tightening or widening?
- Spread direction implies: risk-on (tightening) or risk-off (widening)

### 5. Inflation Expectations & Real Yields (Expanded)
- **TIPS** (iShares TIPS Bond ETF): price and direction
- **5Y breakeven inflation rate**: current level vs prior week — is market pricing more or less inflation?
- **10Y breakeven**: direction — critical for gold and commodity thesis validation
- **10Y TIPS real yield**: nominal 10Y minus 10Y breakeven
  - Positive real yield: headwind for gold and growth stocks
  - Negative real yield: tailwind for gold, commodities, and inflation hedges
  - Current level and direction vs last 30 days
- **5Y5Y forward inflation swap**: where does the market expect inflation 5-10 years out?

### 5B. Credit Quality Migration
- IG credit: any notable downgrades from investment grade to high yield (fallen angels)?
- HY credit: any upgrades from HY to IG (rising stars)?
- Leveraged loan market: CLO formation pace, default rates
- Distressed debt ratio: % of HY bonds at spread >1000bps

### 5C. Sovereign Spread Monitor
- Italy/Greece (peripheral Eurozone) spreads vs German Bund: widening = EU stress
- UK Gilts vs German Bund: any UK fiscal credibility risk?
- EM sovereign spreads (EMBI spread): reference EMB output from international analysis
- Japan JGB 10Y: any BOJ yield control adjustment?

### 6. Watched ETFs
- TLT, IEF: price action and trend
- MOVE index (bond market volatility)

## Output Format

```
### 🏦 BONDS & RATES
**Bias**: [Bullish bonds (yields falling) / Bearish bonds (yields rising) / Neutral / Conflicted]

**Yields**: [2Y: X% | 10Y: X% | 30Y: X% | Daily Δ: ...]
**Curve**: [2s10s: Xbps | Shape: steepening/flattening/inverted | Implication: ...]

**Fed**: [Funds rate: X% | Next meeting: date | Market pricing: X% cut prob]

**Credit**: [HY spreads: tightening/widening | Signal: risk-on/off]

**Inflation / Real Yields**:
- 10Y Breakeven: X.XX% | Direction: [rising/falling]
- 10Y TIPS Real Yield: X.XX% | [Positive = headwind / Negative = tailwind for gold+commodities]
- 5Y Breakeven: X.XX%

**Credit**: HY spreads [tightening/widening at Xbps] | IG: [Xbps] | Signal: [risk-on/off]

**Sovereign Stress**: [Italy/periphery spread | EM sovereign | Any stress flag]

**TLT / IEF**: [Price, trend, key level]

**Watch**: [Upcoming Treasury auction, Fed speak, or inflation print that could move rates]
```

