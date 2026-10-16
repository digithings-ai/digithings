---
type: "Reference"
title: "digiquant Quickstart"
openwiki_generated: true
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
---


# digiquant Quickstart

digiquant (port 8001) is the deterministic quant engine. It needs OHLCV CSV
data and (for real engine runs) the `nautilus` extra
(`pip install -e "digiquant[nautilus]"`). Everything below stays on
research/backtest paths — **never touch `brokers/` live-trading code without
a human gate.**

## 1. Smoke tests

```bash
digiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv -v
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m grid -n 10
```

Strategies resolve through the alias map (`ema`, `s`,
`mean_reversion_tech` → `ema_cross`); six registered families ship in
`strategies/` plus the SDCA engine.

## 2. Data

Default CSVs in `digiquant/data/` are **synthetic** (deterministic
oscillator pattern), which is adversarial to momentum strategies. Use
real market data for meaningful results:

```bash
python digiquant/scripts/fetch_real_ohlcv.py --symbols AAPL MSFT \
  --start 2024-01-01 --end 2024-12-31
```

CSV format: `timestamp, open, high, low, close, volume, symbol`.

## 3. Service and tests

```bash
make stack-local  # digiquant on :8001 (host, no Docker)
# or: make up      # Docker Compose stack
curl -s http://localhost:8001/healthz
pytest tests/ -m unit -k "digiquant" -v
```

**Linux caveat (#42):** real `BacktestEngine` runs can SIGABRT under
pytest on Linux (uvloop/signal-handler clash: Nautilus's Rust runtime and
uvloop both claim POSIX signal handlers). Prefer `make test-baseline`
plus targeted `tests/dq` unit files; the three engine integration tests
skip on Linux CI (`CI=true`).

## 4. Gates

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
