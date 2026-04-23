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
npm install                  # links workspace packages
cd apps/digiquant-atlas/frontend
npm run dev                  # http://localhost:3000/digiquant-atlas/
npm run build                # static export (output: 'export')
npm run lint
```

No `test` script is configured for this workspace yet.

## Token collision notes

Atlas declares its own Tailwind v4 `@theme` palette
(`--color-bg-primary`, `--color-text-primary`, etc). The design
tokens live in the separate `--bg-primary` / `--text-primary` namespace, so
they coexist without collision. Components that need the shared palette
reference the design names (`var(--border-color)`,
`var(--accent-digiquant)`), while Tailwind utilities continue to resolve
the Atlas palette.
