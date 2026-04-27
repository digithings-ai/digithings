---
name: market-earnings
description: >
  Run an earnings-focused analysis. Triggers when the user says "earnings analysis",
  "earnings season", "earnings preview", "how did [ticker] report", "earnings this week",
  "Q[N] earnings", or when it's earnings season (Jan, Apr, Jul, Oct) and the user asks
  about a specific company or sector. Use to preview upcoming earnings, analyze reported
  results, and identify sector-wide read-throughs.
---

# Earnings Analysis Skill

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any earnings release page, analyst note, guidance announcement, press release, or financial article URL. Not for API endpoints, `.json`, or `.md` files.

---

## Session Types

### A) Earnings Preview (before a report)
Triggered by: "preview [ticker] earnings" / "what to expect from [ticker]"

Steps:
1. Search for: consensus EPS and revenue estimates, whisper number if available
2. Search for: analyst sentiment and recent rating changes
3. Search for: key metrics the market is focused on (guidance, margins, specific KPIs)
4. Identify: What would be a "beat" vs. "miss" vs. "in-line" — and what each implies for the stock
5. Technical setup: Is the stock extended or at a good risk/reward into the print?
6. Options: Implied move from options market (IV crush signal)

Output:
```
### [TICKER] Earnings Preview — [DATE]
**Consensus**: EPS $X.XX | Revenue $X.XB
**Street whisper**: [above/below consensus if known]
**Key metric the market cares about**: [guidance / margins / specific KPI]
**Bull case (beat)**: [What happens and price target implication]
**Bear case (miss)**: [What happens]
**Technical setup**: [Extended / good entry / key levels]
**Implied move (options)**: ±X%
**My read**: [What to watch for in the report]
```

---

### B) Earnings Reaction (after a report)
Triggered by: "[ticker] earnings reaction" / "how did [ticker] do"

Steps:
1. Search for: actual EPS and revenue vs. estimates
2. Search for: guidance (raised / maintained / lowered / withdrawn)
3. Search for: after-hours or pre-market price reaction
4. Identify: Key quotes from management / call takeaways
5. Sector read-through: Does this result say anything about competitors or the broader sector?

Output:
```
### [TICKER] Earnings Reaction — [DATE]
**Result**: EPS $X.XX (est. $X.XX) [Beat/Miss/In-line] | Revenue $XB (est. $XB)
**Guidance**: [Raised / Maintained / Lowered | forward EPS/rev guidance]
**Stock reaction**: [±X% AH/PM]
**Key takeaway**: [1-2 sentences on what mattered most]
**Sector read-through**: [Positive / Negative / Neutral for peers]
**Implication for thesis**: [If ticker is in watchlist — confirm/challenge/neutral]
```

---

### C) Earnings Calendar Scan
Triggered by: "earnings this week" / "earnings calendar" / "who's reporting"

Steps:
1. Search for this week's major earnings releases
2. Organize by day with ticker, time (BMO/AMC), sector, and why it matters
3. Flag any with sector-wide read-through significance
4. Flag any in the user's watchlist

Output:
```
### Earnings Calendar — Week of [DATE]

**Monday**: [Ticker (BMO/AMC) — sector, why it matters]
**Tuesday**: [...]
**Wednesday**: [...]
**Thursday**: [...]
**Friday**: [...]

**Most important**: [Top 2-3 reports and why]
**Watchlist alerts**: [Any of your watchlist stocks reporting]
**Sector signals to watch**: [Which sectors get read-throughs this week]
```

---

### D) Earnings Season Themes
Triggered by: "earnings season themes" / "what's the trend this earnings season"

Steps:
1. Search for analyst commentary on Q[N] earnings trends
2. Identify: Beat rate vs. historical average
3. Identify: Guidance trends (raising / cutting)
4. Identify: Which sectors are beating / missing

---

## Quality Standards
- Always search for current data — do not use training data for estimates or results
- Always identify the sector read-through — individual earnings matter less than what they signal for peers
- Always connect earnings results back to active theses in `config/preferences.md`
- Flag if guidance is more important than the quarter (it almost always is)

