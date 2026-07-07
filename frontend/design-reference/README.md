# design-reference

The go-to **live** design reference for digithings frontend work — a React /
Next.js / Tailwind / Motion app that renders every reusable pattern (visual
components, motion, finance surfaces, chrome, account templates) as working
code, wired to the shared design tokens. When you build a new frontend surface,
start here: copy a pattern, keep its grammar.

## Run it

```bash
npm run dev --workspace design-reference   # http://127.0.0.1:4013
# or via the repo's preview tooling: launch config name "design-reference"
```

It consumes the shared workspaces from source: `@digithings/design` (tokens) and
`@digithings/web` (Terminal, emblems, graph, modules data, ThemeProvider). Edits
to those packages hot-reload here.

## Page map

One family of design elements per page; the top bar (`components/site-nav.tsx`)
is the only shared chrome.

| Route              | Family      | Holds |
| ------------------ | ----------- | ----- |
| `/`                | Foundations | contents map, livery switcher, feature picker, button/CTA states |
| `/layout-patterns` | Layout      | feature cell, bento grid, container-scaled product frame |
| `/typography`      | Typography  | scroll-linked word reveals (blur / muted / outline), copy & voice grammar |
| `/data`            | Data        | dot-matrix stat, count-up stat, sticky card deck, changelog rail, pricing, comparison matrix |
| `/finance`         | Finance     | Lightweight-Charts price chart / equity curve / drawdown, synced multi-pane tearsheet, charting rules, performance metrics, monthly-returns heatmap, order book |
| `/effects`         | Effects     | cursor-follow hero graph, typed terminal, scrolly module graph, research pipeline, ambient mesh, rotating prompts, clip reveal, 3D tilt card (revolut-mined) |
| `/chrome`          | Chrome      | announcement bar, command palette, tabs (sliding indicator), toast stack, scroll-aware nav, colophon footer with glow sweep |
| `/terminal`        | Terminal    | diegetic CLI session + budget, streaming chat transcript |
| `/chatbot`         | Chatbot     | digichat surface — thinking chain, composer, markdown, inline chart, inline route graph, custom action widgets |
| `/symbols`         | Symbols     | module emblems, wordmarks, QR marks, vendor logos, utility glyphs |
| `/account`         | Account     | login, sign-up, payment, settings, profile templates |

## Conventions

- **Tokens, never literals.** Colours come from `@digithings/design/tokens.css`:
  `--ink` / `--ink-soft` / `--ink-mute`, `--surface`, `--bg`, `--hair`,
  `--accent`, `--up` / `--down` (money colours only), `--ease`. Use
  `color-mix(in srgb, var(--token) N%, …)` for tints.
- **Livery.** A scope class (`accent-digiquant`, `accent-digichat`, …) sets
  `--accent` for everything inside it. Money colours (`--up`/`--down`) are for
  P&L only — never a livery. The umbrella is monochrome (`--accent: var(--ink)`).
- **Two voices.** `--font-display` (Fraunces serif) for human claims, never
  bolded; `--font-mono` (Geist Mono) for data, labels, and micro-caps.
- **Motion laws.** One motion moment per surface; always honour
  `prefers-reduced-motion` (render the final state); content must read without
  JS. Import Motion as `m` etc. from `motion/react` (LazyMotion is provided
  app-wide by the root layout).
- **Charts.** Prices/candles/equity use TradingView **Lightweight Charts**
  (`lightweight-charts`, self-hosted, our own data, `attributionLogo` off),
  themed from the tokens and re-themed live on `data-theme` change. Static hero
  crops stay lightweight SVG. Do not build custom candle renderers. The full
  house rules render as a callout on `/finance` (`CHART_RULES`); in short:
  transparent canvas, token colours only, `autoSize:true` so the chart fills a
  pane with a definite height, money colours (`--up`/`--down`) for P&L only, and
  multi-series views use **panes with one shared time axis** (see
  `synced-tearsheet-reference.tsx`) rather than stacked separate charts.
- **CSS.** Shared base + nav live in `app/globals.css`; each page keeps its
  family styles in `app/<family>/<family>.css`, prefixed per component. Prefix
  new classes to avoid collisions across the global sheet.

## Adding a section

1. Create the component in `components/` (`"use client"` only if it needs
   state/effects). Take content from the reference-mining doc
   (`frontend/design/references/mine/index.html`) or the canon
   (`frontend/design/spec/index.html`).
2. Put its styles in the owning page's `<family>.css` with a unique class prefix.
3. Import and place it in `app/<family>/page.tsx` using the section grammar:
   `<section className="section-block"><p className="kicker">// label</p>
   <h2 className="title">Claim.</h2><p className="section-copy">…</p>…</section>`.
4. Verify from `frontend/design-reference/`: `npx tsc --noEmit` and `npx eslint .`
   both clean; then check it live in the preview (and toggle theme / mobile).

## Pitfalls learned the hard way

- **Motion + scroll mapping.** A numeric range-map on opacity/transform (e.g.
  `useTransform(p, [a, b], [0, 1])`) can get compiled to a native `view()`
  timeline that ignores a pinned/holding scroll window. Use a **function**
  transform when the mapping must track the JS scroll path exactly.
- **No per-frame `setState`.** For counters / typewriters, write to a DOM ref in
  the effect (rAF/interval/`onUpdate`) instead of `setState` each tick — avoids
  re-renders and the `react-hooks/set-state-in-effect` lint.
- **Fixed overlays under `backdrop-filter`.** A `backdrop-filter` ancestor
  becomes the containing block for `position: fixed` children, pinning them to
  it. Portal full-screen scrims/sheets to `document.body` (see the nav sheet).
- **Server components can't take handlers.** An `onClick` on an element in a
  server component crashes the route. Make the component `"use client"` or drop
  the handler.
- **Container-fit scaling.** CSS `calc()` can't derive a unitless `scale` from
  lengths — measure the container with a `ResizeObserver` and write the factor
  (see the product frame).
