---
name: market-crypto
description: Run crypto market analysis as part of the daily digest. Covers BTC, ETH, major alts, on-chain signals, sentiment, and key levels. In the orchestrator, run as Phase 4D — reads macro regime and institutional ETF flow data from BTC spot ETFs (IBIT/FBTC).
---

# Crypto Analysis Skill — v2

## Inputs
- `config/watchlist.md` (crypto section)
- `config/preferences.md`
- Macro regime output (risk-on/off affects crypto)
- Institutional flows output (IBIT/FBTC daily flow data)

## Data Layer

> DB-first: read crypto levels from Supabase (`daily_snapshots.market_data` / `documents.payload`).

For richer crypto data use MCP tools:
- **Fear & Greed Index**: `mcp_crypto-feargr_get_current_fng_tool` (current value) · `mcp_crypto-feargr_analyze_fng_trend` (trend over N days) · `mcp_crypto-feargr_get_historical_fng_tool` (historical values)
- **Market data / altcoins / DeFi**: `mcp_coingecko_execute` — call CoinGecko API:
  - Prices: `GET /simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true&include_market_cap=true`
  - Market overview: `GET /coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20`
  - Trending: `GET /search/trending`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any crypto news article, narrative piece, on-chain data page, or regulatory filing URL. Not for API endpoints, `.json`, or `.md` files.

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
- Fear & Greed Index level and trend
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

```
### 🪙 CRYPTO
**Bias**: [Bullish / Bearish / Neutral / Conflicted]

**BTC**: [$price | 24h: X% | Key level: ...]
**ETH**: [$price | 24h: X% | ETH/BTC: ...]

**Market Structure**: [Dominance, market cap, phase]

**Sentiment**: [Fear & Greed: X | Funding: ... | OI: ...]

**Watchlist Alts**: [Notable moves + catalyst if any]

**Macro Correlation**: [Correlated / Decorrelated + implication]

**BTC ETF Flows**: IBIT: ±$Xm | FBTC: ±$Xm | Net: [accumulation/distribution]

**Stablecoin Signal**: Total supply $X | [Growing/Shrinking] → [dry powder / deployed]

**BTC/NASDAQ Correlation**: X.XX (90d) — [Correlated risk asset / Decorrelated SoV]

**Active Narratives**: [Top 1-2 themes]

**Watch**: [Key level or event to track]
```

