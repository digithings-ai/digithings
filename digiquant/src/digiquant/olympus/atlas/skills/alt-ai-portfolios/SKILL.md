---
name: alt-data-ai-portfolios
description: Tracks AI-run / AI-driven investment portfolio accounts on X (Claude/Grok/Gemini and multi-model aggregators) that post live equity holdings and named-ticker picks. A proxy for what OTHER AI investment systems are picking at the stock level — Olympus trades ETFs, so the value is the implied sector/theme tilt. Phase-1 alt-data segment.
---

# AI Portfolios Sub-Agent (cross-model stock-bias proxy)

## Grounding (use first)

A pre-fetched **`web_grounding`** block is provided in PHASE_INPUTS when available — it is
an **x_search read of the tracked AI-portfolio accounts' latest posts** (per-account
holdings/changes with named tickers + a cross-account consensus + sector tilt), each claim
cited to its X post URL. Ground every claim on this block; carry its X post URLs into the
output's `sources`. Do **not** assert a holding that is not in the block. If `web_grounding`
is absent or empty, return empty findings and say so in `notes`.

## What to produce

- **`per_account`** — for each account that posted in-window: `handle`, `model`, `picks`
  (named tickers held/added/trimmed), `stance`, `as_of`. Mark `posted_in_window=false` for
  accounts that were silent or hold no equities (do not infer their book).
- **`consensus_longs`** — tickers named long by 2+ accounts.
- **`sector_tilt`** — roll the stock picks up to sectors/themes (e.g. semis, software,
  energy) — this is the signal the equity/sector phases consume.
- **`divergences`** — where the models disagree.

## Discipline (this is a PROXY, not a recommendation)

- These accounts are **self-selected and performative**; treat as a sentiment/positioning
  proxy only, never as ground truth or a direct call.
- **Weight by credibility**: high-follower, high-activity, multi-model aggregator accounts
  (e.g. @theaiportfolios, @grkportfolio, @ralliesarena) carry more than tiny/low-engagement
  ones (e.g. @theAIportfolio, @geminiportfolio). Say so when one account drives a consensus.
- **Flag staleness**: if a pick is from an old post, lower conviction and note the date.
- Set `bias`/`headline` to reflect the *aggregate* AI-system tilt, with `notes` capturing
  caveats (thin coverage, divergence, stale posts).
