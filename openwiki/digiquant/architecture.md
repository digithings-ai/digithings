---
type: service-architecture
title: digiquant Architecture
description: Quant engine design of digiquant — ordered pipeline ownership, NautilusTrader boundary, and module map.
tags: [digiquant, quant, nautilus, architecture]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-f049bd9504f8ed6c09ceb7ff
    resource: repo://digiquant/ARCHITECTURE.md
  - id: openwiki-source-f19c772be6fdd923ef60285a
    resource: repo://digiquant/pyproject.toml
  - id: openwiki-source-ad7069db20f551fc3aab1e24
    resource: repo://digiquant/src/digiquant/graph/pipeline.py
  - id: openwiki-source-35b5233c795203b14b0addda
    resource: repo://digiquant/src/digiquant/nautilus_runner.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiquant Architecture

digiquant (port 8001) is the deterministic quant engine: it owns the
ordered pipeline **validate → backtest → optimize → export**, and no
other service may make performance claims (Sharpe, PnL, trade count)
without a result originating here. Its internal LangGraph pipeline is
local and synchronous — sequencing its own steps — while digigraph
decides *when* to call it from outside.

## Pipeline ownership

`graph/pipeline.py` builds a `StateGraph` over `QuantPipelineState` with
`node_validate → node_backtest → node_optimize → node_export` and
`route_after_*` guards that never skip validation and never optimize
before a backtest. `node_backtest` falls through to `None` when
`nautilus_trader` is not importable — the engine is an optional extra,
not a hard dependency.

## NautilusTrader boundary

Nautilus (`nautilus_trader>=1.190,<2` via `digiquant[nautilus]`, 2.x
excluded for its async-first breaking changes) is the sole backtest and
live-trade engine: Rust-core event loop, `BacktestEngine.run()` in the
current thread, bar-driven replay through `BarDataWrangler` into
strategy `on_bar()` callbacks. `nautilus_runner.py` loads OHLCV with
Polars, crosses to pandas **only** at `BarDataWrangler.process()` (which
requires a pandas frame with a UTC timestamp index), and reassembles
results back into Polars — a deliberate, documented exception to the
Polars-only rule, mirrored by a path allowlist for tearsheet and
research bridges.

**Linux caveat (#42):** `BacktestEngine.run()` registers C-level signal
handlers that clash with uvloop under `uvicorn[standard]`, aborting with
SIGABRT. `tests/dq/conftest.py` resets the asyncio policy for the suite,
and engine integration tests skip on Linux CI.

## Module map (selected)

| Area | Role |
|------|------|
| `graph/` | Local pipeline StateGraph |
| `strategies/` | Nautilus Actor strategies + registry + aliases |
| `strategies/sdca/` | Strategic-DCA engine (Nautilus-free core, thin wrapper) |
| `research/` + `portfolio/` | Research and portfolio sub-graphs, dashboard backend |
| `dashboard/` | Replay, edit-mode, attention-plan server modules |
| `brokers/` | **Human gate** — live-trading adapters, never automated |
| `data/` | Price-history cache, store accessors |
| `backtest.py`, `optimize.py`, `export.py` | Service entry points |
| `addm.py` | ADDM drift detection + Sharpe history |
| `mcp_server.py`, `orchestrator_tools.py` | MCP + federated tool surfaces |
| `cli/` | Operator CLI (backtest, optimize, on-chain, SDCA) |

## Non-negotiable boundaries

Nautilus only (no second backtest path); Polars except allowlisted
bridges; strategies implement the Nautilus Actor interface; pipeline
ordering sacrosanct; Group A book reads pin `workspace_id`; broker
adapters never run without a human gate.
