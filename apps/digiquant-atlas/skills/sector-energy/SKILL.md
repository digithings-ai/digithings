---
name: sector-energy
description: Deep-dive analysis of the Energy sector (XLE, OIH, FCG, DBO). Covers upstream E&P, integrated majors, oil services, refining, and LNG. Integrates WTI/Brent from commodities output. Run as part of the US Equities phase in the daily orchestrator.
---

# Energy Sector Sub-Agent

## Inputs
- `config/watchlist.md` (energy ETFs: XLE, DBO, OIH)
- `config/preferences.md` (XLE and DBO are active portfolio holdings)
- Macro regime output from `macro.md`
- Commodities output (WTI/Brent levels already established)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any OPEC statement, EIA report page, rig count article, or energy news URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Sector ETF Overview
- XLE, OIH, FCG, DBO levels and relative strength vs SPY

### 2. WTI/Brent Integration
- WTI level vs key psych levels; WTI/Brent spread; DBO curve (backwardation/contango)

### 3. Upstream / E&P
- Majors and E&P cash flow and capex discipline; buybacks/dividends

### 4. Geopolitical Supply Risk
- Iran/Hormuz status, OPEC+, outages, sanctions, SPR

### 5. Natural Gas & LNG
- Henry Hub + LNG context

### 6. Oil Services
- Rig count, pricing power, cycle timing

### 7. Valuation Context
- XLE valuation, FCF yield, refining margins

### 8. Portfolio Assessment
- XLE/DBO thesis check; profit-taking vs hold; invalidation trigger monitoring

---

## Output Format

```
### ⚡ ENERGY SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLE: $X (±X%) | OIH: $X (±X%) | DBO: $X (±X%)
**vs 200-DMA**: XLE [above/below by X%]
**Relative Strength vs SPY**: [Outperforming / Underperforming]

**WTI Integration**: $X — [context; curve shape for DBO]
**Equity/Oil Congruence**: [tracking/diverging]

**Geopolitical Supply Premium**: [assessment]

**E&P Free Cash Flow**: [read]
**Oil Services**: [read]
**NatGas**: [read]

**Valuation**: XLE NTM P/E ~Xx | FCF yield ~X%

**Portfolio Note**: Energy thesis [✅/⚠️/❌] + invalidation trigger status
```

