# digiweb — Architecture

digiweb is the **frontend design suite**: the central, agent-readable home for
every reusable web pattern used by digithings.ai and digiquant.io. It is not a
runtime service — it ships no server and no live-trading or auth surface. Its
job is to make frontend work *consistent* by giving people and agents one place
to discover, copy, and extend standardized components.

## Module map

```
packages/ui/
├── README.md              suite overview + the pass-through rule
├── ARCHITECTURE.md        this file
├── DESIGN.md              agent-readable design system (Stitch / Refero shape)
├── CHARTS.md              finance chart house rules
├── CHAT_THEME.md          first-party digichat skin on /chatbot
├── ASSISTANT_UI_ELEMENTS.md  full assistant-ui elements catalog (fetch map)
├── MANIFEST.json          generated machine index of every reference + kit component
├── scripts/
│   └── build-manifest.mjs regenerates MANIFEST.json from the reference + kit sources
├── design/                @digithings/design — tokens.css + CSS primitives
│   ├── BLEND.md           utilitarian-terminal preference ledger (v0.1 locked)
│   ├── ROLLOUT.md         phased apply across digiweb → all product frontends
│   └── references/        external north-star scans (Cursor, herdr, …)
├── brand/                 generated identity kit (avatars, headers, OG) — previewed at design-reference `/brand`, not on digithings.ai
├── web/                   @digithings/ui — shared React component layer
└── reference/             the live showcase app (Next.js 16 / React 19 / Tailwind v4 / Motion)
    ├── app/(gallery)/      family pages (foundations, iterate, controls, …)
    ├── app/(chatbot)/      isolated /chatbot root — do not compile the gallery graph
    ├── components/         the reusable patterns (one file each, docblock-headed)
    └── README.md           the canon: tokens, livery, type, motion, chart rules
```
The **`/iterate`** family is the human preference gallery for the utilitarian
terminal blend (`uv-` CSS only). Picks persist in `localStorage`. Round-1 is
locked in `design/BLEND.md` and promoted into tokens/`DESIGN.md`; further
rounds still paste here before re-promoting. Product rollout: `design/ROLLOUT.md`.

Live apps import `@digithings/design` tokens and `@digithings/ui` primitives —
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
| `@digithings/ui` | `web/` | shared React layer (NavShell, `SocialRow` / `DIGITHINGS_SOCIALS`, DocsLayout/CodeTabs/EndpointDoc, Pricing/PricingMatrix, NumberedStages, PerfMetrics/StatCounter, TerminalManifest, RepoActivity, the chat family including `DigichatLauncher`, the vendored shadcn kit `ui/` (**the only primitive source**, `dress` axis), the conviction primitives, Terminal, emblems, graph, ThemeProvider, MotionProvider, `AuthCard`, module data) + `styles/web-theme.css`, **the single `@theme inline` Tailwind bridge** |

`SocialRow` (`web/src/components/SocialRow.tsx`, dress in `./styles/nav-shell.css`)
is the quiet company-profile utility row: the same borderless `.btn-icon`
grammar as the NavShell GitHub slot (radius 0, ink-mute → ink, `--accent` only
on `:focus-visible`). Default `DIGITHINGS_SOCIALS` is the live GitHub / X /
LinkedIn set; Discord is not a network we run. Specimens live on the reference
chrome page (`SocialsReference`). `Footer` accepts an optional `profiles` slot
so marketing sites can mount the row without a fake Connect column.

`AuthCard` (`web/src/components/account/AuthCard.tsx`, CSS
`./styles/account-auth.css`) is the promoted sign-in / create-account card.
Layouts `compact`, `icons-first`, and `desk` share one form: email + password,
Google / GitHub / X (Supabase OAuth 2.0 provider id `x`, visible label X), primary submit
Sign in / Sign up, footer Create an account / Sign in. Compact places the
`digiquant` wordmark beside the mark. Desk may keep a product kicker, a sign-up
strength meter, and sign-in Forgot password. Specimens live on the reference
account page (`AuthCardProposals`) as a layout catalog. The dashboard login
screen imports compact `AuthCard` (`apps/dashboard/components/login-screen.tsx`).

