---
name: institutional-flows
description: Tracks daily ETF in/outflows, dark pool and block trade prints, short interest changes, and new 13D/13G SEC filings. Reveals where institutional money is actually moving — ahead of price. Run in the Institutional Intelligence phase.
---

# Institutional Flows Sub-Agent

## Purpose
Follow the smart money. ETF flows reveal institutional sector rotation in real-time. Dark pool prints and block trades reveal large-scale repositioning that hasn't hit the tape at full size yet. 13D/13G filings reveal activist entries and large fund position changes. Run before macro and segment analysis.

## Inputs
- `docs/ops/data-sources.md` (ETF flow sources, block trade sources, EDGAR links)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any ETF flow page, EDGAR filing, block trade site, or news article URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. ETF Daily Flow Scan
Scan daily ETF in/outflow data for priority ETFs (portfolio holdings, benchmarks, sectors, gold/oil, TLT/BIL/HYG, EEM/MCHI/EWJ).

### 2. Dark Pool & Block Trade Scan
Scan for notable block prints / elevated dark pool volume.

### 3. Short Interest Changes
Scan for notable short interest changes, especially in holdings.

### 4. SEC EDGAR 13D / 13G Filings (Last 7 Days)
Scan for new 13D/13G filings relevant to watchlist sectors.

### 5. Options-Flow / Institutional Derivatives Positioning
Cross-reference with options intelligence.

### 6. Fund Flows to Asset Classes (Macro-Level)
Weekly fund flow scan if available.

---

## Output Format

```
### 🏦 INSTITUTIONAL FLOWS INTELLIGENCE
**Net Institutional Direction**: [Risk-On / Risk-Off / Neutral / Rotating]

**Top ETF Flows Today:**
| ETF | Category | Flow ($M) | vs Avg | Signal |
|-----|----------|-----------|--------|--------|
| IBIT | BTC Spot | +$XXXm | [above/below avg] | BTC accumulation |

**Notable Sector Rotation via Flows:**
- Into: [sectors]
- Out of: [sectors]

**Dark Pool / Block Trades:**
- [notes]

**Short Interest Update:**
- [notes]

**SEC 13D/13G Filings (Last 7 Days):**
- [notes]

**Fund Flow Macro Signal:**
- Money market level: $X trillion | [Rising/Falling]

**Implication for Portfolio:**
[2-3 sentences]
```

