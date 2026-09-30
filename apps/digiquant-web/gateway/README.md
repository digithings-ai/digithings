# digiquant-web live gateway (local only)

A tiny read-only HTTP gateway so the static digiquant.io site can make real live
calls to the digiquant MCP server without any secret reaching the browser.

- **Local only.** Binds `127.0.0.1` (default port 8792, env `DQ_GATEWAY_PORT`).
  Production exposure is a human decision per `digiquant/ARCHITECTURE.md` and the
  `HUMAN GATE` notes in `wrangler.toml` (digikey JWT at the edge). Do not deploy
  this file as-is.
- **Gloomberb terms must be confirmed** before any public deployment. Responses
  carry the upstream attribution and delay notice verbatim; keep them visible.
- **The session cookie is intentionally never passed.** The MCP server runs as a
  stdio child (no network port) with a scrubbed env (`PATH`, `HOME`, `PYTHONPATH`,
  `LANG` only), so only anonymous free-tier tools work. Cookie-gated tools are not
  exposed; backtest/optimize/export/pipeline are not in `--scope read`.
- **No generic passthrough.** Only the fixed `PROBES` table in `live_gateway.py`.
- LuxAlgo probes return metadata only (never Pine/indicator source), with the
  upstream `attribution` and `license_note` in the envelope's `attribution[]`.

## Run

```
PYTHONPATH=digiquant/src python apps/digiquant-web/gateway/live_gateway.py
```

Env: `DQ_GATEWAY_PORT` (8792), `DQ_GATEWAY_ORIGINS` (comma list, exact match;
default `http://localhost:3910,http://127.0.0.1:3910`). Port 3005 is not used.

## Routes

- `GET /healthz`, `GET /v1/catalog`, `GET /v1/probe/{id}?params`
- `GET /v1/market/closes?tickers=A,B&from=YYYY-MM-DD&to=YYYY-MM-DD` and
  `GET /v1/market/tickers`: read-only proxy of `https://graph.digithings.ai/v1/market/`
  (fixed host, 5 min cache, body unchanged, upstream failure gives 502). Point
  `NEXT_PUBLIC_MARKET_DATA_URL` at the gateway.

Limits: 30 req/min per IP, 15 s tool timeout, 200 KB payload cap, per-probe TTL cache.

## Test

```
PYTHONPATH=digiquant/src pytest apps/digiquant-web/gateway/test_live_gateway.py
```
