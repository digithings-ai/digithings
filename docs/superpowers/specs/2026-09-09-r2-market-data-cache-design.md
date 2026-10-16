# R2 Market-Data Cache (live yfinance + FRED, cron-refreshed) — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan (writing-plans skill)
> is written only after the user approves this spec.

**Date:** 2026-09-09 (revised after 3-agent second-opinion review)
**Status:** draft — awaiting user review
**Author decision (verbatim):** long historical tables live in R2; yfinance
supplies the latest on demand; a cron refreshes the R2 history with latest
prices. Supabase is freed up for fast Postgres cache + retrievals (working
set, auth, user data). Vacuum of the documents table is deferred.

**Second-opinion review (2026-09-09, three parallel reviewer agents):**
data-correctness vs codebase, architecture stress-test, completeness/detail.
All findings below marked **[R1]** (data), **[R2]** (architecture),
**[R3]** (completeness) are incorporated; the verdict stands (feasible).

---

## 1. Goal

Remove the three market-data tables from Supabase — `price_history` (~109MB),
`macro_series_observations` (~104MB), `price_technicals` (~63MB), ≈276MB
combined — so the database stops growing under market-data weight and stays a
fast store for pipeline working set, auth, and (future) user data. Market data
is served instead by:

- **R2** (`digithings-archive` bucket, already live): long trailing history
  per ticker / macro series, plus immutable monthly snapshots.
- **yfinance / FRED**: the latest bars on demand (same sources the daily
  load uses today).
- **A refresh cron**: merges latest into the R2 history daily, before the
  pipeline runs.
- **The existing digiquant MCP server** (FastMCP, `streamable-http`,
  defaults `127.0.0.1:8767` with `DIGIQUANT_MCP_HOST/PORT` overrides **[R1]**):
  the single read path for pipeline phases, dashboard, and agents — same
  tool names, new live backend (see §3.1 migration table).

Projected saving: ≈172MB → database budget **≤320MB** after DROP + VACUUM.
Derivation: 512MB today −172MB price tables −~48MB documents-vacuum
(58MB→~10MB, deferred) = ~292MB + margin → budget 320MB **[R3-A5]**.
CARVE-OUT (ruling 2026-09-09): `macro_series_observations` (~104MB) is NOT
dropped — it remains the sole store for fedprob/bitview series, which have
no R2 home yet (R2 homes for those series are future work outside this
epic). Record `pg_database_size` before migration 124, after DROP, after VACUUM.

---

## 2. Background and measurements (2026-09-09, all read-only MCP probes)

