# Olympus dashboard

Next.js 15 investment-intelligence dashboard for **digiquant Olympus** — the unified product surfacing both Atlas (research) and Hermes (analysis + PM). Joins the root npm workspace at `frontend/olympus/` and consumes the shared design system via
`@digithings/design` as a workspace dependency.

## Quant-native visual layer

Olympus matches the digiquant.io aesthetic by importing the shared canon
tokens, **the** Tailwind v4 bridge (`web-theme.css`), and the quant-native +
finance-tearsheet grammars directly in `app/globals.css`:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
@import "@digithings/design/tokens.css";
@import "@digithings/web/styles/web-theme.css";        /* THE @theme inline bridge (#1402) */
@import "@digithings/design/quant-native/styles.css";
@import "@digithings/web/styles/finance-tearsheet.css"; /* print-grade .ts-* family (#1463) */
```

The performance tear sheet (`/portfolio/performance`) renders persisted NAV and
return metrics, a base-zero portfolio path, current-book contribution, and
open-position outcomes. Closed / trimmed fills live on **Ledger** (single source
of truth) — the tearsheet links there instead of duplicating a Closed positions
tab. Its command band uses the same compact as-of stamp as Holdings and shows one
benchmark-relative headline (**Excess return** = Rp − Rb); Relative gain was a
duplicate alias and was removed. Open-book **Unrealized** prefers stored `unrealized_pnl_pct` /
`since_entry_return_pct`, else derives from `entry_price` vs `current_price`, and
when the nightly metrics stamp is missing fills the mark from `price_history`
(AS OF = that close date). Fail closed to `—` without basis or mark — never invent
P&L. Ledger lists every `OPEN` / `ADD` / `EXIT` / `TRIM` fill with avg entry, fill
price, and realized % vs average entry for sells (sold weight from
`prev_weight_pct − weight_pct`). Fail closed without fill price or cost basis —
never invent fills. `position_events.cumulative_return_since_event_pct` is
post-event drift and must not be presented as trade return. The separate
attribution workspace
(`/portfolio/attribution`) defaults to a compact Decision effectiveness monitor,
with Book attribution and Audit as sibling views. Headline metrics use direction-
adjusted alpha over independently scored decisions: bearish calls negate stored raw
alpha, watch calls remain audit-only, and overlapping same-ticker, same-stance
updates count once from their initiating call. Calibration remains "insufficient
evidence" until at least two buckets each have 10 independent decisions. Audit
preserves every raw row and raw alpha while rendering 25 rows per page. CASH remains outside holding
counts and position charts, but its allocation effect is included in headline active return
so the decomposition reconciles to portfolio return minus benchmark return.
Performance fetches the populated approved benchmark universe from `price_history`,
aligns each series to the NAV dates, defaults to SPY, and recomputes benchmark and
excess return when the comparison changes.
Olympus keeps its finance-tearsheet variants and shell print rules app-side at the
bottom of `globals.css`.

The root layout scopes the page to the digiquant accent and blueprint
background:

```tsx
<body className="qn-blueprint-bg accent-digiquant ...">
```

### Utilities adopted from the design

- `.qn-blueprint-bg` — faint repeating hairline grid; dark by default, the
  light-theme override lives under `html.light .qn-blueprint-bg` in
  `globals.css` (the design tokens are dark-only).
- `.accent-digiquant` — sets `--accent` to the muted emerald used across
  digiquant.io. Individual routes may nest `.accent-atlas` to shift to the
  Atlas-specific green where appropriate.
- `.qn-metric` — tabular, mono, right-aligned numeric cells. Applied to the
  server-metrics strip; extend to additional metric sites as needed.
- `.qn-up` / `.qn-down` — directional P&L text, re-pointed in `globals.css` to
  the canon `--up` / `--down` tokens (money-color semantics, fixed per theme —
  they never follow a livery). Error and warning states draw from the canon set
  too, via `text-down` / `text-warn`; the old `--color-fin-red` /
  `--color-fin-amber` tokens were removed in #1402.

### Page chrome

`app/layout.tsx` renders a thin monospaced header strip (`.qn-page-chrome`)
at the top of `<main>` with route crumbs on the left and an `Open digiquant.io`
link plus version/env label on the right. The version label reads
`process.env.NEXT_PUBLIC_OLYMPUS_VERSION` and falls back to `v0.1 · dev`.

**House identity (#2643 / #1945 Track C):** Brief and Portfolio surfaces show a
compact digithings house ETF paper book banner linking to `/house` —
**Corpus | Book | Profile** (read-only). Profile pins are declared chrome until
Track B ProfileConfig DB lands; they are not editable Settings.

**Portfolio sections:** Holdings · Theses · **Tearsheet** (`/portfolio/performance`) ·
**Ledger** (position-event activity) · Attribution. Legacy `/portfolio/period`
redirects to Tearsheet (#3060). Accounting tip views (`public_accounting_period_status`)
remain available to Tearsheet/Ledger; raw `olympus_accounting_*` bases stay
service_role-only (#2652).

Shared workspace gutters use `SUBPAGE_MAX` from
`components/layout-constants.ts`. The constant intentionally lives outside
client components so server-rendered pages and Suspense fallbacks receive a
plain class string during static export. Interactive section navigation remains
in `components/subpage-tab-bar.tsx` and imports the constant from that module.

### Chart theming

Time-series charts (NAV/equity curves, drawdown, rolling risk, price + position
panes) render on **lightweight-charts** — #1420 migrated six such charts off
recharts onto the shared `useLightweightChart` scaffold (`lib/lw-chart.tsx`).
recharts stays for categorical/composition surfaces (bars keyed by
ticker/bucket, 100%-stacked allocation, trivial sparklines), which
lightweight-charts has no grammar for. The engine ruling and the full per-file
inventory live in [`lib/CHARTS.md`](lib/CHARTS.md).

Global `.recharts-*` overrides in `globals.css` now reference the canon tokens
(`--hair`, `--ink-mute`, `--font-mono`) so the remaining categorical charts
follow the shared palette. Every chart color — both engines — comes from
`lib/chart-colors.ts` (the single sanctioned color source, #1402).

### Table grammar

The portfolio tables stay app-local: the promoted `<SortableTable/>`
leaderboard (`@digithings/web` finance-composites) cannot host their row
drilldown, sector grouping, per-cell money tones, or responsive column
hiding (#1450 F4 batch D). The twelve-x tables stay local too: the frozen
Consensus — G10 spec exceeds the primitive's string-cell API, and MatrixTab
has no sortable tabular surface at all (#1450 F5 tables). The per-file
rulings — and what adoption would take — live in
[`lib/TABLES.md`](lib/TABLES.md). New *flat* leaderboards should adopt the
primitive instead of hand-rolling sort state.

### Portfolio workspace grammar

The Portfolio routes follow digiweb's canonical `PortfolioWorkspaceReference`:
one flat command band establishes book or dossier state, then hairline-divided
ledgers carry positions, activity, research, and decision history. Holdings owns
an exposure command band plus switchable position/activity ledgers; Theses uses
a conviction-ranked research spine. The ticker dossier follows one lifecycle:
current Pipeline view, current or historical portfolio position, material allocation
actions, measured performance and attribution, then analysis history. It shows only
the current stance and concise thesis summary; exact-date links open the Selection
stage in Pipeline, which remains the owner of generated analysis and deliberation.
Position history excludes routine HOLD observations and initially shows six material
actions. Latest ticker attribution is explicitly a stored book window, not since-entry
performance. Thesis detail routes retain the editorial main/context composition.

Attribution follows the dashboard-workspace variant: one command band carries the
decision verdict, sample-size context, selected analysis period, as-of stamp, and the
Decision effectiveness / Book attribution / Audit switch. The default view keeps
four headline metrics, one decision-edge plot, stance/conviction diagnostics, and a
five-item review queue in the primary scan path. Analysis defaults to all available
history; 1W, 1M, 3M, YTD, and 1Y period controls rescope every decision metric,
diagnostic, review item, Audit row, and trend point. The trend is cumulative across
every independently scored decision in the selected time period; it has no separate
call-count window. The visible consistency ratio is explicitly named for what it is
(mean decision edge divided by its variability), rather than presented as an
annualized information ratio. Book attribution remains the latest stored snapshot and
says so explicitly because its persisted rows are not a historical return series.

Across the four Portfolio views, command bands and ledgers carry the context without
introductory feature prose. Holdings and Performance normalize stored allocation keys
into reader-facing categories. Theses opens as a collapsed conviction-ranked register,
leaving generated research detail behind an intentional disclosure. Performance states
the exact inception-to-metrics period for its NAV, portfolio, benchmark, and active
returns; its contribution chart identifies the selected benchmark without visible
interaction instructions.

Every book surface derives invested exposure and displayed weights from the same
effective `positions` snapshot. An independently latest `portfolio_metrics` row
must not rescale those positions: the tables already store percent-of-NAV weights,
and an explicit CASH row is presentation-excluded by `reconcileBook`. This contract
applies equally to the Brief book strip, its Holdings doorway, and Portfolio
Holdings.

`/portfolio/performance` applies the same flat grammar to the shared
finance-tearsheet primitives. Its command band, contribution chart, position
ledgers, and PDF action remain presentation over `nav_history`, `positions`,
`portfolio_metrics`, `position_attribution`, `position_events`, and
`price_history`. Contribution bars contain only tickers in the latest positive-weight
book; the exact NAV return and selected benchmark remain separate line layers.
Portfolio presentation changes must not introduce a second query path or replace
that persisted truth model. Narrow finance chart panes reduce date axes to endpoint
labels while preserving the complete print view.

## Supabase / RLS

Olympus reads portfolio and research data from the shared Atlas Supabase project
(`digiquant/supabase/migrations/`). Migration `001_initial_schema.sql` enables
row-level security and adds `anon_read` policies (`FOR SELECT TO anon USING (true)`)
on core tables so the static export can query with `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