`DigichatLauncher` (`web/src/components/chat/DigichatLauncher.tsx`, CSS
`./styles/digichat-launcher.css`, import `@digithings/ui/chat/launcher`) is the standard embedded-chat entry point
(`chrome.mode: modal`). Its idle state is a 30px square using the canonical
compact `TerminalMark`; hover/focus types `digichat` in the shared mono chrome
size while preserving height and border. Opening runs a two-step expansion out
of that square — the square widens into a composer-height bar, then the bar
lifts to full height — and closing reverses both steps. It dismisses via its
header, Escape, or the transparent outside-click backdrop. `CLOSE_MS` in the
component mirrors the close animation duration in the sheet; reduced-motion
closes immediately. After the first open, the hidden panel keeps its children
mounted so an iframe conversation survives close/reopen. It portals to
`document.body` by default to escape transformed/backdrop-filter app shells;
`portal={false}` contains reference specimens. Product can mount
`DigichatThread` (`@digithings/ui/chat/thread`) as `children`. That subpath
**is** the first-party Thread (`gallery-thread/thread.aui.tsx` + slots),
not a second ChatMarkdown tree. Import the subpath — never the
`@digithings/ui` main barrel (webpack OOM). The design-reference `/chatbot`
page is a fixture lab on **that same import** — see
[`CHAT_THEME.md`](CHAT_THEME.md). Tool rows whose result payload carries the
Gloomberb `attribution` block render the attribution line (canonical string,
delay notice, `term.gloom.sh` deep link) beneath the JSON result pane, driven
by the shared `web/src/lib/gloomberb.ts` helper that the `@digithings/ui`
barrel exports (`GLOOMBERB_*`, `gloomberbTickerUrl`, `readGloomberbAttribution`).
The full assistant-ui elements catalog (every `/elements` slug, purpose, fetch command,
and digichat attach kind) lives in
[`ASSISTANT_UI_ELEMENTS.md`](ASSISTANT_UI_ELEMENTS.md) — discover there, copy
from the registry on demand; do not dump the catalog into `MANIFEST.json`.

