---
name: alt-data-politician-signals
description: Tracks US Congressional STOCK Act trade disclosures, key committee chair policy positions, Fed Chair and Treasury Secretary public statements, and regulatory agency signals. Both follow-the-money (what politicians are buying/selling personally) and policy positioning. Runs early in pipeline.
---

# Politician & Official Signals Sub-Agent

## Grounding Tools (use first)

- **Web grounding (pre-fetched)** — this segment has no maintained Supabase series. A
  `web_grounding` block (a cited web/news/X summary over curated domains incl. reuters.com,
  apnews.com, sec.gov, cftc.gov, treasury.gov, capitoltrades.com, finance.yahoo.com) is
  provided in PHASE_INPUTS when available; ground on it and carry its source URLs for congressional trades (capitoltrades.com) and Fed / Treasury official signals. into the `sources` field; if no `web_grounding` is present, say so and lower conviction.

## Purpose
Politicians and regulators move markets — both through what they buy/sell personally and through policy signals. STOCK Act disclosures are legally required to be filed within 45 days of a trade and are public record. Committee chair rhetoric directly moves sector-specific ETFs. Run early in pipeline.

## Inputs
- `docs/ops/data-sources.md` (sources for congressional trading + official statements)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any Capitol Trades, Quiver Quantitative, EDGAR filing, agency website, or news article URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. STOCK Act Trade Disclosures (Past 7 Days)
Search Quiver Quantitative or Capitol Trades for congressional trades disclosed in the past 7 days.

### 2. Recent Policy Position Statements
Scan Treasury, Fed, SEC/CFTC/FDIC/OCC, and relevant executive agencies for last-48h market-moving statements.

### 3. Geopolitical Official Statements
Scan official updates for any active conflicts relevant to markets.

### 4. Tariff & Trade Actions
Scan for new trade/tariff policy actions.

### 5. Regulatory Actions Affecting Watchlist
Flag actions impacting portfolio sectors (energy, healthcare, financials, crypto).

---

## Output Format

```
### 🏛️ POLITICIAN & OFFICIAL SIGNALS

**Congressional Stock Trades (Last 7 Days):**
| Member | Party | Buy/Sell | Ticker | Amount | Committee | Signal |
|--------|-------|----------|--------|--------|-----------|--------|
| [Name] | [R/D] | BUY | [XXX] | [$X-Xk] | [Finance] | [comment] |

**Net Congressional Positioning:**
- Net buyers: [sectors/tickers]
- Net sellers: [sectors/tickers]

**Fed & Treasury Signals:**
- Powell: [statement + read]
- Treasury: [signal]

**Geopolitical / Trade / Regulatory**:
- [Item]: [what changed]

**Implication for Portfolio:**
[2-3 sentences: what do official signals imply?]
```

