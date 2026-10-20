# fx-hub — Supabase edge functions, ported to Workers

The two FX Hub server functions that still run as Supabase Edge Functions,
ported to a Cloudflare Workers runtime module inside `apps/dashboard-api`.

| Edge function (still live) | Worker module (this port) |
| --- | --- |
| `supabase/functions/fx-hub-session` | `session.ts` → `handleFxHubSession` |
| `supabase/functions/fx-hub-grant-sync` | `grant-sync.ts` → `handleFxHubGrantSync` |
| `Deno.env` / `Deno.serve` | `env.ts` / `router.ts` |
| `@supabase/supabase-js` | `supabase-auth.ts` (four HTTP calls) |

## What "ported" means here

The wire contract is unchanged. Same bodies, same status codes, same check
order: POST, `X-Sync-Secret`, JSON, email, key dictionaries, then the
network. No upstream call runs before the shared-secret check.

Two runtime differences are the whole substance of the port:

- **`Deno.env.get` → an injected `env` record** (`env.ts`). `readApiKey`
  parses `SUPABASE_SECRET_KEYS` and `SUPABASE_PUBLISHABLE_KEYS` as JSON
  objects and returns the `default` member, or null. It never reads
  `SUPABASE_ANON_KEY` or `SUPABASE_SERVICE_ROLE_KEY`.
- **`Deno.serve` → an exported `fetch` handler** (`router.ts`).
  `createFxHubFetch` is the adapter a Worker entrypoint would mount, on
  `/fx-hub-session` and `/fx-hub-grant-sync`.

`supabase-auth.ts` is the narrow stand-in for supabase-js: grant lookup,
`generate_link`, `verify`, and the grant upsert. New-format keys travel on
the `apikey` header. `apiKeyOnlyFetch` strips `Authorization: Bearer
sb_publishable_…` / `sb_secret_…` because those values are not JWTs.

## Mounted

`src/index.ts` sends `FX_HUB_PATHS` to `createFxHubFetch(env)` before the
dashboard catalog. Those two paths use `X-Sync-Secret`. They are not catalog
routes, and they do not use `x-digi-user`.

The key dictionaries and `FX_HUB_GRANT_SYNC_SECRET` are still not in
`wrangler.toml`. Until they are bound on the worker, a request with no
secret answers `401 UNAUTHORIZED`. A request that passes the secret and
finds no key dictionary answers `500 API_KEYS_UNCONFIGURED`. `no-deno.test.ts`
asserts the entrypoint imports `createFxHubFetch` and `FX_HUB_PATHS`.

No `[vars]` key or secret was added, and the Supabase Edge Functions are
untouched. They stay live as the rollback until the cutover is proven.

## Tests

`vitest run src/fx-hub`

- `session.test.ts` — mint with the new keys only, `apikey` and never
  `Bearer`, legacy-key refusal, unparseable and empty dictionaries, ungranted
  email, link/verify failures, shared-secret boundary.
- `grant-sync.test.ts` — upsert with the secret key only, legacy refusal,
  database error, shared-secret boundary.
- `no-deno.test.ts` — no `Deno` global in the tree, and the entrypoint does
  not import the module.
