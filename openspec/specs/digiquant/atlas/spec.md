# DigiQuant / Atlas — Spec

**Sub-graph of digiquant (port 8001)**  
**Role:** Portfolio management, strategy optimization, and backtest orchestration sub-graph.

## Capabilities

- Portfolio construction and weight allocation
- Strategy backtesting via NautilusTrader
- Parameter optimization (grid, Bayesian)
- Pipeline execution: backtest → optimize → export in sequence
- Results persistence and retrieval

## Invariants

- NautilusTrader is the only backtest/optimize engine — no custom loops
- Polars-only for all data manipulation (never pandas)
- Atlas lives at `digiquant/src/digiquant/atlas/` — the old `apps/digiquant-atlas/` path is dead
- Never touch live-trading paths without explicit human approval

## Public API (via digiquant server)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/atlas/backtest` | Run backtest for a strategy |
| POST | `/v1/atlas/optimize` | Parameter search |
| POST | `/v1/atlas/pipeline` | Full backtest→optimize→export pipeline |
| GET | `/v1/atlas/results/{id}` | Fetch run results |

## Data Models

All request/response models use Pydantic v2 with strict typing. Results are Polars DataFrames serialised to JSON (records orientation).
