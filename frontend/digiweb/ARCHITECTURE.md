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
├── MANIFEST.json          generated machine index of every reference component
├── scripts/
│   └── build-manifest.mjs regenerates MANIFEST.json from the reference source
├── design/                @digithings/design — tokens.css + CSS primitives
├── web/                   @digithings/web — shared React component layer
└── reference/             the live showcase app (Next.js 16 / React 19 / Tailwind v4 / Motion)
    ├── app/<family>/       one page per design family (foundations, controls, …)
    ├── components/         the reusable patterns (one file each, docblock-headed)
    └── README.md           the canon: tokens, livery, type, motion, chart rules
```

The three workspaces are consumed **by package name**, so their on-disk location
is irrelevant to resolution — every other frontend imports them the same way:

| Package | Directory | Provides |
| ------- | --------- | -------- |
| `@digithings/design` | `design/` | `tokens.css` — the palette/type/motion tokens every surface uses |
| `@digithings/web` | `web/` | shared React layer (NavShell, DocsLayout/CodeTabs/EndpointDoc, Pricing/PricingMatrix, NumberedStages, PerfMetrics/StatCounter, TerminalManifest, the chat family, the controls layer [`dress` axis], Terminal, emblems, graph, ThemeProvider, MotionProvider, module data) + `styles/web-theme.css`, **the single `@theme inline` Tailwind bridge** |

The F1 promotion campaign (#1450) added four more component families to
`@digithings/web`, each a `web/src/components/<family>/` directory with its own
barrel, re-exported from `src/index.ts`:

| Family | Components | CSS subpath |
| ------ | ---------- | ----------- |
| `finance-charts` | PriceChart, EquityCurve, DrawdownPlot + two chart scaffolds: rebuild-on-data `useFinanceChart` (with `readFinancePalette`, `financeChartOptions`, `tokenAlpha`, `toChartTime`) and the persistent dashboard lifecycle `useLightweightChart` (`chartChromeOptions`, `hostMonoFont`, `toLineData`/`timeToISO`, `useChartTip`/`ChartTipShell`, `useFinanceChartPalette`/`getFinancePalette` — converged from olympus `lib/lw-chart.tsx`, #1450 batch E) and `*_DEMO` datasets. (MonthlyReturns and its `finance-charts.css` were deprecated into finance-tearsheet's ReturnsMatrix, #1463.) | — (the charts are canvas, zero CSS; `ChartTipShell` is utility-classed, covered by the family `@source` line) |
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
family sheet (kept only until digiquant-web/olympus swap their imports).

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
like olympus's subpage tab bar).

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
`frontend-canon` job in `ci.yml` — plus redundantly in the web/olympus/digichat
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

The reference app is **not** built or linted in CI (no workflow references it);
the gate is local — `npx tsc --noEmit` + `npx eslint .` from `reference/`, plus
a live browser check. The suite has no auth, crypto, or live-trading surface, so
the human-gate items in `CLAUDE.md` do not apply to component work here (a
physical relocation of the shared packages, which touches deploy config, does).
