---
type: quickstart
title: dashboard-api Quickstart
description: Start the dashboard-api Worker locally with wrangler dev, verify routes with curl, run the Vitest gates, and set up the SUPABASE_SERVICE_ROLE_KEY secret.
tags: [dashboard-api, quickstart, cloudflare-worker, supabase, vitest]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-27T13:35:24.399Z
---

# dashboard-api Quickstart

> **Human gate.** No new public hostname or routes on any domain. The
> `SUPABASE_SERVICE_ROLE_KEY` secret lives only in worker secrets — never
> in the static bundle, no `NEXT_PUBLIC_` service key.

dashboard-api is a Cloudflare Worker that serves as the central read-only
dashboard data API. Dashboard surfaces in `apps/dashboard` become thin
renderers over its routes and compute nothing locally. The canonical
serving path is the `/dashboard-api/*` mount on the digithings-stack
worker; the standalone worker below works for local development and
testing.

## 1. Start the dev worker

From the repo root, start a local wrangler dev server. The worker serves
on `http://localhost:8787` by default and uses in-memory stub doubles
when no Supabase secrets are configured — no network calls, no database:

```bash
npm run dev --workspace dashboard-api
```

The worker auto-detects whether `SUPABASE_SERVICE_ROLE_KEY` is present.
Without it, every route returns clearly-marked stub fixture data (see
`repo://apps/dashboard-api/src/stubs.ts`). This is the fastest path for
local route work and Vitest runs.

### Configuring real Supabase reads (optional)

To read the live house book during local dev, set the secret:

```bash
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY --env default
```

Then restart `npm run dev --workspace dashboard-api`. The worker now
reads real `daily_snapshots`, `positions`, `portfolio_metrics`, and
`public_accounting_nav_history` rows via PostgREST with the service-role
key. All book reads are house-pinned to workspace
`6b753576-ced9-5319-9bfa-c5d0aacd9319` server-side.

The `SUPABASE_URL` static var is already in
`repo://apps/dashboard-api/wrangler.toml` and does not need a secret.

## 2. Verify

### Health and routes with the stub doubles (no secret)

```bash
# Liveness (always auth-exempt, always {"ok": true, "service": "dashboard-api"})
curl -s http://localhost:8787/healthz

# Committed-book snapshot with the §1 success envelope (stub data)
curl -s "http://localhost:8787/portfolio?retrieval_pin=pin-1"

# Brief scoreboard KPIs
curl -s "http://localhost:8787/brief?overlay=off"

# Performance tearsheet
curl -s "http://localhost:8787/performance"

# Live KPI snapshot
curl -s "http://localhost:8787/kpis/live"

# NAV series
curl -s "http://localhost:8787/nav-series"

# Allocations with folded valuations
curl -s "http://localhost:8787/allocations"

# Benchmarks
curl -s "http://localhost:8787/benchmarks?tickers=SPY"

# Ledger event stream
curl -s "http://localhost:8787/ledger"

# Generic table proxy (bare row array, no envelope)
curl -s "http://localhost:8787/v1/tables/positions?select=*&limit=3"
```

Every response on the eight envelope routes carries `data`, `as_of`,
`retrieval_pin`, and `provenance`. The stub null-book convention is
`asOf=2020-01-01` — requesting that date returns a `not_found` (404)
error envelope so you can test the failure path.

### Error envelope

```bash
# Unknown route → 400 bad_request
curl -s http://localhost:8787/nope

# Malformed asOf → 400 bad_request
curl -s "http://localhost:8787/portfolio?asOf=soon"

# retrieval_pin over 128 chars → 400 bad_request
curl -s "http://localhost:8787/portfolio?retrieval_pin=$(python3 -c 'print("x"*129)')"
```

All errors use the contract §2 shape with `error.code`,
`error.message`, `error.details`, and `error.retrieval_pin`.

### CORS

OPTIONS preflights return 204 with CORS headers for allowed dashboard
origins (defaults: `https://digiquant.io`, `https://digithings.ai`,
localhost/loopback dev ports). Override via the
`DASHBOARD_API_ALLOWED_ORIGINS` worker env var (comma-separated).

