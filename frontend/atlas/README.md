# digiquant-atlas / frontend

Next.js 15 research console for Atlas. Joins the root npm workspace in place
(`apps/*/frontend`) and consumes the shared design system via
`@digithings/design` as a workspace dependency.

## Quant-native visual layer

Atlas matches the digiquant.io aesthetic by importing the shared tokens and
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
`process.env.NEXT_PUBLIC_ATLAS_VERSION` and falls back to `v0.1 · dev`.

### Recharts theming

Global `.recharts-*` overrides in `globals.css` now reference tokens
(`--border-color`, `--text-secondary`, `--font-family-mono`) so charts follow
the shared palette. No chart library was swapped.

## Running

```bash
# From repo root
npm install                                # links workspace packages
npm --workspace frontend/atlas run dev     # http://localhost:3000/digiquant-atlas/
npm --workspace frontend/atlas run build   # static export (output: 'export')
npm --workspace frontend/atlas run lint
npm --workspace frontend/atlas run test    # Vitest (lib/**/*.test.ts + components/**/*.test.tsx)
```

## Environment variables

Copy `.env.local.example` to `.env.local` and fill in your Supabase credentials:

| Variable                          | Purpose                                                                                                  |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`        | Supabase project URL. Used by every client-side reader, including `lib/snapshot-fetch.ts`.               |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`   | Supabase anon key. The frontend reads `daily_snapshots` under the `anon_read` RLS policy (migration 011). |
| `NEXT_PUBLIC_ATLAS_VERSION`       | Optional. Shown in the page-chrome version label (defaults to `v0.1 · dev`).                              |

When the URL or anon key is unset the daily-snapshot panel renders an empty
banner pointing back to this section instead of throwing.

## Daily snapshot envelope

The Overview page renders a typed `SnapshotEnvelope` panel above the KPI strip
(`components/overview/daily-snapshot-panel.tsx`). The envelope shape mirrors
`digiquant.atlas.snapshot.SnapshotEnvelope` from
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
