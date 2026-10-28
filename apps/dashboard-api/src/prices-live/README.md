# prices-live — Supabase edge function, ported to Workers

The `prices-live` server lane that used to run as a Supabase Edge Function
(pg_cron every minute → pg_net → Edge Function → Finnhub → upsert
`prices_live` → Realtime `postgres_changes` to browsers), ported to a
Cloudflare Workers runtime module inside `apps/dashboard-api`.

| Edge function (still live) | Worker module (this port) |
| --- | --- |
| `digiquant/supabase/functions/prices-live/index.ts` | `routes.ts` → `handlePricesLive` |
| atomic lease claim (migration 064) | `admin.ts` → `claimRefresh` |
| ticker view + upsert (migrations 063/050) | `admin.ts` → `listPortfolioTickers` / `upsertPrices` |
| market-hours + timestamp helpers | `market.ts` (verbatim pure port) |
| `Deno.env` / `Deno.serve` | `env.ts` / `router.ts` |

## What "ported" means here, and what it deliberately does not mean

The wire contract is unchanged. Same bodies, same status codes, same check
order — dormant when the Finnhub key is unset, market-closed outside extended
US hours unless forced, not-claimed when the lease window belongs to another
run, and the open-market report otherwise. The pg_cron log scraping parses
those shapes today and must not need a change at cutover. Every body in
`routes.test.ts` is copied from the edge handler it replaces.

Two runtime differences were unavoidable and are the whole substance of the
port:

- **`Deno.env.get` → an injected `env` record** (`env.ts`). Every lookup the
  edge function did is preserved, including the `SUPABASE_*` /
  `CORE_SUPABASE_*` fallback pairs. The port reads `env`; it does not declare
  anything.
- **`Deno.serve` → an exported `fetch` handler** (`router.ts`).
  `createPricesLiveFetch` is the adapter a Worker entrypoint would mount.

One dependency change: `@supabase/supabase-js` is not a dependency of this
package, so `admin.ts` does not vendor a query-builder client. It defines a
narrow `PricesLiveDb` interface and one PostgREST-over-`fetch`
implementation, which also matches the existing house pattern in
`src/supabase.ts`. A later leaf that moves the tables to D1 replaces that one
file; the handler does not change.

## Mounted behind flags (Supabase exit S4, DIG-2887)

`src/index.ts` mounts the router only when `PRICES_LIVE_WORKER_ROUTES` is
`"1"`. Off (the default), the paths fall through to the catalog and the edge
function plus pg_cron keep serving. With the flag on:

| Var / binding | Effect |
| --- | --- |
| `PRICES_LIVE_CRON_TOKEN` (secret) | `POST /prices-live` needs `Authorization: Bearer <token>`. Unset refuses every call (401). The edge path was anon-callable behind the lease; on the worker the cron call is the only caller. |
| `PRICES_LIVE_BACKEND = "kv"` | `kv-store.ts` replaces PostgREST: lease and quotes live in KV. Anything else keeps `prices_live` in Supabase. |
| `PRICES_LIVE_KV` (KV binding) | The namespace for the kv backend. Missing with `kv` set answers 500 `prices-live kv not bound`. |
| `PRICES_LIVE_TICKERS` | Comma list that replaces the core `public_portfolio_positions` read. Unset reads the view if Supabase is configured, else majors only. |
| `FINNHUB_API_KEY` (secret) | Unchanged: unset answers `{ dormant: true }`. |

`GET /prices-live/quotes` returns the KV snapshot `{ updated_at, rows }`
(public quotes, the data the Realtime channel broadcast). It answers 404 on
the Supabase backend.

The KV lease is a best-effort window, not the Postgres row lock: KV has no
compare-and-set. It holds because the bearer gate leaves one caller, the
per-minute cron. A Durable Object would make it atomic if a second caller
ever appears.

Not in this change, each a Cloudflare-side step that needs Chris's go: the KV
namespace and binding, the two secrets, the digithings-cron row that POSTs
the refresh every minute in market hours, re-pointing the browser tickers from
Realtime to the quotes read (or an SSE Durable Object), and disabling the two
pg_cron prices jobs.

## The rate guard survives the port

The atomic lease claim is the only thing bounding Finnhub spend now that the
old invocation secret is gone, so its three fail-closed arms are preserved
exactly: RPC error, thrown exception, and `data` that is not exactly `true`
all skip without fetching. `market.test.ts` pins the burn-rate invariant
(2 × MAX_SYMBOLS against the 60/min free tier); `routes.test.ts` proves the
claim runs after the market-hours gate and before the ticker query, and that
a loser reads nothing.

## Settings: measured, not yet ported

The sibling `settings` edge function was measured rather than eyeballed. The
`Deno.serve` wrapper is 98 lines; the handler it wraps,
`_shared/settings-handlers.ts`, is 1817; `_shared` is 5777 lines across 21
files behind it. Two things decide the shape of the remaining work.

**1. The data layer is the whole supabase-js client, not a narrow one.**
`_shared/supabase-admin.ts:11` is `export type AdminClient = SupabaseClient`,
so the handler chains straight onto the client and there is no seam to port
against. Counted in the handler: 150 chained calls across 12 tables --
`broker_connections`, `broker_executions`, `client_product_grants`,
`entitlement_grants`, `job_runs`, `notification_log`, `notification_prefs`,
`olympus_profile_config`, `product_invite_attempts`, `product_invite_codes`,
`product_invite_redemptions`, `workspace_provider_credentials` -- over 39
`.eq`, 34 `.from`, 27 `.select`, 13 `.maybeSingle`, 9 `.insert`, 7 `.order`,
6 `.single`, 5 `.update`, 5 `.limit`, 2 `.upsert`, 2 `.neq`, 1 `.gte`.

That is why prices-live's narrow `PricesLiveDb` cannot absorb it. It is not
"three narrow calls vs a big handler"; it is *the builder surface itself*.
`../data/postgrest.ts` is that prerequisite, scoped to exactly this census
and shipped with its own emission tests (24) and an 8-mutant kill run.
Absent methods (`rpc`, count, storage, auth, realtime) throw rather than
guess, because the census found none.

**2. The crypto path is its own slice.** `vault.ts` is 350 lines of AES-GCM
seal against `DIGIQUANT_VAULT_MASTER_KEY`, plus a vector file. It needs a
WebCrypto audit with its own vectors, not a drive-by copy.

So the port decomposes into at least three leaves -- builder (landed),
crypto, then the handler -- rather than one slice. Both lanes stay live on
Supabase; nothing here changes what they do.

## Tests

`vitest run src/prices-live` — 34 tests.

- `routes.test.ts` — the wire contract: dormant / closed / forced / 500 /
  not-claimed / open report / CASH exclusion / majors-only degrade / verbatim
  upsert error / all-fetch-failed / cap truncation / bad-timestamp fallback.
- `market.test.ts` — the burn-rate invariant, market-hours boundaries
  (including the 00:xx previous-session rule), and the seconds→ISO multiply
  with its out-of-range fallback.
- `admin.test.ts` — the PostgREST layer, which the route tests never reach
  because they inject a stub: `=== true` claim semantics with its three
  fail-closed arms, ticker passthrough, and the merge-duplicates upsert that
  must never become ignore-duplicates.
- `no-deno.test.ts` — no `Deno` global survives, and the entrypoint does not
  reference the module.
