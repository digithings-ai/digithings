---
name: sector-materials
description: Deep-dive analysis of the Materials sector (XLB). Covers chemicals, metals & mining, paper/packaging, and construction materials. China demand, DXY, and commodity cycles are primary drivers. Run as part of the US Equities phase in the daily orchestrator.
---

# Materials Sector Sub-Agent

## Inputs
- `config/watchlist.md` (XLB and commodity-linked ETFs)
- `config/preferences.md`
- Commodities output (copper, gold)
- Macro regime + international/China output

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any commodity price article, China demand signal page, or materials earnings URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLB level and relative strength vs SPY
2. Metals & mining (copper, gold miners vs bullion, steel/aluminum)
3. Chemicals (industrial gases, fertilizers, lithium)
4. China demand signal (PMI, stimulus, iron ore)
5. Supply chain/geopolitical and DXY effect
6. Valuation context

---

## Output Format

```
### ⛏️ MATERIALS SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLB: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming]

**Metals & Mining**: [copper/gold miner divergence]
**China Demand**: [read]
**Rare earth / critical minerals**: [read]
**DXY Effect**: [read]
**Valuation**: [read]
```

