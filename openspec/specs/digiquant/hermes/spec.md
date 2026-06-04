# DigiQuant / Hermes — Spec

**Sub-graph of digiquant (port 8001)**  
**Role:** Market data ingestion, signal generation, and strategy registry sub-graph.

## Capabilities

- Market data feed management (historical + streaming)
- Technical indicator and signal computation (Polars-based)
- Strategy registry: register, list, retrieve strategy configs
- Export of strategy artefacts for downstream consumers

## Invariants

- Polars-only for all data manipulation
- Hermes lives at `digiquant/src/digiquant/hermes/`
- Signal computation is stateless — no side effects beyond logging
- Strategy configs are Pydantic v2 models; never raw dicts

## Public API (via digiquant server)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/strategies` | List registered strategies |
| POST | `/strategies` | Register a new strategy |
| GET | `/strategies/{id}` | Retrieve strategy config |
| POST | `/run_export` | Export strategy artefacts |

## Extension Pattern

Add new signal types as pure functions that accept a Polars DataFrame and return a Polars DataFrame. Register them in the signal registry — do not add ad-hoc endpoints.
