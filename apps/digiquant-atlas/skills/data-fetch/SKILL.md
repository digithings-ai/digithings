---
name: data-fetch
description: >
  Systematic market data fetch. Downloads live quotes, technicals, and macro series using free
  public APIs (yfinance + US Treasury XML) before the analysis pipeline starts. Produces structured
  JSON + human-readable markdown summaries (legacy archive) and Supabase tables (DB-first). Downstream skills
  read these files FIRST instead of web-browsing for prices and yields.
  Triggers: automatically as Step 0 of every daily pipeline via cowork-daily-prompt.txt.
  Manual: "fetch market data", "refresh data", "run fetch-market-data.sh".
---

# SKILL-data-fetch — Systematic Market Data Layer

This skill describes the data layer that grounds every pipeline run in accurate, systematic numbers.
The fetch scripts run before any analysis phase and produce files that agents read as authoritative
numerical anchors — replacing ad-hoc web browsing for prices, RSI, yield curve levels, and VIX.

---

## Why This Layer Exists

Without it, agents web-browse for each price individually — which is slow, inconsistent, and can
produce stale or incorrect values from article summaries rather than actual price feeds. With this
layer, every agent reads the same source-of-truth JSON/Markdown files fetched right before the run.

---

## Scripts (legacy archive generators)

| Script | What It Does |
|--------|-------------|
| `scripts/preload-history.py` | **Daily (CI)**: `--supabase --supabase-sync` gap-fills from latest `price_history` per ticker and backfills new symbols (`--new-ticker-period max`). **Local**: `--period 2y` etc. or `--refresh` for cache-only stale refresh. |
| `scripts/fetch-quotes.py [date]` | **Daily**: loads cached history, fetches only the latest missing days, appends to cache, then computes RSI(14), MACD, SMA20/50/200, ATR(14), Bollinger Bands via pandas-ta. Falls back to 3-month bulk download if no cache exists. |
| `scripts/fetch-macro.py [date]` | Fetches full US yield curve (US Treasury public XML API, no auth) + VIX, SKEW, crude, gold, NatGas, BTC, ETH, FX pairs via yfinance |
| `scripts/fetch-market-data.sh [date]` | Orchestrator — auto-seeds cache on first run, then runs both fetch scripts; may write transient JSON under `data/agent-cache/daily/.../data/` (gitignored; optional — DB-first runs use Supabase). Pass `--preload` to force a full cache rebuild. |

---

## How to Run

```bash
# First-time setup — preload 2yr price history cache:
python3 scripts/preload-history.py              # all watchlist tickers, 2yr
python3 scripts/preload-history.py --period 5y   # deeper history
python3 scripts/preload-history.py --ticker SPY  # single ticker
python3 scripts/preload-history.py --refresh     # only update stale (>7d) tickers

# Standard daily run (today) — incremental update from cache (writes legacy archive-style summaries):
./scripts/fetch-market-data.sh

# Specific date:
./scripts/fetch-market-data.sh 2026-04-06

# Force full cache rebuild:
./scripts/fetch-market-data.sh --preload

# Dependencies (one-time setup):
pip install -r requirements.txt
```

### Price History Cache

The cache lives at `data/price-history/{TICKER}.csv` — one CSV per ticker with columns: Date, Open, High, Low, Close, Volume. Benefits:

- **SMA200 accuracy**: with 2yr of data, the 200-day SMA is fully warmed up (3-month window only had ~63 trading days)
- **True 52-week high/low**: the range high/low now reflects the actual cached window, not just 3 months
- **Speed**: daily runs download 1–5 new rows per ticker instead of ~63 rows × 70 tickers
- **Resilience**: if yfinance is rate-limited, the cache still provides yesterday's data for technicals

The cache directory is in `.gitignore` (derived data). Run `preload-history.py` to regenerate.

### Sandbox / CI Alternative (no yfinance)

When `fetch-market-data.sh` fails (sandboxed agents, CI, missing yfinance), use the MCP-based
data fetch instead. See **`skills/mcp-data-fetch/SKILL.md`** for full instructions.

DB-first preference: read from Supabase `price_history`, `price_technicals`, and **`macro_series_observations`** (FRED-aligned yields, credit, VIX, FX, crypto Fear & Greed — see `config/macro_series.yaml`) first.

