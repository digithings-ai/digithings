---
name: sector-technology
description: Deep-dive analysis of the Technology sector (XLK, SOXX, QQQ). Covers semiconductors, software, cloud, AI infrastructure, and hardware cycles. Run as part of the US Equities phase in the daily orchestrator.
---

# Technology Sector Sub-Agent

## Inputs
- `config/watchlist.md` (tech ETFs and tickers)
- `config/preferences.md`
- Macro regime output from `macro.md` (read current session's macro output)
- Institutional flows output (if already generated this session)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any earnings page, analyst note, product announcement, or tech news article URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Sector ETF Overview
Search for current levels and daily performance:
- **XLK** (Technology SPDR): price, % change, vs 50-DMA and 200-DMA
- **SOXX** (Semiconductor ETF): price, % change — semis lead/lag XLK as a forward indicator
- **QQQ** (NASDAQ 100, tech-heavy proxy): price, % change
- Is the sector above or below its 50-DMA? How does this compare to SPY's position vs its own 50-DMA?
- Sector relative strength: XLK vs SPY ratio — trending up (tech outperforming) or down (rotating out)?

### 2. Subsector Breakdown
Search for performance within technology:
- **Semiconductors** (SOXX, SMH): AI chip cycle, inventory cycle status, Taiwan risk
- **Software** (IGV): SaaS multiples, DOGE-era federal IT spending, cloud migration pace
- **Cloud / Hyperscalers** (MSFT, AMZN, GOOGL, META weight in XLK): capex trajectory, AI monetization
- **Apple (AAPL)**: largest XLK weighting — any news or technical move
- **Hardware / IT Services**: enterprise spending cycle

### 3. AI / Semiconductor Cycle Check
- NVDA, AMD, AVGO price action: these are the AI bellwethers
- Any supply constraint, pricing news, or demand signal from chip sector
- Taiwan Strait geopolitical risk: any escalation impacting TSMC/supply chain
- Data center capex: any hyperscaler CapEx announcements or guidance updates
- AI inference vs training demand balance

### 4. Earnings & Catalysts
- Any technology sector names reporting today or after close?
- Any recent beats/misses in sector with read-through implications?
- Upcoming tech mega-cap earnings (within 2 weeks)
- Analyst upgrades/downgrades on major tech names
- Notable product launches, regulatory actions, or M&A

### 5. Valuation Context
- XLK NTM P/E vs 5-year and 10-year historical average (search for estimate)
- Is tech expensive or fairly valued relative to history?
- Premium/discount to S&P 500 NTM P/E — is the premium justified by growth?
- Interest rate sensitivity: tech is a long-duration sector — how does today's yield movement affect valuation?

### 6. Macro Regime Fit
- In the current macro regime (from `macro.md`), is technology a favored sector?
  - Growth + Low rates = favorable for tech
  - Inflation + Rising rates = headwind for long-duration growth
  - Risk-off = tech often sells off unless defensive mega-caps hold
- Is tech acting defensively (mega-caps holding) or as pure growth (SOXX/small-cap tech leading)?

### 7. Institutional & Flow Signals
- QQQ and XLK ETF in/outflows (reference institutional flows if available)
- Any notable unusual options activity in XLK, SOXX, or mega-cap tech names
- Short interest in SOXX/XLK trending up or down?

---

## Output Format

```
### 💻 TECHNOLOGY SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLK: $X (±X%) | SOXX: $X (±X%) | QQQ: $X (±X%)
**vs 200-DMA**: XLK [above/below by X%] | SOXX [above/below by X%]
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line] — [trend context]

**Subsector Leaders/Laggards**:
- Leading: [subsector] — [reason]
- Lagging: [subsector] — [reason]

**AI/Semi Signal**: [NVDA/AMD/SOXX action — what it implies for the AI capex cycle]

**Valuation**: XLK NTM P/E: ~Xx | Historical avg: ~Xx | [Premium/discount] — [justified?]

**Rate Sensitivity Today**: [How today's yield move affects tech valuation]

**Catalysts**: [Any earnings, upgrades, product launches, regulatory news]

**Regime Fit**: [Is current macro regime favorable/unfavorable for tech? Why?]

**Implication for Portfolio**: [Do current XLK/QQQ positions need adjustment? What's the tactical read?]
```