```bash
curl -s -X OPTIONS http://localhost:8787/portfolio \
  -H "Origin: http://localhost:3000" -I
```

### MCP tools (secret-gated POST /mcp)

```bash
curl -s -X POST http://localhost:8787/mcp \
  -H "Content-Type: application/json" \
  -H "x-digi-mcp-key: your-key" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Without a matching `MCP_EDGE_KEY` secret the MCP endpoint returns
`401 dashboard-api: unauthorized`.

### Stack-local verify (through the fold)

When running the digithings-stack worker locally, the same routes are
available under the canonical `/dashboard-api/*` prefix:

```bash
curl -s http://localhost:8787/dashboard-api/healthz
curl -s "http://localhost:8787/dashboard-api/portfolio"
```

## 3. Gates

```bash
# Full test suite (Vitest, no network — stub doubles only)
npm run test --workspace dashboard-api

# Type-check without emitting
npm run typecheck --workspace dashboard-api
```

The Vitest suite covers the following gate categories:

| Suite | Source | Coverage |
|---|---|---|
| Error envelope + common params + healthz + portfolio | `repo://apps/dashboard-api/src/index.test.ts` | Error shape, `asOf`/`retrieval_pin` validation, router dispatch, stub-book responses |
| All eight wiring routes | `repo://apps/dashboard-api/src/wiring.test.ts` | Every contracted route returns 200 with the §1 envelope over stubs; null-book path hits 404; `/book-date` is absent |
| Supabase real-source reads | `repo://apps/dashboard-api/src/supabase.test.ts` | `hasSupabaseEnv` gating, `supaGet` service-role headers, `UpstreamError` on non-OK, committed-date selection |
| CORS behavior | `repo://apps/dashboard-api/src/cors.test.ts` | Allowlist defaults and override, CORS headers on success + error + OPTIONS, foreign origin omission |
| Envelope route builders | `repo://apps/dashboard-api/src/envelope.test.ts` | Portfolio, allocations, NAV series builders against fixture data |
| Brief builder | `repo://apps/dashboard-api/src/brief.test.ts` | Scoreboard KPIs, overlay decisions |
| Performance builder | `repo://apps/dashboard-api/src/performance.test.ts` | NAV + benchmark series alignment, headline returns |
| Live KPIs builder | `repo://apps/dashboard-api/src/kpis-live.test.ts` | Live snapshot computation |
| Benchmarks builder | `repo://apps/dashboard-api/src/benchmarks.test.ts` | Benchmark universe + aligned series |
| Ledger events | `repo://apps/dashboard-api/src/ledger.test.ts` | Pagination, event type normalization, ticker filter, cost-basis economics |
| MCP tools | `repo://apps/dashboard-api/src/mcp.test.ts` | `tools/list`, `tools/call` secret-gating, response identity with HTTP |
| Generic tables | `repo://apps/dashboard-api/src/tables.test.ts` | Allowlist enforcement, house/system workspace pins, query builder |
| Validation slice | `repo://apps/dashboard-api/src/validation.test.ts` | Client derivation import parity, SSOT field consistency |
| SSOT kernel | `repo://apps/dashboard-api/src/ssot.test.ts` | Performance SSOT calculation correctness |

The test runner uses `vitest.config.ts` from
`repo://apps/dashboard-api/vitest.config.ts`, which aliases
`@digithings/ui` to the dependency-free source module in
`packages/ui/src/components/finance-tearsheet/live-performance-kpis.ts`
so validation tests can import the real client derivations without
pulling React into the Node test environment.

## Where next

- [dashboard-api Architecture](/openwiki/dashboard-api/architecture.md) —
  request dispatch, entry points, stub/real source switching, the
  digithings-stack fold with fault isolation.
- [dashboard-api Routes and Operations](/openwiki/dashboard-api/api-and-operations.md) —
  complete route contract, error/provenance envelope, retrieval_pin
  passthrough, common param validation, MCP tools, deploy and CI/CD.
