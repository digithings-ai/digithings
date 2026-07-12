# digiquant/supabase/ — the `core` Supabase project

The single Supabase CLI project dir for the suite-wide **`core`** backend (Olympus/Atlas
portfolio, market data, strategy store — see
[ADR 0021](../../docs/adr/0021-digiquant-supabase-project-topology.md)). There is exactly
**one** migration chain: the numbered files under [`migrations/`](migrations/)
(`001`–`050`, checked by `digiquant/scripts/atlas/verify-supabase-migrations.sh`).
[`SCHEMA.md`](SCHEMA.md) inventories the live tables and views.

Everything here is checked in for review and applied to the live project **manually
post-merge** (via MCP, the SQL editor, or `supabase db push` / `supabase functions
deploy`) — nothing auto-deploys.

| Path | What it is |
|---|---|
| `config.toml` | Supabase CLI project config (local alias `digiquant-atlas`) |
| `migrations/` | The numbered migration chain — source of truth for the schema |
| `SCHEMA.md` | Hand-maintained inventory of live tables, views, and RLS conventions |
| `migrations/050_public_portfolio_views.sql` | Three anon-readable views — the public portfolio read surface (#1461/#1462) |
| `functions/prices-live/` | Deno edge function: polls Finnhub, broadcasts quotes on Realtime channel `prices:live` (#1461) |

The rest of this README is the operational guide for the **live price feed** (#1461).

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

1. Apply migration `050` (MCP `apply_migration`, SQL editor, or `supabase db push`).
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

## What is public on purpose, what is locked (#1462 rulings, 2026-07-10)

Many Atlas base tables carry permissive anon SELECT policies predating these rulings.
The user resolved that split explicitly — both halves are deliberate, not oversights:

- **Locked (migration 051):** the live strategy store — `strategy_signals` (current
  position), `strategy_trades` (live trade log), `strategies` (config). Anon access
  here would have bypassed the 3-day public signal delay (`signal_delay_days`,
  PR #1479). Public strategy data flows only through the delayed static JSON and
  `strategy_tearsheets` (which keeps its anon policy — the pipeline writes the delayed
  view there).
- **Public by design:** the Atlas research internals — `documents`, `theses`,
  `decision_log`, `deliberation_*`, and the `rationale`/`pm_notes` columns on
  `positions`. Olympus is an open research project and its dashboard is itself an
  anon-key client of these tables. Do not "fix" this exposure; the curated views above
  exist to give digiquant.io a stable, minimal read surface, not to hide the research.
