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

Deploy is via [`.github/workflows/deploy-dashboard-api.yml`](../../.github/workflows/deploy-dashboard-api.yml)
(path-filtered push to `develop`/`main` + `workflow_dispatch`).
