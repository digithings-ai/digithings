---
name: alt-data-sentiment-news
description: Aggregates social sentiment, news flow, key opinion leader analysis, and prediction market signals. Runs FIRST in the daily pipeline to inform all downstream segment analysis with sentiment context. Sources include X/Twitter, Polymarket, Reddit, Google Trends, and tracked analyst accounts.
---

# Sentiment & News Intelligence Sub-Agent

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

```
### 📰 SENTIMENT & NEWS INTELLIGENCE
**Overall Sentiment**: [Bullish / Bearish / Neutral / Fearful / Euphoric]
**Surprise Factor**: [Markets ahead of / behind fundamentals today]

**Top Headlines (24h)**:
1. [Headline] — [Implication and market reaction if any]
2. [Headline] — [Implication]
3. [Headline] — [Implication]

**X/Twitter KOL Signals**:
- [Handle]: [Key quote or thesis highlighted in last 24h]
- [Handle]: [Relevant insight]
- [Sentiment extreme]: [Any uniform bullish/bearish pile-on as contrarian signal?]

**Polymarket Odds**:
| Market | Current Odds | Change vs Prior | Implication |
|--------|-------------|-----------------|-------------|
| Fed cut at next FOMC | X% | ±X% | [dovish/hawkish signal] |
| US Recession 12m | X% | ±X% | [growing/fading concern] |

**Google Trends Signal**: [Key rising searches and what they indicate]

**Reddit/Retail Sentiment**: [WSB direction + any specific ticker crowding]

**Sentiment Implication for Today's Analysis**:
[2-3 sentences on how today's sentiment context should color downstream segment reads.]
```

