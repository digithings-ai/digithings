# DigiQuant / Atlas — Spec

**Sub-graph of digiquant (port 8001)**  
**Role:** Portfolio management, strategy optimization, and backtest orchestration sub-graph.

## Capabilities

- Strategy backtesting via NautilusTrader (synchronous and async job-based)
- Parameter optimization
- Pipeline execution: backtest → optimize → export in sequence
- Drift detection against ADDM baseline
- Async job progress and result retrieval

## Invariants

- NautilusTrader is the only backtest/optimize engine — no custom loops
- Polars-only for all data manipulation (never pandas)
- Atlas lives at `digiquant/src/digiquant/olympus/atlas/` — the old `apps/digiquant-atlas/` path is dead
- Never touch live-trading paths without explicit human approval

## Public API (via digiquant server)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/run_backtest` | Run synchronous backtest |
| POST | `/backtest/start` | Start async backtest job |
| GET | `/backtest/{job_id}/progress` | Poll job progress |
| GET | `/backtest/{job_id}/result` | Fetch completed job result |
| POST | `/run_optimize` | Run parameter optimization |
| POST | `/run_pipeline` | Full backtest→optimize→export pipeline |
| POST | `/run_export` | Export strategy artefacts |
| GET | `/check_drift` | Check portfolio drift against baseline |
| GET | `/healthz` | Liveness probe |

## Data Models

All request/response models use Pydantic v2 with strict typing. Results are Polars DataFrames serialised to JSON (records orientation).
