---
name: market-crypto
description: Run crypto market analysis as part of the daily digest. Covers BTC, ETH, major alts, on-chain signals, sentiment, and key levels. In the orchestrator, run as Phase 4D — reads macro regime and institutional ETF flow data from BTC spot ETFs (IBIT/FBTC).
---

# Crypto Analysis Skill — v2

## Grounding Tools (use first)

- **`get_price_technicals`** — your primary grounding. For each ticker/ETF in scope
  (your watchlist and any `sector_config` / asset-class symbols in PHASE_INPUTS), call
  `get_price_technicals(ticker="<SYMBOL>", lookback=20)`
  before asserting trend, momentum, or relative strength. The response carries the recent
  computed indicators (sma/rsi/macd/adx/atr/zscore), newest first — use those
  values; **never invent a number** — every quantitative claim must cite a value you fetched.
  If a call returns no rows for a symbol, say so and lower conviction. Market history is not
  readable through `query_research` (#3780) — never use it to fetch prices or technicals.
- Cover the crypto proxies in scope; use the pre-fetched **`web_grounding`** block (when present) for 24/7 spot moves not in the daily series.

## Inputs
- `config/watchlist.md` — repository provenance for a maintainer (crypto section); NOT retrievable by a tool.
- `config/preferences.md` — repository provenance for a maintainer; NOT retrievable by a tool.
- Macro regime output (risk-on/off affects crypto)
- Institutional flows output (IBIT/FBTC daily flow data)

## Data Layer

> DB-first: read crypto levels from Supabase (`daily_snapshots.market_data` / `documents.payload`).

There is no MCP client and no CoinGecko tool in this loop. Read crypto levels from the
ingested layer (`daily_snapshots.market_data`) with your data tools
(`get_price_technicals(ticker="BTC-USD")`, `get_macro_series`) and from the
`web_grounding` block when one is provided.

- **Fear & Greed Index**: not ingested daily (issue #328). Only report it if the
  `web_grounding` block states it; otherwise omit it. Do not search for it.

---

## Research Steps

### 1. BTC & ETH Core Read
- Current price and 24h % change
- Distance from key levels: recent highs/lows, round numbers, prior support/resistance
- Volume: is volume confirming the move or diverging?
- Is BTC leading or lagging ETH? (ETH/BTC ratio direction)

### 2. Market Structure
- Total crypto market cap and 24h change
- Bitcoin dominance (BTC.D) — rising or falling? (implication for alt season)
- Fear & Greed Index level and trend — only if the `web_grounding` block states it; otherwise omit
- Is the market in a bull/bear/consolidation phase structurally?

### 3. Watchlist Alts
For each alt in watchlist:
- Price, 24h change
- Any protocol news, upgrades, token events, listings, or liquidations
- Outperforming or underperforming BTC?

### 4. Sentiment & On-Chain (search for available signals)
- Funding rates on perpetuals (positive = longs paying, negative = shorts paying)
- Open interest direction
- Any major liquidation events in last 24h
- Exchange inflows/outflows if notable
- Social sentiment / trending narratives

### 5. BTC Spot ETF Institutional Flows (Critical)
- **IBIT** (BlackRock): daily creation/redemption flow — largest institutional BTC vehicle
- **FBTC** (Fidelity): daily flow
- Combined daily BTC ETF flow: net positive = institutional accumulation; net negative = institutional distribution
- Cumulative flows since inception: context for structural demand
- IBIT options: any notable institutional hedging or speculation?
- Is institutional Bitcoin adoption accelerating or stalling based on flow trend?

### 6. Stablecoin Market Signal
- Total stablecoin market cap direction: growing = dry powder accumulating; shrinking = deployed or exiting
- USDT, USDC supply trends
- Stablecoin dominance: rising = capital waiting on sidelines (cautious); falling = deploying into risk

### 7. Macro-Crypto Correlation
- Is crypto moving with or against equities / risk assets today?
- BTC/NASDAQ 90-day rolling correlation: near 1.0 = correlated risk asset; near 0 = decorrelated store of value
- Any macro triggers driving crypto (Fed, dollar, risk-off)?
- Does crypto's correlation today reinforce or break the recent trend?

### 8. Key Narratives
- What are the dominant crypto narratives right now? (e.g., BTC ETF institutional flows, ETH staking yields, Solana ecosystem, L2s, AI tokens, RWA, etc.)
- Any breaking news in crypto space?
- Any regulatory development (SEC, CFTC, global regulation)?

## Output Format

Write a markdown `body`. Suggested skeleton (skip empty sections). Inline [title](url) citations. Do **not** invent scores, a Signals section, or print `Bias:` at the top.

```markdown
# Crypto — {as-of date of the data}

## BTC and ETH
Price, key levels, dominance — dated.

## Flows and structure
ETF flows, funding, stablecoin supply if retrieved.

## Macro correlation
Risk-asset vs store-of-value read for today's research.
```