---

## Supabase as Primary Data Source (post-April 2026)

A GitHub Actions workflow runs every trading day at **00:00 UTC** (~**8:00 PM Eastern** during EDT,
~**7:00 PM Eastern** during EST — after US cash close). It fetches OHLCV for all 56 watchlist tickers and computes 35 TA indicators, writing
both into Supabase. The same job then ingests **macro / FX / sentiment / official Treasury curve** into `macro_series_observations`. **SEC issuer filings** are **not** batch-loaded (ETF-heavy watchlist); agents check EDGAR **ad hoc** during research / delta / deep dives when a stock or sector story warrants it (see `skills/research-daily`, `skills/daily-delta`, `skills/deep-dive`; optional **`sec-edgar`** MCP).

### Tables

| Table | Contents | Refresh |
|-------|----------|---------|
| `price_history` | OHLCV rows per ticker per date | Daily, 00:00 UTC (~8 PM ET EDT) |
| `price_technicals` | 35 TA indicators per ticker per date | Daily, after price_history |
| `macro_series_observations` | FRED, Frankfurter, crypto F&G, **`us_treasury`** / **`treasury_market`** (`YC/…`) | Daily, after price_technicals |

### Example MCP queries (use `mcp_supabase_execute_sql`)

```sql
-- Latest indicators for all tickers
SELECT * FROM price_technicals
WHERE date = (SELECT MAX(date) FROM price_technicals);

-- Single ticker detail
SELECT * FROM price_technicals
WHERE ticker = 'SPY'
ORDER BY date DESC
LIMIT 5;

-- Check freshness
SELECT MAX(date) AS latest_date, COUNT(DISTINCT ticker) AS tickers
FROM price_technicals;

-- Latest FRED 10Y and VIX (observation dates vary by series)
SELECT series_id, obs_date, value, unit
FROM macro_series_observations
WHERE source = 'fred' AND series_id IN ('DGS10', 'VIXCLS')
ORDER BY series_id, obs_date DESC
LIMIT 6;

-- FX vs USD (Frankfurter)
SELECT series_id, obs_date, value
FROM macro_series_observations
WHERE source = 'frankfurter' AND obs_date = (SELECT MAX(obs_date) FROM macro_series_observations WHERE source = 'frankfurter');

-- Crypto Fear & Greed latest
SELECT value, meta, obs_date
FROM macro_series_observations
WHERE source = 'crypto_fear_greed'
ORDER BY obs_date DESC
LIMIT 3;

-- Treasury 10Y (prefer official XML when present; else Yahoo proxy)
SELECT source, obs_date, value FROM macro_series_observations
WHERE series_id = 'YC/10Y' AND source IN ('us_treasury', 'treasury_market')
ORDER BY obs_date DESC, source LIMIT 8;

```

---

## Local fetch cache (gitignored)

When you run fetch scripts locally, they may write under `data/agent-cache/daily/YYYY-MM-DD/data/` (not committed). Prefer **Supabase** `price_history` / `price_technicals` when available.

Files (when present on disk):

| File | Contents |
|------|---------|
| `quotes.json` | Full technical snapshot for every watchlist ticker (JSON array) |
| `quotes-summary.md` | Human-readable table sorted by 1D%, plus UPTREND/DOWNTREND/MIXED buckets |
| `macro.json` | Yield curve 1M–30Y, spreads, VIX, SKEW, commodities, crypto, FX (JSON) |
| `macro-summary.md` | Human-readable yield curve table + spread signals + all macro series |

---

## Agent Instructions

When the data files exist, **always read them first** before web-searching for numbers:

1. **For prices, RSI, MACD, trend**: Read `quotes-summary.md` — find the ticker row.
2. **For yield curve, VIX, commodities, FX**: Read `macro-summary.md` — values are in tables.
3. **Web search only for**:
   - News catalysts and narrative (why prices moved)
   - Economic calendar actual vs. consensus
   - Fed speeches, analyst upgrades/downgrades
   - Earnings reactions and forward guidance
   - Data not in the files (e.g., breadth indicators, McClellan oscillator)

---

## Dependency Installation

```bash
pip install -r requirements.txt
```

