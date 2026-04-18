---
name: sector-utilities
description: Deep-dive analysis of the Utilities sector (XLU). Covers regulated electric, water, gas distribution, and merchant power. Highly rate-sensitive bond-proxy sector. Run as part of the US Equities phase in the daily orchestrator.
---

# Utilities Sector Sub-Agent

## Inputs
- `config/watchlist.md` (XLU and related)
- `config/preferences.md`
- Bonds output from current session (10Y yield is the primary driver)
- Macro regime output from `macro.md`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any regulatory filing, rate case decision, utility earnings page, or rate-sensitivity article URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLU levels and relative strength vs SPY
2. Rate sensitivity (div yield vs 10Y spread)
3. AI/data center power demand theme
4. Grid modernization/regulation and capex approvals
5. Renewables/nuclear developments
6. Valuation context

---

## Output Format

```
### ⚡ UTILITIES SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLU: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line]

**Rate Sensitivity**: 10Y X% | XLU div yield ~X% | Spread Xbps
**AI Power Demand**: [read]
**Valuation**: [read]
```

