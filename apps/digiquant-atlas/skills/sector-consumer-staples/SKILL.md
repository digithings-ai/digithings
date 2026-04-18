---
name: sector-consumer-staples
description: Deep-dive analysis of the Consumer Staples sector (XLP). Covers food/beverage, household products, tobacco, and retail staples. Defensive income-generating sector — tracks pricing power, input costs, and volume trends. Run as part of the US Equities phase in the daily orchestrator.
---

# Consumer Staples Sector Sub-Agent

## Inputs
- `config/watchlist.md` (XLP and consumer ETFs)
- `config/preferences.md` (XLP may be a portfolio holding)
- Macro regime output from `macro.md`
- Commodities output (food/energy input costs)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any earnings release, pricing power article, or consumer staples news URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLP level and relative strength vs SPY
2. Pricing power vs volume
3. Input costs (ag, energy, FX, labor)
4. Defensive premium vs rates (div yield vs 10Y)
5. Consumer health signals
6. Earnings/catalysts, GLP-1 secular demand implications

---

## Output Format

```
### 🛒 CONSUMER STAPLES SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLP: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line]

**Pricing Power**: [read]
**Input Costs**: [read]
**Defensive Premium**: Div yield ~X% vs 10Y X% (spread Xbps)
**Consumer Health**: [read]
**Portfolio Note**: [thesis status]
```

