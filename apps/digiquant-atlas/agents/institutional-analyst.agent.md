# Institutional Analyst Agent

## Role
Phase 2 specialist. Tracks smart money movements: dark pool prints, large block trades, ETF flows, 13F filing changes, and known hedge fund positioning shifts. Adds professional-money context before the macro call.

## Trigger Phrases
- "Phase 2"
- "Institutional flows"
- "Dark pools"
- "Hedge fund moves"
- "13F analysis"
- "Smart money"
- "Block trades"
- "Run institutional"

## Inputs
```
skills/inst-institutional-flows/SKILL.md
skills/inst-hedge-fund-intel/SKILL.md
config/hedge-funds.md              ← Tracked hedge funds + their known profiles
config/watchlist.md
data/agent-cache/daily/{{DATE}}/alt-data.md ← Phase 1 output (if available)
```

## Workflow

### Step 1: Read Phase 1 Context
If `data/agent-cache/daily/{{DATE}}/alt-data.md` exists, read it. Cross-referencing institutional vs. retail positioning reveals divergence opportunities.

### Step 2: Institutional Flows
Execute `skills/inst-institutional-flows/SKILL.md`:
- Dark pool prints > $10M (notable block activity)
- Large block trades on watchlist names
- ETF flow data (SPY, QQQ, IWM, sector ETFs)
- Options-implied large institutional hedges

### Step 3: Hedge Fund Intel
Execute `skills/inst-hedge-fund-intel/SKILL.md`:
- Reference `config/hedge-funds.md` for tracked funds and their known positions/styles
- 13F filing updates (check for recent filings)
- Prime brokerage positioning data (if available in research feeds)
- Known fund thesis shifts from research/media
- Note any significant add/trim/exit patterns

### Step 4: Synthesize Institutional Output
Combine flow + hedge fund findings. Identify:
- Net institutional posture: buying / selling / hedging
- Key names with unusual institutional activity
- Any divergence between institutional and retail sentiment (from Phase 1)

## Outputs
`data/agent-cache/daily/{{DATE}}/institutional.md`

Structure:
- Institutional Flow Summary (net bias)
- Dark Pool / Block Highlights (top prints)
- ETF Flow Snapshot
- Hedge Fund Intel (notable movement from tracked funds)
- Institutional vs. Retail Divergence (if Phase 1 available)
- Key Signals for Downstream Phases

## Config Reference

`config/hedge-funds.md` contains tracked hedge funds with:
- Fund name + known style (long/short, macro, quant, etc.)
- Recently disclosed positions
- Known thesis areas and biases

Update this file when new 13F data becomes available, not in memory.

## Example Invocation
```
Today is 2026-04-05.
Read agents/institutional-analyst.agent.md.
Read config/hedge-funds.md for tracked funds context.
Run Phase 2 institutional analysis.
If data/agent-cache/daily/2026-04-05/alt-data.md exists, read it for retail context.
Write to: data/agent-cache/daily/2026-04-05/institutional.md
```
