---
type: "Reference"
title: "digiquant API and Operations"
openwiki_generated: true
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-7f45b1234a1e80c66e4d2b61
    resource: repo://digiquant/Dockerfile
  - id: openwiki-source-625fca79ede3d43dd5fce6a3
    resource: repo://digiquant/Dockerfile.mcp
  - id: openwiki-source-a9751447740cc08ce33e5fc4
    resource: repo://digiquant/Dockerfile.sandbox
  - id: openwiki-source-fe843d7876eed7decd652157
    resource: repo://digiquant/src/digiquant/mcp_server.py
  - id: openwiki-source-90b6f9dfa8d57a7f0b61f0be
    resource: repo://digiquant/src/digiquant/server.py
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
  validate → backtest → optimize → export chain via internal LangGraph.
  `POST /v1/workflow` is a versioned alias.
- `POST /backtest/start` + `GET /backtest/{job_id}/progress|result` and
  `POST /v1/jobs/backtest` + `GET /v1/jobs/{job_id}/status` — async job
  variants for long runs. Progress is SSE-streamed (`start`/`done`/`error`
  events with `heartbeat` keep-alive); status returns `running`/`completed`/`failed`.
- `GET /strategies` — registered Nautilus strategies with aliases and
  default params.
- `POST /v1/orchestrator_tools` / `POST /v1/orchestrator_invoke` —
  digigraph's federated entry points. Manifest returns 16 OpenAI-style
  tool schemas (11 digiquant + 5 dashboard policy-replay); invoke
  dispatches by named `tool` field, including `digifetch_*` tools routed
  through the shared Gloomberb dispatcher.
- Dashboard policy routes under `/v1/dashboard/policy_*` with legacy
  `/v1/olympus/*` aliases (`include_in_schema=False`) — replay,
  comparison, gate evaluation, governance decisions. Governance-decisions
  endpoint requires an authenticated DigiAuth principal (no MCP path).

### Rate limiting

Per-IP sliding-window rate limits: pipeline/backtest paths 10 req/min;
`/v1/orchestrator_tools` 30 req/min; default 30 req/min. `/health` and
`/healthz` are exempt. Disable via `DIGI_DISABLE_RATE_LIMIT=1`.

## Drift (ADDM)

`GET /check_drift` accepts `strategy_id`, `baseline_run_id`, and
`current_sharpe`; digiclaw's heartbeat polls it and triggers
re-optimization on `drift_detected`. Drift fires once Sharpe history
holds enough observations. History is an in-process deque today — not
durable across restarts.

## MCP server

`python -m digiquant.mcp_server` serves a FastMCP server (streamable-http
on `127.0.0.1:8767` or `--stdio` for Claude Desktop). Requires the
`digiquant[mcp]` extra. The server runs a **scope-gated** tool registry:

- **`full`** (default, local): all 34+ tools — pipeline (backtest,
  optimize, export, pipeline, strategy catalog), prices/technicals/macro,
  trade levels, research query, SDCA risk-index building and on-chain
  data fetches (Bitview, BGeometrics, CoinMetrics), Coinbase OHLCV fetch,
  BTC power-law fitting, Slapper tearsheet generation, TradingView parity
  validation, dashboard policy-replay tools, plus all 33
  digifetch/Gloomberb enrichment reads.
- **`read`**: only the `READ_SCOPE_TOOLS` frozenset — strategy catalog,
  prices/technicals, macro series, trade levels, research query,
  dashboard policy reads (replay, comparison, gate evaluation), the
  CoinMetrics catalog discovery tool, and the 33 digifetch/Gloomberb
  tools. Compute and mutate tools (backtest, optimize, pipeline, export,
  fetches, fits, tearsheets, policy-replay runs) are excluded.

Scope is selected via `--scope full|read` CLI flag or
`DIGIQUANT_MCP_SCOPE` env.

### Digifetch / Gloomberb enrichment

33 read-scope tools (`digifetch_*`) surface the Gloomberb Cloud API via a
shared env-keyed client factory with pacing, cache, and circuit-breaker.
The client is built once per `(GLOOMBERB_ENABLED, GLOOMBERB_SESSION_COOKIE)`
pair. Tools include: quotes, quotes batch, price history, ticker
financials, options chain, SEC filings, holders, analyst research,
corporate actions, earnings calendar, exchange rate, search, news,
economic calendar, economic series, yield curve, CDS, research search,
Congress trades, transcripts, statements, ticker tweets, tweet search,
venues, screener, 13F funds, 13F holdings, Shiller, proxy statements,
filing events, risk reports, short interest, equity diagnostic, saved
searches. Attribution is carried per §7 of the Gloomberb specification.
The `digifetch_earnings_calendar` tool routes through Yahoo (explicitly
not attributed to Gloomberb). Cloud payloads are delayed up to 15 minutes
and are never a pipeline primary.

