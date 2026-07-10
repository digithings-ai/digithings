# Olympus dashboard

Next.js 15 investment-intelligence dashboard for **DigiQuant Olympus** — the unified product surfacing both Atlas (research) and Hermes (analysis + PM). Joins the root npm workspace at `frontend/olympus/` and consumes the shared design system via
`@digithings/design` as a workspace dependency.

## Quant-native visual layer

Olympus matches the digiquant.io aesthetic by importing the shared canon
tokens, **the** Tailwind v4 bridge (`web-theme.css`), and the quant-native +
tearsheet primitives directly in `app/globals.css`:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
@import "@digithings/design/tokens.css";
@import "@digithings/web/styles/web-theme.css";        /* THE @theme inline bridge (#1402) */
@import "@digithings/design/quant-native/styles.css";
@import "@digithings/design/tearsheet/styles.css";
```

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
hiding (#1450 F4 batch D). The per-file ruling — and what adoption would
take — lives in [`lib/TABLES.md`](lib/TABLES.md). New *flat* leaderboards
should adopt the primitive instead of hand-rolling sort state.

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

## Morning Read (Overview)

`app/page.tsx` is the daily decision document — top to bottom it reads
regime → KPIs → what to do → why → where to read more. The panels under
`components/overview/` wire data that the dashboard query already loads:

- **Today's Actions** (`today-actions-panel.tsx`) — `portfolio_management.rebalance_actions`
  (computed in `queries.ts`, surfaced from #702). EXIT→OPEN→TRIM→ADD→HOLD sort;
  HOLDs collapse; explicit "no changes proposed" state. Per-ticker rationale is
  joined from the `pm-rebalance` doc's actions when present (#704).
- **Morning Brief** (`morning-brief-panel.tsx`) — the digest, tabbed
  (Market / Equities / Risk / Actions). Shares the snapshot fetch via the
  exported `useLatestSnapshot()` hook and reuses the snapshot panel's section
  renderers; it replaces the single long scroll on the Overview.
- **Deliberations** (`deliberations-strip.tsx`) — bull/bear `DebateSummary`
  cards from `pipeline_observability.deliberation_transcripts` (the
  pipeline `deliberation/{ticker}` docs, #699) plus a portfolio-level
  **risk-debate** card (`risk-debate` doc, via `renderRiskDebateMarkdown`).
  `fetchPipelineObservabilityForDate` loads both the flat pipeline keys
  (`deliberation/%`, `risk-debate`, `pm-rebalance`) and the operator-flow
  keys (#704). Expand-in-place, no extra fetch; renders null when neither ran.
- **Decision Trail** (`decision-trail-panel.tsx`) — navigable rows into the
  day's artifacts (deliberations, PM memo, digest); honest empty state.
- **AsOfBadge** (`as-of-badge.tsx`) — freshness pill in the hero; amber when the
  run date is older than yesterday (UTC).

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
