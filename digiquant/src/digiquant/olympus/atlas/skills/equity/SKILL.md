---
name: market-equity
description: Run US equity market overview analysis. In the orchestrator pipeline, run as Phase 5A — establishes the market-wide read (breadth, indices, factors). Sector deep-dives are handled separately by 11 sector sub-agent skills. International equities are handled by `skills/international/SKILL.md`.
---

# US Equities Overview Skill — v2

## Inputs
- `config/watchlist.md` (equity section)
- `config/preferences.md`
- Macro regime output (anchors all analysis)
- CTA positioning output (systematic equity direction)
- Institutional flows output (ETF in/outflows)
- Options output (GEX, VIX level, P/C ratio)

## Data Layer

> **Read before analysis** — these files contain systematic technicals for all ~60 watchlist tickers.
> Use them as the authoritative price and technical source. Web-search only for qualitative context.

1. DB-first: use Supabase `price_history` + `price_technicals` as the authoritative source for prices/technicals.
   - **Current prices and 1D%** for every watchlist ticker — do NOT web-browse individual prices
   - **Trend** (UPTREND / DOWNTREND / NEUTRAL) — pre-classified from SMA50/200 relationship
   - **RSI(14)** — overbought (≥70 ⚠️) / oversold (≤35 🟡) flags already shown
   - **MACD signal** — BULLISH_CROSS / BEARISH_CROSS / BULLISH / BEARISH
   - **vs SMA50 / vs SMA200** — ✅/❌ flags already computed
   - **Volume ratio** — >1.3× = elevated volume; useful for confirming moves
   - **ATR(14)** — dollar volatility measure for position sizing context
   - **Overview Buckets** at the top — immediate UPTREND / MIXED / DOWNTREND count

2. In the **Technicals** step, quote numbers directly from the data file.
   No need to search for SPY/QQQ/IWM levels — they are in the table.

3. **Web search for** (not in the data files):
   - Earnings reactions, guidance, analyst actions
   - News catalysts behind notable movers
   - Market breadth indicators (A/D line, 52W H/L, % above 200DMA) — check Finviz/Barchart
   - McClellan Oscillator, breadth divergences
   - Sector ETF flows (not price — ETF.com for flow data)

> DB-first: do not require `data/agent-cache/daily`. If you need refreshed numbers, run `./scripts/fetch-market-data.sh` (writes legacy archive summaries) or use MCP sources.
> If that fails (sandbox), follow `skills/mcp-data-fetch/SKILL.md` for MCP-based data fetch.
> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any news article, breadth site, earnings page, or analyst note URL. Not for API endpoints, `.json`, or `.md` files.

## Research Steps

### 1. Index Overview
Search for current levels and % change for:
- S&P 500 (SPY), NASDAQ 100 (QQQ), Russell 2000 (IWM), Dow (DIA)
- Note if any index is testing key technical levels (52-week high/low, major MA, prior resistance)

### 2. Sector Rotation
Check performance of all 11 S&P sectors (XLK, XLF, XLE, XLV, XLI, XLRE, XLU, XLY, XLP, XLB, XLC).
- Which sectors are leading and lagging TODAY?
- What does sector rotation imply about risk appetite? (e.g., XLU/XLP leading = defensive rotation)
- Is this consistent with recent rotation from prior outputs or a change?

### 3. Watchlist Movers
For each equity in the user's watchlist:
- Any notable % move today?
- Any news, earnings, analyst actions, or catalysts?
- Any approaching key technical levels?

### 4. Earnings Calendar
- What major earnings are reported today or after close?
- Any major earnings tomorrow pre-market?
- Note any earnings that could have sector-wide read-throughs

### 5. Market Breadth (Advanced)
- NYSE Advance/Decline line: rising or falling vs index?
- New 52W highs vs new 52W lows: is the market broadening or narrowing?
- % of S&P 500 stocks above 200-DMA: >70% = healthy; <50% = narrow leadership
- % of S&P 500 stocks above 50-DMA: momentum breadth
- McClellan Oscillator or summation if available
- A/D divergence: if index makes new high but A/D doesn't → bearish divergence

### 6. Factor Performance Today
- **Value** (VTV, IVE): outperforming or underperforming growth?
- **Growth** (VUG, IVW): risk-on or risk-off signal
- **Momentum** (MTUM): is momentum factor working or reversing?
- **Quality** (QUAL): defensive quality premium expanding or shrinking?
- **Small Cap** (IWM) vs **Large Cap** (SPY): risk appetite signal
- **Dividend/Income** (VYM, DVY): safe haven demand?
- Factor read: what does today's factor performance say about regime and risk appetite?

### 7. Technicals (Market-Wide)
- Is the broad market in an uptrend, downtrend, or consolidation?
- VIX level (from options output) — cross-reference
- Any notable divergences (e.g., index at highs but breadth deteriorating)
- Key support/resistance for SPY: 50-DMA, 200-DMA, prior swing lows/highs

**Note**: International equities are covered in full by `skills/international/SKILL.md`. Only note overnight DM performance here for context.

## Output Format

```
### 📈 EQUITIES
**Bias**: [Bullish / Bearish / Neutral / Conflicted]

**Index Levels**: [SPY, QQQ, IWM — price, % change, key level notes]

**Sector Rotation**: [Leading: ... | Lagging: ... | Implication: ...]

**Watchlist Movers**: [Notable moves with brief reason]

**Earnings Today**: [Key names + reaction if available]

**Technical Read**: [Trend, VIX, breadth summary]

**Market Breadth**: A/D: [X:X] | 52W H/L: [X/X] | % above 200D: X% | [Healthy/Narrow/Deteriorating]

**Factor Read**: [Leading: Value/Growth/Momentum/Quality | Lagging: which] | [Risk-on or defensive rotation?]

**Watch**: [1-2 things to monitor in next 24-48h]

**Note**: Full sector-by-sector analysis in sector sub-agent outputs. International in international.md.
```