Gated tools (holders, analyst, corporate-actions, research-search,
transcripts, statements, tweets, short-interest, equity-diagnostic)
require `GLOOMBERB_SESSION_COOKIE`; some additionally require a Pro plan.
The dispatcher returns typed error envelopes (`auth_required`,
`pro_required`) rather than 400s when credentials are missing.

### Market-data backend

`DIGIQUANT_MARKET_DATA_BACKEND=r2` routes the price/macro MCP tools
(`digiquant_get_price_technicals`, `digiquant_get_macro_series`) through
the R2 history store instead of the default Supabase path. The R2 path
reads versioned, SHA-verified generations sealed at `manifest["as_of"]`,
merged with a live overlap of up to 30 calendar days with settled-close
semantics. A staleness gate rejects reads where the manifest seal is more
than 5 trading days behind the requested `as_of`. The Supabase fallback
remains available when the env var is unset or set to `supabase`.

### SDCA, on-chain, and crypto tools

Compute-scope (full only) tools:
- `digiquant_fit_btc_power_law` — fit BTC power-law valuation rails
- `digiquant_build_sdca_risk_index` — build the SDCA `date`/`risk` parquet
- `digiquant_fit_sdca_weights` — Stage A cycle-window weight fit
- `digiquant_fetch_coinbase_ohlcv` — CCXT Coinbase OHLCV into price cache
- `digiquant_fetch_bitview_series` — BRK/Bitview on-chain day1 series
- `digiquant_fetch_bgeometrics_series` — bitcoin-data.com metrics (rate-limited)
- `digiquant_fetch_coinmetrics_series` — CoinMetrics Community API (CC BY-NC)
- `digiquant_list_coinmetrics_catalog` — CoinMetrics asset/metric discovery (read-scope)
- `digiquant_generate_slapper_tearsheet` — Slapper family backtest + JSON
- `digiquant_validate_slapper_vs_tradingview` — TradingView parity check
- `digiquant_compile_research_portfolio` — digigraph dry-run graph compile

### Dedicated MCP container

`digiquant/Dockerfile.mcp` builds a standalone MCP container (no Nautilus
engine, no `[nautilus]` extra). It installs `digiquant[research,mcp]`
plus workspace deps and runs `python -m digiquant.mcp_server` with
`DIGIQUANT_MCP_SCOPE=read` on `0.0.0.0:8767` by default. Local
`python -m digiquant.mcp_server` still defaults to `full`. The hosted
container never exposes compute/mutate tools.

## Research sandbox image

`Dockerfile.sandbox` is a **separate** image from the HTTP service:
build-time-baked open-source quant stack (skfolio, riskfolio, TA-Lib with
bundled C wheels, `pandas_ta` shim and `yfinance_retry` on `PYTHONPATH`)
for research agents to execute paper-book code. No live trading, no broker
credentials, no order paths; optional outbound HTTPS for free data only.
Never `pip install` inside agent runs.

## Containers

Three digiquant images ship separately:

| Image | Dockerfile | Purpose | Port |
|---|---|---|---|
| HTTP service | `Dockerfile` | FastAPI + `digiquant[nautilus]` | `:8001` |
| MCP | `Dockerfile.mcp` | FastMCP + `digiquant[research,mcp]` | `:8767` |
| Sandbox | `Dockerfile.sandbox` | Baked quant stack (no digiquant pkg) | none |

**HTTP service:** uvicorn serving `digiquant.server:app`, loopback-bound
by default (`0.0.0.0` in Docker). `/healthz` healthcheck, standard
digibase middleware (CORS, request-id, metrics, OTel, DigiAuth with
path-scoped JWT). Linux hosts note the Nautilus SIGABRT caveat (#42) for
in-process backtests. The `docker-compose.yml` definition mounts
`digiquant/data` read-only and `digiquant/results` writable.

**MCP container:** `Dockerfile.mcp` — see MCP server section above.

**Sandbox:** `Dockerfile.sandbox` — see research sandbox section above.
Runs as non-root UID 10001 (`sandbox`), no sudo, no docker socket.
