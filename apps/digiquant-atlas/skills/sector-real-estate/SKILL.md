---
name: sector-real-estate
description: Deep-dive analysis of the Real Estate sector (XLRE, VNQ). Covers equity REITs across sub-types: industrial, retail, office, residential, data center, healthcare, and specialty. Highly rate-sensitive. Run as part of the US Equities phase in the daily orchestrator.
---

# Real Estate Sector Sub-Agent

## Inputs
- `config/watchlist.md` (XLRE, VNQ and related)
- `config/preferences.md`
- Bonds output from current session (10Y yield is the primary pricing factor)
- Macro regime output

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any REIT earnings page, housing data article, rate sensitivity news, or real estate sector URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLRE/VNQ levels and relative strength vs SPY
2. Rate sensitivity (div yield vs 10Y)
3. Sub-type scan (data centers, industrial, residential, office, towers, healthcare, storage)
4. CRE stress monitor (maturity wall, CMBS, bank exposure)
5. Valuation (FFO multiple, cap rate spread)

---

## Output Format

```
### 🏢 REAL ESTATE SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLRE: $X (±X%) | VNQ: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming]

**Rate Sensitivity**: 10Y X% | XLRE div yield X% | Spread Xbps
**Sub-type leaders/laggards**: [read]
**CRE Risk Monitor**: [read]
**Valuation**: [read]
```

