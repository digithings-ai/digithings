# The digiweb canon — adoption playbook

Every frontend surface consumes the design system the same way. This is the
playbook that migrated all five apps (#1399, 2026-07) and the contract the
**frontend canon guard** (`scripts/check_frontend_canon.py`, wired into the
web/olympus/digichat CI jobs) enforces going forward.

## The wiring (every app, in this order)

```css
@import "tailwindcss";
@import "@digithings/design/tokens.css";
@import "@digithings/design/site/site.css" layer(components); /* if used — see below */
@import "@digithings/web/styles/web-theme.css";               /* THE bridge */
@import "@digithings/web/styles/nav-shell.css";               /* if using NavShell */
@import "@digithings/web/styles/docs.css";                    /* if using the docs family */

/* Tailwind never scans package sources — point it at the shared components you use: */
@source "../../digiweb/web/src/components/NavShell.tsx";
@source "../../digiweb/web/src/components/docs";
```

Three rules that are load-bearing, learned the hard way:

1. **One bridge, `@theme inline`, never app-local.** `web-theme.css` is the
   only `@theme` block. `inline` makes utilities emit `var(--token)` at the
   use site, so scoped liveries (`.accent-digiquant { --accent: … }`) and
   `data-theme` flips re-resolve inside every utility. A plain `@theme`
   freezes the var at `:root` — the scoped-livery bug that shipped to both
   marketing sites before #1399.
2. **Never import a shared sheet unlayered.** Unlayered author CSS outranks
   ALL `@layer`s: site.css's `* { margin: 0 }` reset silently killed every
   margin utility (including NavShell's `mx-auto` centering) until imported
   as `layer(components)`.
3. **`@source` any package component you render.** Without it the shared
   component's utilities are never generated — the failure is silent (its
   own CSS file masks most of it).

Theming: `data-theme` on `<html>` is authoritative (shared `ThemeProvider` +
`themeInitScript` from `@digithings/web`). If an app needs `.dark`/`.light`
classes (shadcn-style selectors), mirror them from the attribute (see
digichat's `ThemeClassSync`) — never the other way around.

## Migrate vs leave (styling placement)

**To token utilities in TSX:** clean layout, spacing, color, typography —
`text-ink`, `bg-surface`, `border-hair`, `text-up`/`text-down` (P&L only),
`font-mono`, arbitrary sizes like `text-[0.72rem]` where the scale demands.

**Stays CSS** (family sheet or app globals): `@keyframes`, masks, SVG/canvas
art, `::before`/`::after` art, scroll-driven transforms
(`animation-timeline`), `@container` queries, `:nth-child`/combinator/
descendant selectors, two-color `color-mix()`, custom-prop readers, print
blocks, and unlayered-override classes. Re-point their color values at
tokens; never leave raw hex without a comment naming the token it mirrors.

**Concrete colors are sanctioned only in:** `olympus/lib/chart-colors.ts`
(categorical/benchmark hues), tenant embed accents, SSR `theme-color` metas
(commented), canvas scenes, print pins, and the reference livery swatch
table — the guard's ALLOWLIST. Anything else needs a
`canon-allow: <reason>` comment on the line, and a reason that survives
review.

## Shared primitives first

Before writing new UI, check `frontend/digiweb/MANIFEST.json` (84 components,
13 families) and `@digithings/web` exports: NavShell, Footer/Colophon,
DocsLayout/CodeTabs/EndpointDoc, Terminal, Emblem/StackRow, ModuleCard,
Reveal/Stagger/HeroEntrance, useScrollyFeatures/ScrollyRail. Motion always
via `m` under `MotionProvider` (LazyMotion `domAnimation` `strict` — a raw
`motion.*` element creator throws). The reference app (port 4013) is the
live catalog; `/digiweb` is the agent entry point.

## Debugging checklist (QA'ing an app against the canon)

- Utility "not applying" but present in compiled CSS → cascade layering
  (rule 2 above).
- Utility missing from compiled CSS entirely → missing `@source`, or a stale
  Turbopack cache: `rm -rf frontend/<app>/.next` after switching branches.
- Livery/accent not changing inside a scope → something reintroduced a plain
  `@theme` block (rule 1).
- Money colors: `--up`/`--down` are fixed per theme in tokens.css (dark wears
  the digiquant phosphor) and must never follow a livery.
