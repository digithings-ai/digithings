# DigiClone seed brief: gold (XAU) and systematic trading context

This file is **curated narrative** for local DigiSearch indexing (DigiClone / literature-style ideation).
It is **not** financial advice and **not** backtest results. Always run DigiQuant for empirical metrics.

## Gold as a risk asset

- Gold spot and gold-linked ETFs (e.g. GLD-style proxies) are often used as **drawdown hedges** and **inflation narratives**; short-horizon behavior is driven by real yields, USD, and flows.
- **Trend** and **medium-frequency momentum** are common themes in managed-futures and CTA literature; **mean-reversion** can appear on shorter intraday horizons but is regime-dependent.

## Strategy families to discuss (not performance claims)

1. **Cross-sectional / time-series momentum** on gold or a basket including gold.
2. **Moving-average crossover** and **MACD-style** trend filters (implemented in DigiQuant as `ema_cross`, `macd_trend`).
3. **Mean reversion** via band-type rules (e.g. Bollinger-style; DigiQuant `bollinger_mr`).
4. **Volatility-scaled position sizing** — conceptually important; parameterize via `trade_size` in experiments.

## Citations habit

When answering from RAG, cite **document titles or sources** from DigiSearch hits. Never invent Sharpe ratios or drawdowns; point users to **DigiQuant backtests** after OHLCV is available.
