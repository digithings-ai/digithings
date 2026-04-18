---
name: market-sector-rotation
description: >
  Track and analyze sector rotation signals. Use when the user asks about "sector rotation",
  "which sectors are leading", "defensive vs growth rotation", "sector heat map", or
  "what does sector performance say about the cycle". Also runs as a sub-component of
  `skills/equity/SKILL.md`.
---

# Sector Rotation Skill

Sector rotation is one of the clearest signals of market regime and risk appetite shifts.
This skill tracks it systematically across the economic cycle.

---

## The 11 S&P 500 Sectors

| ETF | Sector | Cycle Phase Typical Leadership |
|-----|--------|-------------------------------|
| XLK | Technology | Late expansion / early bull |
| XLC | Communication Services | Early-mid expansion |
| XLY | Consumer Discretionary | Early expansion |
| XLF | Financials | Early expansion / rising rates |
| XLI | Industrials | Mid expansion |
| XLB | Materials | Mid expansion / commodity cycle |
| XLE | Energy | Late expansion / inflation |
| XLV | Healthcare | Late cycle / defensive |
| XLP | Consumer Staples | Contraction / defensive |
| XLU | Utilities | Contraction / falling rates |
| XLRE | Real Estate | Falling rates / early recovery |

---

## Daily Rotation Check

1. Get 1-day % change for all 11 sectors
2. Rank from best to worst
3. Note: which are beating SPY? Which are lagging?
4. Classify the rotation:

**Risk-On signals:**
- XLK, XLC, XLY, XLF leading
- XLP, XLU, XLRE lagging

**Risk-Off / Defensive signals:**
- XLP, XLU, XLV leading
- XLK, XLY lagging

**Inflation / Late-Cycle signals:**
- XLE, XLB, XLI leading
- Growth sectors lagging

**Rate-Sensitive Rotation:**
- Rates rising: XLF leads, XLRE/XLU suffer
- Rates falling: XLRE/XLU recover, XLF pressure

5. Compare to the prior week's rotation — is rotation consistent or shifting?

---

## Weekly Momentum Table (update weekly)

Track 1-week and 4-week performance to see momentum:

```
| Sector | ETF  | 1D% | 1W% | 4W% | Trend | vs SPY (4W) |
|--------|------|-----|-----|-----|-------|-------------|
| Tech   | XLK  |     |     |     |       |             |
| Comms  | XLC  |     |     |     |       |             |
| Discr  | XLY  |     |     |     |       |             |
| Fins   | XLF  |     |     |     |       |             |
| Indus  | XLI  |     |     |     |       |             |
| Mats   | XLB  |     |     |     |       |             |
| Energy | XLE  |     |     |     |       |             |
| Health | XLV  |     |     |     |       |             |
| Staples| XLP  |     |     |     |       |             |
| Utils  | XLU  |     |     |     |       |             |
| RE     | XLRE |     |     |     |       |             |
```

---

## Output Format

```
### 🔄 Sector Rotation
**Today's Leaders**: [top 3 sectors + %]
**Today's Laggards**: [bottom 3 sectors + %]
**Rotation Signal**: [Risk-On / Risk-Off / Defensive / Inflation / Mixed]
**Consistent with prior week?**: [Yes / No — explain if no]
**Cycle Implication**: [Where does this rotation suggest we are in the cycle?]
```

