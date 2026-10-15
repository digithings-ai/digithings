## digiquant Data Layer — Strategy Store + Shared Data (#1064)

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

The digiquant shared backend is the **`core`** Supabase project — the project historically
used by dashboard/research (`config.toml project_id "digiquant-research"`, rooted at
`digiquant/supabase/`), repurposed (renamed `core`) as the suite-wide backend rather than a
separate project, because the `digiquant.io` org is free-tier (2-project limit) and both
slots are taken (dashboard + the confidential twelve-x). The shared market datasets
(`trading_calendar`, `macro_series_observations`; the two price tables were dropped in
migration 127, #4053) already live here; #1064 only **adds** the strategy store. See
`docs/adr/0021-digiquant-supabase-project-topology.md`.

**Connection.** Accessor `digiquant.data.store` (`build_digiquant_client` + Polars-friendly
helpers in `strategies.py`). Credentials resolve the standardized `CORE_SUPABASE_URL` /
`CORE_SUPABASE_SERVICE_KEY` ([ADR 0022](../../../docs/adr/0022-supabase-env-naming-standard.md)),
falling back to the legacy `*_DIGIQUANT` and shared `SUPABASE_URL` /
`SUPABASE_SERVICE_ROLE_KEY` names — one project today, a zero-code split if the store ever
graduates onto its own project.

**Strategy store** (added by [`supabase/migrations/046_strategy_store.sql`](../../supabase/migrations/046_strategy_store.sql))

- `strategies` — `id`, `symbol`, `label`, `engine`, `config` jsonb, `enabled`, `version`. Public-readable.
- `strategy_calibrations` — **private** 1:1 sidecar holding fitted `calibration` jsonb. Service-role-only.
- `strategy_trades` — executed trade history (entry/exit ts, side, prices, qty, pnl, return_pct).
- `strategy_tearsheets` — latest tearsheet payload per strategy (`metrics`, `equity_curve`, `as_of`).
- `strategy_signals` — current state per strategy (`position` long/flat/short, `last_signal_date`, `last_price`).

**Shared data layer.** `trading_calendar` and `macro_series_observations` already
reside in `core` (no migration needed; `price_history`/`price_technicals` were dropped
in migration 127, #4053). `#1065`'s
cross-project price copy is therefore **superseded**. `#1066` adds a shared
`economic_calendar` (migration `047`, mirroring twelve-x's `fx_economic_calendar`
— since retired: core is the single source, and core's own vestigial
`fx_economic_calendar` was dropped in migration 128, #4053;
incl. `event_datetime_utc` + the impact CHECK + unique `external_id`; additive
`economic_calendar_authenticated_select` in `114` so signed-in JWT users can
SELECT the same public calendar as anon — do not number this `113`, which is
the staged cutover under `migrations/cutover/`): the twelve-x
ingest (`fx_calendar/calendar_db.py`) is repointed to write it, and the dashboard
twelve-x **events tab reads it via the main dashboard client** (`getUpcomingEvents` in
`apps/dashboard/lib/twelve-x/fetch.ts`) rather than the twelve-x project — the
other FX research tables stay on `twelveXSupabase`. Cutover is gated: the frontend
read goes live only once the repointed ingest has populated `core`.

**Checkpoint + document archive v2 (#3766).** LangGraph's PostgresSaver snapshots full
channel state per step, so each daily run leaves ~50–100MB of `bytea` in
`checkpoint_blobs` / `checkpoint_writes` — the tables that pushed `core` past its
500MB quota (price/macro/documents are already deduped). `digiquant.ops.checkpoint_archive`
offloads finished threads' payloads to Cloudflare R2 as zstd level-3 blobs with a
version byte (`compress_payload` / `decompress_payload`), keyed
`checkpoints/<thread>/<table>/<checkpoint_id>.zst`. Every upload is SHA-256-verified
on read-back, then `record_pointer` writes an `archive_objects` registry row
(migration 119: `source_table`, `source_key`, `r2_key`, `sha256`, `size`, `owner`,
`status`) **before** the Supabase cell is NULLed — pointer failure keeps the Supabase
row, so a payload is never orphaned without its pointer. `previous_threads` keeps the
newest run per owner live in Supabase (resume only ever touches the current run id);
`--retain-days` / `--keep` intersect that set. `evict_to_watermark` deletes
oldest-first down from the 8.5GB high watermark to the 7GB low watermark (ledger
`size` sum), never touching the latest run's keys; `reconcile_ledger` drops dead
ledger rows and reports orphan R2 keys without auto-deleting them. Every key and
ledger scan pages explicitly past the PostgREST 1000-row cap (`_scan_all` over
`DOC_SCAN_PAGE_SIZE`), and every page carries a unique ORDER BY tiebreak so
offset paging is stable on an unordered table: `STABLE_ORDER_BY_TABLE` maps each
table to its total-order key (`archive_objects` → `archived_at,r2_key`;
`checkpoints` → `thread_id,checkpoint_ns,checkpoint_id`; `documents` and the blob
tables → their key columns) and `_scan_all` appends it after any caller order
(skipping columns the caller already ordered by). `evict_to_watermark` keeps a
local running total instead of re-querying per row, and `reconcile_ledger` lists
both `checkpoints/` and `documents/` prefixes. `resolve_payload`
is the read-through contract: pointer lookup → R2 GET → sha256 verify
(`ArchiveVerifyError`) → decompress; `ArchiveNotFoundError` when no pointer row
exists **or** when the pointed-to object is missing/evicted from the bucket
(normalized via `r2_history.is_missing_object_error`, so a reader cannot
distinguish "never archived" from "archived then evicted").
Documents phase (migration 120): pointer-per-row for non-latest
`(workspace_id, document_key, date)` versions under
`documents/<ws>/<date>/<key>.zst`, newest date per key stays live. Creds are
`R2_ACCOUNT_ID` / `R2_BUCKET` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`, endpoint
built as `https://<account>.r2.cloudflarestorage.com`.
`.github/workflows/pipeline-checkpoint-archive.yml` runs it daily. The live
checkpointer path is untouched. Read-through consumers (#3792):
`read_archived_document` wraps `resolve_payload` + JSON decode and honors a
"never raises" contract on the read path — ``None`` on pointer/object miss,
corrupt bytes, undecodable JSON, **or** any storage/registry fault (logged at
WARNING with the traceback, so a broken read-through is visible-but-soft).
Document readers take an optional `store` (tests inject a fake, production
resolves the R2 backend from `R2_*` env); when creds are absent the hydration
point logs a WARNING ("archive read-through disabled (no R2 backend)") instead
of silently degrading every archived row to missing. Wired into the
dashboard fallback (`research_retrieval/queries.py::_query_documents_row` via
`query_research`) and the research priors (`research/supabase_io.py`:
`load_prior_context`, analyst/deliberation summaries, `load_latest_beliefs_document`).
Only the `payload` cell is archived — `content` is untouched.

**RLS.** Every strategy-store table RLS-enabled. Public reference + tearsheet tables grant
`anon SELECT USING (true)`; writers use the service role (RLS bypass). `strategy_calibrations`
has no anon policy — anon reads return an empty set (not a permission error) while the service
role keeps full access (mirrors the `run_diagnostics` idiom, migration 033). Run
`get_advisors(type="security")` after applying; expect zero `rls_disabled_in_public` findings.

**Grants — RLS is no longer the only write gate (#1757).** Migration
[`supabase/migrations/060_lock_public_write_grants.sql`](../../supabase/migrations/060_lock_public_write_grants.sql)
revokes `INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER` from `PUBLIC`, `anon` and
`authenticated` on **all tables in schema `public`** and narrows `ALTER DEFAULT PRIVILEGES`
with the same list, so new relations inherit read-only instead of Supabase's bootstrap
`GRANT ALL`. Before it, the *published* anon JWT held full DML on all 35 base tables plus
two views, and RLS-with-no-write-policy was the single layer denying writes — one already
exploitable: `run_health` (migration 041) is auto-updatable and deliberately
`security_invoker = false`, so an unauthenticated `DELETE` through it ran as `postgres` and
erased every `run_diagnostics` row. `service_role` is untouched — it is the only
writer. When adding a public view, pair `GRANT SELECT` with an explicit `REVOKE` (050/052
do; 041/018 did not) and never use `REVOKE ALL` in the default-privileges statement: it
would strip `SELECT` and `safeSelect` renders a PostgREST 42501 as an empty panel, not an
error. See [`supabase/SCHEMA.md`](../../supabase/SCHEMA.md) "Grants" for the residuals and for why
the statement must not carry a `FOR ROLE` clause.

**Private provider telemetry (#1951).** Migration
[`supabase/migrations/067_olympus_provider_telemetry.sql`](../../supabase/migrations/067_olympus_provider_telemetry.sql)
adds `olympus_node_runs`, `olympus_provider_calls`, and `olympus_provider_attempts`. All three are
service-role-only, RLS-enabled with no policies, and append-only: `service_role` receives only
`SELECT`/`INSERT`, while database triggers reject `UPDATE` and `DELETE`. The schema stores generic
artifact references but no provider payload. It is prospective only; no historical attempts or
costs are inferred from `run_diagnostics` aggregates. Task #1963 does not write these tables:
it establishes in-process logical purpose, parentage, cache status, exact observable attempt count,
and artifact disposition; Task 1.5 owns durable persistence and reconciliation.

**Live price fan-out + public portfolio surface (#1461/#1462).** Migration
[`supabase/migrations/050_public_portfolio_views.sql`](../../supabase/migrations/050_public_portfolio_views.sql)
adds digiquant.io's public read surface to this project's single migration chain: three
curated anon-readable views — `public_portfolio_positions`, `public_nav_history`,
`public_price_latest` (dropped in migration 127, #4053; browsers read the R2 market
API now) — exposing performance metrics only (never
`rationale`/`pm_notes`/risk parameters; user ruling 2026-07-10, #1462). The landing
blotter uses `public_price_latest` as the mark when `positions.current_price` is
still null (metrics cron is 22:00 UTC; the 12:00 book is unmarked until then). They pair with
the `supabase/functions/prices-live/` Deno edge function, which polls Finnhub
server-side (key held as a Supabase secret; **live since 2026-07-13** on a 60s pg_cron
schedule) and upserts one row per ticker into `public.prices_live` (migration `063`),
which browsers read over Realtime `postgres_changes`. Crypto
quotes take the other lane — streamed client-side from Coinbase's public WebSocket. See
[`supabase/README.md`](../../supabase/README.md) for the two-lane design, pg_cron + pg_net
scheduling, and the one-time setup steps, and [`supabase/SCHEMA.md`](../../supabase/SCHEMA.md)
for the view and table inventory.

**Invocation is rate-limited, not authorized — the shared secret was withdrawn (migration
`064`, superseding #1756).** `verify_jwt: true` was never authorization: it proves the caller
holds *a* project key, and the anon key ships in plaintext in every digiquant.io bundle. So
anyone can invoke `prices-live`, and the harm available to them is to exhaust Finnhub's free
tier (60 calls/min) out from under the 60s cron — the feed then goes stale for every real
visitor. That is a **rate** problem, not an **identity** problem, and #1756's
`x-prices-live-secret` / `PRICES_LIVE_INVOKE_SECRET` header answered the wrong one at the cost
of a real operational credential to store, embed in `cron.job`, rotate and lose. It is gone.
[`supabase/migrations/064_prices_live_lease.sql`](../../supabase/migrations/064_prices_live_lease.sql)
replaces it with an **atomic claim**: every invocation calls
`public.claim_prices_live_refresh(50)` before touching a symbol, which is ONE conditional
`UPDATE` of the single-row `public.prices_live_lease` (`WHERE id = 1 AND claimed_at <
clock_timestamp() - <min_age>`, returning `FOUND`). Concurrent callers block on that row, then
re-evaluate the predicate against the committed new value under READ COMMITTED and match zero
rows — exactly one winner per window, for any arrival pattern. Losers get `200
{"skipped": "not claimed"}` and fetch nothing. The caller **fails closed**: an RPC error, a
thrown exception, or any `data` that is not exactly `true` all mean not-claimed, so deploying
the function ahead of the migration fetches nothing rather than everything. `MAX_SYMBOLS = 40`
at one fetch per 50s is 48 Finnhub calls/min against the 60/min tier (a rate over the claim
window, not a cap on an arbitrary sliding minute); raising `MAX_SYMBOLS` or lowering
`MIN_REFRESH_SECONDS` breaks that and a test asserts the product.

*The rejected design, because it is the one a reader will propose.* A freshness check —
`select max(updated_at) from prices_live`, skip if young — is **read-then-act and protects
nothing**. `updated_at` is written by the upsert *after* the whole fetch loop (40 symbols ×
150 ms ≈ 6 seconds), so for those ~6s every concurrent invocation reads the same stale
timestamp, all pass the check, and all fetch: ten parallel requests become ~400 Finnhub calls.
It is not a narrow race a tighter threshold would shrink, and a sequential test of it passes
perfectly — which is why the design survives review. Advisory locks cannot substitute either:
the protected region is a ~6s fetch in Deno that outlives the RPC, and PostgREST returns the
pooled session at commit. Test-and-consume in one statement or there is no guard.

*What the rate guard does and does not cover.* Unauthorized callers are **not blocked** — they reach
the function and get a `200`. What they cannot do is exceed the legitimate refresh rate, so
invoking the endpoint gains an attacker nothing beyond a Supabase function invocation: a caller
who *wins* a claim causes the same real Finnhub fetch and the same correct upsert the cron
would have. `verify_jwt` stays **on** as a cheap outer layer. Two things this deliberately does
not cover. (1) **Invocation volume itself is unprotected** — ten thousand calls a minute yield
ten thousand `skipped` responses, each still costing an edge-function invocation and a claim
round-trip, and only Supabase's platform rate limiting bounds that; what is bounded here is the
metered Finnhub spend. (2) **Direct RPC access would starve the feed**, which is why `064`
revokes `EXECUTE` from `PUBLIC`/`anon`/`authenticated` and grants it to `service_role` only:
every winning call advances `claimed_at`, so a caller hitting the RPC directly — no edge
function, no Finnhub call, no cost — could win every window and leave the cron nothing to
claim, a denial of *freshness* cheaper than the quota attack. The REVOKE is half the control.

**The live equity transport is a table, not a broadcast channel (#1807).** The feed used to
ride the Realtime *broadcast* topic `prices:live`, and that was forgeable: broadcast
messages are client-authored, delivery is a bare INSERT into `realtime.messages`, Supabase
grants `anon` INSERT on that table, and the anon key ships in plaintext in every
digiquant.io bundle — so anyone could publish forged quotes straight onto the feed,
bypassing the edge function, and whatever gate it carried, entirely.
[`supabase/migrations/063_prices_live_table.sql`](../../supabase/migrations/063_prices_live_table.sql)
moves the transport onto `public.prices_live`: the publisher upserts one row per ticker
(`functions/prices-live/index.ts`) and the browser subscribes to `postgres_changes` on that
table (`apps/digiquant-web/lib/live/useLivePrices.ts`). **Neither end passes
`config: { private: true }` any more, deliberately** — that flag routes authorization back
through RLS on `realtime.messages`, which we can never police.

*Why the textbook fix was withdrawn.* The obvious patch — RLS policies on
`realtime.messages` plus private channels on both ends — was written as migration `062`, then
proved **impossible to apply**. It never reached production (no migration-ledger
row; two `db-migrate` runs failed on it), so it was deleted and the number burned. `realtime.messages` is
owned by `supabase_realtime_admin`, a role with zero members over which zero roles hold
admin option; our connection is `postgres` (`rolsuper = false`, not a member), and on
PostgreSQL 17.6 `CREATEROLE` no longer implies admin over pre-existing roles. `CREATE
POLICY` requires ownership, so it raises `42501` for us permanently — including from the
dashboard SQL editor, which runs as the same role. Verified read-only against the live
project on 2026-08-01. The `supabase_realtime` publication and every `public` table *are*
owned by `postgres`, which is exactly why `063` is appliable and `062` was not.

*Security posture, stated precisely.* The forgery hole is **abandoned, not policed**.
`prices:live` remains an open, anon-writable broadcast topic on this project permanently —
`anon`'s INSERT grant on `realtime.messages` is platform-managed and cannot be revoked. It
is harmless only because **nothing subscribes to it any more**. The control is
`public.prices_live`: RLS enabled with exactly one policy (`FOR SELECT TO anon,
authenticated USING (true)`), **no** write policy for any role (absent policy = deny), and
the write grants revoked from `PUBLIC`/`anon`/`authenticated` with `service_role` the sole
writer. Because `postgres_changes` events originate from the WAL, a client cannot inject
one at all — forgery becomes impossible rather than merely disallowed. See
[`supabase/README.md`](../../supabase/README.md) for the migration-first rollout runbook and the
subscribe snippet (the topic must be unique per hook instance — `RealtimeClient.channel()`
dedupes by topic, and a shared one silently kills the lane for every consumer), and
[`supabase/SCHEMA.md`](../../supabase/SCHEMA.md) for the table inventory.