**Threat model:** this is a **public read-only demo** — anyone with the anon key
(canonical in the client bundle) can `SELECT` published snapshot rows. Write paths
are not exposed to the browser. A production hardening path is a BFF with
service-role credentials and restrictive RLS; that is tracked under audit REM-035/036
and requires human product/security sign-off before changing live policies.

**REM-036 (optional BFF):** set `NEXT_PUBLIC_OLYMPUS_USE_BFF=1` and host Olympus on a
Node runtime with `GET /api/snapshots` (service-role read). Static export on
digiquant.io cannot ship App Router API routes — `lib/snapshot-fetch.ts` keeps the
anon path as default. See `docs/reviews/REM-deferred-ops.md`.

**REM-037:** `public/dashboard-data.json` is **gitignored** and must not be committed;
`scripts/build-digiquant.sh` fails the build if the file is present. Portfolio data
comes from Supabase (`daily_snapshots`), not a static JSON artifact in git.

**CSP (REM-077):** security headers ship from `frontend/digiquant-web/public/_headers`,
which `scripts/build-digiquant.sh` copies to the **dist root** — Cloudflare Pages
ignores `_headers` files below the output root, so a copy under `dist/olympus/`
would never apply in production (#674).
The dashboard CSP is scoped to `/olympus*`; landing pages keep Google Fonts working.
Its `connect-src` permits Supabase reads over HTTPS and Realtime subscriptions over
secure WebSockets (`wss://*.supabase.co`).
Constants live in `lib/security-headers.mjs` (Vitest-covered, asserts alignment).

**Deploy freshness (#1759):** `scripts/write-build-info.sh` writes
`dist/build-info.json` (`site`, `commit`, `branch`, `builder`, `built_at`) into the
export root on every build. A Cloudflare Pages project that stops producing
deployments keeps serving the last good build with a 200 and no `last-modified`
header, so the asset probes in `smoke-site.yml` pass throughout a deploy freeze.
The `freshness` job in that workflow reads the live stamp through
`scripts/check_deploy_freshness.py` and fails when it is missing or older than 7
days. Why the *cause* of a freeze is not detectable here: Pages' deployment list,
build log, production branch and watch-path config are visible only in the
Cloudflare dashboard.

## Settings workspace (T3)

`/settings` is a tabbed workspace — **Profile | Pipeline | Keys | Brokers | Notifications | Billing | About**.
The 2026-06-24 Settings plan's "no accounts/login" constraint is **superseded** by the
Kairos tenancy program: authenticated users edit versioned investment overlays, connect
paper brokers, seal BYOK LLM keys, and open Stripe checkout/portal.

- **Profile** — client JSON-schema validation (bundled v1 schemas) plus Edge Function
  re-validation; saves append `olympus_profile_config` versions (never mutate; never the
  reserved `house` key). Optimistic concurrency via last-seen version id → 409 → reload UI.
  Gated as Custom-tier (`overlay_profile` via `EntitledSurface`).
- **Pipeline** — overlay watchlist / themes / `research_budget_usd` knobs, plus a read of
  `GET /settings/jobs` (skip reasons such as `no_credentials` are visible; remaining-hop
  proof is `succeeded` only).
- **Keys** — BYOK LLM provider seal/revoke (fingerprint-only after save).
- **Brokers** — Alpaca OAuth (`env=paper` + sessionStorage `state`) and API-key entry;
  IBKR credential entry labeled beta. Renders fingerprint / broker / env / status /
  `last_used_at` only, plus `GET /settings/fills` paper-fill fingerprints. Gated as
  Custom-tier (`broker_status`).
- **Notifications** — PATCH prefs; `GET /settings/notifications/log` delivery events
  (digest remaining-hop needs a `digest:` log key **and** inbox confirmation).
- **Billing** — links T2 `create-checkout-session` / `customer-portal`; shows
  "billing not configured" when Supabase/billing envs are absent.
- **About** — remaining-hop product state (member-scoped Settings reads; Observer can
  see unproven Stripe / Alpaca OAuth / overlay / fill / digest without Custom writes)
  plus prior ops/status/appearance card content.

Edge Function: `digiquant/supabase/functions/settings` (`verify_jwt` true). **Deploy is
blocked on K3** (vault + `broker_connections`) — see that function's README.

## Running

```bash
# From repo root
npm install                                # links workspace packages
npm --workspace frontend/olympus run dev     # http://localhost:3000/olympus/
npm --workspace frontend/olympus run build   # static export (output: 'export')
npm --workspace frontend/olympus run check:static-export # verify server/client class boundaries
npm --workspace frontend/olympus run lint
npm --workspace frontend/olympus run test    # Vitest (lib/**/*.test.ts + components/**/*.test.tsx)
```

## Environment variables

Copy `.env.local.example` to `.env.local` and fill in your Supabase credentials:

| Variable                          | Purpose                                                                                                  |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`        | Supabase project URL. Used by every client-side reader, including `lib/snapshot-fetch.ts`.               |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`   | Supabase anon key. The frontend reads `daily_snapshots` under the `anon_read` RLS policy (migration 011). |
| `NEXT_PUBLIC_OLYMPUS_AUTH`        | Optional. Set to `1` to enable Supabase Auth login (Google/GitHub PKCE). Default off = today's anon path. |
| `NEXT_PUBLIC_OLYMPUS_VERSION`     | Optional. Shown in the page-chrome version label (defaults to `v0.1 · dev`).                              |
| `NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID` | Public Alpaca OAuth client id for Brokers connect (secret stays on the Edge Function).               |
| `NEXT_PUBLIC_SUPABASE_FUNCTIONS_URL` | Optional Functions base; defaults to `$NEXT_PUBLIC_SUPABASE_URL/functions/v1`.                       |
| `NEXT_PUBLIC_STRIPE_BILLING_ENABLED` | Set `0` to force Billing "not configured"; otherwise inferred from Supabase URL.                     |

When the URL or anon key is unset the daily-snapshot panel renders an empty
banner pointing back to this section instead of throwing. On Cloudflare Pages
builds (`CF_PAGES=1`) both vars are **required** — `scripts/build-digiquant.sh`
aborts rather than shipping a bundle whose every page shows the unconfigured
error (#674).

**Thesis detail routes (#1760):** a thesis detail view is `/portfolio/theses?thesis=<id>`
— one statically exported page that reads the id from the query string at runtime.
It replaced a `[thesisId]` dynamic segment whose `generateStaticParams` enumerated
the `theses` table at build time: under `output: 'export'` only enumerated ids get
an HTML file, so every thesis the daily pipeline created after the last deploy
hard-404ed (five live links on 2026-08-01). Build a thesis href with
`thesisDetailHref()` from `lib/portfolio-url-state.ts`, never by interpolating a
path segment — `lib/thesis-route-canon.test.ts` fails the build if either the
dynamic segment or a path-form href comes back. The `?ticker=` dossier route
(`app/portfolio/tickers/page.tsx`) is the same pattern for the same reason.

Path-form URLs (`/portfolio/theses/<id>`) are no longer served; old bookmarks land
on the Olympus 404. Every in-app link, the command palette, and the legacy
`/strategy?thesis=` redirect all emit the query form.

## Brief workspace

`app/page.tsx` is the daily decision workspace. It owns benchmark alignment,
percentage-return calculations, book freshness, rebalance rationale joins, and a
brief-only read of the anon-safe `atlas_run_health` view. It passes those truth
contracts into `components/today/daily-brief-workspace.tsx`, which follows one
fixed daily-reader sequence:

1. **Situation** — attention headline and Research/Portfolio/Watch beats, each
   deep-linked to the sourced detail (digest, ticker dossier, theses, ledger).
2. **Decision and system state** — the latest allocation decision (dossier /
   pm-rebalance) beside completed, degraded, failed, loading, or unavailable
   pipeline health (Open → run date on Pipeline).
3. **Scoreboard** — day and since-inception returns, aligned benchmark excess,
  alpha, information ratio, and invested allocation (whole band → Tearsheet).
4. **Risk and debate** — ranked actionable signals → digest; thesis name → thesis
   detail when known.
5. **Book monitor** — session ledger preview → Ledger; holdings tickers → dossiers.
6. **Drill-ins** — Digest, Pipeline, Performance, Holdings, Ledger, Theses.

The workspace adapts the digiweb `DashboardWorkspaceReference`: one command band,
compact metrics, flat hairline ledgers, and no nested or decorative cards. The
headline appears once. Loading uses `PageSkeleton`; failures use the shared
`EmptyState`; missing book, research, or run-health values render explicit local
empty states. Research and book dates remain independent and use `AsOfBadge`, so
a fresh digest cannot make stale performance or allocation look current. `--up` and
`--down` remain reserved for signed returns; regime and pipeline state use accent,
warning, or neutral tokens.

## Pipeline and Why workspaces

Pipeline and Why extend the same digiweb workspace grammar across the
reasoning workflow without replacing their domain interactions:

- **Pipeline** owns one command band for the run headline, stage/document
  counts, run date, and temporal pager. The existing custom topology remains
  the interaction engine: desktop pan/zoom and fit controls, expandable
  stages, mobile stage walkthrough, URL document selection, and the artifact
  dossier keep their original contracts. Desktop arrows move and open the selected
  step; mobile arrows move the highlight only, leaving document opening to an explicit
  tap. Graph nodes and camera overlays use explicit hairline surfaces rather than
  page-level card primitives.
- Pipeline has three separate inspection surfaces: the topology explains process and
  run status, All artifacts lists every persisted `document_key`, and Call trace lists
  ordered model/search/tool operations from `olympus_run_event_trace`. Soft-stamped
  `call_id` / `attempt_id` / `node_run_id` (#2763) join each row to WP1
  `olympus_provider_*` (067 is economics authority; the public view still omits
  tokens/cost). Every known
  representative-run key is classified as a topology leaf, fan-out branch, or
  ledger-only discovery path (`lib/pipeline-document-discoverability.ts`) so deep
  links can still resolve a stage. Call trace pages 100 rows at a time (searchable and
  stage-filterable via `lib/pipeline-trace-stage.ts`), groups by run attempt and phase,
  and opens retries/errors by default. Vitest pins a ~300-call fixture for filter +
  paginate. Stage filter prefers `document_key` (Pipeline deep-link grammar) with
  phase-slug fallback. **Inputs** is a typed call-persistence gap (preflight /
  attention-plan do not emit model/search/tool rows) — the UI says so and does not
  invent calls. Historical runs without ingestion-time events say "Call details were
  not recorded for this run"; they are never reconstructed from aggregate diagnostics.
- Graph status is explicit: not run, state-only operation, persisted artifact, expected
  artifact missing, parallel dispatch, and stage overview (`lib/pipeline-topology-status.ts`).
  Atlas / Hermes / Learning bands gate active chrome — research artifacts never paint Hermes
  or Learning as run. Snapshot presence establishes that a run was recorded even when it
  published no documents (degraded reach across bands).
- Screenshot matrix (#2645): every topology stage × desktop/mobile plus representative
  artifact families are listed in [`docs/screenshot-matrix.md`](docs/screenshot-matrix.md).
  Vitest (`lib/screenshot-manifest.test.ts`) fails if a required path is missing from
  `fixtures/screenshots/` (1×1 PNG placeholders are allowed until operator capture).
- **Why** owns one reasoning command band above the shared responsive tab bar.
  `?why=read` presents the latest synthesis as a divided reading workspace;
  `?why=deliberations` presents rebalance actions, risk and ticker debates,
  and PM memo history as flat ledgers. The tab remains URL-driven and does not
  reset page scroll.
- Snapshot loading, error, empty, actionable, and risk components expose an
  opt-in flat presentation for Why. Their default card presentation remains
  unchanged for Overview and other consumers.

Across both routes, accent and warning tokens describe workflow state and
argument stance. `--up` and `--down` remain reserved for signed P&L or return
values.

> **Sharing / auth:** Olympus is a static export (`output: 'export'`). Product
> login is **Supabase Auth** (Google + GitHub PKCE) behind
> `NEXT_PUBLIC_OLYMPUS_AUTH=1` — see [`AUTH.md`](AUTH.md) § App auth (T1). Flag
> off (default) keeps today's anon client. Until cutover, anon RLS
> `USING (true)` still applies; gate shared hosts with **Cloudflare Access**
> (staging overlay after T1; production Access comes off at cutover — D7).
> Migration `033` drops anon SELECT on operator cost telemetry
> (`atlas_run_diagnostics`); `pm_notes` is intentionally kept.

## Daily snapshot envelope

The Overview page renders a typed `SnapshotEnvelope` panel above the KPI strip
(`components/overview/daily-snapshot-panel.tsx`). The envelope shape mirrors
`digiquant.olympus.atlas.snapshot.SnapshotEnvelope` from
[`atlas_snapshot.v1.json`](../../../digiquant/docs/schemas/atlas_snapshot.v1.json):

- `lib/snapshot-types.ts` — TypeScript mirror of the Pydantic model.
- `lib/snapshot-fetch.ts` — `fetchLatestSnapshot()` reads the freshest
  `daily_snapshots` row and only surfaces it when the row is from today or
  yesterday (UTC). Older rows resolve to `kind: 'empty'`.
- `lib/snapshot-staleness.ts` — `isStale(publishedAt, hours)` decides whether
  to show the "stale" banner above the panel; default threshold is 48h.
- `components/overview/daily-snapshot-panel.tsx` — render component with
  loading skeleton, error banner (with Retry button), stale banner, and empty
  state.

## Pipeline payload rendering

The Atlas pipeline (SIMP-013) writes validated Pydantic payloads into
`documents.payload` and the digest into `daily_snapshots.snapshot`; the legacy
`documents.content` and `daily_snapshots.regime` / `actionable` / `risks` /
`market_data` / `segment_biases` columns stay null. The frontend therefore
renders from the payloads:

- `lib/render-pipeline-payloads.ts` — markdown renderers + shape sniffers for
  the pipeline payload shapes: segment reports (`macro`, `bonds`, `equity`,
  `sector-*`, `alt-*`, `inst-*`, …), the Phase-7 master digest (`digest-delta`
  / `digest-baseline` and the snapshot jsonb), the Hermes `pm-rebalance`
  decision, the per-ticker bull/bear `deliberation/{ticker}` debate summaries,
  and the portfolio-level `risk-debate` (#698). Segment-specific metric fields
  render generically so new segments display without frontend changes.
- `lib/render-document-from-payload.ts` — routes payloads by shape first, then
  by the legacy `doc_type` / `document_key` conventions. Unknown object payloads return
  no markdown so `PayloadKeyValueView` renders labelled nested fields; it never emits a raw
  JSON block. Large collections reveal 20 items initially and deep branches require explicit
  disclosure, while all values remain inspectable.
- `lib/queries.ts` — the Overview strategy panel falls back to the snapshot
  jsonb (`market_regime_snapshot`, `bias`, `headline`, `actionable_summary`,
  `risk_radar`, narrative summaries) when the legacy columns are null.

`positions` and `nav_history` are written by the pipeline itself — Phase 9D
(`hermes/portfolio_materialize.py`, #700) materializes the PM's daily decision
into the paper book: target weights → `positions` (+ a CASH residual row), and
a base-100 normalized NAV index → `nav_history` (chained from the prior book's
realized return). So the portfolio + performance panels populate from the first
run that produces a rebalance. `theses` / `portfolio_metrics` remain
operator/refresh-script territory and may still be empty.

Instrument identity and classification come from the migration-055 `instruments` table.
`lib/queries.ts` joins that table once per dashboard load and carries the full provider row on
each assembled `Position`; the Holdings ledger renders `official_name` below the ticker and
uses the canonical persisted `category`. If migration 055 is absent, Olympus falls back only
to the stored `positions.name` / `positions.category` values and labels a missing category
`unknown`; it never expands or classifies a ticker in React.

## Theme tokens

Olympus declares **no** Tailwind `@theme` bridge of its own — #1402 deleted the
old app-local `@theme` palette (`--color-bg-primary`, `--color-text-primary`,
`--color-fin-*`). `app/globals.css` now imports the shared bridge
(`@digithings/web/styles/web-theme.css`) over the canon tokens
(`@digithings/design/tokens.css`), so every utility (`bg-surface`, `text-ink`,
`border-hair`, `text-up` / `text-down`, `font-mono`) resolves to the one canon
palette. The only app-local custom props left in `globals.css` are non-utility
depth cues (`--shadow-overlay`) and the next/font family re-declarations that
route the canon font tokens to the self-hosted Geist Mono face — no color
palette and no serif display face. Dashboard panels use `.oly-slab` (tonal
`--surface` + hairline, radius 0). See [`../digiweb/MIGRATION.md`](../digiweb/MIGRATION.md) for
the canon wiring and the `@theme inline` bridge rule.
