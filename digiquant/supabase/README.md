# digiquant/supabase/ — the `core` Supabase project

The single Supabase CLI project dir for the suite-wide **`core`** backend (Olympus/Atlas
portfolio, market data, strategy store — see
[ADR 0021](../../docs/adr/0021-digiquant-supabase-project-topology.md)). There is exactly
**one** migration chain: the numbered files under [`migrations/`](migrations/) —
`001`–`063` at time of writing, with `037`, `038` and `059` never used and `062`
**burned — see below, do not reuse it**; new work appends the next unused prefix. [`SCHEMA.md`](SCHEMA.md) inventories the live
tables and views.

`digiquant/scripts/atlas/verify-supabase-migrations.sh` guards the chain's shape:
`config.toml` is present, every file matches `NNN_name.sql`, and no two files share
a numeric prefix. It runs as the first step of `test-digiquant.yml` (the
`digiquant/**` path filter covers this directory) and locally via `make
supabase-migrations-check`. It does **not** check ordering, and it does not compare
against the live schema — `olympus_schema_migrations` is what records what prod has
actually applied.

**The one grandfathered collision: `025`.** `025_thesis_daily_fields.sql` and
`025_trading_calendar.sql` both exist and were both applied on 2026-06-26.
`db-migrate.yml` keys the ledger on the *full filename*, so renumbering either one
mints a new ledger key for a file prod already ran. They are exempted by exact
basename in the guard's `GRANDFATHERED_DUPES`; a third `025` still fails. Don't add
to that list — take the next free prefix instead.

