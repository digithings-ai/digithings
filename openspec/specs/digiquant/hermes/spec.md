# DigiQuant / Hermes — Spec

**Sub-graph of digiquant (port 8001)**  
**Role:** Market data ingestion, signal generation, and strategy registry sub-graph.

## Capabilities

- Strategy registry: list registered strategy configs
- Export of strategy artefacts for downstream consumers
- Technical indicator and signal computation (Polars-based)

## Invariants

- Polars-only for all data manipulation
- Hermes lives at `digiquant/src/digiquant/olympus/hermes/`
- Signal computation is stateless — no side effects beyond logging
- Strategy configs are Pydantic v2 models; never raw dicts

## Public API (via digiquant server)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/strategies` | List registered strategies |
| POST | `/run_export` | Export strategy artefacts |
| GET | `/healthz` | Liveness probe |

## Extension Pattern

Add new signal types as pure functions that accept a Polars DataFrame and return a Polars DataFrame. Register them in the signal registry — do not add ad-hoc endpoints.
