---
name: market-premarket-pulse
description: >
  Run a fast pre-market scan — a 5-minute read before the open. Triggers when the user says
  "pre-market", "pre-market pulse", "quick scan", "what's moving pre-market", "before the open",
  "morning scan", or "anything overnight". Much faster than a full digest — just the critical
  overnight and pre-market signals. Use this on days when the full digest will run later,
  or as a standalone quick check.
---

# Pre-Market Pulse Skill

Fast, focused, no filler. 5 minutes to read. Covers only what changed overnight.

---

## What to Search

Run these searches in parallel (4-5 searches max):
1. "pre-market futures S&P Nasdaq today [date]"
2. "overnight market news [date]"
3. "economic data released today [date]"
4. "BTC ETH price pre-market [date]"

---

## Output Format

Keep it under 300 words. No tables. No lengthy explanations.

```
## ⚡ Pre-Market Pulse — [DATE] — [TIME]

**Futures**: S&P [±X%] | Nasdaq [±X%] | Dow [±X%] | Russell [±X%]
**Overnight tone**: Risk-on / Risk-off / Mixed

**Biggest overnight move**: [Asset] [±X%] — [one sentence reason]

**Key data out today**: [Event, time, consensus] or "Light calendar today"

**Yields**: 10Y [X%] [±Xbps] | 2Y [X%] [±Xbps]
**DXY**: [X.XX] [±X%] | **BTC**: [$X] [±X% 24h]

**Top 3 things to know before the open**:
1. [Most important overnight development]
2. [Second most important]
3. [Catalyst or event to watch today]

**Bias heading into the open**: [One sentence]
```

---

## Rules
- Do NOT write full paragraphs — this is a scan, not an analysis
- Do NOT update memory files — that's for the full digest
- Do NOT cover every segment — only what materially moved
- If nothing notable happened overnight: say "Quiet overnight — no material changes" and stop
- This output does NOT replace the daily digest — it supplements it

