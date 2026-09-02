---
name: alt-data-sentiment-news
description: Aggregates social sentiment, news flow, key opinion leader analysis, and prediction market signals. Runs FIRST in the daily pipeline to inform all downstream segment analysis with sentiment context. Sources include X/Twitter, Polymarket, Reddit, Google Trends, and tracked analyst accounts.
---

# Sentiment & News Intelligence Sub-Agent

## Grounding Tools (use first)

- **Web grounding (pre-fetched)** — this segment has no maintained Supabase series. A
  `web_grounding` block (a cited web/news/X summary over curated domains incl. reuters.com,
  apnews.com, sec.gov, cftc.gov, treasury.gov, capitoltrades.com, finance.yahoo.com) is
  provided in PHASE_INPUTS when available; ground on it and carry its source URLs for market-moving news and sentiment shifts. into the `sources` field; if no `web_grounding` is present, say so and lower conviction.

## Purpose
Run this skill **before** macro and segment analysis. Its output colors how downstream segments interpret ambiguous signals. Sentiment extremes (euphoria/panic) can override technical/fundamental reads.

## Inputs
- `docs/ops/data-sources.md` — full list of tracked accounts and signal sources
- Previous day's digest snapshot / derived digest markdown (for narrative continuity)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any article, news page, Reddit thread, or post URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Market Headline Scan (Last 24h)
Search for the top 3-5 market-moving headlines from the past 24 hours:
- What is the dominant narrative today?
- Is fear or greed driving the conversation?
- Any surprise developments (geopolitical, economic, earnings, policy) vs prior expectations?
- Are markets reacting to **new information** or repricing on **narrative shift** with no new data?

### 2. X / Twitter Sentiment Scan
Search for recent posts from tracked accounts and hashtags.

### 3. Polymarket Prediction Markets
Use the MCP Polymarket tools to see today's most active markets, then query specifics:
- Fed path, recession odds, geopolitics, BTC levels

### 4. Reddit Community Sentiment
Scan WSB and r/investing for any memetic crowding or panic signals.

### 5. Google Trends Signals
Scan key search terms ("recession", "gold", "bitcoin", "market crash", key geopolitical term).

### 6. News Sentiment Scoring
After reviewing headlines, score:
- **Headline Sentiment**: Bullish / Bearish / Neutral for markets overall
- **Surprise Factor**: expected (+0) vs upside (+1) vs downside (-1)
- **Narrative Momentum**: strengthening or fading
- **Cross-asset coherence**: coherent or conflicting

---

## Output Format

Write a markdown `body`. Suggested skeleton (skip empty sections). Inline [title](url) citations. Do **not** invent data-quality or confidence scores, emit a Signals section, or print `Bias:` at the top.

```markdown
# Sentiment and news — {as-of date of the data}

## Narrative
Dominant 24h story and whether it is new information or a repricing.

## Headlines
1. [Outlet](url) — implication
2. …

## Positioning color
X/KOL, Polymarket, retail/Reddit, Google Trends — only what you actually retrieved.

## Implication for today's research
How this should color downstream segment reads.
```
