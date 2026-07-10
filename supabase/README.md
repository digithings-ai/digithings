# supabase/ — live price fan-out + public portfolio surface

Cross-cutting Supabase infrastructure for the digiquant.io live price feed
(**#1461**) and the public portfolio read surface (**#1462**). Everything here is
checked in for review and applied to the live `core` project **manually post-merge**
(via MCP or `supabase db push` / `supabase functions deploy`) — nothing in this
directory auto-deploys.

> **Relationship to `digiquant/supabase/`** — the historical Olympus/Atlas migration
> chain (`001`–`049`, sequential numbering) lives in
> [`digiquant/supabase/migrations/`](../digiquant/supabase/migrations/) and targets the
> **same** `core` project (see
> [ADR 0021](../docs/adr/0021-digiquant-supabase-project-topology.md)). This top-level
> directory holds the cross-cutting public-web surface (edge functions + timestamped
> migrations) that spans `frontend/` and `digiquant/`. Apply order relative to the
> Atlas chain doesn't matter: this migration only creates views over tables the Atlas
> chain already owns.

## What lives here

| Path | What it is |
|---|---|
| `migrations/20260710120000_public_portfolio_views.sql` | Three anon-readable views — the entire public portfolio read surface |
| `functions/prices-live/` | Deno edge function: polls Finnhub, broadcasts quotes on Realtime channel `prices:live` |

## The two-lane live price feed

digiquant.io is a **static Cloudflare Pages site** — no secret may ship in the bundle.
Prices therefore arrive in two lanes:

1. **Crypto (frontend lane)** — browsers stream directly from Coinbase's public,
   keyless WebSocket. No server involved; not in this directory.
2. **Equities/ETFs (server lane, this directory)** — the `prices-live` edge function
   polls Finnhub's free REST tier (60 calls/min) with the API key held as a Supabase
   secret, then fans out **one** message per run to the Realtime broadcast channel
   `prices:live`. Browsers subscribe with the anon key; the Finnhub key never leaves
   the function.

The symbol set per run = distinct tickers from `public_portfolio_positions` + a small
curated majors list (SPY QQQ DIA IWM GLD TLT UUP EFA EEM HYG), capped at 40 symbols —
well under the 60/min limit even at a 60s schedule.

## Dormant until the key exists

The Finnhub key **does not exist yet**. The function is designed to be deployed and
scheduled **before** the key is created: when the `FINNHUB_API_KEY` secret is unset,
every invocation logs and returns `200 {"dormant": true}` without fetching anything.
Similarly, outside extended US market hours (13:00–01:00 UTC, Mon–Fri) it returns
`200 {"market": "closed"}` without burning quota. Both gates exit 200 so schedulers
never see failures for expected idle states.

Until the key is set (and outside market hours), the frontend values positions from
the `public_price_latest` view — the latest daily close per ticker from
`price_history`, which the `pipeline-digiquant-prices.yml` job keeps fed.

## One-time human steps (post-merge)

1. Apply the migration (MCP `apply_migration`, SQL editor, or `supabase db push`).
2. Deploy the function: `supabase functions deploy prices-live` (keep JWT verification
   **on** — the scheduler passes the anon key, see below).
3. Create a free API key at [finnhub.io](https://finnhub.io) (Dashboard → API Keys).
4. `supabase secrets set FINNHUB_API_KEY=<key>` — the function wakes up on its next
   invocation; no redeploy needed.

## Scheduling: pg_cron + pg_net, every 60s during market hours

Recommended schedule (run in the SQL editor — **not** a checked-in migration, because
it embeds the project URL and anon key). Two entries because the 13:00–01:00 UTC
window wraps midnight; the function also self-gates on market hours, so an
over-generous schedule is harmless:

```sql
-- 13:00–23:59 UTC, Mon–Fri
select cron.schedule(
  'prices-live-day',
  '* 13-23 * * 1-5',
  $$
  select net.http_post(
    url     := 'https://<PROJECT_REF>.supabase.co/functions/v1/prices-live',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer <SUPABASE_ANON_KEY>'
    ),
    body    := '{}'::jsonb
  );
  $$
);

-- 00:00–00:59 UTC, Tue–Sat (= Mon–Fri US evening; the midnight-wrap tail)
select cron.schedule(
  'prices-live-late',
  '* 0 * * 2-6',
  $$
  select net.http_post(
    url     := 'https://<PROJECT_REF>.supabase.co/functions/v1/prices-live',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer <SUPABASE_ANON_KEY>'
    ),
    body    := '{}'::jsonb
  );
  $$
);

-- To pause:
-- select cron.unschedule('prices-live-day');
-- select cron.unschedule('prices-live-late');
```

The anon key is safe to embed here (it ships in every browser bundle anyway); it only
authenticates the function invocation past JWT verification. Requires the `pg_cron`
and `pg_net` extensions (Dashboard → Database → Extensions).

## How the frontend consumes it

**Live quotes** — subscribe to the broadcast channel with the anon client:

```ts
supabase
  .channel("prices:live")
  .on("broadcast", { event: "quotes" }, ({ payload }) => {
    // payload = { type: "quotes", at: ISO8601,
    //             quotes: { SPY: { c, d, dp, t }, ... } }
  })
  .subscribe();
```

Fields per symbol mirror Finnhub's quote: `c` current price, `d` change, `dp` percent
change, `t` quote unix time.

**Public views** (anon `SELECT` via PostgREST) — the column projection is the privacy
allowlist (performance metrics only, never research notes — user ruling 2026-07-10,
#1462):

| View | Contents |
|---|---|
| `public_portfolio_positions` | Latest-date positions: ticker, name, category, sector, weight, entry/current price, day/unrealized/since-entry returns. **Excludes** rationale, PM notes, thesis id, conviction, stops/targets/horizon. |
| `public_nav_history` | NAV series + cash/invested % + derived daily return. |
| `public_price_latest` | Latest daily close per ticker — the valuation fallback while `prices-live` is dormant or the market is closed. |

**Known follow-up (#1462):** the base tables currently carry a permissive `anon_read`
SELECT policy predating this ruling, so `positions` is still directly anon-readable —
including the research columns. Tightening those policies so the views become the
*only* public surface is deliberately out of scope here (base-table RLS untouched by
ruling) and tracked on #1462.
