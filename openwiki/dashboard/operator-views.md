---
type: frontend-guide
title: Dashboard Operator Views
description: Operator-facing views of the digiquant dashboard — brief/today, portfolio (holdings, performance tearsheet, ledger, attribution, theses, tickers), research, pipeline, settings, system, observability, twelve-x, house, library, strategy, architecture, why — each backed by fail-closed contracts and shared SSOT helpers.
tags: [dashboard, digiquant, portfolio, tearsheet, ledger, attribution, research, pipeline]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-85221aa402153c771b314594
    resource: repo://apps/dashboard/lib/accounting-views.ts
  - id: openwiki-source-8a7a17e9a899f3930a5c4c63
    resource: repo://apps/dashboard/lib/digichat-popup.ts
  - id: openwiki-source-4cac2ac8f07d77951dc2b672
    resource: repo://apps/dashboard/lib/house-workspace.test.ts
  - id: openwiki-source-a9e59e8cc238958ba3d5acf9
    resource: repo://apps/dashboard/lib/house-workspace.ts
  - id: openwiki-source-6d9cdb1078237cf717390fec
    resource: repo://apps/dashboard/lib/market-data.ts
  - id: openwiki-source-de1d9ec92ca3775a29f1459f
    resource: repo://apps/dashboard/lib/observability-queries.ts
  - id: openwiki-source-cf61959e1136cb7d059b142f
    resource: repo://apps/dashboard/lib/position-event-economics.ts
  - id: openwiki-source-12065caf14bd4a8a603a39e4
    resource: repo://apps/dashboard/lib/TABLES.md
  - id: openwiki-source-5a929f63280e765f1f3d432a
    resource: repo://apps/dashboard/README.md
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# Dashboard Operator Views

The dashboard (`apps/dashboard`) renders persisted research and portfolio state
from Supabase-backed book tables. Every view shares two invariants: **house book
scope** (Group A reads go through `houseBook()` so overlay weights never seed
the public book) and **fail-closed P&L** (missing basis or mark renders `—`; the
UI never invents numbers).

## View inventory

The top-level route groups at `app/` define the operator surface:

| Route | Role |
|---|---|
| `/` (`app/page.tsx`) | Daily Brief workspace — the morning-read landing page |
| `/portfolio` | Holdings tab shell with Theses, Tearsheet, Ledger, Attribution |
| `/portfolio/performance` | Finance tearsheet — NAV path, contribution, open-book P&L |
| `/portfolio/ledger` | Activity ledger — OPEN/ADD/EXIT/TRIM fills |
| `/portfolio/attribution` | Decision-effectiveness monitor, Book attribution, Audit |
| `/pipeline` | Zoomable/pannable topology graph of the daily decision pipeline |
| `/why` | Reasoning surface — Read, Deliberations, Documents |
| `/research` | Redirects to `/why` (legacy path consolidated) |
| `/library` | Redirects to `/why` |
| `/strategy` | Redirects to `/why` (analysis) |
| `/house` | Corpus \| Book \| Profile — read-only house identity panels |
| `/twelve-x` | FX Hub suite (gated behind `fx_hub` client product grant) |
| `/settings` | Profile \| Pipeline \| Keys \| Brokers \| Notifications \| Billing \| About |
| `/system` | Redirects to `/pipeline` (run health moved) |
| `/observability` | Redirects to `/system` → `/pipeline` |
| `/architecture` | Redirects to `/system` → `/pipeline` |

All views render inside the shared `AppFrame` shell (sidebar + mobile app bar +
command palette). When the Supabase backend is down, the shell stays mounted and
swaps the page body for a `DbUnavailable` card on non-exempt routes
(`apps/dashboard/README.md#L68-L73`).

## Daily Brief (`app/page.tsx`)

The root page is the daily decision workspace. It owns benchmark alignment,
percentage-return calculations, book freshness, rebalance rationale joins, and
a brief-only read of the anon-safe `run_health` view. The workspace follows one
fixed daily-reader sequence:

1. **Situation** — attention headline and Research/Portfolio/Watch beats, each
   deep-linked to the sourced detail
2. **Decision and system state** — latest allocation decision beside pipeline
   health (completed/degraded/failed/loading/unavailable)
3. **Scoreboard** — day and since-inception returns, aligned benchmark excess,
   alpha, information ratio, invested allocation (whole band → Tearsheet)
4. **Risk and debate** — ranked actionable signals → digest; thesis name → thesis
   detail when known
5. **Book monitor** — session ledger preview → Ledger; holdings tickers →
   dossiers
