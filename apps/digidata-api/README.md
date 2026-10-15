# digidata-api

Worker data API for the Supabase-to-Cloudflare move (epic DIG-2887, ticket DIG-2895).
Python modules (twelve-x first, then digiquant/digivault/digisearch) call this instead of Supabase directly.

- `DATA_BACKEND=supabase` (default): PostgREST passthrough to the live project. Lets callers switch to this API before any data moves.
- `DATA_BACKEND=d1`: parameterized SQLite on the `TWELVEX_DB` D1 binding.
- PostgREST-style reads: `GET /v1/twelvex/<table>?col=eq.v&order=col.desc&limit=100&select=a,b`
- Upserts: `POST /v1/twelvex/<table>?on_conflict=a,b` with 1..500 rows (defaults to the primary key).
- Every `/v1` call needs `Authorization: Bearer $DATA_API_TOKEN` (fails closed). Tables and columns are an allowlist generated from `d1/twelvex/0001_init.sql`.

Local: `npm run d1:local:twelvex && npm run dev` with `.dev.vars` (`DATA_BACKEND=d1`, `DATA_API_TOKEN=...`).

Not deployed: there is no deploy workflow, routes or remote D1 yet. Deploying needs Chris's approval at cutover (DIG-2902).
Still to do: the core tables, RLS-equivalent per-tenant authz (DIG-2894), Python client, twelve-x CHECK constraints (commented in the SQL).
