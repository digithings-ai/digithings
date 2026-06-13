# Phase D — free-source ingestion replaces paid agentic search

**Goal:** cut a daily delta run from ~$3 to **<$1** *without reducing research
capability* (owner directive: optimize/replace, never narrow). ~$2.44 of the
baseline is xAI agentic `web_search`/`x_search` ($5 per 1k server-side
invocations; one call spawns dozens). The fix: push all fetching off the hot
path to the existing GitHub Actions cron, store in Supabase, and have research
phases read via in-process data tools instead of paid search.

## The seam

`phases/_node_factory.py:build_grounding()` — per segment, flip the
`SegmentNodeSpec` from `live_search=True` to `use_data_tools=True`. Run time
becomes flat Supabase SELECTs; the xAI internal-invocation multiplier disappears
for converted segments. Scalar series reuse `macro_series_observations`
(migration 015); relational data gets new tables.

## Capability guarantee (fail-soft-to-paid)

Every converted segment either reads fresh ingested data **or** (for
fallback-flagged segments) falls through to the original paid call when the
table is stale/empty. A dead free source raises cost for that one segment but
never yields an ungrounded/degraded output. Most segments get *strictly better*
data — exact regulator/central-bank integers vs lossy prose summaries.

## PR sequence (greedy by leverage)

| PR | Segment(s) | Source | New infra |
|----|-----------|--------|-----------|
| **PR-1** (this) | alt-options-derivatives | FRED vol complex (VIX/VIX3M/VXN/GVZ/OVX) | none — FRED job + `get_macro_series` exist |
| PR-2 | macro, international | FRED non-US M2 + CB balance sheets; intl index levels (yfinance→price_history) | + the ingested-first/paid-fallback helper |
| PR-3 | alt-cta-positioning | CFTC COT (Socrata SODA) | `cftc_ingest.py`, `get_cot_positioning` tool, weekly cron |
| PR-4 | inst-institutional-flows, inst-hedge-fund-intel | SEC EDGAR (13F / 13D-G / Form 4) | `edgar_ingest.py`, `sec_filings_positions` table, 2 tools |
| PR-5 | alt-politician-signals | House Clerk STOCK Act ZIP | `congress_ingest.py`, `congress_trades` table, tool; keep trimmed Fed/Treasury fallback search |
| PR-6 | alt-sentiment-news | GDELT + RSS + FinBERT scoring | `news_ingest.py`, `news_sentiment_daily` table, tool |
| PR-7 (opt) | alt-ai-portfolios | X archiver (best-effort) | `ai_portfolio_x_posts`; keep x_search fallback |
| PR-8 | — | freshness/staleness panel + fallback-fired alert; final docs | — |

## Deliberately-retained paid fallbacks (the honest gaps)

- **alt-ai-portfolios x_search** (~$0.12/day) — X has no robust free read API.
- **Fed/Treasury policy *rhetoric*** — a domain-trimmed (`federalreserve.gov` /
  `treasury.gov` / `sec.gov`), `max_results=3`, **fallback-only** `web_search`,
  fired only when the ingested layer is stale. Data series capture the numbers,
  not "Powell signaled a cut at today's presser."

The pipeline clears <$1/day even if both stay fully paid.

## Known gaps / risks (see the design workflow output for detail)

- Put/call ratio & dealer GEX: no free source (paid search never had real GEX
  either). VIX term structure + cross-asset vol proxy it; state when absent.
- China M2 (`MYAGM2CNM189N` discontinued — verify `MABMM301CNM189S`), Reuters/AP
  RSS dead (use Google News RSS + GDELT tone), 13F/COT/congress freshness lags
  are structural — store 2+ periods, compute deltas.
- **Implementer must add the new data hosts to
  `scripts/claude-hooks/network-host-guard.sh`**: `api.gdeltproject.org`,
  `data.gdeltproject.org`, `efts.sec.gov`, `data.sec.gov`, `www.sec.gov`,
  `publicreporting.cftc.gov`, `disclosures-clerk.house.gov`,
  `production.dataviz.cnn.io`, `news.google.com`, RSS feed hosts. SEC/House
  require a descriptive `User-Agent` (403 without).
