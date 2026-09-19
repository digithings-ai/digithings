---
type: quickstart
title: digiquant Quickstart
description: Run digiquant CLI backtest and optimize smokes, run the safe unit subset, and understand the data layout.
tags: [digiquant, quickstart, backtest]
sources:
  - id: openwiki-source-3cca7b16d985d38458390d9a
    resource: repo://digiquant/AGENTS.md
  - id: openwiki-source-f049bd9504f8ed6c09ceb7ff
    resource: repo://digiquant/ARCHITECTURE.md
  - id: openwiki-source-b23b2f9482c9ae6160099d2a
    resource: repo://digiquant/src/digiquant/cli/__init__.py
  - id: openwiki-source-90b6f9dfa8d57a7f0b61f0be
    resource: repo://digiquant/src/digiquant/server.py
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
---

# digiquant Quickstart

digiquant (port 8001) needs OHLCV data and (for real engine runs) the
Nautilus extra. Everything below stays on research/backtest paths —
**never touch `brokers/` live-trading code without a human gate.**

## 1. Smoke tests

```bash
digiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m grid -n 10
```

Strategies resolve through the alias map (`ema`, `s`,
`mean_reversion_tech` → `ema_cross`). The registry holds ten registered
strategies across nine families — the original six Nautilus-wrapped
strategies (`ema_cross`, `ema_cross_long`, `ema_cross_trailing`,
`rsi_momentum`, `bollinger_mr`, `macd_trend`) plus `m2_liquidity`,
`rs_rotation`, the `slapper` family (BTC/ETH/SOL), and the SDCA engine
(`btc_sdca`).

The CLI resolves `--data-path` and `--data-dir` under
`DIGIQUANT_DATA_ROOT` (defaults to `$CWD`). Data must live inside that
root; the CLI rejects paths that escape it.

CSV columns must include `timestamp`, `open`, `high`, `low`, `close`,
`volume`, plus optional `symbol`. Use
`digiquant.data.loader.generate_synthetic_ohlcv` to create deterministic
test data when real OHLCV is unavailable. `make stack-local` does this
automatically.

## 2. Service and tests

```bash
make stack-local          # digiquant on :8001 (or make up for Docker)
curl -s http://localhost:8001/healthz
pytest tests/dq/ -m unit -v
```

`make stack-local` starts the full host-native stack (digikey, digiquant,
digisearch, digismith, digigraph). It auto-generates synthetic OHLCV
CSVs in `digiquant/data/` when none exist. `make up` builds and starts
the Docker Compose stack instead.

**Linux caveat (#42):** real `BacktestEngine` runs can SIGABRT under
pytest on Linux (uvloop/signal-handler clash). Prefer `make
test-baseline` plus targeted `tests/dq` unit files; engine integration
tests skip on Linux CI. The `tests/dq/conftest.py` resets the asyncio
policy to `DefaultEventLoopPolicy` before the dq suite loads, preventing
uvloop from conflicting with Nautilus's Rust signal handlers.

## 3. Gates

```bash
ruff check digiquant/ && ruff format --check digiquant/
```

Polars everywhere except the documented Nautilus/tearsheet pandas
bridges — no new `pandas` imports outside the allowlist.

## Where next

- [digiquant Architecture](/openwiki/digiquant/architecture.md) —
  pipeline, Nautilus boundary, module map.
- [digiquant Strategies and Backtest](/openwiki/digiquant/strategies-and-backtest.md) —
  registry, aliases, result models.
- [digiquant Research and Portfolio](/openwiki/digiquant/research-and-portfolio.md) —
  sub-graphs and dashboard backend.
- [digiquant API and Operations](/openwiki/digiquant/api-and-operations.md) —
  endpoints, drift, sandbox, container.
