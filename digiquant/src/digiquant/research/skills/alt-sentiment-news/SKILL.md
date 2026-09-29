---
name: alt-data-sentiment-news
description: Aggregates news flow, narrative shift, and positioning colour from the pre-fetched web-grounding block plus the prior document. Runs FIRST in the daily pipeline to inform all downstream segment analysis with sentiment context.
---

# Sentiment & News Intelligence Sub-Agent

## Grounding Tools (use first)

- **Web grounding (pre-fetched) — this IS your news source.** This segment has no
  maintained Supabase series. A `web_grounding` block (a cited web/news summary over
  curated domains incl. reuters.com, apnews.com, cnbc.com, marketwatch.com,
  bloomberg.com) is provided in PHASE_INPUTS. Ground on it, carry its source URLs into
  the `sources` field, and do not try to fetch its pages yourself. If no `web_grounding`
  is present, say so and lower conviction.
- **Prior document** — `fetch_prior_document(document_key="alt-sentiment-news")` once
  reads yesterday's body for narrative continuity. There is no X/Twitter, Reddit,
  Polymarket or Google Trends tool in this loop; those signals reach you only through the
  `web_grounding` block.

## Purpose
Run this skill **before** macro and segment analysis. Its output colors how downstream segments interpret ambiguous signals. Sentiment extremes (euphoria/panic) can override technical/fundamental reads.

## Inputs
- The `web_grounding` block in PHASE_INPUTS (news, narrative, positioning colour)
- Your own prior document, for narrative continuity (one fetch, see Tools above)
- `docs/ops/data-sources.md` — repository provenance for a maintainer (the list of
  tracked accounts and signal sources); NOT retrievable by a tool.

---

## Research Steps

### 1. Market Headline Scan (Last 24h)
Search for the top 3-5 market-moving headlines from the past 24 hours:
- What is the dominant narrative today?
- Is fear or greed driving the conversation?
- Any surprise developments (geopolitical, economic, earnings, policy) vs prior expectations?
- Are markets reacting to **new information** or repricing on **narrative shift** with no new data?

### 2. Positioning Colour
Report only what the `web_grounding` block and the prior document actually state about
prediction markets, sentiment, and retail/pro flows. Name the source for each. If a
signal (Polymarket odds, an X/KOL read, retail sentiment) is not in the grounding, write
that it is unavailable — do not search for it.

### 3. Narrative Continuity
Read the prior document once. What changed since yesterday: a new catalyst, a reversal of
a prior read, or the same story continuing? Note the shift explicitly.

### 4. Cross-Asset Coherence
Does the narrative cohere across equities, rates, FX and crypto as described in the
grounding, or do they conflict?

### 5. News Sentiment Scoring
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
Prediction markets, sentiment, retail/pro — only what the grounding actually states.

## Implication for today's research
How this should color downstream segment reads.
```
