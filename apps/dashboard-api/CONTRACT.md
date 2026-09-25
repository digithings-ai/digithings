# dashboard-api contract (slice 1 — spec only, no implementation)

Status: contract spec for the dashboard central API. This file is the
interface; implementation lands in later slices. Base for all routes below is
the dashboard-api worker; dashboard surfaces in `apps/dashboard` become thin
renderers over these routes and compute nothing locally.

Conventions: all digi product names stay lowercase (`digithings`,
`digiquant`, `digichat`, …). Auth, JWT, and crypto behavior is unchanged —
this contract adds no new auth surface and touches no `digikey/` code, no
`digiquant/brokers/` code, and no live-trading paths.

## 0. Endpoint resolution (9 names → 8 routes)

The plan names nine functional areas for eight route slots. This contract
keeps **8 routes** with two folds:

- `/book-date` folds into `GET /portfolio` as the `book_as_of` object (the
  committed-book date gate has no standalone route).
- `/valuations` folds into `GET /allocations` as per-row mark/unrealized
  fields (same book read, same envelope — a separate route would duplicate
  the `houseBook()` + `reconcileBook` round trip).

Final route list: `GET /portfolio`, `GET /allocations`, `GET /brief`,
`GET /performance`, `GET /kpis/live`, `GET /nav-series`,
`GET /benchmarks`, `GET /ledger`.

## 1. Global conventions

- All routes are `GET` and read-only. No request body anywhere.
- Common query params on every route: `asOf?: string` (calendar date
  `YYYY-MM-DD`; default = latest committed), `retrieval_pin?: string`
  (opaque caller-supplied pin, see §4).
- Every success response is an object with `data`, plus `as_of`,
  `retrieval_pin` (echo, see §4), and `provenance` (see below).
- `provenance` object (every route): `{ source: string; tip_date: string |
  null; contract: "finalized_accounting" | "legacy_estimate" | null;
  seam: boolean; marks: "stored" | "market_api" | "unavailable" }`. Badges
  always describe the source of the displayed numbers.
- House workspace pinning (§3) applies to every book-backed route
  (`/portfolio`, `/allocations`, `/brief`, `/performance`, `/ledger`).
- No timeouts, retries, or call caps are specified anywhere in this
  contract — surfaces fail closed with the error envelope (§2) instead.
- Realtime stays client-side (§5): this API serves snapshots only.

## 2. Error envelope