- Supabase DB went 588MB → 512MB after the checkpoint/documents archive
  (PRs #3768, #3776); documents table still awaiting VACUUM (deferred).
- Remaining split (measured unless noted): `price_history` ~109MB,
  `macro_series_observations` ~104MB (intentional multi-source duplicates),
  `price_technicals` ~63MB, checkpoint live tables ~124MB post-vacuum,
  `documents` ~58MB pre-vacuum (≈5–10MB live after), `checkpoints` 1.1MB,
  rest indexes/overhead.
- Consumer read shapes (verified in `research/data/queries.py`,
  `supabase_io.py`): **all windowed + point-in-time** —
  `get_price_technicals(ticker, lookback=20)`,
  `get_macro_series(series_ids, lookback=6)` (note: `series_ids` is a
  required `list[str]` param **[R1]**), sector relative-strength
  `lookback_days=220` (paginated), flows/breadth 63d,
  `.lte("date", run_date)` as-of semantics throughout,
  `_price_delta_ticker_batch` batches to fit the PostgREST row cap.
  Depth need: **exactly 730 calendar days (≈500 trading bars)** per
  ticker/series, date-ascending, one row per trading day. Rationale: max
  consumer need is 220 trading days + 280d indicator warmup; 730d gives
  >2x margin **[R3-A1]**.
- Writers today: daily refresh (yfinance bulk for ~60 watchlist tickers,
  15-minute delayed, + incremental top-up; FRED official ingest +
  yfinance macro proxies: VIX, oil, gold, FX, credit) →
  `compute_indicators` (pure-Polars, no DB needed) → tables.
- Live-fetch precedent already inside the MCP server (not CLI-only
  **[R1]**): `digiquant_fetch_coinbase_ohlcv` (CCXT → CSV cache),
  `digiquant_fit_btc_power_law` / `digiquant_build_sdca_risk_index` on the
  canonical file cache (`digiquant.data.prices.history_cache`:
  `incremental_update` + `load_cached`; both MCP tools default to
  `bulk_period="max"` **[R1]**). That cache is repo-local disk
  (`data/price-history`) and SDCA-only — the pattern is proven, the
  location is not (ephemeral on Containers → R2 instead).
- Known pain this solves (`DESIGN-DECISIONS.md:520`): yfinance + indicator
  libs need a local venv; CI/sandbox/cloud agents often can't run them.
  Hosting the fetch env once behind MCP fixes every consumer at once.
- Hard constraint discovered the same day (do NOT regress): **all
  PostgREST traffic is capped at ~8s per statement** (Supabase
  `authenticator`-role `statement_timeout`, proven by SET ROLE tests).
  Bulk history must therefore never flow through PostgREST — direct-R2
  reads (or direct-PG) only. The checkpoint archiver already follows this
  rule.

---

## 3. Approved architecture

```
yfinance / FRED ──live latest──▶ digiquant MCP ──windowed, as-of reads──▶ pipeline / dashboard / agents
        │                              ▲
        │ daily merge                  │ full trailing history
        ▼                              │
R2 market-data/ ◀── refresh cron ──────┘
  price/<ticker>/<as_of>.parquet (immutable generations + `latest` pointer)
  macro/<source>__<series>/<as_of>.parquet (immutable, per-source)
  snapshots/<yyyymm>/*.parquet (immutable monthly freezes, 24-month rolling)
  manifest.json (versioned, atomic-swap)
```

- **R2 holds the long history — as immutable generations, never in-place
  overwrites [R2-LB1].** Each refresh writes NEW objects keyed by
  generation (`price/{TICKER}/{as_of}.parquet`), following the checkpoint
  archiver's proven ordering verbatim: `put` → `get` → SHA-256 compare →
  registry/manifest update → swap the `latest` pointer. The prior
  generation is retained until the next successful refresh. A crash
  mid-refresh leaves readers on the previous complete generation.
- **Key grammar (all keys rooted at `market-data/`) [R3-B3]:**
  `market-data/price/{TICKER}/{as_of}.parquet`
  (TICKER = uppercased yfinance symbol, `/`→`-`, e.g. `BTC-USD`),
  `market-data/price/{TICKER}/latest` (pointer object),
  `market-data/macro/{SOURCE}__{SERIES}/{as_of}.parquet`
  (e.g. `FRED__DGS10` — per-source namespacing; macro duplicates are
  PRESERVED per source, closing former open Q5),
  `market-data/snapshots/{yyyymm}/{TICKER}.parquet`,
  `market-data/manifest.json`.
- **Parquet schema [R3-E3]:** Snappy compression; `date` DATE (UTC,
  no tz); OHLCV `open/high/low/close FLOAT64`, `volume INT64`,
  `dividends FLOAT64`; holiday gaps are absent rows, never nulls;
  corporate actions follow the adjustment policy in §3.2
  (yfinance `auto_adjust=true`; a detected restatement triggers
  full-series re-pull, not silent divergence).
- **yfinance/FRED supply the latest** via the existing adapters
  (`data/prices/fetchers.py::download_ohlcv_batch` with
  `interval="1d"`, overlap capped at **30 calendar days** so per-call
  Yahoo cost is ≤1 request/ticker **[R3-E4]**;
  `macro_ingest.py::fetch_fred/fetch_fx_yahoo` with identical
  timeout/retry: max 3 attempts, exponential backoff 1s/2s/4s,
  per-ticker isolation (one ticker failure returns per-ticker error,
  batch continues) **[R3-A3]**).
- **The MCP is the only read path — no signed-URL second path [R2-I4].**
  Dashboard reads go via MCP tools (preserves `as_of` enforcement);
  direct-R2 access is cron + backfill only. Existing tool names stay;
  backends change per the §3.1 table. Technicals are **computed on read**
  (pure-Polars `compute_indicators` over the merged window: budget
  p50 <50ms / p99 <200ms per 500-bar window on standard-2, measured by
  the §8 load harness **[R3-A3]**) instead of stored: the
  `price_technicals` table goes away entirely.
- **Supabase keeps:** pipeline working set (positions, NAV, decisions,
  theses, runs, diagnostics), `archive_objects` (the R2 pointer registry —
  it is the index into R2, never move it), auth/user data,
  `trading_calendar` (tiny; also feeds the staleness gate in §3.3),
  migrations ledger. No market-data tables.
- **Registry decision [R2-LB2]:** market-data pointers live IN
  `archive_objects` with namespaced `source_table` values
  (`market-data/price`, `market-data/macro`, `market-data/snapshot`),
  carrying the same invariants as checkpoint pointers (idempotent
  insert, same-sha-skip / different-sha-raise, SHA-verified reads).
  Checkpoint `evict_to_watermark` and `reconcile_ledger` are updated to
  scope ONLY their `checkpoints/` + `documents/` prefixes and must never
  touch `market-data/` rows. There is exactly one source of truth for
  "what is in R2".

### 3.1 Tool-signature migration (old → new) [R2-I2][R3-B1]

Real standard (observed in `mcp_server.py`): tools return JSON strings,
never raise (`{"error": "<Exc>: <msg>"}` envelope via
`json.dumps(result, default=str)`), server-side caps. Changes:

| Tool | Old params | New params | Backend |
|------|-----------|-----------|---------|
| `digiquant_get_price_technicals` | `ticker: str, lookback: int = 20` | + `as_of: str \| None = None` (ISO `YYYY-MM-DD`; None → manifest `as_of` watermark, never wall-clock). Returns JSON list of `{date, open, high, low, close, volume, <indicators>}`, `date <= as_of`, `len <= lookback`; lookback capped server-side at 500. Response envelope always includes resolved `{"as_of": …}` for audit. | R2 history + 30d live overlap → merge → Polars indicators |
| `digiquant_get_macro_series` | `series_ids: list[str], lookback: int = 6` | + `as_of` (same semantics). Per-source series preserved (`<SOURCE>__<SERIES>`); no silent collapsing. | R2 macro history + FRED/yfinance latest |
| `digiquant_query_data` | whitelist incl. `price_history, price_technicals, macro_series_observations` | whitelist LOSES the three market tables at cutover; keeps `positions, nav_history, theses, thesis_vehicles, position_events, portfolio_metrics, trading_calendar` | unchanged (Supabase state reads) |

Generic `lte={"date": …}` on `query_data` must not become a backdoor
around `as_of` enforcement: market tables leave the whitelist, so the
only date-filtered market reads are the two tools above.

### 3.2 Merge rule (normative) [R2-LB5][R3-E2]

- Canonical date: exchange calendar → UTC date; yfinance bar timestamps,
  stored `date`, FRED dates, and `trading_calendar` are normalized by one
  named function (implementer pins the module path).
- Precedence: **R2 history wins for `date <= manifest.as_of`;
  live wins only for `manifest.as_of < date <= as_of`.**
- Dedupe on `(date)`: single winner per the precedence above.
- Restatements: overlap-hash comparison each refresh; on mismatch,
  full-series re-pull (splits/dividends adjust the whole yfinance
  series, not just recent bars).
- Macro: `<series>.<source>` namespaced end-to-end; FRED revisions never
  overwrite frozen snapshots (snapshot immutability).

### 3.3 `as_of` settled-close semantics + staleness gate [R2-LB4][R2-LB6]

- `as_of` means **settled close**: the live `as_of`-dated bar is EXCLUDED
  unless the refresh cron has sealed it (yfinance is 15-minute-delayed;
  same-date bars update intraday — including them leaks information a
  settled-close backtest never had). Default `as_of` = manifest
  watermark, never wall-clock/yfinance-latest; live bars with
  `date > as_of` are excluded even if fetched.
- **Skip live fetch entirely when `as_of` predates the 30d live window**
  (pure waste × phases × agents otherwise).
- TTL cache key MUST include `(as_of, manifest_version)`; filtering
  applies after merge, never before. Single-replica assumption documented;
  correctness never depends on the cache (R2 is source of truth) **[R3-C7]**.
- Staleness gate the pipeline enforces: manifest `as_of` vs `run_date`
  in trading days (against retained `trading_calendar`); past the bound
  (default: 5 trading days, tunable) the pipeline refuses/degrades
  instead of publishing theses on stale data. Stale-serve additionally
  writes `manifest.stale=true`.
- Per-run live-fetch budget: one merged live fetch per run shared across
  phases (batch tool shape), not per-call fetches with only TTL
  mitigation **[R2-M1]**.

---

## 4. Read contract (load-bearing) — unchanged, now measurable

Every market-data tool takes explicit `as_of` per §3.1. Verification
(commands, not adjectives) **[R3-D2][R3-D3]**:

- Fixtures: `tests/fixtures/r2/<date>/` frozen R2 objects +
  `tests/fixtures/supabase-answers/<date>.json` goldens recorded before
  cutover, for pinned dates **2024-12-31, 2025-03-15, 2025-08-29**
  (backtest date, 220d-RS date, month-end).
- `pytest tests/dq/test_market_data_parity.py -v` — exact date/OHLC
  match; indicators ±1e-9 (recomputed, not copied).
- `pytest tests/dq/test_market_data_asof.py -m unit -v` — (1) no row
  with `date > as_of` across 10 sampled values; (2) lookback k returns
  `min(k, available)` rows date-ascending; (3) `as_of` before first bar
  → `{"rows": []}`, not error; (4) single-row window returns one row
  with warmup indicators null.

---

## 5. Caching and rate limits (normative values)

- R2 history objects (full trailing history, zero per-call Yahoo cost).
- In-memory TTL **900s** in the MCP process for the live-latest window
  (matches the 15-minute data delay; fresher polling buys nothing).
- Retries: max 3, backoff 1s/2s/4s, per-ticker isolation (§3).
- FRED: same live-or-cached shape; R2 snapshots additionally fix FRED
  revisions.
- Container disk is ephemeral → the file cache (`history_cache`,
  `data/price-history`) is NOT used in the hosted path; R2 is the cache.

---

## 6. Hosting — Option A locked in [R2-I3][R3-E7]

**Dedicated `digiquant-mcp` container** from the existing
`digiquant/Dockerfile` conventions (per-service-image pattern), with a
documented Dockerfile delta (base + `[research]`/`[mcp]` extras —
`digiquant/Dockerfile` today ends in `uvicorn … 8001` with `[nautilus]`,
neither of which serves the MCP — + MCP entrypoint + exposed port),
plus a networking/auth subsection the plan must write: public hostname,
non-loopback bind (today `127.0.0.1:8767`), caller auth via digikey
(current tools are unauthenticated localhost), egress verification for
yahoo/FRED endpoints (shared-egress throttling check), warm policy
(min-instances or warm schedule — a post-refresh health ping alone does
not keep the container warm for reads hours later), and the per-component
secrets list (`FRED_API_KEY` + the four `R2_*` names spelled out).
Option B (extend the chat stack container) is rejected: it bloats the
chat-only profile and couples deploys.

---

## 7. Migration and backfill (order matters)

1. **Backfill R2 from Supabase first** (one-time export job): full trailing
   history per ticker/series → R2 objects + manifest. Reads go via
   **direct-PG** (URI-style, statement-timeout bypass, paginated by
   `(ticker, date)` in small pages — never PostgREST, per the §2 8s cap),
   resume-from-manifest, SHA-256 verify per object mirroring the
   checkpoint archiver's put-verify-then-pointer discipline **[R3-E5]**.
   Universe iterated is exactly the ticker/series list from
   **<config path pinned by plan>** (unknown ticker →
   `{"error": "unknown ticker …"}` enumerating valid values) **[R3-E1]**.
2. **Add the MCP tools** behind feature flag
   `DIGIQUANT_MARKET_DATA_BACKEND=r2|supabase` (global; default `supabase`
   until cutover; per-tool scoping only if the plan justifies it).
   Rollback = set flag to `supabase` **[R3-E6]**.
3. **Cut reads over; dual-write window with a promotion gate** (not "one
   cycle" hand-wave): writers keep running in parallel for N daily cycles
   (plan pins N) with parity sampling; cutover gate = parity green +
   load green **[R2-LB3]**.
4. **Point of no return — declared explicitly.** Ships as
   `digiquant/supabase/migrations/124_drop_market_data_tables.sql`
   (header per the 119–121 convention: `-- 124_<name>.sql`, run/ledger
   lines, `-- <issue-ref + what/why>`, bare DDL, **no `BEGIN;`** anywhere
   incl. comments **[R3-B4]**):
    `DROP TABLE IF EXISTS price_history,
    price_technicals` + ledger insert in the same db-migrate transaction.
    (`macro_series_observations` is CARVED OUT — it stays as the sole store
    for fedprob/bitview series until those get R2 homes as future work.)
   Requires N retained daily R2 generations (or R2 versioning) + manifest
   history BEFORE this step; post-4 rollback = restore-from-generation
   + replay. Then VACUUM (ANALYZE) the freed storage
   (documents-table VACUUM stays out of scope per §10).
5. Retire the Supabase-bound refresh; its adapters move into the R2
   refresh cron (same fetch code, new sink).

---

## 8. Verification (measurable)

- **Parity**: `scripts/check_r2_parity.py --manifest
  market-data/manifest.json` — per-ticker/series row counts, Supabase vs
  R2; PASS = exact match per dataset (tolerance 0; holiday-gap handling
  documented); output as CI artifact **[R3-D1]**.
- **As-of + contract**: §4 commands.
- **Live-fire**: pipeline CLI `--dry-run --as-of <date>` exits 0 with no
  writes; then the exact daily command in staging; PASS = exit 0 +
  positions/NAV row-counts within ±5% of Supabase-baseline run;
  dashboard renders with no empty states (screenshot artifact) **[R3-D4]**.
- **Size**: `SELECT pg_size_pretty(pg_database_size('core'))` before
  migration 124, after DROP, after VACUUM; plus per-table
  `pg_total_relation_size` pre-drop (expect ~109/104/63MB ±10%).
  PASS = total ≤320MB **[R3-D5]** (`macro_series_observations` ~104MB stays
  per carve-out; derivation: ~512MB − ~48MB documents-vacuum − ~172MB
  price/technicals ≈ ~292MB + margin).
- **Load**: `scripts/bench_market_data.py --tools
  get_price_technicals,get_macro_series --n 100 --as-of <frozen>` →
  `{p50, p99}` per tool as a CI job; baseline = Supabase-backed numbers
  checked into `docs/perf/baseline.json`. **Fallback-B trigger: any tool
  p99 >2x baseline OR p99 >800ms over 3 consecutive daily runs**
  → land follow-up migration with trailing-90d thin tables (schema pinned
  by plan), refreshed by the cron, with a sunset condition. Until
  triggered: NO Postgres market-data tables **[R2-I5][R3-D6][R3-C5]**.

---

## 9. Risks and fallbacks

- **yfinance flakiness** (already lived with daily; cache absorbs it;
  cron fail-soft keeps serving stale + alerts).
- **Read latency**: mitigated by §5 TTL; fallback B is trigger-bound
  per §8 (not "decided later").
- **Container cold starts**: warm policy per §6.
- **R2 costs**: rolling history ≈15MB churn/day; snapshots retained
  **24 months rolling (≈432MB cap)**, not "all history" **[R3-A2][R2-M3]**.
  Shared-budget accounting: the `digithings-archive` bucket is co-tenanted
  with the checkpoint archive (8.5GB high / 7GB low watermarks) — market
  data (~0.5GB cap) leaves ≈7 years of checkpoint headroom, not decades;
  eviction namespaces from §3 keep the two tenants apart **[R2-I1][R2-LB2]**.
  Thin-window default stays deferred-with-threshold **[R2-M3]**.

---

## 10. Out of scope

- Touching pipeline state tables (positions, NAV, decisions, theses,
  runs, diagnostics), `archive_objects`, auth/user tables, or the
  checkpoint archive itself — all stay in Supabase.
- The deferred documents-table VACUUM (separate op, needs the Postgres
  URI or dashboard).
- Rewriting the SDCA/file-cache tools (they keep working; they can adopt
  the R2 backend later).

## 11. Open questions (for spec review, not implementation)

1. R2 object granularity: one versioned object per ticker per generation
   (recommended — §3; single-object-per-ticker rewrites rejected per
   [R2-LB1]).
2. Snapshots: 24-month rolling retention (recommended — §9).
3. Thin Postgres tables: deferred-with-threshold (§8 trigger).
4. Dashboard path: MCP tools only (decided — §3; signed-URL alternative
   rejected: bypasses `as_of`/merge/compute **[R2-I4]**).
5. Macro duplicates: preserved per-source (`<SOURCE>__<SERIES>`,
   decided — §3).
