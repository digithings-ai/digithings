---
name: institutional-flows
description: Tracks daily ETF in/outflows, dark pool and block trade prints, short interest changes, and new 13D/13G SEC filings. Reveals where institutional money is actually moving — ahead of price. Run in the Institutional Intelligence phase.
---

# Institutional Flows Sub-Agent

## Grounding Tools (use first)

- **Web grounding (pre-fetched)** — this segment has no maintained Supabase series. A
  `web_grounding` block (a cited web/news/X summary over curated domains incl. reuters.com,
  apnews.com, sec.gov, cftc.gov, treasury.gov, capitoltrades.com, finance.yahoo.com) is
  provided in PHASE_INPUTS when available; ground on it and carry its source URLs for 13F filings (sec.gov), fund flows, and ETF flows. into the `sources` field; if no `web_grounding` is present, say so and lower conviction.

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

Write a markdown `body`. Suggested skeleton (skip empty sections). Cite flow sources with [title](url). Do **not** invent scores, a Signals section, or print `Bias:` at the top.

```markdown
# Institutional flows — {as-of date of the data}

## ETF flows
Net direction and the largest in/out names.

## Rotation and filings
Sector rotation, dark-pool/block notes, 13D/13G if retrieved.

## Implication
What the flow tape implies for today's research.
```
