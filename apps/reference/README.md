# design-reference

The go-to **live** design reference for digithings frontend work — a React /
Next.js / Tailwind / Motion app that renders every reusable pattern (visual
components, motion, finance surfaces, chrome, account templates) as working
code, wired to the shared design tokens. When you build a new frontend surface,
start here: copy a pattern, keep its grammar.

## Run it

```bash
npm run dev --workspace design-reference -- --port 4013
# Gallery: http://127.0.0.1:4013/
# Chatbot (isolated root): http://127.0.0.1:4013/chatbot/
```

Retired URLs (`/ui`, `/tearsheet`) redirect in `next dev` (see `next.config.mjs`)
so an old link does not 404 mid-session; the static export emits no redirects.

It consumes the shared workspaces from source: `@digithings/design` (tokens) and
`@digithings/ui` (Terminal, emblems, graph, modules data, ThemeProvider). Edits
to those packages hot-reload here.

## Page map

One family of design elements per page; the top bar (`components/site-nav.tsx`)
is the only shared chrome.

Families live in route groups under `app/(gallery)/` (`(foundations)`, `(controls)`,
`(data-display)`, `(motion)`, `(layout)`, `(pages)/(templates)`, …) so the folder
names state the IA without changing the URLs. `/ui` folded into `/controls` and
`/tearsheet` into `/finance`; `/brand` and `/iterate` are reference-only and stay
off the primary nav. The route/specimen inventory is machine-readable in
`lib/specimen-inventory.ts` and pinned by `lib/*.test.ts`.

| Route              | Family      | Holds |
| ------------------ | ----------- | ----- |
| `/`                | Foundations | contents map, livery switcher, feature picker, button/CTA states |
| `/rtl`             | RTL         | the whole canon under a `dir=ltr`/`dir=rtl` toggle — the direction proof |
| `/typography`      | Typography  | type specimen + live type-suite switcher, scroll-linked word reveals, copy & voice grammar |
| `/controls`        | Controls    | the kit's current surface — Button, Input/Label/Textarea, Checkbox, Switch, Select (+`SelectPopup`), DropdownMenu, Dialog, Sheet, Tooltip, Collapsible, Card, Separator, Alert, Tabs, Badge tones, Table (`density`/`numeric`/`TableRowHeader`/`interactive`) — plus search, nav buttons, slider, tags input, skeleton, empty/error |
| `/data`            | Data        | dot-matrix stat, count-up stat, odometer, marquee, card deck, changelog rail, repo activity, sortable table, precision/pricing tables, conviction, roadmap Gantt, pricing matrix |
| `/finance`         | Finance     | canvas dashboards (ticker, price, equity, drawdown, synced tearsheet, performance, blotter, metrics, returns matrix, order book) **and** the print-grade SVG tearsheet branch (folded from the old `/tearsheet`) |
| `/effects`         | Motion      | cursor-follow hero graph, typed terminal, scrolly graph, research pipeline, ambient mesh, reveals, section transitions, routing map |
| `/chrome`          | Chrome      | announcement bar, command palette, tabs, toast stack, scroll nav, nav shell/menu, breadcrumbs, pagination, module card, socials, footer |
| `/terminal`        | Chat        | diegetic CLI session + budget, terminal loaders, streaming chat transcript |
| `/chatbot`         | Chat        | first-party Thread as product `/embed` (`@digithings/ui/chat/thread`), fixture runtime. Isolated Next root (`app/(chatbot)/`). Elements index: [`../ASSISTANT_UI_ELEMENTS.md`](../ASSISTANT_UI_ELEMENTS.md). |
| `/layout-patterns` | Layout      | feature cell, bento grid, numbered stages, container-scaled product frame, phone mockup, testimonial wall |
| `/symbols`         | Symbols     | module emblems, brand marks, favicon tiles, vendor logos, utility glyphs |
| `/account`         | Templates   | login, sign-up, payment, settings, profile templates |
| `/brand`           | reference-only | avatars, social headers, OG card, mail sign-off — not shipped on digithings.ai |
| `/iterate`         | reference-only | blend lab — pick corners, type, CTAs, heroes, density; preference ledger → `design/BLEND.md` |

## Conventions

