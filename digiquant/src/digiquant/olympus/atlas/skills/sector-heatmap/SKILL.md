---
name: market-sector-heatmap
description: >
  Generate a sector rotation heatmap and analysis. Triggers when the user says
  "sector heatmap", "sector rotation", "where's the money flowing", "sector analysis",
  "which sectors are leading", or "sector breakdown". Produces a text-based heatmap
  of all 11 S&P sectors with rotation interpretation and implied macro signal.
---

# Sector Rotation Heatmap Skill

---

## Step 1: Data Collection

Search for today's performance of all 11 SPDR sector ETFs:
XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU, XLRE, XLB, XLC

Also collect:
- SPY (benchmark)
- 1-week and 1-month performance for each sector (for trend context)
- VIX level

---

## Step 2: Classify Each Sector

For each sector, classify:
- **Today**: 🟢 (>+0.5%) | 🟡 (-0.5% to +0.5%) | 🔴 (<-0.5%)
- **1-Week trend**: ↑ Leading | → Neutral | ↓ Lagging
- **Type**: Cyclical (XLK, XLF, XLE, XLI, XLY, XLB) vs. Defensive (XLP, XLU, XLRE, XLV) vs. Mixed (XLC)

---

## Step 3: Rotation Interpretation

Using the sector performance matrix, identify the rotation pattern:

**Risk-On signals** (cyclicals leading, defensives lagging):
- XLK, XLY, XLF outperforming → growth/risk-on
- XLE leading with XLI → reflation/growth

**Risk-Off signals** (defensives leading, cyclicals lagging):
- XLP, XLU leading → flight to defensives
- XLV outperforming → healthcare as safe haven

**Rates-Driven signals**:
- XLRE, XLU selling hard → rising yield environment (higher for longer)
- XLF outperforming → benefiting from steeper curve or net interest margin expansion

**Stagflation signal**:
- XLE + XLP leading, XLK + XLRE lagging → energy/staples inflation play, growth assets suffering

---

## Output Format

```
## 🌡️ Sector Heatmap — [DATE]

SPY: $XXX (±X%) | VIX: XX

| Sector | ETF | Today | 1-Week | 1-Month | Signal |
|--------|-----|-------|--------|---------|--------|
| Technology | XLK | 🟢/🟡/🔴 +X% | ↑/→/↓ | ↑/→/↓ | [1-word] |
| Financials | XLF | | | | |
| Healthcare | XLV | | | | |
| Energy | XLE | | | | |
| Industrials | XLI | | | | |
| Cons. Disc. | XLY | | | | |
| Cons. Stap. | XLP | | | | |
| Utilities | XLU | | | | |
| Real Estate | XLRE | | | | |
| Materials | XLB | | | | |
| Comm. Svcs | XLC | | | | |

**Rotation Pattern**: [Risk-On / Risk-Off / Rates-Driven / Stagflation / Mixed]

**Money is flowing INTO**: [Top 2-3 sectors]
**Money is flowing OUT OF**: [Bottom 2-3 sectors]

**Macro Implication**: [2-3 sentences on what this rotation tells us about the market's macro read]

**Most Interesting Divergence**: [Any sector behaving unexpectedly vs. the overall tone — and why]

**For your watchlist**: [How this rotation affects specific names or ETFs the user holds]
```

---

## Rotation Cheat Sheet Reference

| Economic Phase | Leading Sectors | Lagging Sectors |
|---------------|----------------|-----------------|
| Early cycle (recovery) | XLF, XLY, XLI | XLU, XLP |
| Mid cycle (expansion) | XLK, XLI, XLE | XLRE, XLU |
| Late cycle (slowing) | XLE, XLV, XLP | XLK, XLY |
| Recession | XLU, XLP, XLV | XLF, XLY, XLK |
| Rates rising | XLF, XLE | XLRE, XLU, XLK |
| Rates falling | XLRE, XLU, XLK | XLF, XLE |
```

