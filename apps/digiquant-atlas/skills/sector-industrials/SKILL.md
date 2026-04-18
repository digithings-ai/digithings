---
name: sector-industrials
description: Deep-dive analysis of the Industrials sector (XLI, ITA). Covers aerospace/defense, transportation, infrastructure, machinery, and commercial services. Strong correlation to PMI and economic cycle. Run as part of the US Equities phase in the daily orchestrator.
---

# Industrials Sector Sub-Agent

## Inputs
- `config/watchlist.md` (XLI, ITA and related ETFs)
- `config/preferences.md`
- Macro regime output from `macro.md`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any PMI release page, defense contract announcement, infrastructure news, or industrials earnings URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLI / ITA levels and relative strength vs SPY
2. PMI/manufacturing correlation (PMI, new orders, industrial production)
3. Aerospace & defense (geopolitical spend)
4. Transportation (fuel headwind, freight)
5. Infrastructure/capex (AI buildout, IIJA/CHIPS)
6. Earnings/catalysts + valuation

---

## Output Format

```
### 🏭 INDUSTRIALS SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLI: $X (±X%) | ITA: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line]

**PMI Read**: [read]
**A&D Signal**: [read]
**Transportation**: [read]
**Infrastructure Spend**: [read]
```

