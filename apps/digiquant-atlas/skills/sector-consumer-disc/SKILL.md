---
name: sector-consumer-discretionary
description: Deep-dive analysis of the Consumer Discretionary sector (XLY). Covers auto, housing, retail, restaurants, leisure, and e-commerce. Cyclical high-beta sector — signals consumer spending health and risk appetite. Run as part of the US Equities phase in the daily orchestrator.
---

# Consumer Discretionary Sub-Agent

## Inputs
- `config/watchlist.md` (XLY and related ETFs)
- `config/preferences.md`
- Macro regime output from `macro.md`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any retail sales article, consumer confidence page, or earnings release URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

1. XLY level and relative strength vs SPY (note AMZN/TSLA concentration)
2. Sub-sector scan (auto, housing, travel, retail)
3. Consumer spending health check (retail sales, credit, gas price effect)
4. Housing adjacency (30Y mortgage, starts/permits, NAHB)
5. Earnings/catalysts and valuation context

---

## Output Format

```
### 🛍️ CONSUMER DISCRETIONARY SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLY: $X (±X%)
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line]
**XLY ex AMZN/TSLA**: [independent trend]

**Consumer Spending Signal**: [read]
**Sub-sector read**: [auto/housing/travel]
**XLY/XLP Ratio**: [risk appetite read]
```

