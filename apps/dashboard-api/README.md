# dashboard-api

Central read-only dashboard API (Cloudflare Worker). Slice 2 scaffold for
issue #4647 — router + error envelope + provenance + `GET /healthz` +
`GET /portfolio` (with the `book_as_of` gate folded in per `CONTRACT.md`
§0; there is no standalone `/book-date` route).

Contract: [`CONTRACT.md`](./CONTRACT.md) — the interface. This worker is
the implementation.

## Routes

- `GET /healthz` — liveness probe, auth-exempt, always `{"ok": true}`.
- `GET /portfolio` — committed-book snapshot (§6.1). Query: `asOf?`
  (`YYYY-MM-DD`, default latest committed), `retrieval_pin?` (opaque,
  max 128 chars, echoed back).

Remaining contract routes (`/allocations`, `/brief`, `/performance`,
`/kpis/live`, `/nav-series`, `/benchmarks`, `/ledger`) land in later
slices and currently return the contract error envelope (`not_found`
is not used for unbuilt routes — they are simply absent, 404 from the
router's unknown-route branch).

## Secrets

`SUPABASE_SERVICE_ROLE_KEY` lives ONLY in worker secrets
(`wrangler secret put`). Never in the static bundle, no `NEXT_PUBLIC_`
service key. Without it the book endpoints fail closed with
`upstream_empty` (502) — never synthesized numbers.

## Dev

```bash
npm run test --workspace dashboard-api
npm run typecheck --workspace dashboard-api
npm run dev --workspace dashboard-api
```

### Live data for the digiquant-app

```bash
cp .dev.vars.example .dev.vars      # then paste SUPABASE_SERVICE_ROLE_KEY
npx wrangler dev --port 8788
# in apps/digiquant-app (defaults to http://127.0.0.1:8788):
npx next dev -p 3930
```

Only the contracted routes (§6.1–6.9) exist on the worker; blocks bound to
routes not built yet show "Withheld" (never invented numbers).

### Access gate

HTTP routes and MCP tools share one policy (`src/access.ts`): identity comes
from edge headers `x-digi-tier` / `x-digi-groups`; a route named by the catalog
is served only if the caller's manifest grants it (403 `forbidden`, MCP
`-32003`). `tools/list` returns only the tools the caller may call, so an
MCP-only client sees the same desks and tiers as the app. `get_access_manifest`
is the discovery tool.

Tiers, lowest to highest: `free | brief | desk | studio | enterprise`.
`12x` is the app-facing group name; the edge maps the product grant `fx_hub`
to it. Local dev: `DASHBOARD_DEV_CALLER=enterprise+12x`.

Identity headers (`x-digi-tier`, `x-digi-groups`, `x-digi-user`) are trusted only
with an `x-digi-edge-key` equal to the `DASHBOARD_EDGE_KEY` secret. A deployed
worker must have that secret set by the edge that injects identity. With no key,
the headers are ignored and every caller is `free` (fail closed); local dev and
tests opt back in with `DASHBOARD_TRUST_IDENTITY_HEADERS=1`, which must never be
set on a deployed worker.

MCP tools are generated from the catalog: one per GET route (the original
eight names kept, plus `get_access_manifest`); `{param}` routes take the
param as a tool argument. `get_access_manifest` is the discovery tool —
call it first; `tools/list` then shows only the routes this caller may
read. Phase 4 routes (strategies, desks, features, settings, chat) are
generated the same way. Chat reads fail closed until digichat is wired.
Settings writes return 503 `not_provisioned` until the settings edge
function is configured. Strategy deploy stays a typed "soon" state.

### Route modules and writes

Domains register routes in `src/routes/` (`Registry`; `{param}` templates;
exact beats template); `index.ts` consults it for paths the legacy table does
not serve. PUT/POST/DELETE exist only for registered routes and need
`x-digi-user` (401 `unauthorized` otherwise) plus a catalog route the caller's
manifest grants (403). No auth/session logic in the worker.

`src/table-read.ts`: `tableRead()` / `twelvexRead()` return the standard
envelope over PostgREST and fail closed (`upstream_empty`) on missing env,
upstream errors or empty rows. twelve-x uses optional `TWELVEX_SUPABASE_URL` /
`TWELVEX_SUPABASE_SERVICE_KEY` secrets.

Canonical serving path is the `/dashboard-api/*` mount on the digithings-stack
worker (#4687) — the standalone deploy below stays until cutover.
Deploy is via [`.github/workflows/deploy-dashboard-api.yml`](../../.github/workflows/deploy-dashboard-api.yml)
(path-filtered push to `develop`/`main` + `workflow_dispatch`).
