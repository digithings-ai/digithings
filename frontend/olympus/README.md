# Olympus dashboard

Next.js 15 investment-intelligence dashboard for **DigiQuant Olympus** — the unified product surfacing both Atlas (research) and Hermes (analysis + PM). Joins the root npm workspace at `frontend/olympus/` and consumes the shared design system via
`@digithings/design` as a workspace dependency.

## Quant-native visual layer

Olympus matches the digiquant.io aesthetic by importing the shared tokens and
the quant-native primitives directly in `app/globals.css`:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
@import "@digithings/design/tokens.css";
@import "@digithings/design/quant-native/styles.css";
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
- `.qn-up` / `.qn-down` — muted emerald / copper for directional P&L. Do
  **not** reuse these for error states — those still use the
  existing `--color-fin-red` / `--color-fin-amber` tokens.

### Page chrome

`app/layout.tsx` renders a thin monospaced header strip (`.qn-page-chrome`)
at the top of `<main>` with route crumbs on the left and an `Open digiquant.io`
link plus version/env label on the right. The version label reads
`process.env.NEXT_PUBLIC_OLYMPUS_VERSION` and falls back to `v0.1 · dev`.

### Recharts theming

Global `.recharts-*` overrides in `globals.css` now reference tokens
(`--border-color`, `--text-secondary`, `--font-family-mono`) so charts follow
the shared palette. No chart library was swapped.

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

**CSP (REM-077):** `public/_headers` ships with the static export for Cloudflare Pages
(`output: 'export'` does not apply `next.config` `headers()`). Constants live in
`lib/security-headers.mjs` (Vitest-covered).

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
banner pointing back to this section instead of throwing.

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

## Token collision notes

Atlas declares its own Tailwind v4 `@theme` palette
(`--color-bg-primary`, `--color-text-primary`, etc). The design
tokens live in the separate `--bg-primary` / `--text-primary` namespace, so
they coexist without collision. Components that need the shared palette
reference the design names (`var(--border-color)`,
`var(--accent-digiquant)`), while Tailwind utilities continue to resolve
the Atlas palette.