The F1 promotion campaign (#1450) added four more component families to
`@digithings/ui`, each a `web/src/components/<family>/` directory with its own
barrel, re-exported from `src/index.ts`:

| Family | Components | CSS subpath |
| ------ | ---------- | ----------- |
| `finance-charts` | PriceChart, EquityCurve, DrawdownPlot + two chart scaffolds: rebuild-on-data `useFinanceChart` (with `readFinancePalette`, `financeChartOptions`, `tokenAlpha`, `toChartTime`) and the persistent dashboard lifecycle `useLightweightChart` (`chartChromeOptions`, `hostMonoFont`, `toLineData`/`timeToISO`, `useChartTip`/`ChartTipShell`, `useFinanceChartPalette`/`getFinancePalette` — converged from dashboard `lib/lw-chart.tsx`, #1450 batch E) and `*_DEMO` datasets. (MonthlyReturns and its `finance-charts.css` were deprecated into finance-tearsheet's ReturnsMatrix, #1463.) | — (the charts are canvas, zero CSS; `ChartTipShell` is utility-classed, covered by the family `@source` line) |
| `finance-composites` | StockTicker, OrderBook, SortableTable, PerformanceDashboard, SyncedTearsheet | `./styles/finance-composites.css` |
| `data-layout` | Odometer/OdometerStrip, DotMatrixStat, BentoGrid/BentoCell, ProductFrame, FeatureCell, TestimonialWall | `./styles/data-layout.css` |
| `repo-activity` | RepoActivity (compact + detailed) + `fetchRepoActivityLive`. Snapshot-first GitHub velocity: three 30-day counts (commits on the configured branch, merged PRs, closed issues), current open PRs/issues, latest release, recent merged PRs, recently updated open issues. Optional client refresh applies atomically or keeps the snapshot. No stars/forks/watchers. | `./styles/repo-activity.css` |
| `effects-chrome` | Pipeline, RotatingPrompts, StackingPanels, AnnouncementBar, TabStrip (+ `tabId`/`tabPanelId` helpers), ToastStack | `./styles/effects-chrome.css` |

The #1463 reverse-promotion added the **`finance-tearsheet`** family — the
print-grade SVG tearsheet grammar (`.ts-*`) promoted from
`apps/digiquant-web/components/tearsheet/`:

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

Waves 0–3 of the shadcn migration (#4206) built the **`ui`** family — the
first *vendored* package family (stock shadcn/ui on Base UI, `base-lyra`
preset), with no sheet of its own (all utilities, same bridge). Wave 4's W4-P1
closed the Table/Select/Badge gaps — Table `numeric`/`density` and the new
`TableRowHeader` (`<th scope="row">`), Select composition (`SelectPopup` +
exported `SelectItemIndicator`), and the Badge
`neutral`/`accent`/`warn`/`up`/`down` tones — so the consumers still pinned to
`components/controls/*` could move onto the kit. Wave 4's cleanup (W4-J) then
re-pointed the seven dashboard twelve-x `Sheet` imports onto the kit and deleted
the controls files with zero consumers (`Avatar`, `Badge`, `Sheet`,
`Collapsible`), the second `gallery-thread` component library, digichat's four
dead `ui/` wrappers, and the orphan `dashboard-workspace-reference.tsx`.
Batches K1–K2 promoted the last missing capabilities, and batch K3 retired the
layer outright (below). Deferred kit items live in #4306.

Batch K1 (#4306) then promoted the seven highest-impact remaining gaps in one
pass: **Slider** (the vendored stock shadcn Base UI slider — single + range
thumbs, token-bridged to the accent mechanic), **EmptyState**, **Skeleton**
(+ `SkeletonGroup`), **RadioGroup**/**Radio**, **Field**, **IconButton**, and
**SegmentedControl**. Every live consumer was repointed — the canon specimens
(`apps/reference/components/controls/*`), the dashboard's empty-state/skeleton/
icon-button/segmented-control files, `packages/digichat-ui`, and
`packages/ui/src/components/ThemeProvider.tsx`. The controls copies stayed in
place and kept exporting until the retirement batch; only the reference's local
`.sl-input` mechanic was deleted. The promote-from-controls recipe is
[MIGRATION.md § Promote a part out of the controls layer](MIGRATION.md#promote-a-part-out-of-the-controls-layer-batch-k1).

Batch K2 (#4306) then promoted the remaining keep-list parts — **Breadcrumbs,
Pagination, DatePager, TagsInput (+ `TagChip`), SearchBar** — and added the two
net-new kit parts the canon lacked: **Avatar** (the vendored stock shadcn/Base UI
avatar, with image/fallback/badge/group parts) and **Form** (a presentational
`Form`/`FormField`/`FormActions` wrapper over `Field`; no form-library
dependency). Every live consumer was repointed (the canon specimens, the RTL
proof, the dashboard `PipelineDaySelector` and `BriefsIndex`), and the
`DatePager` calendar CSS moved into `styles/web-theme.css` (`.nb-cal*`, plus the
kit's own `.kit-pop` travel) so the kit no longer depends on the controls sheet.
The controls copies remained at zero consumers until batch K3 deleted them. Part
coverage finished too: the specimens now render `AlertAction`, `CardAction`,
`DialogOverlay`/`DialogPortal`, the `DropdownMenu` portal/checkbox/submenu parts,
the `Select` content/group/label/separator parts, and `SheetClose`/`SheetFooter`.

Batch K3 (#4306) **retired the controls layer**: the last main-barrel consumers
were repointed to the kit, `Pager`/`PagerPage` were promoted into
`ui/pager.tsx` (their only remaining consumer was the canon nav-buttons
specimen), the one live helper (`cx`) moved to `lib/cx.ts` for `ContactMailto`,
and every `packages/ui/src/components/controls/*` file plus its exports in
`src/index.ts` was deleted. The dead `.ctl-*` CSS went with it — `ctl-avatar*`,
`ctl-badge-ref*`, `ctl-search-row`, and `ctl-sheet*` in
`styles/controls-core.css` / `controls-overlay.css` — while the chat-dress
families the kit still emits (`ctl-btn-chat*`, `ctl-badge-chat*`,
`ctl-card-chat*`, `ctl-input-chat`, `ctl-label-chat`) stay live. `@digithings/ui`
is no longer a primitive source; the kit (`@digithings/ui/ui`) is the only one.

| Family | Components | CSS subpath |
| ------ | ---------- | ----------- |
| `ui` | Alert, Avatar (+ parts), Badge, Breadcrumbs, Button (+ `buttonVariants`), Card (+ parts), Checkbox, Collapsible, DatePager, Dialog (+ parts), DropdownMenu (+ parts), EmptyState, Field, Form, IconButton, Input, Label, Pager, Pagination, Radio/RadioGroup, SearchBar, SegmentedControl, Select (+ parts), Separator, Sheet (+ parts), Skeleton/SkeletonGroup, Slider, Switch, Table (+ parts), Tabs, TagsInput, Textarea, Tooltip (+ parts) — barrel `web/src/ui/index.ts`, export `@digithings/ui/ui` | `styles/web-theme.css` (the `sk-shimmer` keyframes plus the ported `.nb-cal*` calendar grid and `.kit-pop` travel; otherwise utility-only — consumers add `@source "../../../packages/ui/src/ui"`) |

The five parts digichat needed a chat tone for carry the `dress="chat"` axis
(Button/Card/Badge/Input/Label), which emits the existing `ctl-*-chat` classes
from `styles/controls-core.css` instead of the kit utilities; `Card` propagates
`dress` to its parts through a context. Kit Table separators resolve to
`border-border` (the hairline token), and the kit's focus fills use the neutral
`secondary` surface (not the brand accent).

`Spinner` is **not** part of the `ui` family: it lives in the main barrel
(`web/src/index.ts` → `./components/Spinner`, export `@digithings/ui`), so
`import { Spinner } from '@digithings/ui/ui'` is a build error.

Refresh it with `npx shadcn@latest add <name>` inside `packages/ui`
(the `components.json` there is authoritative); local deltas stay limited to
import adaptations (`cn` from `../lib/utils`, sibling `./button`). The kit is
indexed in `MANIFEST.json` under family `ui` (one row per `web/src/ui/<name>.tsx`,
`path` relative to the digiweb root), because the gallery proves it through the
package export `@digithings/ui/ui` rather than a `@/components/*` path (#4225);
the barrel remains the export source of truth and
[MIGRATION.md](MIGRATION.md) the adoption guide.

Page-level dashboard composition is owned by the dashboard app
(`apps/dashboard`): a command band establishes one primary state, compact
metrics add context, and a flat hairline ledger owns the working detail. Product
apps adapt that composition around their own data and interactions rather than
introducing generic cards or duplicating existing controls such as `TabStrip`,
`SegmentedControl`, `Sheet`, and `EmptyState`.

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
(a relative `../packages/ui/...` import), the `packages/design/**`
invariant in `CLAUDE.md`, and doc links checked by `make doc-check`. Consumers
build unchanged.

## MANIFEST.json — the agent index

A generated JSON so any agent (including via MCP filesystem access) can discover
components without reading every file. Shape:

```jsonc
{
  "generatedAt": "<ISO timestamp>",
  "source": "apps/reference",
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
node scripts/build-manifest.mjs
```

The generator derives structure (name, path, family) from the filesystem and
the family a component is imported into, and the `summary` from the leading
`/** … */` docblock. Components without a docblock appear with `summary: null` —
the generator prints the coverage so gaps are visible and easy to backfill.

Two indexing rules are worth calling out (#4225): next.js route groups
(`(gallery)`, `(chatbot)`) are transparent, so family pages at
`reference/app/(gallery)/<fam>/page.tsx` land under `<fam>` and
`reference/app/(gallery)/page.tsx` under `foundations`; and the vendored shadcn
kit at `web/src/ui/*.tsx` — importable only as the package export
`@digithings/ui/ui`, so no reference page ever maps it — is indexed directly
from source, one row per `<name>.tsx` with `path` relative to the digiweb root,
under family `ui`.

## Brand identity — the terminal marks

`@digithings/ui` `components/symbols/terminal-marks.tsx` is the canonical
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
`packages/brand/` — avatars from the favicon tile, OG cards and social
headers from outlined Geist Mono + `HEADLINES` in `build-og.py`. Headers are a
**compact stack**, not a cropped 1200×630 card. `build-header.py --check` keeps
the served copies on the design-reference `/brand` page in sync (not on
digithings.ai). See `packages/brand/README.md`.

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

## RTL & logical properties (#4306)

The kit is **direction-agnostic by construction**: every part is authored with
logical CSS so LTR rendering is byte-identical and `dir="rtl"` mirrors the whole
tree — no per-page work. The preset declares this honestly: `rtl: true` in
`components.json` (kit, reference, digichat).

**Setting direction.** `ThemeProvider` takes `dir?: "ltr" | "rtl"` (default
`"ltr"`) and applies it to `<html>`; that is the app-level switch —
`<ThemeProvider dir="rtl">` mirrors the entire document, chrome included. For a
region, `DirectionProvider` renders a `<div dir=…>` (and `useDirection()` reads
the nearest one); `DirectionProvider root` applies to `<html>` instead and
resets to `ltr` on unmount. Both are exported from the package barrel. RTL is
never the default and there is no language switcher.

**Policy for new parts.** Never write a physical directional property. Convert
at authoring time:

| Physical | Logical |
| --- | --- |
| `margin-left/right` | `margin-inline-start/end` (`ml-/mr-` → `ms-/me-`) |
| `padding-left/right` | `padding-inline-start/end` (`pl-/pr-` → `ps-/pe-`) |
| `left` / `right` (positioning) | `inset-inline-start/end` (`left-/right-` → `start-/end-`) |
| `text-align: left/right` | `text-align: start/end` (`text-left/right` → `text-start/end`) |
| `border-left/right` | `border-inline-start/end` (`border-l-/r-` → `border-s-/e-`) |
| `border-top/bottom-left/right-radius` | `border-start-start`, `border-start-end`, `border-end-start`, `border-end-end` (`rounded-tl/tr/bl/br-` → `rounded-ss/se/es/ee-`) |

**Directional art.** `translate`/`transform` and `transform-origin` have no
logical form, so a few pieces carry explicit direction awareness instead:

- **`TabStrip`** — the sliding ink anchors on `inset-inline-start` and measures
  the active tab from that same edge via `getBoundingClientRect`, negating x
  under RTL; arrow-key nav swaps ArrowLeft/ArrowRight. This is the one
  non-mechanical piece in the sweep.
- Chevrons/arrows that encode a direction are mirrored: the dropdown
  sub-trigger (`rtl:-scale-x-100`), `Pagination` prev/next and `DatePager` month
  steps (`rtl:scale-x-[-1]` on the kit parts).
- Switch / billing-toggle knobs anchor inline-start and negate their checked
  `translateX` under RTL.

**Deliberately physical** (mirroring would be wrong; each carries an inline
comment): `ui/sheet.tsx` and `.ctl-sheet[data-side=…]` geometry — `side` names a
physical edge in the API; `.nav-shell-group-caret` and the
`accordion-reference` caret (rotated corners that build a vertical caret);
`.ctl-tip-arrow[data-side=left|right]` (physical placements, split from the
logical `inline-start/end` rules); markdown-table `[[align=right]]:text-right`
(HTML `align` is physical); toast-stack `inset` shorthand.

**Proof route.** `apps/reference/app/(gallery)/rtl/page.tsx` renders the canon
behind an LTR/RTL toggle (`DirectionProvider root`), covering chrome, every
button variant × size, fields, Select + `SelectPopup`, checkbox/switch, dropdown,
dialog and both sheet sides, both tab systems, tooltip, pager/date-pager, a
table with end-aligned numerics, badge tones, empty state, cards, and a
pinned/two-column layout.

## Pointer cursors (#4306, phase 0.3)

Cursor is part of the part, not the page. Tailwind v4 preflight leaves buttons
at the default arrow, so every activatable kit part sets `cursor-pointer`
itself: `ui/button.tsx`, the menu/select items and sub-triggers, `TabsTrigger`,
`Switch`, `Checkbox`, `CollapsibleTrigger`, `TableRow interactive` (opt-in —
only some rows activate), and the kit `Pagination`, `DatePager`, `TagsInput`,
`SearchBar` and `Breadcrumbs` controls (via token utilities). Disabled parts
carry `cursor: not-allowed` (the `disabled:` / `data-disabled:` variant, or the
kit sheet rule) so the state names the affordance instead of inheriting the
base pointer.

The convention is enforced: `scripts/check_frontend_canon.py` flags any
`cursor-*` utility under `apps/**` (`apps/reference` is the exempt proof
surface). An app-local cursor is treated as a missing-kit signal — promote the
part, or leave a reviewed `canon-allow: <reason>` on genuinely app-specific
chrome (canvas gestures, native `<summary>`, custom timelines). See
[MIGRATION.md § Pointer cursors](MIGRATION.md).

## Build / CI posture

The reference app is **linted and type-checked** in CI by the `web` lane
(`test-web.yml`), gated on `apps/reference/**`: `npm run lint` and
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
because neither site builds it; `apps/reference/**` is watched by the
`web` lane instead, which lints and type-checks rather than building.

Before #1981 nothing built, linted or type-checked this app, but "no coverage at
all" would overstate it. `scripts/check_frontend_canon.py` (the unconditional
`frontend-canon` job) does scan this workspace for raw palette utilities, legacy
vocabulary and colour literals. What it does *not* scan here is new CSS class
families: digiweb is exempt from that census by design, because the reference is
where new families are supposed to be born. `make score` also reaches this
directory — only `packages/design/` sits in `score.py`'s skip list — but
`ci.yml`'s `score` path filter excludes `apps/**` and `packages/**` (#1310), so the lane does
not fire on a frontend-only PR. Note the distinction: the CI *filter* excludes
`apps/**` and `packages/**`, the *tool* does not.

The suite has no auth, crypto, or live-trading surface, so
the human-gate items in `CLAUDE.md` do not apply to component work here (a
physical relocation of the shared packages, which touches deploy config, does).

## Family CSS layering (#4306, workstream A)

Kit utilities live in Tailwind's `utilities` layer, so any app rule that must
lose to them belongs in `components`. The reference's per-family sheets wrap
their dress in `@layer components { … }` for exactly that reason; a rule that
has to beat a utility stays unlayered and says so inline (the reference's
`.sb-hint` vs the unlayered `.kbd`). `@import` lines stay ahead of the layer
block. The reference `(chatbot)` root, which themes vendor assistant-ui CSS,
keeps its own unlayered cascade. Full rule and the pinned test:
[MIGRATION.md § App family CSS layering](MIGRATION.md).
