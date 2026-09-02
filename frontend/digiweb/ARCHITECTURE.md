# digiweb — Architecture

digiweb is the **frontend design suite**: the central, agent-readable home for
every reusable web pattern used by digithings.ai and digiquant.io. It is not a
runtime service — it ships no server and no live-trading or auth surface. Its
job is to make frontend work *consistent* by giving people and agents one place
to discover, copy, and extend standardized components.

## Module map

```
frontend/digiweb/
├── README.md              suite overview + the pass-through rule
├── ARCHITECTURE.md        this file
├── DESIGN.md              agent-readable design system (Stitch / Refero shape)
├── MANIFEST.json          generated machine index of every reference component
├── scripts/
│   └── build-manifest.mjs regenerates MANIFEST.json from the reference source
├── design/                @digithings/design — tokens.css + CSS primitives
│   ├── BLEND.md           utilitarian-terminal preference ledger (v0.1 locked)
│   ├── ROLLOUT.md         phased apply across digiweb → all product frontends
│   └── references/        external north-star scans (Cursor, herdr, …)
├── web/                   @digithings/web — shared React component layer
└── reference/             the live showcase app (Next.js 16 / React 19 / Tailwind v4 / Motion)
    ├── app/<family>/       one page per design family (foundations, iterate, controls, …)
    ├── components/         the reusable patterns (one file each, docblock-headed)
    └── README.md           the canon: tokens, livery, type, motion, chart rules
```

The **`/iterate`** family is the human preference gallery for the utilitarian
terminal blend (`uv-` CSS only). Picks persist in `localStorage`. Round-1 is
locked in `design/BLEND.md` and promoted into tokens/`DESIGN.md`; further
rounds still paste here before re-promoting. Product rollout: `design/ROLLOUT.md`.

Live apps import `@digithings/design` tokens and `@digithings/web` primitives —
they do not fork a second look. Phase 3 product-local fights on this branch:
digichat shadcn `--radius` pinned to 0, dashboard `.glass-card` retired, leftover
`rounded-*` chrome stripped. Marketing Fraunces heroes are gone (Phase 2).
Themed `--font-family` follows `--font-sans` (mono); unthemed `:root` Inter
remains a sans escape hatch.

The three workspaces are consumed **by package name**, so their on-disk location
is irrelevant to resolution — every other frontend imports them the same way:

| Package | Directory | Provides |
| ------- | --------- | -------- |
| `@digithings/design` | `design/` | `tokens.css` — the palette/type/motion tokens every surface uses |
| `@digithings/web` | `web/` | shared React layer (NavShell, DocsLayout/CodeTabs/EndpointDoc, Pricing/PricingMatrix, NumberedStages, PerfMetrics/StatCounter, TerminalManifest, the chat family, the controls layer [`dress` axis], Terminal, emblems, graph, ThemeProvider, MotionProvider, `AuthCard`, module data) + `styles/web-theme.css`, **the single `@theme inline` Tailwind bridge** |

`AuthCard` (`web/src/components/account/AuthCard.tsx`, CSS
`./styles/account-auth.css`) is the promoted sign-in / create-account card.
Layouts `compact`, `icons-first`, and `desk` share one form: email + password,
Google / GitHub / X (Supabase OAuth 2.0 provider id `x`, visible label X), primary submit
Sign in / Sign up, footer Create an account / Sign in. Compact places the
`digiquant` wordmark beside the mark. Desk may keep a product kicker, a sign-up
strength meter, and sign-in Forgot password. Specimens live on the reference
account page (`AuthCardProposals`) as a layout catalog. The dashboard login
screen imports compact `AuthCard` (`frontend/dashboard/components/login-screen.tsx`).

