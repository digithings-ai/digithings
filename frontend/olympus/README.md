# Olympus dashboard

Next.js 15 investment-intelligence dashboard for **DigiQuant Olympus** — the unified product surfacing both Atlas (research) and Hermes (analysis + PM). Joins the root npm workspace at `frontend/olympus/` and consumes the shared design system via
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

The performance tear sheet (`/portfolio/performance`) renders the shared
finance-tearsheet family (`TimeSeries`, `SignedBars`, `Kpi`/`KpiStrip`,
`runTearsheetPrint` from `@digithings/web`); olympus keeps its §13 dashboard
variants and shell print rules app-side at the bottom of `globals.css`.

The root layout scopes the page to the DigiQuant accent and blueprint
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

The Portfolio routes follow DigiWeb's canonical `PortfolioWorkspaceReference`:
one flat command band establishes book or dossier state, then hairline-divided
ledgers carry positions, activity, research, and decision history. Holdings owns
an exposure command band plus switchable position/activity ledgers; Theses uses
a conviction-ranked research spine; thesis and ticker detail routes use editorial
main/context compositions rather than nested card stacks.

`/portfolio/performance` applies the same flat grammar to the shared
finance-tearsheet primitives. Its command band, asymmetric NAV workspace, bounded
decision ledger, attribution section, and PDF action remain presentation over the
existing `nav_history` + `decision_log` contract. Portfolio presentation changes
must not introduce a second query path or replace that persisted truth model.
Embedded attribution uses flat divided sections, and narrow finance chart panes
reduce date axes to endpoint labels while preserving the complete print view.

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
Constants live in `lib/security-headers.mjs` (Vitest-covered, asserts alignment).

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
| `NEXT_PUBLIC_OLYMPUS_VERSION`     | Optional. Shown in the page-chrome version label (defaults to `v0.1 · dev`).                              |

When the URL or anon key is unset the daily-snapshot panel renders an empty
banner pointing back to this section instead of throwing. On Cloudflare Pages
builds (`CF_PAGES=1`) both vars are **required** — `scripts/build-digiquant.sh`
aborts rather than shipping a bundle whose every page shows the unconfigured
error (#674).

**Thesis detail routes:** `/portfolio/theses/[thesisId]` is statically exported, so
only ids returned by `lib/thesis-static-params.ts` get HTML files. With Supabase env
present at build time the real ids are fetched from the `theses` table; without it
only the `_unlinked` fallback is exported. Theses created after a deploy 404 on
direct load until the next deploy.

## Brief workspace

`app/page.tsx` is the daily decision workspace. It owns benchmark alignment,
NAV-window calculations, book freshness, and rebalance rationale joins, then
passes those truth contracts into the presentational modules under
`components/today/`:

- **Command band** (`move-hero.tsx`) — regime and run provenance, digest
  headline, rebalance status, and compact NAV context. `--up` / `--down` are
  reserved for signed returns; regime chrome uses accent, warning, or neutral.
- **Watch ledger** (`what-to-watch.tsx`) — ranked actionables and tail risks,
  with a date-keyed deep link to the Pipeline digest.
- **Book ledger** (`book-strip.tsx`) — reconciled invested/cash state and held
  positions ordered by absolute daily move. Its as-of badge uses the latest
  NAV date rather than borrowing the research digest date.
- **Destination ledger** (`today-summaries.tsx`) — divided Read, Holdings, and
  Theses columns with no independent card surfaces.

The four modules are enclosed by one page-level hairline frame, adapting the
DigiWeb `DashboardWorkspaceReference` command-band and ledger composition.
Loading uses `PageSkeleton`; failures use the shared `EmptyState`; missing book
or research values render local quiet copy; stale research and book dates use
the shared `AsOfBadge` treatment.

> **Sharing:** the static export embeds the Supabase anon key and every table
> has `anon` RLS `USING (true)`, so the dashboard URL is world-readable. Gate it
> with **Cloudflare Access** before sharing — see [`AUTH.md`](AUTH.md) for the
> runbook and the exact exposure. Migration `033` drops the anon SELECT RLS
> policy on the operator cost/token telemetry table (`atlas_run_diagnostics`);
> `pm_notes` is intentionally kept (it's PM commentary the dashboard renders).

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
  by the legacy `doc_type` / `document_key` conventions; unknown object
  payloads fall back to a JSON code block instead of "_No content available._".
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

## Theme tokens

Olympus declares **no** Tailwind `@theme` bridge of its own — #1402 deleted the
old app-local `@theme` palette (`--color-bg-primary`, `--color-text-primary`,
`--color-fin-*`). `app/globals.css` now imports the shared bridge
(`@digithings/web/styles/web-theme.css`) over the canon tokens
(`@digithings/design/tokens.css`), so every utility (`bg-surface`, `text-ink`,
`border-hair`, `text-up` / `text-down`, `font-mono`) resolves to the one canon
palette. The only app-local custom props left in `globals.css` are non-utility
depth cues (`--shadow-glass`) and the next/font family re-declarations that
route the canon font tokens to the self-hosted Geist / Fraunces faces (#684) —
no color palette. See [`../digiweb/MIGRATION.md`](../digiweb/MIGRATION.md) for
the canon wiring and the `@theme inline` bridge rule.
