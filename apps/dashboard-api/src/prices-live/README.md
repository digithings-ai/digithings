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

## Not wired, on purpose

`createPricesLiveFetch` is not mounted in `src/index.ts`. Mounting it means
binding `FINNHUB_API_KEY` and `SUPABASE_SERVICE_ROLE_KEY` as Worker secrets,
which is a production change and is Chris's call under the supabase-exit
epic. A test pins this: `no-deno.test.ts` asserts the dashboard-api
entrypoint does not reference `prices-live`.

No `wrangler.toml` was edited, no `[vars]` key or secret was added, and the
Supabase Edge Function is untouched. It stays live as the two-week rollback
while the Worker path is exercised.

## The rate guard survives the port

The atomic lease claim is the only thing bounding Finnhub spend now that the
old invocation secret is gone, so its three fail-closed arms are preserved
exactly: RPC error, thrown exception, and `data` that is not exactly `true`
all skip without fetching. `market.test.ts` pins the burn-rate invariant
(2 × MAX_SYMBOLS against the 60/min free tier); `routes.test.ts` proves the
claim runs after the market-hours gate and before the ticker query, and that
a loser reads nothing.

## Settings: assessed, not yet ported

The sibling `settings` edge function (`handleSettingsRequest`, ~1800 lines
plus the vault/access/invite/profile-schemas helpers) was assessed against
the same pattern and deliberately left out of this slice:

- its data layer is the full `supabase-js` query-builder surface (chained
  `.from().select().eq().order().limit().maybeSingle().single()`, plus
  `auth.admin` claim sync), not the three narrow calls prices-live needs —
  a faithful `AdminDb` for it is a second leaf on its own;
- its crypto path (`vault.ts` AES-GCM seal, `DIGIQUANT_VAULT_MASTER_KEY`)
  needs a WebCrypto-audit slice with its own vectors, not a drive-by copy.

Both lanes stay live on Supabase; nothing here changes what they do.

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