The F1 promotion campaign (#1450) added four more component families to
`@digithings/web`, each a `web/src/components/<family>/` directory with its own
barrel, re-exported from `src/index.ts`:

| Family | Components | CSS subpath |
| ------ | ---------- | ----------- |
| `finance-charts` | PriceChart, EquityCurve, DrawdownPlot + two chart scaffolds: rebuild-on-data `useFinanceChart` (with `readFinancePalette`, `financeChartOptions`, `tokenAlpha`, `toChartTime`) and the persistent dashboard lifecycle `useLightweightChart` (`chartChromeOptions`, `hostMonoFont`, `toLineData`/`timeToISO`, `useChartTip`/`ChartTipShell`, `useFinanceChartPalette`/`getFinancePalette` — converged from dashboard `lib/lw-chart.tsx`, #1450 batch E) and `*_DEMO` datasets. (MonthlyReturns and its `finance-charts.css` were deprecated into finance-tearsheet's ReturnsMatrix, #1463.) | — (the charts are canvas, zero CSS; `ChartTipShell` is utility-classed, covered by the family `@source` line) |
| `finance-composites` | StockTicker, OrderBook, SortableTable, PerformanceDashboard, SyncedTearsheet | `./styles/finance-composites.css` |
| `data-layout` | Odometer/OdometerStrip, DotMatrixStat, BentoGrid/BentoCell, ProductFrame, FeatureCell, TestimonialWall | `./styles/data-layout.css` |
| `effects-chrome` | Pipeline, RotatingPrompts, StackingPanels, AnnouncementBar, TabStrip (+ `tabId`/`tabPanelId` helpers), ToastStack | `./styles/effects-chrome.css` |

The #1463 reverse-promotion added the **`finance-tearsheet`** family — the
print-grade SVG tearsheet grammar (`.ts-*`) promoted from
`frontend/digiquant-web/components/tearsheet/`:

| Family | Components | CSS subpath |
| ------ | ---------- | ----------- |
| `finance-tearsheet` | CandlestickChart (trade entry/exit markers + hover cards), TimeSeries, SignedBars, TradeReturnChart, ContributionReturnChart (signed cumulative contribution bars + exact portfolio-return line; linear/log/symlog scales; one shared normalized `ViewWindow` synced across interactive series charts; `LOOKBACK_OPTIONS`/`viewWindowForPreset`/`matchLookbackPreset`), ReturnsMatrix (3 metrics × 3 periods — THE matrix grammar), KpiStrip/Kpi, TradeLogTable/DirectionPill (ReactNode cells, open-row state), TearsheetCard(+Kpis/Kpi) anchor dress, LiveBadge, `runTearsheetPrint`/`PRINT_FULL_VIEW` (flushSync + `window.print` PDF pipeline), format/tone helpers, `TEARSHEET_DEMO` | `./styles/finance-tearsheet.css` (self-layering; the ENTIRE `@media print` grammar lives here, unlayered — the family's differentiator) |

Engine ruling: canvas families are for screen-only dashboards; any surface
with a PDF export composes finance-tearsheet — see [CHARTS.md](CHARTS.md).
`@digithings/design/tearsheet/styles.css` is deprecated in favour of the
family sheet (kept only until digiquant-web/dashboard swap their imports).

Family notes: the dashboard time-series primitives ride **TradingView
Lightweight Charts** (`lightweight-charts` is a package dependency; hosts fill
their pane via `autoSize`, so consumers must give the pane a definite height);
the finance-tearsheet charts are **dependency-free SVG** (the PDF pipeline
constraint — [CHARTS.md](CHARTS.md)). The family sheets **manage their own
layering** (single-class defaults in `@layer components`, state/structural —
and, for finance-tearsheet, print — grammar unlayered) — import them
**plainly**, never wrapped in `layer(...)`. The families carry
token-backed utilities, so consuming apps need an `@source` line per family
directory. `PerformanceDashboard` exposes a `children` slot for finance-charts
content passed in by the page (it never imports charts itself); `ToastStack` is
imperative-free (`toasts` + `onDismiss` props — app-level toast state stays
app-owned). `TabStrip` wears three dresses (`underline`, `pill`, and `chip` —
the dashboard sub-nav chip row, which may flex-wrap; the ink follows across
rows), takes `ReactNode` labels, and accepts `linkPanels={false}` to omit
`aria-controls` when the consumer owns no panel ids (wrapper-adaption cases
like the dashboard's subpage tab bar).

Page-level dashboard composition is specified by
`reference/components/dashboard-workspace-reference.tsx` on the Finance page.
Its `dw-*` grammar is deliberately reference-only: a command band establishes
one primary state, compact metrics add context, and a flat hairline ledger owns
the working detail. Product apps adapt that composition around their own data
and interactions rather than introducing generic cards or duplicating existing
controls such as `TabStrip`, `SegmentedControl`, `Sheet`, and `EmptyState`.

Since the canon migration (#1399, 2026-07): apps declare **no local `@theme`
block** — `web-theme.css` is the one bridge (its `inline` semantics keep scoped
liveries live inside utilities); shared sheets import with `layer(components)`;
package components rendered by an app need an `@source` line. The adoption
playbook and the CI guard contract live in [MIGRATION.md](MIGRATION.md)
(`scripts/check_frontend_canon.py`, enforced by the unconditional
`frontend-canon` job in `ci.yml` — plus redundantly in the web/dashboard/digichat
test jobs).

### The move touched deploy config

Relocating `design/` and `web/` under `digiweb/` was pure directory bookkeeping
for *resolution* (imports are by package name), but it did touch the **live
deploy path**, all updated in the relocation commit: `scripts/ci_paths.yaml`
(regenerating the `ci.yml` filter block via `scripts/generate_ci_path_filters.py`)
+ the two Cloudflare deploy workflows + `agent-claude-review.yml`,
`scripts/score.py` (skip list + a per-file rule), `scripts/gen-api-vault.ts`
(a relative `../frontend/digiweb/web/...` import), the `frontend/digiweb/design/**`
invariant in `CLAUDE.md`, and doc links checked by `make doc-check`. Consumers
build unchanged.

## MANIFEST.json — the agent index

A generated JSON so any agent (including via MCP filesystem access) can discover
components without reading every file. Shape:

```jsonc
{
  "generatedAt": "<ISO timestamp>",
  "source": "frontend/digiweb/reference",
  "counts": { "components": 0, "described": 0, "families": 0 },
  "families": {
    "<family>": [
      {
        "name": "PortfolioReference",       // exported component
        "id": "portfolio",                   // file basename, -reference stripped
        "path": "reference/components/portfolio-reference.tsx",
        "summary": "…first sentence of the file's /** */ docblock…"
      }
    ]
  }
}
```

Regenerate after adding/renaming a component:

```bash
node frontend/digiweb/scripts/build-manifest.mjs
```

The generator derives structure (name, path, family) from the filesystem and
the family a component is imported into, and the `summary` from the leading
`/** … */` docblock. Components without a docblock appear with `summary: null` —
the generator prints the coverage so gaps are visible and easy to backfill.

## Brand identity — the terminal marks

`@digithings/web` `components/symbols/terminal-marks.tsx` is the canonical
identity; `reference/components/symbols/terminal-marks.tsx` re-exports it as the
specimen. Three components, each matching the weight of the surface it imitates:

| export | form | weight | use |
|--------|------|--------|-----|
| `TerminalMark` | outlined SVG paths + a `<rect>` cursor | 400 | the mark. `variant="full"` is `digi` + cursor; `variant="compact"` is the `d` reduction |
| `TerminalWordmark` | text, token-backed utilities | 400 | the default wordmark |
| `HairlineWordmark` | outlined SVG, stroked | 500 | display only, replicating the footer colophon |

Three constraints that fail silently if broken:

- **The mark and hairline are outlined paths, not text.** The mark because the
  same artwork is the favicon source and must not depend on a loaded font; the
  hairline because its overlapping contours are the design. `TerminalWordmark`
  is deliberately text — it is plain mono at tracking 0 with nothing to preserve,
  so outlining would ship ~9 KB of path data for a glyph-identical result.
- **The hairline's contours are left overlapping and un-booleaned**, outlined
  from the *variable* font. Stroked, those overlaps give the `t` its crossing
  grid and the `d`/`i` their stem spurs. Never run a boolean union, a "remove
  overlap", or an SVG "simplify paths" pass over that data, and never regenerate
  it from a static cut — a static `t` has one merged contour where the variable
  font has two, and the crossings vanish with no error.
- **Each register has a floor.** `variant="full"` closes up below ~64px, so
  chrome uses `compact`. The hairline's stroke scales with the art, so its floor
  is on the em (~173px): for `digithings` that is a ~1036px rendered width before
  the stroke reaches one device pixel. Below that use `TerminalWordmark`; do not
  shrink the hairline to fit.

Weight 400 is not a style choice — `.term-body`, `.term-title`, `.cmdline` and
`.app-input-field` set no `font-weight` and inherit `body { font-weight: 400 }`
(`design/site/site.css`), so 400 *is* terminal text. The hairline sits at 500
because `.colo-word` does.

Favicons are the `compact` mark baked into a tile with its own background — the
one place a mark cannot inherit ink — wired through `metadata.icons` with
`prefers-color-scheme` queries. Neither marketing site uses an `app/icon.svg`:
that Next.js file convention overrides `metadata.icons` and would drop the
queries silently.

Each product app also owns explicit 32px fallback, 180px Apple touch, and
192/512px web-app PNGs plus a maskable 512px variant. digithings and digiquant
use the compact terminal mark; the digiquant dashboard uses the canonical four-stroke mark.
Tab and Apple metadata publish light/dark pairs with media queries. Web App
Manifest icons use one contrast-safe default because installed icons are cached
by the operating system and the manifest standard has no live colour-scheme
selector; changing those assets requires removing and reinstalling the shortcut.

Off-repo uploads (GitHub, X, LinkedIn, slides, mail) are generated under
`frontend/digiweb/brand/` — avatars from the favicon tile, OG cards and social
headers from outlined Geist Mono + `HEADLINES` in `build-og.py`. Headers are a
**compact stack**, not a cropped 1200×630 card. `build-header.py --check` keeps
the served copies on digithings.ai/brand in sync. See `frontend/digiweb/brand/README.md`.

The older text `Wordmark` (`symbols/marks.tsx`) and `Colophon`
(`components/chrome.tsx`) are superseded for new work but not retired — the
surfaces already using them still do.

## The `digiweb` skill — the routing contract

`agents/sources/skills/digiweb/SKILL.md` (generated to `.claude/skills/` by
`make agents-init`, declared in `agents.yml` under `claude_code_surface.skills`)
tells an agent doing digithings/digiquant frontend work to: (1) read
`MANIFEST.json`, (2) reuse the closest component, (3) if none fits, add the new
pattern to the reference first, then consume it — never invent a one-off in a
product app. Editing the generated `.claude/` copy is forbidden; edit the source
and run `make agents-init` (CI enforces idempotence).

## Extension guide

- **New component** → see [README.md](README.md) “Adding a component”; give it a
  docblock, place it in a family page, regenerate the manifest.
- **New design family (page)** → add `reference/app/<family>/page.tsx` +
  `<family>.css`, register it in the nav (`reference/components/site-nav.tsx`)
  and the contents overview, then update this map and the reference README.
- **New token** → lives in `@digithings/design/tokens.css` (the shared package);
  reference it, never hardcode the literal.

## Build / CI posture

The reference app is **linted and type-checked** in CI by the `web` lane
(`test-web.yml`), gated on `frontend/digiweb/reference/**`: `npm run lint` and
`npm run typecheck` (`tsc --noEmit`) for the `design-reference` workspace (#1981).
Run the same two commands locally from `reference/`, plus a live browser check —
that last half is the only one CI cannot do.

It is deliberately **not built** in CI. Neither Cloudflare site compiles this
workspace, so a `next build` here would cost two app builds with no consumer.

Both Cloudflare deploy checks nevertheless watch `reference/package.json` in their
`paths:` filters (#1977). That is an *install* input, not a build input: the root
`npm install` both build scripts run resolves all eight workspace manifests before
either site compiles, so an unresolvable range here fails both production builds,
and of the eight this was the only manifest watched by nothing.
`tests/scripts/test_deploy_build_inputs.py` now asserts no workspace manifest is
orphaned, so a newly scaffolded workspace cannot silently reopen that hole. The
*directory* stays out of those two filters — see the comment beside the entry —
because neither site builds it; `frontend/digiweb/reference/**` is watched by the
`web` lane instead, which lints and type-checks rather than building.

Before #1981 nothing built, linted or type-checked this app, but "no coverage at
all" would overstate it. `scripts/check_frontend_canon.py` (the unconditional
`frontend-canon` job) does scan this workspace for raw palette utilities, legacy
vocabulary and colour literals. What it does *not* scan here is new CSS class
families: digiweb is exempt from that census by design, because the reference is
where new families are supposed to be born. `make score` also reaches this
directory — only `frontend/digiweb/design/` sits in `score.py`'s skip list — but
`ci.yml`'s `score` path filter excludes `frontend/**` (#1310), so the lane does
not fire on a frontend-only PR. Note the distinction: the CI *filter* excludes
`frontend/**`, the *tool* does not.

The suite has no auth, crypto, or live-trading surface, so
the human-gate items in `CLAUDE.md` do not apply to component work here (a
physical relocation of the shared packages, which touches deploy config, does).