6. **Drill-ins** — Digest, Pipeline, Performance, Holdings, Ledger, Theses

The Brief consumes the same Performance SSOT helpers as the Tearsheet:
`buildPerformanceSsotMeta`, `persistedHeadlinesFromNav`,
`persistedInsightMetrics`. Live marks on Brief are a **badged overlay only**
— never a silent second truth. The workspace is one command band, compact
metrics, flat hairline ledgers, and no nested or decorative cards.
(`apps/dashboard/app/page.tsx#L1-L33`,
`apps/dashboard/README.md#L418-L444`)

## Portfolio Holdings

`app/portfolio/page.tsx` renders `PortfolioShellInner`, which owns the
Allocations / Theses tab bar, the sleeve-stack series (by ticker, category, or
thesis via `buildSleeveStackSeries` in `lib/portfolio-aggregates.ts`), position
history, thesis-vehicle joins, and decision badges. Holdings tables use a local
table grammar (sector group header rows, conviction meters, responsive column
hiding) that the promoted `<SortableTable/>` leaderboard cannot host
(`apps/dashboard/lib/TABLES.md#L1-L27`). The ticker dossier
(`app/portfolio/tickers/page.tsx`) uses query-string routing (`?ticker=`), never
a dynamic segment, to avoid hard-404s on pipeline-created tickers after the last
deploy (`apps/dashboard/README.md#L402-L415`).

## Performance Tearsheet (`/portfolio/performance`)

