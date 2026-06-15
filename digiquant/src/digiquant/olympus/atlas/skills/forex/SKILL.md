---
name: market-forex
description: Run forex and currency analysis as part of the daily digest. Covers DXY, major pairs, EM currencies, carry trades, and FX as a risk sentiment signal. In the orchestrator, run as Phase 4C — output (DXY direction) feeds into international, commodities, and materials analysis.
---

# Forex Analysis Skill — v2

## Grounding Tools (use first)

- **`query_data`** — your primary grounding. For each ticker/ETF in scope (your watchlist and
  any `sector_config` / asset-class symbols in PHASE_INPUTS), call
  `query_data(table="price_technicals", columns="date,sma_50,sma_200,pct_vs_sma50,pct_vs_sma200,rsi_14,macd_hist,roc_21,adx_14,atr_pct,bb_pct_b,zscore_200", eq={"ticker": "<SYMBOL>"}, order="date", desc=true, limit=20)`
  before asserting trend, momentum, or relative strength. Pass that exact `columns` list so you
  fetch only the indicators you need (not all 35+ columns). Use the returned
  sma/rsi/macd/adx/atr/zscore values; **never invent a number** — every quantitative claim must
  cite a value you fetched. If a call returns no rows for a symbol, say so and lower conviction.
  Need raw prices? `query_data(table="price_history", columns="date,open,high,low,close,volume", eq={"ticker": "<SYMBOL>"}, order="date", desc=true, limit=30)`.
- Also **`get_macro_series`** for `DTWEXBGS` (broad USD index) to anchor the dollar view.

## Inputs
- `config/watchlist.md` (forex section)
- `config/preferences.md`
- Macro regime output
- Bonds output (rate differentials drive FX)

## Data Layer

> DB-first: read FX levels from Supabase `macro_series_observations` (series IDs `FX/EUR`, `FX/GBP`, `FX/JPY`, `FX/CAD`; `source = "yahoo"`; `meta.quote_convention` documents direction — `USD_per_EUR`, `USD_per_GBP`, `JPY_per_USD`, `CAD_per_USD`). Daily-snapshot consolidations also surface in `daily_snapshots.market_data` / `documents.payload`.

For live or intraday rates that have not yet been snapshotted, query the same Yahoo Finance symbols directly (`EURUSD=X`, `GBPUSD=X`, `JPY=X`, `CAD=X`) — the underlying provider for the daily feed.

For richer FX context (cross-rates, historical comparisons over arbitrary windows, or pairs not in the daily watchlist), pull the relevant central bank statement or FT/Reuters article via web fetch and read the published rate alongside.

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any central bank statement, geopolitical news article, or FX analysis page URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. US Dollar (DXY)
- DXY level and 24h change
- Is the dollar strengthening or weakening?
- Key technical level: is it above or below 200-day MA? Near recent highs/lows?
- Dollar direction is the master variable for commodities, EM equities, and risk assets

### 2. Major Pairs
For each pair in watchlist:
- EUR/USD: price, direction, key ECB/Fed divergence driver
- USD/JPY: level, any BOJ intervention risk, carry implications
- GBP/USD: UK macro, any political or data driver
- USD/CAD: oil correlation, any CAD-specific catalyst
- AUD/USD: China proxy, commodity currency

### 3. Risk Sentiment from FX
- AUD/USD and NZD/USD rising = risk-on signal
- USD/JPY rising without yen intervention = carry risk-on
- Safe haven demand: JPY, CHF appreciating = risk-off
- EM currencies: strengthening = global risk appetite
- Summarize: what is FX collectively saying about risk sentiment?

### 4. Carry Trade Watch
- Is the yen carry trade under stress? (rapid USD/JPY moves can cause cross-asset liquidation)
- Any sudden JPY strengthening that could ripple into equities/crypto?

### 5. EM FX Stress Monitor
- **DXY and EM currencies**: strong DXY → EM capital outflows → EM currency weakness
- Key EM FX pairs: USD/BRL, USD/TRY, USD/ZAR, USD/MXN — any stress?
- EM FX Volatility Index (EMVX) if available
- Any country-specific EM currency crisis risk?
- USD/CNH (offshore yuan): PBOC fixing vs market rate — any significant divergence indicating stress?

### 6. Real Effective Exchange Rates (REER)
- USD REER: Is the dollar overvalued or undervalued on a trade-weighted, inflation-adjusted basis?
- Overvalued USD REER = headwind for US multinational earnings (currency effect on overseas revenues)
- EUR REER, JPY REER: any currency that is dramatically mis-valued creating regime risk?

### 7. Canadian Dollar (if relevant)
- USD/CAD level
- Oil correlation holding? (At $112 WTI, CAD should be strong)
- Any Bank of Canada signals or Canada-specific macro events?

## Output Format

```
### 💱 FOREX
**DXY**: [Level (±X%) | Trend: strengthening/weakening | Key level: ...]

**Key Pairs**:
- EUR/USD: X.XXXX (±X%) | [driver]
- USD/JPY: XXX.XX (±X%) | [driver / intervention risk?]
- GBP/USD: X.XXXX (±X%) | [driver]
- USD/CAD: X.XXXX (±X%) | [oil/BoC driver]

**EM FX Stress**: [Any EM currency crisis signal | USD/CNH fixing vs market]

**FX Risk Signal**: [Risk-on / Risk-off / Mixed — rationale]

**Carry Watch**: [Yen carry stable/stressed | implication for risk assets]

**USD REER**: [Over/undervalued — implication for US multinational earnings]

**Watch**: [Key FX event or level to monitor]
```

