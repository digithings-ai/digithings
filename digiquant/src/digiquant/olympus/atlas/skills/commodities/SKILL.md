---
name: market-commodities
description: Run commodities analysis as part of the daily digest. Covers energy, metals, agriculture, and their cross-asset implications. In the orchestrator, run as Phase 4B — reads macro regime and bonds/real yield output. Feeds into energy sector sub-agent.
---

# Commodities Analysis Skill — v2

## Inputs
- `config/watchlist.md` (commodities section)
- `config/preferences.md`
- Macro regime output
- Bonds output (real yields — key driver for gold)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any OPEC news page, EIA report page, commodity news article, or central bank buying announcement URL. Not for API endpoints, `.json`, or `.md` files.

## Research Steps

### 1. Energy
- WTI Crude: price, 24h change, key technical levels
- Brent Crude: price and WTI/Brent spread
- Natural Gas: price and direction
- Catalysts: OPEC+ news, US inventory data (EIA report), geopolitical supply risk
- What is energy saying about growth expectations?

### 2. Precious Metals
- Gold (XAU/USD): price, 24h change, trend
- Silver (XAG/USD): price, gold/silver ratio
- What is gold's move signaling? (real yield direction, dollar, safe haven demand, inflation hedge)
- Any central bank buying data or ETF flow signals?

### 3. Copper & Industrial Metals
- Copper: price and direction
- Dr. Copper as a growth indicator — what is it saying?
- Any China demand signals from industrial metals?

### 4. Oil Supply/Demand Balance
- EIA weekly inventory data (published Wednesdays): crude draw or build?
- OPEC+ production compliance: are members cheating on quotas?
- US shale production trend: rig count direction and efficiency gains
- Refinery utilization rates: product inventory levels
- Demand signals: Chinese import data, air travel demand, industrial activity
- DBO roll yield: futures curve in backwardation (positive) or contango (negative)? At $112 WTI, backwardation typically confirms the supply squeeze.

### 5. Gold Drivers Deep Analysis
- **Real yield correlation**: gold moves inversely to real yields — reference bonds output
- **Central bank buying**: major central bank gold purchases (China, India, Turkey, others)
- **Dollar (DXY) effect**: weaker dollar = gold tailwind (though at current geopolitical stress, gold can rise with DXY)
- **Safe haven premium**: how much of current gold price reflects war premium vs inflation premium?
- At $4,686: is gold in price discovery (no historical resistance) or approaching exhaustion?
- Gold/Silver ratio: a rising ratio favors gold (safety demand); falling ratio = silver catches up (industrial + monetary demand)

### 6. Agriculture (if relevant)
- Wheat, corn, soybeans if any major move or relevant news
- Flag only if materially moving or relevant to inflation narrative
- Food inflation: any supply disruption via weather events or conflict?

### 7. Commodity-Macro Cross
- DXY direction and its effect on commodity pricing (inverse relationship)
- Is commodity movement driven by supply or demand factors?
- Do commodities confirm or contradict the macro regime?
- CTA speculative positioning in commodities (from Phase 1B): is speculative long stretched?

## Output Format

```
### 🛢️ COMMODITIES
**Bias**: [Bullish / Bearish / Neutral / Conflicted]

**Energy**: [WTI: $X (±X%) | Brent: $X | NatGas: $X | Driver: ...]
**Gold**: [$X (±X%) | Signal: safe haven / inflation hedge / real yield play]
**Silver**: [$X | Gold/Silver ratio: X]
**Copper**: [$X (±X%) | Growth signal: ...]

**Oil Supply/Demand**: [EIA inventory + OPEC compliance + US shale signal]
**Gold Real Yield Link**: Real yield X% → [tailwind/headwind for gold at ATH]
**Gold/Silver Ratio**: X — [Safety bid dominant / Silver catching up]
**CTA Positioning**: [Are speculative longs stretched in oil or gold?]

**Dollar Effect**: [DXY impact on commodities]

**Watch**: [Key upcoming data: EIA Wednesday, OPEC meeting, gold central bank data]
```

