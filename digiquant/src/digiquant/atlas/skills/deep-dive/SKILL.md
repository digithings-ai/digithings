---
name: market-deep-dive
description: >
  Run a deep-dive analysis on a single asset, sector, or theme. Triggers when the user says
  "deep dive on [X]", "full analysis of [X]", "break down [X] for me", "research [X]",
  "what's the full picture on [X]", or when they ask for more detail on something flagged
  in the daily digest. Produces a standalone research note with full fundamental,
  technical, and macro context. Always use this skill for single-asset research requests.
---

# Deep Dive Analysis Skill

Produces a standalone research note on any single asset, sector, theme, or instrument.

---

## Web Fetch Protocol (token-efficient)

When fetching news articles, earnings pages, analyst notes, or any standard web page during Sections A–D:

```bash
# Prefer defuddle over WebFetch — strips nav/ads/clutter before the LLM reads
defuddle parse <url> --md

# Install if missing
npm install -g defuddle
```

Do NOT use defuddle for `.md` URLs or Supabase/API endpoints — use WebFetch or MCP directly.

---

## Step 1: Identify the Subject

Determine what's being analyzed:
- **Single stock**: Use sections A, B, C, D, E
- **Sector/ETF**: Use sections A, C, D, E (skip B)
- **Crypto asset**: Use sections A, C, D, E + crypto-specific (skip B, modify C)
- **Macro theme** (e.g., "AI trade", "rate cuts", "China recovery"): Use D and E primarily
- **Commodity**: Use sections A, C, D, E

---

## Section A: The Current Setup

Search for: current price, 52-week range, YTD performance, recent trend
- Where is it in its range? (near highs / near lows / mid-range)
- What's the recent momentum? (trending / consolidating / reversing)
- Volume: Any unusual volume patterns recently?
- Relative performance: Outperforming or underperforming its benchmark/sector?

---

## Section B: Fundamental Picture (stocks only)

Search for: latest earnings, valuation multiples, analyst ratings, balance sheet headline
- **Valuation**: P/E, EV/EBITDA, P/S — cheap / fair / expensive vs. sector and history
- **Growth**: Revenue and EPS growth trajectory (accelerating / decelerating)
- **Profitability**: Margins trend (expanding / compressing)
- **Balance sheet**: Debt load, cash position — any financial stress?
- **Analyst consensus**: Buy / Hold / Sell ratio, average price target vs. current
- **Upcoming catalysts**: Earnings date, product launches, regulatory events
- **SEC filings (when material):** For **single-stock** or issuer-heavy themes, optionally review recent **8-K**, **10-Q**, **10-K** (or 20-F) on [EDGAR](https://www.sec.gov/edgar) or via the **`sec-edgar`** MCP if configured — especially around earnings, restatements, or heavy news flow. ETF-only sleeves usually skip this.

---

## Section C: Technical Analysis

Analyze the chart structure:
- **Trend**: Uptrend / downtrend / consolidation (define with timeframe)
- **Key levels**:
  - Support 1 (nearest): $X
  - Support 2 (major): $X
  - Resistance 1 (nearest): $X
  - Resistance 2 (major): $X
- **Moving averages**: Price vs. 20/50/200-day MA — bullish or bearish configuration?
- **Momentum**: RSI (overbought >70 / oversold <30), MACD signal
- **Pattern**: Any notable chart patterns (breakout, breakdown, consolidation, head & shoulders, etc.)
- **Risk/reward**: Current entry — what's a logical stop vs. target?

---

## Section D: Macro & Narrative Context

- What macro regime is most relevant to this asset?
- What's the dominant market narrative around this asset right now?
- Is the macro tailwind or headwind for this asset?
- What would need to change macro-wise to change the outlook?

---

## Section E: Synthesis & Verdict

Produce a clear research note conclusion:

```
## Deep Dive: [ASSET] — [DATE]

**Verdict**: [Bullish / Bearish / Neutral / Watching]
**Conviction**: [High / Medium / Low]
**Time horizon**: [Short-term (days-weeks) / Medium (weeks-months) / Long (months+)]

**Bull case**: [2-3 sentences — what makes this work]
**Bear case**: [2-3 sentences — what breaks the thesis]

**Entry zone**: $X - $X (if applicable)
**Stop loss level**: $X (technical invalidation)
**Target**: $X / +X% (if bullish) or downside to $X (if bearish)

**Key catalyst to watch**: [The specific event or data that resolves the setup]
**The one thing that would change this view**: [What would flip the verdict]
```

---

## Output Note

### Check for prior research first

Before running a new deep dive, check Supabase for a recent one on this subject:

```bash
python3 scripts/fetch_research_library.py --ticker {TICKER}
```

If a note exists within 7 days, load it and assess whether a refresh is needed.

### Publish to research library

After completing the deep dive, publish to Supabase research library:

```bash
python3 scripts/publish_research.py \
  --key research/deep-dives/{TICKER}-{DATE} \
  --title "{TICKER} Deep Dive" \
  --type deep-dive \
  --ticker {TICKER} \
  --date {DATE} \
  --content -   # pipe the markdown note via stdin
```

Or from a scratch file:

```bash
python3 scripts/publish_research.py \
  --key research/deep-dives/{TICKER}-{DATE} \
  --title "{TICKER} Deep Dive" \
  --type deep-dive \
  --file data/agent-cache/deep-dives/{DATE}-{TICKER}.md \
  --date {DATE}
```

If this deep dive surfaces a reusable framework or concept (not asset-specific), publish with `--type concept` and key `research/concepts/{SLUG}` instead.

Flag if findings change or validate any active thesis in `config/preferences.md`.