**`062` is burned, not merely free (#1807).** `037`, `038` and `059` were never written.
`062` was. `062_realtime_broadcast_authorization.sql` tried to add RLS policies to
`realtime.messages`; that table is owned by `supabase_realtime_admin`, a role with **zero**
members over which **zero** roles hold admin option, so nobody reachable from here can join
or grant it — `CREATE POLICY` raises `42501 must be owner of table messages` as `postgres`
and always will (verified read-only against the live project, 2026-08-01; PostgreSQL 17.6
no longer lets `CREATEROLE` imply admin over pre-existing roles, and the dashboard SQL
editor runs as the same `postgres`). The file could never be applied, so it never got an
`olympus_schema_migrations` row and was deleted outright — a clean withdrawal, no orphan
ledger row, no tombstone. Migration `063` supersedes it. **Nothing in this repo enforces
that.** The verifier checks filename shape and prefix uniqueness only; nothing hashes
migration contents and there is no contiguity check, so `062` now looks merely "free" to
every tool here — this README is the only place the burn is recorded. Do not reuse the
number: "migration 062" already denotes the abandoned `realtime.messages` approach in the
git history, in PR #1813, and in the docs of that era.

**Migrations auto-deploy; edge functions do not.** A merge to `main` that touches
`migrations/**` triggers [`db-migrate.yml`](../../.github/workflows/db-migrate.yml),
which applies every pending file to the live project within seconds — no manual step,
no `supabase db push`. (2026-08-01: PR #1809's promotion merged at 20:47:38Z and
`057`/`058`/`060`/`061` were live by 20:48:20Z.) Since 2026-08-01T20:50Z the run waits
on a required reviewer via the `production` environment (#1768); before that it was
ungated entirely. Treat a migration reaching `main` as a production schema change.

Edge functions and the pg_cron schedules below really are manual — `supabase functions
deploy`, or the SQL editor.

| Path | What it is |
|---|---|
| `config.toml` | Supabase CLI project config (local alias `digiquant-atlas`) |
| `migrations/` | The numbered migration chain — source of truth for the schema |
| `SCHEMA.md` | Hand-maintained inventory of live tables, views, and RLS conventions |
| `migrations/050_public_portfolio_views.sql` | Three anon-readable views — the public portfolio read surface (#1461/#1462) |
| `migrations/063_prices_live_table.sql` | `public.prices_live` — the quote table Realtime streams as `postgres_changes`; RLS on, one SELECT policy, no write policy, `service_role` the sole writer (#1807) |
| `functions/prices-live/` | Deno edge function: polls Finnhub, upserts one row per ticker into `public.prices_live` (#1461, #1807) |

The rest of this README is the operational guide for the **live price feed** (#1461).

## The two-lane live price feed

digiquant.io is a **static Cloudflare Pages site** — no secret may ship in the bundle.
Prices therefore arrive in two lanes:

1. **Crypto (frontend lane)** — browsers stream directly from Coinbase's public,
   keyless WebSocket. No server involved; not in this directory.
2. **Equities/ETFs (server lane, this directory)** — the `prices-live` edge function
   polls Finnhub's free REST tier (60 calls/min) with the API key held as a Supabase
   secret, then **upserts one row per ticker** into `public.prices_live` (migration
   `063`). Browsers subscribe to Realtime `postgres_changes` on that table with the anon
   key; the Finnhub key never leaves the function.

### The transport is a table we own — that is the security control (#1807)

Until 2026-08-01 the server lane fanned **one** message per run out to the Realtime
*broadcast* channel `prices:live`. Broadcast messages are client-authored: delivery is a
bare INSERT into `realtime.messages`, Supabase grants `anon` INSERT on that table, and the
anon key ships in plaintext in every digiquant.io bundle. Anyone could POST **forged
quotes** onto the feed and every open tab would render them as live Finnhub data — the edge
function and its invocation secret (#1756) bypassed entirely.

The textbook Supabase answer — RLS on `realtime.messages` plus `config: { private: true }`
on both ends — is **unreachable on this project** and was withdrawn with migration `062`
(see "`062` is burned" above). The feed moved instead. State the resulting posture
precisely — the old hole is *abandoned*, and a different object is what protects the feed:

- **`prices:live` is abandoned, not policed.** It remains an open, anon-writable broadcast
  topic on this project, permanently. `anon`'s INSERT grant on `realtime.messages` is
  platform-managed — unsupported to revoke and reverted by the platform — and we cannot add
  a policy to that table. The topic is harmless *only* because **nothing subscribes to it
  any more**: an attacker can still publish there and the message lands in an empty room.
  The exposure was never the INSERT grant alone, it was the grant plus a listener. Anything
  added later that subscribes to a broadcast topic on this project re-opens the hole in
  full, and inherits every constraint above.
- **The control is `public.prices_live`.** RLS is enabled with exactly **one** policy —
  `FOR SELECT TO anon, authenticated USING (true)` — and **no** INSERT, UPDATE or DELETE
  policy for any role. Under RLS, absent policy = deny; the omission *is* the fix, so do not
  "complete" the policy set. The six write privileges are additionally revoked from
  `PUBLIC`/`anon`/`authenticated` (the 050/052/060 convention), and `service_role` is the
  sole writer.
- **Forgery is now impossible rather than disallowed.** A `postgres_changes` event is
  generated by Realtime from the WAL, so it is a consequence of a committed write. There is
  no client-supplied path into the WAL: to put a fake quote on this feed you must first
  write the row, and no anon-reachable credential can.

The symbol set per run = distinct tickers from `public_portfolio_positions` + a small
curated majors list (SPY QQQ DIA IWM GLD TLT UUP EFA EEM HYG), capped at 40 symbols —
well under the 60/min limit even at a 60s schedule.

## Live since 2026-07-13 — and gated (#1756)

The feed is **live**: `FINNHUB_API_KEY` is set, both pg_cron jobs are `active`, and the
function fetches on every scheduled invocation. It is **not** dormant. (Evidence:
`net._http_response` id 1360, 2026-08-01T00:59Z — `{"market":"open","forced":false,
"symbols":17,"quoted":17,"failed":0,"broadcast":"ok"}`, one of ~10,800 succeeded cron
runs since 2026-07-13.) That capture predates #1807: the publish-result field was renamed
`broadcast` → `published` when the transport moved onto `public.prices_live`, and it now
carries the upsert result. A healthy run today ends `…,"failed":0,"published":"ok"}` —
grep the cron log for `published`, not `broadcast`.

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
the invocation gate) — one full fetch + publish cycle on demand, so the end-to-end path
can be proven on a weekend instead of waiting for Monday's open:

```bash
curl -s -X POST 'https://<PROJECT_REF>.supabase.co/functions/v1/prices-live' \
  -H 'Authorization: Bearer <SUPABASE_ANON_KEY>' \
  -H 'x-prices-live-secret: <PRICES_LIVE_INVOKE_SECRET>' \
  -H 'Content-Type: application/json' -d '{"force": true}'
```

Omitting the secret header returns `401` and fetches nothing — that is the cheapest way
to confirm the gate is actually deployed.

The response reports `forced: true`, per-symbol failures, and `published` — the
`public.prices_live` upsert result: `"ok"`, or the PostgREST error verbatim (a scheduled
run has no other diagnostic surface). Subscribers then receive **one `postgres_changes`
event per upserted row**, not one message per run.

## How the frontend consumes it

**Live quotes** — subscribe to Realtime `postgres_changes` on `public.prices_live` with the
anon client. This is the live shape from
[`frontend/digiquant-web/lib/live/useLivePrices.ts`](../../frontend/digiquant-web/lib/live/useLivePrices.ts),
which is the reference implementation; read the two warnings under it before adapting.

```ts
const instanceId = useId(); // one Realtime topic PER HOOK INSTANCE — see below

supabase
  .channel(`prices-live-db-${instanceId}`)
  .on(
    "postgres_changes",
    { event: "*", schema: "public", table: "prices_live" },
    ({ new: row }) => {
      // row = { ticker, price, change, change_pct, quoted_at, updated_at }
    },
  )
  .subscribe();
```

**No `config: { private: true }`, deliberately.** That flag routes authorization through RLS
on `realtime.messages`, the table we can never police (#1807) — every join would be refused
and the tape would silently decay to daily closes. Security here comes from the table's
missing write policy, not from a private channel.

**The topic must be unique per subscribing component.** `RealtimeClient.channel()` dedupes
by topic, so two components sharing one topic string get one channel with two
`postgres_changes` bindings against a single server-side filter; the reply is index-matched,
the second binding finds no counterpart, and realtime-js calls `unsubscribe()` — killing the
lane for **both** consumers with no exception and no console error. A bare constant is
enough to trigger it; the trap does not exist on broadcast, which is why the retired code
could get away with one.

Row fields are the table's columns, not Finnhub's: `price` (Finnhub `c`), `change` (`d`,
nullable), `change_pct` (`dp`, nullable, percent **points** — `1.24` means +1.24%),
`quoted_at` (a `timestamptz` converted from Finnhub's unix **seconds** `t` — the exchange's
clock, what staleness should be judged on), and `updated_at` (our write clock, which keeps
advancing when the market is quiet). `DELETE` events carry only the primary key under
`REPLICA IDENTITY DEFAULT`; the publisher never deletes, so drop them.

### Rolling out the table transport — migration FIRST, or the feed goes dark

Migration `063`, the publisher and the subscriber are one change in three files, and the
order they reach production is load-bearing. A browser subscribing to `postgres_changes` on
a table the project does not yet carry simply receives **no events** — there is no error
`useLivePrices` can surface, so the tape silently degrades to `public_price_latest` daily
closes marked `stale`. A dark live feed with nothing logged anywhere.

1. **Apply migration `063` and verify it.** Unlike the withdrawn `062`, this one applies as
   `postgres`: `public.prices_live` and the `supabase_realtime` publication are both owned
   by `postgres`, which is the whole reason this design is reachable and that one was not.
   A merge to `main` touching `migrations/**` runs `db-migrate.yml` automatically — but
   **the run now pauses for a required reviewer** on the `production` environment (#1768,
   live since 2026-08-01T20:50Z). Approve it, or the migration sits unapplied and the
   "within seconds" behaviour described above no longer holds. Then confirm all three
   properties before going anywhere near step 3:

   ```sql
   -- (a) exactly one policy, SELECT only. Any write policy here is a regression.
   select policyname, cmd, roles
     from pg_policies
    where schemaname = 'public' and tablename = 'prices_live';
   -- expect exactly one row: prices_live_public_read | SELECT | {anon,authenticated}

   -- (b) RLS actually enabled — without it the missing write policy denies nothing
   select relrowsecurity from pg_class where oid = 'public.prices_live'::regclass;
   -- expect: t

   -- (c) the table is in the publication, or Realtime emits nothing at all
   select schemaname, tablename
     from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'prices_live';
   -- expect one row
   ```

2. **Deploy the publisher.** `supabase functions deploy prices-live` — it now upserts the
   table instead of broadcasting. Deploying it ahead of step 1 is safe and self-diagnosing:
   `published` comes back `PGRST205 Could not find the table 'public.prices_live' in the
   schema cache`, which is the entire diagnosis.
3. **Let the frontend reach production last.** digiquant.io builds from `main` via the
   Cloudflare Pages git integration, so the subscriber ships on a `develop` → `main`
   promotion. Do not promote until step 1 verifies.

The in-between windows are benign in this order: an old cached bundle still listening on
`prices:live` hears nothing, and a new bundle pointed at a table that exists but is not yet
being written shows the lane-1 seed until the next pg_cron minute. Both fall back to stale
daily closes, never a blank UI. Reversing 1 and 3 is the case that goes dark — re-run step
1's queries first if quotes stop.

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

**Public means readable, never writable (migration 060, #1757).** That ruling is about
`SELECT`. Supabase's bootstrap also granted `anon`/`authenticated` full DML on every
relation in `public`, and RLS with no write policy was the only thing stopping a write from
the *published* anon key. Migration 060 revokes `INSERT, UPDATE, DELETE, TRUNCATE,
REFERENCES, TRIGGER` schema-wide and narrows `ALTER DEFAULT PRIVILEGES` so new relations
inherit read-only. Two consequences for anyone adding a table or view here:

- Follow the 050/051/052 pattern — pair every `GRANT SELECT` with an explicit `REVOKE`.
  Migrations 041 and 018 did not, which is how `atlas_run_health` (auto-updatable and
  `security_invoker = false`, so writes through it run as `postgres` and bypass the base
  table's RLS) ended up accepting an unauthenticated `DELETE` of the whole
  `atlas_run_diagnostics` history.
- Never widen the revoke to `REVOKE ALL` in the default-privileges statement. It would
  strip `SELECT` from the next curated view, and `safeSelect` in the frontend turns the
  resulting PostgREST 42501 into an empty panel rather than an error — a silent break.

`service_role` is unaffected: it is the only writer (workflows, Python connectors, and the
`prices-live` edge function all authenticate with it).