- **Tokens, never literals.** Colours come from `@digithings/design/tokens.css`:
  `--ink` / `--ink-soft` / `--ink-mute`, `--surface`, `--bg`, `--hair`,
  `--accent`, `--up` / `--down` (money colours only), `--ease`. Use
  `color-mix(in srgb, var(--token) N%, …)` for tints.
- **Livery.** **Monochrome is the default** (`--accent: var(--ink)`, black +
  white); colour is opt-in per product via a scope class (`accent-digiquant`,
  `accent-digichat`, …) or the nav selector. research/portfolio/execution are backend
  langgraph names, **not** coloured products — their accent tokens collapse to
  ink (reference-only). Money colours (`--up`/`--down`) are P&L-only and never
  follow a livery: `--up` is the fixed digiquant phosphor teal, `--down` a
  paired red — the single always-on colour domain. **These colour overrides
  live in the reference's `globals.css` only; `tokens.css` (which the live sites
  build from) is untouched.**
- **One voice (v0.1).** `--font-display`, `--font-sans`, and `--font-mono` all
  default to the Geist Mono stack. Hierarchy is size and tracking, not a second
  face. Serif is an escape hatch via the type-suite picker (`serif-legacy`,
  `editorial`, …) — comparison furniture, not the shipping default. All three
  tokens still swap together as a coordinated **type suite** from the nav
  selector (see `type-store.ts`; suites: default, plex, editorial, grotesk,
  terminal, utilitarian, omarchy).
- **Motion laws.** One motion moment per surface; always honour
  `prefers-reduced-motion` (render the final state); content must read without
  JS. Import Motion as `m` etc. from `motion/react` (LazyMotion is provided
  app-wide by the root layout).
- **Charts.** DASHBOARD prices/candles/equity use TradingView **Lightweight
  Charts** (`lightweight-charts`, self-hosted, our own data, `attributionLogo`
  off), themed from the tokens and re-themed live on `data-theme` change.
  Static hero crops stay lightweight SVG. PRINT-GRADE surfaces (anything with
  a PDF export) compose the shared SVG **finance-tearsheet** family instead —
  do not build new custom candle renderers outside it (the split ruling:
  `packages/ui/CHARTS.md`). The full canvas
  house rules render as a callout on `/finance` (`CHART_RULES`); in short:
  transparent canvas, token colours only, `autoSize:true` so the chart fills a
  pane with a definite height, money colours (`--up`/`--down`) for P&L only, and
  multi-series views use **panes with one shared time axis** (see
  `synced-tearsheet-reference.tsx`) rather than stacked separate charts.
- **CSS.** Shared base + nav live in `app/globals.css`; each family keeps its
  styles in `app/(gallery)/(<family>)/<route>/<route>.css`, prefixed per
  component. Family sheets put their dress in `@layer components` so kit
  Tailwind utilities win on a tie (the app-rebuild rule in
  `packages/ui/MIGRATION.md`); a rule that must beat a utility stays unlayered
  and says so inline (see `.sb-hint`). `(chatbot)` is a second root that themes
  vendor assistant-ui styles and keeps its own unlayered cascade.

## Adding a section

1. Create the component in `components/` (`"use client"` only if it needs
   state/effects). Take content from the reference-mining doc
   (`packages/design/references/mine/index.html`) or the canon
   (`packages/design/spec/index.html`).
2. Put its styles in the owning page's `<family>.css` with a unique class prefix.
3. Import and place it in the family's `app/(gallery)/(<family>)/<route>/page.tsx` using the section grammar:
   `<section className="section-block"><p className="kicker">// label</p>
   <h2 className="title">Claim.</h2><p className="section-copy">…</p>…</section>`.
4. Verify from `apps/reference/`: `npm run typecheck` and `npm run lint`
   both clean; then check it live in the preview (and toggle theme / mobile).
   CI runs the same two commands in the `web` lane, so a failure there is a red PR.
   Your local run is the *stronger* one, though: if you have run `npm run dev`,
   tsc also reads `.next/types/**` (route/layout export validation), which CI never
   has because the lane runs no build and `.next/` is gitignored. A failure only in
   those generated types will not redden the PR. The live check stays yours alone.

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
