---
name: market-forex
description: Run forex and currency analysis as part of the daily digest. Covers DXY, major pairs, EM currencies, carry trades, and FX as a risk sentiment signal. In the orchestrator, run as Phase 4C — output (DXY direction) feeds into international, commodities, and materials analysis.
---

# Forex Analysis Skill — v2

## Grounding Tools (use first)

- **`get_price_technicals`** — your primary grounding. For each ticker/ETF in scope
  (your watchlist and any `sector_config` / asset-class symbols in PHASE_INPUTS), call
  `get_price_technicals(ticker="<SYMBOL>", lookback=20)`
  before asserting trend, momentum, or relative strength. The response carries the recent
  computed indicators (sma/rsi/macd/adx/atr/zscore), newest first — use those
  values; **never invent a number** — every quantitative claim must cite a value you fetched.
  If a call returns no rows for a symbol, say so and lower conviction. Market history is not
  readable through `query_research` (#3780) — never use it to fetch prices or technicals.
- Also **`get_macro_series`** for `DTWEXBGS` (broad USD index) to anchor the dollar view.

## Inputs
- `config/watchlist.md` — repository provenance for a maintainer (forex section); NOT retrievable by a tool.
- `config/preferences.md` — repository provenance for a maintainer; NOT retrievable by a tool.
- Macro regime output
- Bonds output (rate differentials drive FX)

## Data Layer

> DB-first: read DXY and FX levels from published `daily_snapshots.market_data` / `documents.payload` (web for fresh intraday). Anchor the dollar view with `get_macro_series` (`DTWEXBGS`, and `DGS10` / `DGS2` for rate differentials). The per-pair Yahoo feed (`EURUSD=X` → `FX/EUR`, `GBPUSD=X` → `FX/GBP`, `JPY=X` → `FX/JPY`, `CAD=X` → `FX/CAD`; directions `USD_per_EUR`, `USD_per_GBP`, `JPY_per_USD`, `CAD_per_USD`) is not part of the injected `market_context` macro block — read the pairs from the snapshot payload; market history is not readable through `query_research` (#3780).

For live or intraday rates that have not yet been snapshotted, query the same Yahoo Finance symbols directly (`EURUSD=X`, `GBPUSD=X`, `JPY=X`, `CAD=X`) — the underlying provider for the daily feed.

For richer FX context (cross-rates, historical comparisons over arbitrary windows, or pairs not in the daily watchlist), use the `web_grounding` block's central-bank and FT/Reuters coverage when it is provided; if it is absent, state that the context is unavailable.

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

Write a markdown `body`. Suggested skeleton (skip empty sections). Inline [title](url) citations. Do **not** invent scores, a Signals section, or print `Bias:` at the top.

```markdown
# Forex — {as-of date of the data}

## Dollar
DXY level, trend, key level.

## Major pairs
EUR, JPY, GBP, CAD with the driver.

## EM and carry
Stress flags and yen-carry implications for risk assets.
```