The tearsheet renders via `PerformanceTearsheetView`, loaded by
`getPerformanceBundle()` in `lib/observability-queries.ts` — the same NAV
adapter Brief uses (#3580). The tier gate is `house_weights_nav` (Brief+);
`EntitledSurface` blocks the fetch for locked tiers.

The tearsheet consumes the **Performance SSOT** metric-source matrix
(`apps/dashboard/lib/TABLES.md#L95-L111`):

| Metric | Source | Date | Units | Null / fallback |
|---|---|---|---|---|
| NAV chart | `public_accounting_nav_history` | Each row `date` | Paper NAV index (base-100 continuity) | Fail closed on query error |
| Day return | Accounting tip `day_return_pct`; else adjacent NAV ratio | Tip date | Percentage points, one session | Null when gap > 4 calendar days |
| Since inception | Chained base-100 continuity tip − 100 | First NAV date → tip | Percentage points | Null with fewer than 2 finite NAV points |
| Excess return | Rp − Rb over aligned benchmark window | Aligned start → tip | Percentage points | Null if benchmark missing |
| Alpha (Jensen) | Rp − β·Rb; β = OLS of overlapping daily returns | Same window | Percentage points | Null when daily pairs < 20 |
| Information ratio | mean(daily excess) / sampleStd × √252 | Same overlap | Dimensionless annualized | Null when overlap short or TE ≈ 0 |
| Invested % | Accounting NAV tip `invested_pct` | Tip date | % of NAV | Fallback: book weights → `portfolio_metrics` |
| Book as-of | `committedBookDate(snapshot, positions)` | Snapshot ∩ positions | Calendar date | Null when snapshot missing |
| Marks / unrealized | `positions.metrics_as_of` + `current_price` / market API `GET /v1/market/closes` | `metrics_as_of` or close date | Unrealized % vs avg entry | Fail closed without basis or mark |

The NAV chart chains source runs so the legacy→finalized seam never enters the
return window, and calendar gaps ≤4 days forward-fill the last value (#4014).
Benchmark prices come from `fetchComparablePriceHistory` (paginated), not a
single `limit(5000)` across all tickers. The benchmark universe is fetched from
the R2-backed market API (`GET /v1/market/tickers`); an empty answer falls back
to the benchmark keys. Contribution bars read the finalized per-ticker daily
contribution from `public_daily_realized_attribution` (#3956), falling back to
weight-times-mark accrual when the view yields no usable rows.

(`apps/dashboard/lib/performance-ssot.ts#L1-L50`,
`apps/dashboard/lib/TABLES.md#L78-L117`,
`apps/dashboard/app/portfolio/performance/page.tsx#L1-L60`)

## Ledger (`/portfolio/ledger`)

Ledger is the **single source of truth for fills**. Every `OPEN` / `ADD` /
`EXIT` / `TRIM` event renders with average entry, fill price, sold weight, and
realized % vs average entry for sells. The tearsheet links here instead of
duplicating a closed-positions tab.

Trade economics flow through `ledgerEventEconomics()` in
`lib/position-event-economics.ts`:

- Average entry: latest `entry_price` on or before the event date for the
  ticker, from the position history
- Fill price: `finitePositive(event.price)`, null when missing
- Sold weight: `prev_weight_pct − weight_pct` for TRIM; `prev_weight_pct` for
  EXIT without a residual
- Realized return: `(fillPrice / avgEntry − 1) * 100`, null without both
  components

`position_events.cumulative_return_since_event_pct` is post-event drift and
must never be presented as trade return. Non-sell events (OPEN/ADD) prefer
`positions.entry_price` as of the event date, falling back to fill price when no
mark exists — never label fill as average cost when the book already carries a
basis. Tier gate is `house_weights_nav` (Brief+); `LockedSurface` renders
before loading chrome so Observer never waits on the book payload.

(`apps/dashboard/lib/position-event-economics.ts#L1-L107`,
`apps/dashboard/app/portfolio/ledger/page.tsx#L1-L40`)

## Attribution (`/portfolio/attribution`)

The attribution workspace defaults to a compact **Decision effectiveness**
monitor with Book attribution and Audit as sibling views. Headline metrics use
direction-adjusted alpha over independently scored decisions: bearish calls
negate stored raw alpha, watch calls remain audit-only, and overlapping
same-ticker, same-stance updates count once from their initiating call.
Calibration stays "insufficient evidence" until at least two buckets each hold
10 independent decisions.

Analysis defaults to all available history; 1W, 1M, 3M, YTD, and 1Y period
controls rescope every decision metric, diagnostic, review item, Audit row, and
trend point. The trend is cumulative across every independently scored decision
in the selected period; it has no separate call-count window. The visible
consistency ratio is mean decision edge divided by its variability — never
presented as an annualized information ratio. Book attribution is the latest
stored snapshot and says so explicitly. Audit preserves every raw row and raw
alpha at 25 rows per page.

Tier gate is `house_weights_nav` (Brief+). Data loads via
`fetchPortfolioAttribution()` in `lib/observability-queries.ts`, which collects
from `position_attribution` and `decision_log`.

(`apps/dashboard/README.md#L38-L48`,
`apps/dashboard/README.md#L157-L168`,
`apps/dashboard/app/portfolio/attribution/page.tsx#L1-L39`)

## Pipeline and Why

Pipeline (`app/pipeline/page.tsx`) renders a zoomable/pannable topology graph of
the daily decision pipeline (Inputs → Research → Synthesis → Selection →
Decision). It supports deep-link grammar (`?date=&stage=&node=`) via
`useSearchParams()` — a Suspense boundary wraps `PipelineClient` because this is
a static export with no server-side `searchParams`. The workspace has no visible
page heading; the accessible `h1` is `sr-only`.

Why (`app/why/page.tsx`) is the reasoning surface with three URL-driven tabs:
`?why=read` (latest synthesis as a divided reading workspace),
`?why=deliberations` (rebalance actions, risk/ticker debates, PM memo history as
flat ledgers), and `?why=documents` (underlying artifact library). `app/research`,
`app/library`, and `app/strategy` all redirect to Why.

Pipeline has three inspection surfaces: Topology (graph + run status), All
Artifacts (every persisted `document_key`), and Call Trace (ordered
model/search/tool operations from `run_event_trace`, paged 100 rows at a time,
grouped by run attempt and phase). Historical runs without ingestion-time events
say "Call details were not recorded for this run" — they are never reconstructed
from aggregate diagnostics. Pipeline Health notes hidden newer positions only
when those dates exist; a snapshot query error fails closed.

(`apps/dashboard/app/pipeline/page.tsx#L1-L36`,
`apps/dashboard/app/why/page.tsx#L1-L14`,
`apps/dashboard/README.md#L446-L495`)

## House

`app/house/page.tsx` renders three read-only panels — Corpus | Book | Profile —
with `HouseIdentityChrome` tab navigation. Profile pins are declared chrome until
Track B `ProfileConfig` DB lands; they are not editable Settings. The house book
banner links to this surface from Brief and Portfolio views.

(`apps/dashboard/app/house/page.tsx#L1-L43`,
`apps/dashboard/README.md#L98-L101`)

## Twelve-X

The FX Hub suite (`app/twelve-x/page.tsx`) is gated behind
`ClientProductGate` with product key `fx_hub` (creator +
`client_product_grants` email allowlist). The client gates itself on its own
research feed (`isTwelveXConfigured`), making the route DB-exempt. Tabs include
Today, Briefs, Ideas, Consensus, Events, Matrix, and Trades. The Consensus table
keeps local code because its frozen visual spec exceeds the promoted
`<SortableTable/>` string-cell API on six axes (ReactNode cells, per-cell
conditional color, a presentational score-bar column, derived sort values with
null-last ordering, optional Trace column, unlayered `.srt-table td`
typography).

(`apps/dashboard/app/twelve-x/page.tsx#L1-L41`,
`apps/dashboard/components/twelve-x/TwelveXClient.tsx#L1-L60`,
`apps/dashboard/lib/TABLES.md#L34-L39`)

## Settings

`/settings` is a tabbed workspace — **Profile | Pipeline | Keys | Brokers |
Notifications | Billing | About**. Tab visibility is tier-gated: Observer and
Brief see Notifications | Billing | About only; Desk adds Brokers; Studio+ sees
the full set. Tabs the current tier cannot use are omitted, not greyed.

- **Profile** — client JSON-schema validation + Edge Function re-validation;
  saves append `olympus_profile_config` versions. Studio+ only.
- **Pipeline** — overlay watchlist/themes/budget knobs, 7×3 schedule grid, and
  execution-policy controls. Studio+ only.
- **Keys** — BYOK LLM provider seal/revoke (fingerprint-only after save). Studio+.
- **Brokers** — Alpaca OAuth (`env=paper`) and API-key entry; IBKR labeled beta.
  Desk+ only.
- **Notifications** — PATCH prefs; delivery event log.
- **Billing** — links Stripe checkout/portal for Brief/Desk/Studio tiers.
  Observer is free, not a Stripe product.
- **About** — remaining-hop product state with closed-vocabulary blockers.

(`apps/dashboard/README.md#L320-L368`,
`apps/dashboard/app/settings/page.tsx#L1-L30`)

## Redirect routes

Several top-level routes are thin redirects:
- `/research` → `/why` (legacy research path consolidated)
- `/library` → `/why` (document library folded into Why's Documents tab)
- `/strategy` → `/why` (analysis → reasoning)
- `/system` → `/pipeline` (run health moved to Pipeline Health)
- `/observability` → `/system` → `/pipeline`
- `/architecture` → `/system` → `/pipeline`
- `/portfolio/period` → `/portfolio/performance` (legacy period view → Tearsheet, #3060)

Thesis detail routes use query-form URLs (`/portfolio/theses?thesis=<id>`) rather
than `[thesisId]` dynamic segments, because under `output: 'export'` only
enumerated ids get an HTML file and every thesis created after the last deploy
would hard-404. The ticker dossier uses the same pattern. Legacy path-form URLs
(`/portfolio/theses/<id>`) land on the dashboard 404.

(`apps/dashboard/README.md#L402-L415`)

## Desk+ digichat popup

Desk / Studio / Enterprise sessions see a bottom-right digichat launcher that
iframes digichat `/embed?layout=embed`. Brief and Observer see the same
launcher, but opening it shows an upgrade CTA panel with chat disabled — no
iframe, so baseline never burns turns and never meets the free-3 gate.

**Plan proof is HMAC-based, never raw-tier-header.** The embed mints an HMAC
proof via `POST /api/plan-proof` only after verifying the dashboard Supabase
access token and reading `app_metadata.plan_tier` (Desk / Studio / enterprise
only). Chat accepts `X-Embed-Plan-Proof` (or an authenticated digichat session
with claims `plan_tier`). The popup never trusts client-asserted
`X-Embed-Plan-Tier` or `?plan_tier=` query params. Ops secrets:
`DIGICHAT_PLAN_PROOF_SECRET`, `DIGICHAT_DASHBOARD_SUPABASE_URL`,
`DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY` on digichat.

The popup sends page-context (structurally sanitized HTML ≤12k chars + visible
text ≤8k) on open and then only when the page signature changes (~500ms
debounced, deduped by FNV-1a hash). The sender walks the live DOM and honors
`data-digichat-private` opt-out regions. The embed can opt out by including
`pageContext: "off"` on its `digichat:ready` payload.

The popup is on by default; kill with `NEXT_PUBLIC_DIGICHAT_POPUP=0`. Client
reads use direct `process.env.NEXT_PUBLIC_*` property access so Turbopack
inlines them — passing whole `process.env` leaves the client empty and the
launcher disappears after hydrate (#3561).

(`apps/dashboard/lib/digichat-popup.ts#L1-L360`,
`apps/dashboard/README.md#L248-L307`)

## House book scope

Every house-dashboard Group A read (`positions`, `nav_history`,
`position_events`, `portfolio_metrics`) goes through `houseBook()`, which pins
the house `workspace_id` (`6b753576-ced9-5319-9bfa-c5d0aacd9319`). Migration 109
lets an authenticated Custom member SELECT their own overlay rows or house, so
omitting the workspace filter would mix overlay weights into the public Brief /
Holdings / Performance surfaces. Shared teasers without `workspace_id`
(`daily_snapshots`, `theses`, `instruments`) stay date-only.

The accounting NAV reads `public_accounting_nav_history` (security definer;
house-only until a later view rewrite). Rollback to legacy views is a constant
repoint (`LEGACY_PUBLIC_NAV_VIEW = 'public_nav_history'`).

(`apps/dashboard/lib/house-workspace.ts#L1-L45`,
`apps/dashboard/lib/house-workspace.test.ts#L54-L73`,
`apps/dashboard/lib/accounting-views.ts#L1-L12`)

## Performance SSOT (#3580 / #3604)

The canonical metric-source matrix lives in `apps/dashboard/lib/TABLES.md` §
Performance SSOT. Condensed rules:

- NAV / day / since-inception from the **tip** of `public_accounting_nav_history`
  (chained across source runs, calendar gaps ≤4 days forward-filled — #4014)
- Alpha / IR need ≥20 overlapping daily pairs
- Invested % is the tip (unclamped); live Brief marks are a `live marks` overlay
  and must never wear a `finalized accounting` badge
- Metrics↔NAV lag is symmetric (`metrics lag` / `nav lag`), signed UTC calendar
  days, badged when |lag| ≥ 1
- Brief persisted KPIs must match Tearsheet within 0.05 pp when overlay is off

Code entrypoints: `lib/performance-ssot.ts` (pure SSOT helpers),
`lib/observability-queries.ts` (`getPerformanceBundle()`),
`app/page.tsx` (Brief persisted path + live-marks badge),
`app/portfolio/performance/page.tsx` (Tearsheet consumer).

(`apps/dashboard/lib/TABLES.md#L78-L117`,
`apps/dashboard/lib/performance-ssot.ts#L1-L330`)

## Fail-closed P&L

Every view that renders a performance number fails closed to `—` without a
basis or mark:

- **Unrealized P&L:** prefers stored `unrealized_pnl_pct` /
  `since_entry_return_pct`, else derives from `entry_price` vs `current_price`.
  When the nightly metrics stamp is missing, fills the mark from the market API
  (`GET /v1/market/closes`, AS OF = that close date; empty when
  `NEXT_PUBLIC_MARKET_DATA_URL` is unset, R2-API-only, no Supabase fallback —
  #4053). Fail closed to `—` without basis or mark.
- **Ledger fills:** fail closed without fill price or cost basis — never invent
  fills.
- **NAV chart:** `getPerformanceBundle` fails closed on
  `public_accounting_nav_history` query error — swallowing into an empty series
  would look like a healthy empty book (#3029).
- **Book reconciliation:** `reconcileBook()` dedupes overlapping tickers, excludes
  an explicit CASH row from the held set (#1553), and normalizes so held + cash
  = 100% — never >100%.
- **Committed-book SSOT:** Brief, Pipeline, pm-rebalance, and holdings follow
  `daily_snapshots.date`. Positions newer than the snapshot are ignored;
  `assertDailySnapshotQueryOk` fails closed on query error.

(`apps/dashboard/lib/book-reconciliation.ts#L1-L90`,
`apps/dashboard/lib/dashboard-ssot.ts#L1-L71`,
`apps/dashboard/lib/market-data.ts#L1-L77`,
`apps/dashboard/lib/observability-queries.ts#L19-L27`)

## Committed-book SSOT

`lib/dashboard-ssot.ts` provides:

- `committedBookDate(snapshotDate, positionDates)` — latest position date on or
  before the committed snapshot
- `previousBookDate(bookDate, positionDates)` — prior book date strictly before
- `bookedCoversCommittedSnapshot(snapshotDate, bookDate)` — true when booked
  positions are for the snapshot date itself
- `unpublishedBookNote(snapshotDate, positionDates)` — operator copy when
  positions are newer than the committed snapshot
- `assertDailySnapshotQueryOk(error)` — throw when the daily_snapshots query
  failed

Every book surface derives invested exposure and displayed weights from the same
effective `positions` snapshot. An independently latest `portfolio_metrics` row
must not rescale those positions.

(`apps/dashboard/lib/dashboard-ssot.ts#L1-L71`)
