---
type: quickstart
title: digiquant Quickstart
description: Run digiquant CLI backtest and optimize smokes, run the safe unit subset, and understand the data layout.
tags: [digiquant, quickstart, backtest]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-3cca7b16d985d38458390d9a
    resource: repo://digiquant/AGENTS.md
  - id: openwiki-source-f049bd9504f8ed6c09ceb7ff
    resource: repo://digiquant/ARCHITECTURE.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiquant Quickstart

digiquant (port 8001) needs OHLCV data and (for real engine runs) the
Nautilus extra. Everything below stays on research/backtest paths —
**never touch `brokers/` live-trading code without a human gate.**

## 1. Smoke tests

```bash
digiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv -v
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m grid -n 10
```

Strategies resolve through the alias map (`ema`, `s`,
`mean_reversion_tech` → `ema_cross`); six registered families ship in
`strategies/` plus the SDCA engine.

## 2. Service and tests

```bash
make stack-local     # digiquant on :8001 (or make up)
curl -s http://localhost:8001/healthz
pytest tests/ -m unit -k "digiquant" -v
```

**Linux caveat (#42):** real `BacktestEngine` runs can SIGABRT under
pytest on Linux (uvloop/signal-handler clash). Prefer `make
test-baseline` plus targeted `tests/dq` unit files; engine integration
tests skip on Linux CI.

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
