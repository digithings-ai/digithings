---
name: market-thesis-tracker
description: >
  Run a standalone thesis review and portfolio bias check. Triggers when the user says
  "check my theses", "thesis review", "how are my positions doing", "portfolio check",
  "validate my biases", or "where do I stand". Reads active theses from preferences.md
  and cross-references against Supabase daily_snapshots and current market data.
  Use this for focused mid-week or between-digest thesis health checks.
---

# Thesis Tracker Skill

A focused, fast review of the user's active theses without running a full digest.

---

## Step 1: Load Theses

Read `config/preferences.md` — extract the "Current Portfolio Themes / Active Theses" section.
List each thesis explicitly before proceeding.

---

## Step 2: Load Recent Context

Query Supabase `daily_snapshots` for the last 3-5 entries relevant to each thesis.
Note any recent confirmations, contradictions, or shifts.

---

## Step 3: Current Market Search

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch when following any search result URL to read an article or analysis page. Not for API endpoints, `.json`, or `.md` files.

For each active thesis, run a targeted web search to get the latest data point most relevant to that thesis.

Examples:
- "Long AI infrastructure" → search NVDA, QQQ, SOX recent performance + analyst views
- "Cautious on rate-sensitive" → search XLRE, XLU, 10Y yield direction
- "BTC halving" → search BTC price, ETF flows, halving countdown
- "TLT long" → search TLT price, 10Y yield, recession probability

Be efficient — one search per thesis, targeted.

---

## Step 4: Score Each Thesis

For each thesis, produce a structured assessment:

```
### [Thesis Name]
**Status**: ✅ Confirmed | ⚠️ Conflicted | ❌ Challenged | ⏳ No Signal | 🆕 Evolving
**Conviction**: High / Medium / Low (based on weight of evidence)
**Evidence for**: [1-2 data points supporting the thesis]
**Evidence against**: [1-2 data points challenging it]
**Key level/catalyst to watch**: [The specific thing that would resolve the conflict or confirm the thesis]
**Suggested action**: [Hold / Add / Reduce / Exit / Watch — not financial advice, just signal read]
**Time horizon**: Still valid within original time frame? Y/N
```

---

## Step 5: Portfolio-Level Summary

After scoring all individual theses, produce a portfolio-level read:

```
## Portfolio Bias Summary

**Net directional bias**: [Net long / Net short / Balanced / Conflicted]
**Biggest risk to current portfolio**: [The single factor that could hurt most positions simultaneously]
**Biggest opportunity signal**: [The clearest conviction signal right now]
**Hedges working**: [Are any hedges performing as expected?]
**Suggested focus for next 48-72h**: [Where to direct attention]
```

---

## Step 6: Thesis Hygiene Check

Review the thesis list itself:
- Are any theses stale (no supporting data in last 5 daily entries)?
- Are any theses redundant (two theses making the same bet)?
- Should any be closed, merged, or promoted to higher conviction?
- Are there any emerging themes from recent Supabase snapshots that should be added as a new thesis?

Output a short "Thesis Hygiene" note with recommendations.

---

## Format

Keep this output tighter than a full digest — the user already knows the market context.
Focus on signal vs. noise. Don't rehash what they already know.
Lead with the most urgent / most changed thesis, not alphabetically.
End with one clear sentence: "The portfolio's biggest risk right now is X."

