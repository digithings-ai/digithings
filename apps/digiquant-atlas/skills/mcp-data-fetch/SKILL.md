---
name: mcp-data-fetch
description: >
  Sandbox-compatible market data fetch using MCP tool connections (Alpha Vantage, FRED, CoinGecko,
  Frankfurter) instead of yfinance Python scripts. Produces the same quotes.json and macro.json
  output schema that downstream skills expect. Use when yfinance/pandas-ta are unavailable (sandbox,
  CI environments) or when fetch-market-data.sh fails.
  Triggers: "fetch data via MCP", "sandbox data fetch", or automatically when the orchestrator
  Data Layer Check detects missing data files and shell scripts cannot run.
---

# SKILL-mcp-data-fetch — Sandbox Market Data via MCP Tools

This skill replaces the Python-based data fetch (`fetch-quotes.py` + `fetch-macro.py`) with
direct MCP tool calls. It produces **identical output files** (`quotes.json`, `macro.json`,
`quotes-summary.md`, `macro-summary.md`) so downstream skills work without changes.

**When to use**: Any environment where `yfinance` or `pandas-ta` cannot be installed or cannot
reach Yahoo Finance APIs (sandboxed agents, CI, restricted networks).

**When NOT to use**: If `./scripts/fetch-market-data.sh` succeeds, prefer it — it produces richer
data (full technicals, 3-month OHLCV history, Bollinger Bands, ATR).

---

## MCP Tool → Data Mapping

| Data Need | MCP Tool | Notes |
|-----------|----------|-------|
| US Treasury yield curve | `mcp_fred_fred_series_observations` | Series: DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30 |
| VIX | `mcp_fred_fred_series_observations` | Series: VIXCLS |
| Yield curve spreads | `mcp_fred_fred_series_observations` | Series: T10Y2Y (2s10s), T10Y3M (3m10y) |
| Stock/ETF prices | `mcp_alpha-vantage_get_stock_price` | 1 call per ticker — prioritize portfolio + benchmarks |
| Technical indicators | `mcp_alpha-vantage_get_technical_indicator` | RSI, SMA, EMA, MACD — 1 call per ticker×indicator |
| BTC, ETH prices | `mcp_coingecko_execute` | Single call gets both |
| FX rates | `mcp_frankfurter-f_get_latest_exchange_rates` | Single call for all pairs (base=USD) |
| Inflation breakevens | `mcp_fred_fred_series_observations` | T10YIE, T5YIE, DFII10 |

---

## Step 0A — Check Supabase First (Zero-Cost Technicals)

Before consuming any Alpha Vantage budget, check whether the GitHub Actions workflow has already
run recently and pre-computed all 35 TA indicators for all watchlist tickers:

```sql
-- Run via mcp_supabase_execute_sql:
SELECT MAX(date) AS latest_date, COUNT(DISTINCT ticker) AS tickers
FROM price_technicals;
```

**If `latest_date` is within the last 3 calendar days**: Query `price_technicals` directly instead of
calling Alpha Vantage for RSI/MACD/SMA/EMA. See `skills/data-fetch/SKILL.md` for the column reference.

---

## Rate Limit Awareness

| MCP Server | Free Tier Limit | Strategy |
|------------|----------------|----------|
| **Supabase** | Unlimited (own DB) | **Check first** — 35 indicators, 56 tickers, zero cost |
| **FRED** | 120 requests/min | Generous — fetch all macro series freely |
| **Frankfurter** | Unlimited | Single call returns all FX rates |
| **CoinGecko** | ~30 calls/min | Single call for BTC + ETH is sufficient |
| **Alpha Vantage** | 25 calls/day (free) | **Budget carefully** |

---

## Step-by-Step Procedure (high level)

1. If you need on-disk JSON for validation, use a temp directory or (legacy) `data/agent-cache/daily/{DATE}/data/` — not required when publishing straight to Supabase (`data/README.md`).
2. Fetch yield curve + spreads + VIX via FRED.
3. Fetch FX via Frankfurter.
4. Fetch BTC/ETH via CoinGecko.
5. Fetch priority ETF prices (portfolio + benchmarks + selected sectors) via Alpha Vantage.
6. If budget remains (and Supabase isn’t current), fetch RSI/SMA technicals for portfolio tickers.
7. Write `macro.json`, `quotes.json`, and the two summary markdown files.

---

## Completeness Comparison

| Feature | yfinance (`fetch-market-data.sh`) | MCP (this skill) |
|---------|-----------------------------------|------------------|
| Tickers covered | ~60 (full watchlist) | ~15–25 (prioritized) |
| Price data | ✅ latest close | ✅ quote |
| 1D % change | ✅ computed from OHLCV | ⚠️ limited |
| RSI(14) | ✅ pandas-ta | ⚠️ Alpha Vantage (if budget) |
| MACD | ✅ pandas-ta | ⚠️ limited |
| SMA 20/50/200 | ✅ pandas-ta | ⚠️ Alpha Vantage (if budget) |
| ATR, Bollinger | ✅ pandas-ta | ❌ not available |
| Volume ratio | ✅ computed | ❌ not available |
| Yield curve | ✅ Treasury XML API | ✅ FRED |
| VIX | ✅ yfinance (^VIX) | ✅ FRED (may lag 1 day) |
| SKEW | ✅ yfinance (^SKEW) | ❌ not in FRED |
| Crypto | ✅ yfinance | ✅ CoinGecko |
| FX rates | ✅ yfinance | ✅ Frankfurter |

