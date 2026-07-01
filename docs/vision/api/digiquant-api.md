---
title: "digiquant — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - core
relevance:
  - digiquant
---
# digiquant — API reference

> Strategy research that ends in an order, not a markdown file.

**Role:** Quant engine · NautilusTrader · **Tier:** core

## Overview
Atlas runs scheduled research, Hermes turns it into signals, Kairos executes on a NautilusTrader core, with Optuna driving optimization.

Every step writes an immutable audit trail; live trading stays loopback-only until a human flips the gate.

## Authentication
Backtest/optimize/pipeline routes accept a digikey JWT (optional in passthrough mode). Async jobs stream progress over SSE.

- `digiquant:backtest` — /run_backtest, /backtest/*, /v1/jobs/*, /v1/orchestrator_tools
- `digiquant:optimize` — /run_optimize, /run_pipeline, /v1/workflow

## Run locally
```bash
docker compose up -d digiquant
```

```bash
uvicorn digiquant.server:app
```

## Configuration
- `DIGIQUANT_DATA_DIR` (default `/app/data`): Directory of OHLCV CSVs for backtests.
- `DIGIKEY_JWKS_URL`: JWT public-key (JWKS) endpoint.
- `DIGIQUANT_ALLOW_EXPORT` (default `1`): Enable export of strategy configs.

## Endpoints

Base URL: `$DIGIQUANT_URL` (the service URL from docker-compose.yml).

### GET /strategies
List registered NautilusTrader strategies.

auth: none · rate: 30/min/IP

Response example:
```json
[{ "name": "mean_reversion_tech", "aliases": [], "description": "...", "default_params": {} }]
```

```bash
curl $DIGIQUANT_URL/strategies
```

### POST /run_backtest
Synchronous backtest. Returns a BacktestResult.

auth: digiquant:backtest (optional) · rate: 10/min/IP

Request:
- `strategy_name` (string) — required: Registered strategy id.
- `symbols` (string[]) — required: Instruments to test.
- `data_dir` (string): Directory of {symbol}.csv OHLCV files.
- `strategy_params` (object): Strategy parameter overrides.
- `full_tearsheet` (boolean): Include extended charts (default true).

Response:
- `run_id` (string): Unique run identifier.
- `total_pnl` (number): Total P&L.
- `sharpe_ratio` (number | null): Sharpe ratio.
- `num_trades` (integer): Number of trades executed.
- `status` (string): "completed" | "failed".

```bash
curl -X POST $DIGIQUANT_URL/run_backtest \
  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \
  -d '{"strategy_name":"mean_reversion_tech","symbols":["AAPL"]}'
```

```python
r = httpx.post(
    f"{os.environ['DIGIQUANT_URL']}/run_backtest",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"strategy_name": "mean_reversion_tech", "symbols": ["AAPL"]},
    timeout=300,
)
print(r.json()["sharpe_ratio"])
```

### POST /backtest/start
Submit an async backtest job; returns {job_id}. Poll progress over SSE.

auth: none · rate: 10/min/IP

Response example:
```json
{ "job_id": "..." }
```

### GET /backtest/{job_id}/progress
SSE stream of backtest progress events (JSON frames).

auth: none

```bash
curl -N $DIGIQUANT_URL/backtest/$JOB_ID/progress
```

### POST /run_optimize
Parameter optimization (grid / bayesian / random). Returns best params.

auth: digiquant:optimize (optional) · rate: 10/min/IP

Request:
- `strategy_name` (string) — required: Registered strategy id.
- `symbols` (string[]) — required: Instruments.
- `method` (string): "grid" | "bayesian" | "random" (default grid).
- `n_trials` (integer): Trial budget (default 50).
- `objective` (string): "sharpe" | "return" | "pnl".

Response:
- `best_params` (object): Best parameter set found.
- `best_sharpe` (number | null): Objective value at best params.
- `num_evaluations` (integer): Trials evaluated.

### POST /run_pipeline
Full pipeline: backtest → optimize → export.

auth: digiquant:optimize (optional) · rate: 10/min/IP

## Stack
NautilusTrader, Optuna, LangGraph, Polars, yfinance, Supabase

## Related
digigraph, digistore, digilink

## Links
- [digiquant.io](https://digiquant.io)
- [Source](https://github.com/digithings-ai)

See also [[digiquant]].