All failures return HTTP status + this body (no other shape):

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {},
    "retrieval_pin": "string | null"
  }
}
```

Codes: `bad_request` (400, malformed `asOf`/`retrieval_pin`/params),
`not_found` (404, no committed book or tip for `asOf`),
`upstream_empty` (200-body is never empty-as-healthy; 502 when a required
upstream read fails — never synthesize numbers), `internal` (500).
Empty sessions (e.g. ledger with no events in range) are success with empty
arrays plus honest `provenance`, never errors. Fail closed to `null`/`—`
downstream — never invent P&L, fills, or weights.

## 3. House workspace pinning

Every Group A book read filters `workspace_id = <house>` where house is the
public book selector `6b753576-ced9-5319-9bfa-c5d0aacd9319` (matches
`houseBook()` in `apps/dashboard/lib/house-workspace.ts` and the Python
`house_workspace_id()` uuid5 `house` slug). Overlay workspace rows are
excluded even when RLS would allow them for the caller JWT. Shared teasers
without `workspace_id` (`daily_snapshots`, `theses`, `instruments`) stay
date-only; accounting NAV reads go through
`public_accounting_nav_history` (security definer). The UUID is a selector,
not a secret.

## 4. `retrieval_pin` passthrough

`retrieval_pin` is an opaque string the caller supplies (e.g. a
digisearch/digigraph retrieval correlation id). The API never interprets
it: it echoes the exact value back in every success (`top-level
retrieval_pin`) and every error (`error.retrieval_pin`, null when absent),
and forwards it unchanged to any upstream market-data fetch
(`GET /v1/market/closes`, `GET /v1/market/tickers`) so traces join across
the hop. Max length 128; longer values are rejected with `bad_request`.

## 5. Realtime-stays-client-side rule

No route below opens a websocket, SSE stream, or subscription. Live marks
arrive via the existing client lane only: Supabase Realtime
`postgres_changes` on `prices_live` (seed + coalesce per
`apps/dashboard/lib/hooks/use-live-prices.ts`), rendered as a badged
`live marks` overlay that must never wear a `finalized accounting` badge.
`GET /kpis/live` is a point-in-time snapshot computed from the latest
quotes the server can see — it does not push, and clients must not poll it
as a realtime substitute.

## 6. Endpoints

### 6.1 `GET /portfolio`

Committed-book snapshot + invested envelope + folded book-date gate.
Replaces per-page `houseBook()` + `reconcileBook` duplication for the shell.

Query: `asOf?`, `retrieval_pin?`.

Response `data`:

```json
{
  "book_as_of": "2026-09-24",
  "nav_tip": {
    "date": "2026-09-24",
    "nav": 99.909,
    "contract": "legacy_estimate",
    "invested_pct": 35.13,
    "cash_pct": 64.87,
    "day_return_pct": null
  },
  "seam": { "crosses_nav_seam": true, "lag_days": 1, "lag_direction": "metrics lag" },
  "invested": { "kpi_pct": 35.13, "envelope_pct": 35.13, "cash_pct": 64.87, "definition": "accounting_nav_tip" },
  "positions": [
    { "ticker": "XLV", "weight_pct": 20.0, "is_cash": false }
  ]
}
```

Rules: `invested.kpi_pct` is the raw NAV tip `invested_pct` (unclamped —
do not clamp `>100` under an `accounting_nav_tip` label). Row weights are
laid out inside the clamped-100 `reconcileBook` envelope; that envelope is
not the KPI. Fallback order for invested: NAV tip → non-CASH
`positions.weight_pct` sum on the committed book →
`portfolio_metrics.invested_pct` → null. `invested.definition` names the
winning source (`accounting_nav_tip` | `book_weights` |
`portfolio_metrics` | `unavailable`) so surfaces can badge which fallback
produced the KPI. `book_as_of =
committedBookDate(daily_snapshots.date, positions.date)`; null (with
`not_found`) when the snapshot is missing — never silently substitute the
latest position date as "committed". `day_return_pct` is null across NAV
seams or calendar gaps > 4 days. CASH is outside holding counts.

### 6.2 `GET /allocations`

Reconciled allocation rows with folded per-row valuations. Consumes the
same committed book as §6.1.

Query: `asOf?`, `retrieval_pin?`, `include_marks?: boolean` (default true).

Response `data`:

```json
{
  "book_as_of": "2026-09-24",
  "invested_pct": 35.13,
  "cash_pct": 64.87,
  "invested_definition": "accounting_nav_tip",
  "rows": [
    {
      "ticker": "DBO",
      "weight_pct": 5.0031,
      "scaled_weight_pct": 5.0031,
      "entry_price": 22.14,
      "current_price": null,
      "unrealized_pct": null,
      "marks": "unavailable",
      "marks_as_of": null
    }
  ],
  "marks_unstamped": true
}
```

Rules: rows scale into the §6.1 envelope (`invested = min(100,
investedPct ?? heldSum)`, CASH excluded, `scale = invested/heldSum`).
Valuation per row: prefer stored `unrealized_pnl_pct` /
`since_entry_return_pct`; else derive from `entry_price` vs
`current_price`; when the nightly metrics stamp is missing, fill the mark
from the market API (`GET /v1/market/closes`; R2-API-only — empty when unset,
no Supabase fallback); fail closed to null without basis or mark.
`marks_unstamped` is true when the open book is empty or any row lacks
`metrics_as_of` (the `performance-ssot.ts` `marksUnstamped` chrome contract).
`invested_definition` names the §6.1 precedence winner
(`accounting_nav_tip | book_weights | portfolio_metrics | unavailable`).
Mid-session NULL marks affect marks only, never weights.

### 6.3 `GET /brief`

Brief scoreboard KPIs with the persisted-vs-overlay decision made in one
place. Replaces the split page/hooks/ssot decision. `since_inception_start_date`
is the first date of the chained NAV series the since-% is measured from
(null when the series is empty).

Query: `asOf?`, `retrieval_pin?`, `overlay?: "auto" | "off"`
(default `"auto"`).

Response `data`:

```json
{
  "book_as_of": "2026-09-24",
  "nav_tip": { "date": "2026-09-24", "nav": 99.909, "contract": "legacy_estimate" },
  "day_return_pct": null,
  "since_inception_pct": 8.4,
  "since_inception_start_date": "2026-08-20",
  "overlay": { "active": false, "live_vs_mark_pct": 0, "badge": "finalized accounting" },
  "invested_pct": 35.13,
  "session_events": []
}
```

Rules: persisted path first (same tip + ssot helpers as the Tearsheet);
the live overlay engages only when `|liveVsMarkPct| > 0`, and then the tile
is labeled `live marks` — never finalized accounting. The seam guard nulls
persisted day return when `crossesNavSeam` is true. Overlay-off Brief must
match Tearsheet within 0.05 pp. `session_events` is the day's
`position_events` slice (honest empty when none).

### 6.4 `GET /performance`

Tearsheet bundle: one contracted NAV series, benchmark-relative headline,
overlap-gated alpha/IR. Served by the shared `getPerformanceBundle`
builder, not recomputed per consumer.

Query: `asOf?`, `retrieval_pin?`, `benchmark?: string` (default `SPY`),
`window?: "inception" | "1y" | "6m" | "3m"` (default `"inception"`).

Response `data`:

```json
{
  "nav": { "tip_date": "2026-09-24", "base100_tip": 108.4, "points": [{ "date": "2026-09-24", "index": 108.4, "day_return_pct": null }] },
  "metrics": {
    "day_return_pct": null,
    "since_inception_pct": 8.4,
    "excess_return_pct": 1.2,
    "alpha_pct": null,
    "information_ratio": null,
    "beta": null,
    "overlap_days": 21
  },
  "benchmark": { "ticker": "SPY", "aligned_start": "2025-09-24" },
  "stale": { "lag_days": 1, "lag_direction": "metrics lag", "metrics_as_of": "2026-09-23" },
  "ssot": { "tipCashPct": 64.9, "tipInvestedPct": 35.1, "investedDefinition": "accounting_nav_tip", "bookAsOf": "2026-09-24", "marksUnstamped": false }
}
```

Rules: NAV chart is the single base-100 continuity index over
`public_accounting_nav_history` (each row's own day return; calendar gaps
≤ 4 days forward-fill; tip badge from the latest dated row only — mixed
history with a legacy tip is not finalized). Excess = `Rp − Rb` over the
NAV-aligned benchmark window. Alpha (Jensen) and IR need ≥ 20 overlapping
daily return pairs (`MIN_OVERLAP_DAYS`) — null below the floor, never
invented from endpoints. Benchmark prices come from paginated
`fetchComparablePriceHistory`, not a single bulk fetch. Lag is signed UTC
calendar days and symmetric (`metrics lag` / `nav lag`); `metricsAsOf` is
the metrics stamp, never overwritten with the NAV tip. `ssot` is the full
`PerformanceSsotMeta` object (same builder the client used: `tipCashPct`,
`tipInvestedPct`, `investedDefinition`, `tipDate`, `metricsAsOf`,
`navContract`, `metricsLag`, `bookAsOf`, `marksUnstamped`,
`metricsDivergenceBadgeLabel`, `navContractBadgeLabel`,
`performanceFreshnessNote`, `isLiveMarksOverlay`) so the Brief scoreboard
can consume it unchanged.

### 6.5 `GET /kpis/live`

Point-in-time live snapshot (see §5 — snapshot only, not a stream).

Query: `retrieval_pin?` (no `asOf` — always latest quotes).

Response `data`:

```json
{
  "quote_date": "2026-09-24",
  "live_vs_mark_pct": 0.4,
  "day_return_live_pct": -0.2,
  "since_inception_live_pct": 8.8,
  "excess_live_pct": 1.4,
  "overlay_eligible": true,
  "universe": ["DBO", "EWZ", "XLV", "XLF"]
}
```

Rules: computed by `computeLivePerformanceKpis` semantics (live quote vs
`entry_price`; excess/alpha/IR need ≥ 20 overlapping NAV/benchmark pairs).
`overlay_eligible` is false (and overlay must stay off) when
`liveVsMarkPct === 0` or the book's `current_price` marks are all NULL.
Numbers here are `live marks` by definition and must never be labeled
finalized accounting.

### 6.6 `GET /nav-series`

Shared NAV + close series. Replaces the `nav-seam.ts` ∥
`accounting-views.ts` duplication — one series builder for all surfaces.

Query: `retrieval_pin?`, `from?: string`, `to?: string`
(`YYYY-MM-DD`; default = full history).

Response `data`:

```json
{
  "tip": { "date": "2026-09-24", "contract": "legacy_estimate" },
  "points": [{ "date": "2026-09-24", "nav": 99.909, "day_return_pct": null, "contract": "legacy_estimate" }]
}
```

Rules: same continuity-index semantics as §6.4 (per-row day returns,
≤ 4-day forward-fill, seam basis changes carry flat). Per-point contract
labels preserved so consumers can badge tip flips (e.g.
`finalized_accounting` → `legacy_estimate`).

### 6.7 `GET /benchmarks`

Benchmark universe + aligned series for a given NAV window. R2-API-only
with benchmark-key fallback.

Query: `retrieval_pin?`, `tickers?: string` (comma-separated; default =
universe from `GET /v1/market/tickers`), `from?: string`, `to?: string`.

Response `data`:

```json
{
  "universe": ["SPY", "QQQ"],
  "series": { "SPY": [{ "date": "2026-09-24", "close": 512.3 }] },
  "aligned_start": "2025-09-24",
  "overlap_days": 21
}
```

Rules: an empty market-API answer falls back to the benchmark keys (#4053,
R2-API-only, no Supabase fallback). Each series aligns to the NAV dates;
sparse/paginated history still renders when remaining overlap meets the
§6.4 floor. Recomputing benchmark + excess on comparison change is a
client re-request with a different `tickers` value, not server state.

### 6.8 `GET /ledger`

Ledger event stream. Single source of truth is `position_events` (house
book); fills/weight changes only — never derive fills from weight diffs.

Query: `asOf?`, `retrieval_pin?`, `ticker?: string`,
`limit?: number` (default 50, max 500), `cursor?: string` (opaque).

Response `data`:

```json
{
  "events": [
    {
      "date": "2026-09-03",
      "ticker": "XLF",
      "type": "TRIM",
      "fill_price": 54.1,
      "avg_entry": 52.0,
      "realized_pct": 4.0,
      "prev_weight_pct": 9.9,
      "weight_pct": 4.9
    }
  ],
  "next_cursor": null
}
```

Rules: `type` ∈ `OPEN | ADD | EXIT | TRIM`. Realized % for sells is vs
average entry (sold weight = `prev_weight_pct − weight_pct`); fail closed
without fill price or cost basis. `cumulative_return_since_event_pct` is
post-event drift and must not be presented as trade return. Empty range →
success with `"events": []` plus honest `provenance`.

## 7. Generic table reads

`GET /v1/tables/:table` serves the dashboard's long-tail direct reads
through one allowlisted worker route so the static bundle never needs the
service-role key. The route proxies PostgREST with the service key and
enforces the §3 house pin server-side.

Allowlisted tables: `daily_snapshots`, `positions`, `instruments`,
`theses`, `portfolio_metrics`, `documents`, `position_events`,
`macro_series_observations`, `decision_log`, `run_health`,
`position_attribution`, `run_event_trace`, `public_accounting_nav_history`,
`thesis_vehicles`, `analyst_coverage`,
`public_daily_realized_attribution` (dossier + observability reads;
main-project tables with no house pin).
Unknown tables → `not_found` (404).

Query: `select?` (comma list, default `*`), repeatable `order=<col>.<asc|desc>`,
`limit?` (default 100, cap 5000), `offset?`, and repeatable filters
`eq.<col>=<v>`, `ilike.<col>=<pattern>`, `like.<col>=<pattern>`,
`in.<col>=(a,b)`, `lt|lte|gt|gte.<col>=<v>`.

Rules: the house pin (`workspace_id = <house>`) is appended server-side for
`positions`, `position_events`, and `portfolio_metrics` and is never
forwarded from the caller; `retrieval_pin` is echoed, never forwarded
upstream. No stub lane — without the service-role key the route fails
closed (`upstream_empty`, 502), never an empty success.

Out of scope for this route: the twelve-x suite (separate Supabase
project with its own session-RLS model — stays direct), Realtime
subscriptions, and Edge Function calls (billing/Alpaca — stay direct).

## 8. Deferred (explicitly not in this contract)

- Write paths: none — all routes are read-only; execution/commit flows
  stay where they are.
- Ledger pipeline repair (at-open execution stall, `recover_ledger.py`
  scope, evening-cron restatement semantics) — Slice Y follow-up, not an
  API shape question.
- NAV-contract badge rendering, carry markers on reused conclusions, and
  structured deliberation→sizing directives — unforced improvements for
  later slices.
- Auth/session changes of any kind (`digikey/` untouched).
- Pagination beyond `GET /ledger` cursor (`limit`/`cursor` only there).
- Any timeout, retry, rate-limit, or tool-call budget language — none
  specified, none implied.
