---
type: api-operations-guide
title: digiquant API and Operations
description: digiquant HTTP and MCP surface plus operations — pipeline endpoints, drift checks, sandbox image, and container.
tags: [digiquant, api, mcp, operations]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-7f45b1234a1e80c66e4d2b61
    resource: repo://digiquant/Dockerfile
  - id: openwiki-source-a9751447740cc08ce33e5fc4
    resource: repo://digiquant/Dockerfile.sandbox
  - id: openwiki-source-fe843d7876eed7decd652157
    resource: repo://digiquant/src/digiquant/mcp_server.py
  - id: openwiki-source-90b6f9dfa8d57a7f0b61f0be
    resource: repo://digiquant/src/digiquant/server.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiquant API and Operations

digiquant (port 8001 HTTP, 8767 MCP) exposes the ordered pipeline over
both transports, plus strategy catalog, drift, job, and dashboard-policy
routes. **Human gate:** `digiquant/brokers/` live-trading paths must never
be touched without explicit human approval — this page describes the
research/backtest surface only.

## Pipeline endpoints

- `POST /run_backtest` → `BacktestResult` (requires `data_path` or
  `data_dir`; no defaults). Records Sharpe into ADDM history on success.
- `POST /run_optimize` → `OptimizeResult` (grid/random/bayesian over the
  strategy param spec).
- `POST /run_export` → `ExportResult`; `POST /run_pipeline` runs the full
  validate → backtest → optimize → export chain.
- `POST /backtest/start` + `GET /backtest/{job_id}/progress|result` and
  `POST /jobs/backtest` + `GET /jobs/{job_id}/status` — async job
  variants for long runs.
- `GET /strategies` — registered Nautilus strategies with aliases and
  default params.
- `POST /v1/orchestrator_tools` / `POST /v1/orchestrator_invoke` —
  digigraph's federated entry points.
- Dashboard policy routes (`/v1/dashboard/policy_*` with legacy
  `/v1/olympus/*` aliases) — replay, comparison, gate evaluation,
  governance decisions.

## Drift (ADDM)

`GET /check_drift` accepts `strategy_id`, `baseline_run_id`, and
`current_sharpe`; digiclaw's heartbeat polls it and triggers
re-optimization on `drift_detected`. Drift fires once Sharpe history
holds enough observations. History is an in-process deque today — not
durable across restarts.

## MCP server

`digiquant` MCP tools (backtest, optimize, export, strategy catalog,
risk-index builders) attach via streamable-http on 8767 or stdio,
consumed by IDEs, Claude Desktop, and digiclaw. Requires the
`digiquant[mcp]` extra.

## research sandbox image

`Dockerfile.sandbox` is a **separate** image from the HTTP service:
build-time-baked open-source quant stack (skfolio, riskfolio, TA-Lib with
bundled C wheels, `pandas_ta` shim and `yfinance_retry` on `PYTHONPATH`)
for research agents to execute paper-book code. No live trading, no broker
credentials, no order paths; optional outbound HTTPS for free data only.
Never `pip install` inside agent runs.

## Container

Loopback-bound `:8001`, `/healthz` healthcheck, uvicorn serving
`digiquant.server:app`. Standard digibase middleware applies; Linux hosts
note the Nautilus SIGABRT caveat (#42) for in-process backtests.
