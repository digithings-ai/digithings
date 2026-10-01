# digiquant-web live gateway (local only)

A tiny read-only HTTP gateway so the static digiquant.io site can make real live
calls to the digiquant MCP server without any secret reaching the browser.

- **Local only.** Binds `127.0.0.1` (default port 8792, env `DQ_GATEWAY_PORT`).
  `DQ_GATEWAY_ORIGINS` rejects anything except exact loopback HTTP origins, and
  the browser client independently rejects non-loopback gateway URLs and pages.
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

## Run the local pair (`:3910` + `:8792`)

Chris can run the site and gateway together with two terminals:

Terminal 1, from the repo root:

```sh
PYTHONPATH=digiquant/src python apps/digiquant-web/gateway/live_gateway.py
```

Terminal 2, from the repo root:

```sh
cp apps/digiquant-web/.env.local.example apps/digiquant-web/.env.local
npm run dev:local --workspace digiquant-web
```

Open `http://127.0.0.1:3910`. The site uses the gateway for the LuxAlgo Library
search handoff and for the existing market-data seam. Keep both public variables
pointed at loopback:

```dotenv
NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL=http://127.0.0.1:8792
NEXT_PUBLIC_MARKET_DATA_URL=http://127.0.0.1:8792
```

Do not use either loopback value in production or staging.
`NEXT_PUBLIC_MARKET_DATA_URL` must keep pointing at the deployed R2-backed market
worker there; unlike the dedicated gateway client, that existing market-data
client does not apply a loopback guard. If `NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL` is
set accidentally, its client still refuses to connect from a non-loopback page
or to a non-loopback URL.

Env: `DQ_GATEWAY_PORT` (8792), `DQ_GATEWAY_ORIGINS` (comma list, exact match;
default `http://localhost:3910,http://127.0.0.1:3910`). Port 3005 is not used.

## Routes

- `GET /healthz`, `GET /v1/catalog`, `GET /v1/probe/{id}?params`
- `GET /v1/market/closes?tickers=A,B&from=YYYY-MM-DD&to=YYYY-MM-DD` and
  `GET /v1/market/tickers`: read-only proxy of `https://graph.digithings.ai/v1/market/`
  (fixed host, 5 min cache, body unchanged, upstream failure gives 502). Point
  `NEXT_PUBLIC_MARKET_DATA_URL` at the gateway.

Limits: 30 req/min per IP, 15 s tool timeout, 200 KB payload cap, per-probe TTL cache.

## Human-gate blockers before any non-local wire

- design and review digikey JWT enforcement at the edge;
- replace the loopback bind and origin policy only as part of that reviewed design;
- confirm Gloomberb public-use terms and required attribution;
- define hosted rate limits, abuse controls, observability and secret handling;
- review deployment and network exposure with One/Chris.

Until those are resolved, this gateway is a local development adapter only.

## Test

```
PYTHONPATH=digiquant/src pytest apps/digiquant-web/gateway/test_live_gateway.py
```
