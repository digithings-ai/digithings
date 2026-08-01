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

## Live since 2026-07-13 — and gated (#1756)

The feed is **live**: `FINNHUB_API_KEY` is set, both pg_cron jobs are `active`, and the
function fetches on every scheduled invocation. It is **not** dormant. (Evidence:
`net._http_response` id 1360, 2026-08-01T00:59Z — `{"market":"open","forced":false,
"symbols":17,"quoted":17,"failed":0,"broadcast":"ok"}`, one of ~10,800 succeeded cron
runs since 2026-07-13.)

Because it is live, invocation is **authorized by a shared secret**, not by JWT alone:

- The caller must send `x-prices-live-secret: <PRICES_LIVE_INVOKE_SECRET>`. Without it
  the function returns `401` and fetches nothing.
- This gate runs **before** the key gate, the body parse, and the market-hours gate, so
  an unauthorized caller learns nothing about the feed's state and triggers no outbound
  request.
- It **fails closed**: if `PRICES_LIVE_INVOKE_SECRET` is unset, every invocation is
  refused with `503`. There is no fall-open path.

The anon key alone is **not** sufficient and never was. `verify_jwt` proves the caller
holds *a* project key; the anon key is published in every browser bundle, so it proves
nothing about *who* is calling. Keep `verify_jwt` on — it is a useful outer layer — but
the invoke secret is what actually distinguishes the scheduler from the internet.

Outside extended US market hours (13:00–01:00 UTC, Mon–Fri) an authorized caller gets
`200 {"market": "closed"}` without burning quota; if the Finnhub key were ever unset it
gets `200 {"dormant": true}`. Both exit 200 so schedulers never see failures for
expected idle states. In those windows the frontend values positions from the
`public_price_latest` view — the latest daily close per ticker from `price_history`,
which the `pipeline-digiquant-prices.yml` job keeps fed.

## Rolling out the invocation secret

**Order matters — reversing steps 1 and 3 takes the live feed dark.** A deployed
function that predates the gate simply ignores an unexpected header, so setting the
secret and re-issuing the crons first is a no-op against the running version; deploying
first would 401 the existing header-less crons for as long as the rollout takes.

1. `supabase secrets set PRICES_LIVE_INVOKE_SECRET=<generated>` — generate with
   `openssl rand -hex 32`. Ignored by the currently deployed version.
2. Re-issue **both** cron jobs with the header added (SQL below). pg_cron upserts by
   jobname, so this updates in place rather than creating duplicates. This is a manual
   SQL-editor step — the schedule is deliberately **not** a checked-in migration (see
   below), so it will not happen on its own.
3. `supabase functions deploy prices-live` — the gate goes live and the crons already
   carry the header.

Confirm with `select status_code, content from net._http_response order by id desc
limit 3;` — still `200 {"market":...}`, not `401`.

## Historical: one-time setup steps (all completed)

1. Apply migration `050` (MCP `apply_migration`, SQL editor, or `supabase db push`).
2. Deploy the function: `supabase functions deploy prices-live` (keep JWT verification
   **on** — necessary but not sufficient; see the invoke secret above).
3. Create a free API key at [finnhub.io](https://finnhub.io) (Dashboard → API Keys).
4. `supabase secrets set FINNHUB_API_KEY=<key>` — no redeploy needed.

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
      'Content-Type',          'application/json',
      'Authorization',         'Bearer <SUPABASE_ANON_KEY>',
      'x-prices-live-secret',  '<PRICES_LIVE_INVOKE_SECRET>'
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
      'Content-Type',          'application/json',
      'Authorization',         'Bearer <SUPABASE_ANON_KEY>',
      'x-prices-live-secret',  '<PRICES_LIVE_INVOKE_SECRET>'
    ),
    body    := '{}'::jsonb
  );
  $$
);

-- To pause:
-- select cron.unschedule('prices-live-day');
-- select cron.unschedule('prices-live-late');
```

The anon key is safe to embed here (it ships in every browser bundle anyway) — and that
is exactly why it cannot be the authorization: it gets the request past `verify_jwt` and
nothing more. The `x-prices-live-secret` header is the part that identifies the caller as
the scheduler. Requires the `pg_cron` and `pg_net` extensions (Dashboard → Database →
Extensions).

**Where the invoke secret lives, honestly.** Embedding it in the cron `command` puts it
in plaintext in `cron.job`, readable by anyone who can `select` there. That is a real
property to know about, not a hidden one — but it is a strictly smaller surface than
today's: reading `cron.job` needs database access, whereas the anon key needs only
`view-source`. The secret is never served to a browser and never leaves the project.
Rotate by re-running steps 1–2 of the rollout (the function reads the secret per
invocation, so no redeploy is needed).

### Smoke testing outside market hours

Pass `{"force": true}` to override the market-hours gate (never the key gate, and never
the invocation gate) — one full fetch + broadcast cycle on demand, so the end-to-end path
can be proven on a weekend instead of waiting for Monday's open:

```bash
curl -s -X POST 'https://<PROJECT_REF>.supabase.co/functions/v1/prices-live' \
  -H 'Authorization: Bearer <SUPABASE_ANON_KEY>' \
  -H 'x-prices-live-secret: <PRICES_LIVE_INVOKE_SECRET>' \
  -H 'Content-Type: application/json' -d '{"force": true}'
```

Omitting the secret header returns `401` and fetches nothing — that is the cheapest way
to confirm the gate is actually deployed.

The response reports `forced: true`, per-symbol failures, and the broadcast result;
subscribers on `prices:live` receive the quotes message.

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
| `public_price_latest` | Latest daily close per ticker — the valuation fallback outside market hours (`prices-live` is live, not dormant, since 2026-07-13). |

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
