# Cross-cutting dashboard rebuild plan

This is synthesized from the eight briefs (Brief, Portfolio, Pipeline, FX Hub, Settings, House, Tools, DigiChat). I did not verify anything against the repo beyond what the briefs state.

## 1. Sidebar and page structure

**WORKSPACE group**
- **Brief** (`/`) stays.
- **Portfolio** goes from 5 children to 3. Paths are kept, so no inbound link breaks.
  - **Book** at `/portfolio`. It absorbs Ledger as an Activity pane (`?pane=activity`).
  - **Performance** at `/portfolio/performance`, alias `/performance`. It absorbs the book-attribution waterfall.
  - **Decisions** at `/portfolio/attribution`. It absorbs Theses and Audit.
- These old routes stay as aliases: `/portfolio/ledger`, `/portfolio?tab=theses`, `/portfolio/theses`.
- `/portfolio/tickers?ticker=` and `/portfolio/theses?thesis=` stay as static query-param routes, not nav items, and also open in a Sheet inspector.
- **Pipeline** (`/pipeline`, canvas layout) stays as the glass-box centerpiece. The 30-day run strip doubles as the date selector.
- **FX Hub** keeps 6 tabs. `track-record` gets folded into Trades as a "Record" segment, and `?tab=track-record` must keep resolving.
- **Chat** is new (`/chat`, canvas layout, Desk+). The popup launcher is hidden on this route.

**REFERENCE group**
- **House** keeps Corpus, Book and Profile.

**TOOLS group**
- The Tools group is promoted from hardcoded JSX in `sidebar.tsx` to a `TOOLS` export in `nav-model.ts`. Items become data with optional `external` and `badge` fields.
- Entries:
  - **Connections** at `/tools`, with category children driven by `?tab=`.
  - **Gloomberb**, external, keeping testid `sidebar-gloomberb-link`.
  - **LuxAlgo**, a collapsed group with Charting & Scripting, Broker SDK and Journal. Each is a "planned" static page.
- fx_hub-only invitees see none of Tools.

**Settings**
- Settings collapses from 7 tabs to 5 to 6 anchored sections on one scrolling page: Account (profile plus notifications), Pipeline, Connections (brokers plus keys), Plan, Appearance and System.
- Old hash ids stay as aliases: `brokers` and `keys` go to `connections`, `about` to `system`, `billing` to `plan`.
- The OAuth callback bug is fixed: `settingsHomeHref()` must append `#brokers`.

**Pipeline selector placement**
- One shell-level `PipelineSelect` sits in the app header and is visible on every surface.
- It shows a single "Baseline" option today, rendered as a real Select rather than a stub.
- Pipeline, House and FX Hub read it from context. Settings/Pipeline shows a local echo of it.
- Only the Pipeline surface applies `scope` to its data reads today. The other surfaces keep the selector as a visible seam only.

## 2. Shared kit primitives

Every new part needs the full promotion path: `packages/ui`, then a reference specimen plus `specimen-inventory.ts`, then a regenerated `MANIFEST.json`, then render tests. All parts use tokens only, and health states use accent/warn/mute rather than up/down. Every brief flagged the same gap: no sparkline, stacked bar, heatmap, range track or status strip exists in the kit.

**Promotion order (deduped across the briefs):**
1. **Sparkline** (SVG, tone, last-dot, null-gap). Needed by Brief, Portfolio, FX Hub and House.
2. **StatusDot and StatusStrip** (N hairline cells with tooltips). Needed by Pipeline run strip, Settings run ribbon, Tools health, House and the hop-proof meter.
3. **CompositionBar** (stacked and 100% share bar, cash segment, click). Needed by Brief, House and FX stance mix. Portfolio's weight-over-time stacked-area chart is a separate part (step 6).
4. **DivergingBars** (horizontal ranked, labelled) and a **DivergingBar/ScoreBar with ticks**. This promotes the app-local `ConsensusScoreBar` and its `.dbar-*` CSS. It also covers BulletDelta and TargetActualBar.
5. **RangeTrack**. Lift `RiskEnvelopeCell` math, keep it as a thin adapter, and cover FX `LevelLadder` and `ExcursionRangeCell` too.
6. **HeatGrid and CalendarHeatmap.** HeatGrid serves the FX matrix and event density. Generalise `RepoHeatmap` with a `unit` prop for the House corpus calendar.
7. **AllocationTreemap** and **StackedAreaChart**. StackedAreaChart replaces the recharts sleeve chart.
8. **Waterfall**, used for the Pipeline call trace and the attribution bridge. **StepMeter** and **PlanLadder** for Settings.
9. **ToolSelector** and **PipelineSelector**. Check whether the existing stock composer picker can be composed from Select, Switch and Collapsible first.

Nice-to-have: DotPlot for decisions and DayTimeline for FX. Both can ship v1 using SignedBars.

**Open decision before any app work: the chart import path.**
- Charts live on the `@digithings/ui` root barrel, not on `@digithings/ui/ui`. The "only `@digithings/ui/ui`" rule can't be met for charts.
- Existing dashboard code already imports from the root. Either add an `@digithings/ui/charts` subpath or confirm the canon guard allows root imports.

**Engine rule.** Performance prints, so it must stay on the SVG tearsheet family. Every other surface is screen-only, but I recommend SVG for all new parts. That keeps `renderToStaticMarkup` tests working, since canvas charts render nothing under SSR, and it keeps many small instances cheap.

## 3. Pipeline context and selector data design

**Types**
- `PipelineRef = {id, label, kind: 'baseline'|'user'|'fork', profileKey, topologyId}`.
- `PipelineScope = {pipelineId, profileKey?}`.

**Registry**
- `lib/pipelines.ts` holds a static `[baseline]` list and a `usePipelines()` hook ready for a fetched list later.
- DigiChat and House add no registries of their own. They consume this one.

**Provider**
- `PipelineSelectionProvider` is mounted next to `app-shell-context`.
- Resolution order is `?pipeline=` first, then localStorage, then `baseline`. An unknown id falls back to baseline with a warn notice.
- `?pipeline=` is omitted from URLs when the value is baseline. `buildPipelineHref` and `parsePipelineParams` gain an optional param, so the existing consumers are unchanged.

**Data plumbing**
- Fetchers gain an optional `scope` parameter defaulting to baseline. Examples:
  - `fetchResearchRunDiagnostics`
  - `fetchPipelineTrace`
  - `getPerformanceBundle`
  - `fetchPortfolioAttribution`
  - the FX data hook
  - `useDashboard`
- A helper `scopeFilters(scope)` in `api-query.ts` is a no-op for baseline. It adds `.eq('pipeline_id', …)` only where the table has the column.
- `getTopology(scope)` defaults to `PIPELINE_TOPOLOGY`.

**Selection persistence**
- Tools and MCP selection is a separate `DigichatSelection` in `lib/digichat-selection.ts` (localStorage plus `?pipeline=` in the `/chat` URL). It carries `pipelineId` alongside tools and mcp.
- The connection registry's `feeds` field is the join key for a future pipeline-to-connection filter.

**Blocker.** No pipeline or profile column exists on documents, `daily_snapshots`, `run_health` or `run_event_trace`. The backend contract must be confirmed before any non-baseline pipeline is enabled.

## 4. Implementation waves

The shared files are `nav-model.ts` (with its tests, `sidebar.tsx`, `command-palette` and `lib/nav.ts`), `packages/ui/src/index.ts` and `ui/index.ts`, `MANIFEST.json`, `specimen-inventory.ts`, `globals.css`, `dashboard-context` and `app-shell-context`. Wave 0 owns all of them, and later waves get only their own directories.

**Wave 0: foundation (one owner, serial)**
- Kit parts 1 to 6 with specimens, manifest and tests.
- Decide the import subpath.
- `pipelines.ts`, `PipelineSelectionProvider`, `scopeFilters` and the shell header selector.
- Rewrite `nav-model.ts` in one pass: Portfolio 3 children, `TOOLS`, `chat`, Settings sections, `external` and `badge` fields. Update `sidebar.tsx`, `command-palette`, `lib/nav.ts` aliases and their tests.
- `lib/portfolio-url-state.ts` aliases, and the `alpaca-oauth` `#brokers` fix.

**Wave 1: parallel worktrees on disjoint directories (start after Wave 0)**
- **A. Brief.** `apps/dashboard/app/page.tsx`, `components/today/*`, and a new `lib/brief-visuals.ts`.
- **B. Portfolio.** `app/portfolio/**`, `components/portfolio/**`, `components/tearsheet/**`, and `lib/portfolio-*`.
  - Sub-order: Performance first (cheapest big win, since the NAV line data is loaded but not drawn), then Book, then Decisions.
  - This is the largest wave and can be split into B1 (Performance) and B2 (Book, Decisions and the inspector).
- **C. Pipeline.** `components/pipeline/**` and `lib/pipeline-*`.
  - Order: scope plumbing, then the run strip and KPI strip, then the waterfall, then node micro-visuals and tabs.
- **D. FX Hub.** `components/twelve-x/**` and `lib/twelve-x/**`.
  - Leave `subpage-tab-bar` alone.
  - Do not touch `fx-hub-only` files.
- **E. Settings.** `app/settings/**` and `components/settings/**`.
  - Sub-order: sections, then the merged Connections table.
  - It needs the `CONNECTION_KINDS` registry seam that Tools also uses.
- **F. House.** `app/house/**`, `components/house/**` and a new `lib/house-view.ts`. It is small.

**Wave 2: dependent surfaces**
- **G. Tools.** `app/tools/**`, `components/tools/**` and `lib/integrations/**`.
  - It depends on Wave 0's `TOOLS` nav and StatusStrip.
  - Broker UI extraction from `brokers-tab.tsx` must wait for or coordinate with E. Single-source the credentials UI, keep testids and the `SAFE_KEYS` whitelist, and leave the callback route where it is.
- **H. DigiChat.**
  - Steps 4 and 5 of its plan (hook extraction from the popup, then `/chat`) can start in Wave 1. `digichat-popup.tsx` is its own file.
  - The selector rail needs an `apps/digichat` change: a new `digichat:selection` message. The dashboard side ships behind a flag and falls back to "selector disabled" if no ack arrives within 2 seconds.

**Wave 3: cross-cutting cleanup**
- Delete `sleeve-stacked-chart.tsx` (recharts), the `.dbar-*` CSS, `PortfolioSectionNav`, the orphan `components/overview/*` (grep first) and dead settings variants.
- Add structured `meta {route, surface, tab, date}` to the popup's page-context payload. Chart-heavy views otherwise blind the popup, which only reads DOM text.
- Every new chart part exposes an sr-only text summary.
- Sweep `chart-colors` hex use, then run vitest, tsc, eslint, the frontend-canon guard, a static export build and visual QA.

**Ownership rules**
- No wave edits another wave's directory or the shared files listed above.
- A wave that needs a new kit part files it back to Wave 0.

**Cross-brief conflicts to resolve**
- Brief and Portfolio both use TimeSeries for NAV. Standardise on the SVG family so tests stay SSR-safe.
- `RiskEnvelopeCell` and FX `ExcursionRangeCell` become one RangeTrack.
- Settings Connections and Tools both render broker rows. One owner extracts a shared adapter (`lib/integrations/adapters/brokers.ts`), and Settings keeps credential entry until the rebuild lands.

## 5. Decisions the user must make

1. **Portfolio consolidation.** Is Book / Performance / Decisions (3 views, Ledger and Theses folded in) acceptable? Or should Theses or Ledger keep their own nav entries?
2. **Chart import path.** Add an `@digithings/ui/charts` subpath, or allow root-barrel imports?
3. **Pipeline backend contract.** Will `documents`, `run_health` and the other views carry a `pipeline_id` or `profile_key`? Where do user pipelines live? Until answered, the selector stays single-option.
4. **DigiChat selection message.** Are you willing to have `apps/digichat` add `digichat:selection` (an embed URL param would be the alternative)? Without it, tool and pipeline switching is a visual stub. This work is the largest scope decision, since the full-screen `/chat` reuses the iframe rather than rebuilding chat UI.
5. **LuxAlgo and MCP.** There are no references in the repo today. Are "planned" pages plus a registry acceptable now, or do you want real wiring later? Where should MCP servers be stored (a `workspace_integrations` table versus the digichat tenant config)? Should LuxAlgo journaling live in Tools, DigiChat, or both?
6. **Attribution semantics.** Keep the "current-book lookback diagnostic" label on the waterfall?
7. **Trace gating.** The call trace and timeline are body-free but ungated today. Do they need the `glassbox_economics` gate?
8. **Track record.** Fold it into FX Trades, or leave it hidden as it is now?
9. **Settings model.** Is one scrolling page with a rail and search acceptable, and should the sidebar dropdown keep theme and density, or drop them in favor of Settings?
10. **Usage and billing data.** No spend, usage or invoice endpoint exists. Do you want a backend follow-up, or should the plan ladder ship without usage meters?
11. **Print scope.** Is Performance the only PDF surface, or should Brief or House get print too?
12. **Naming.** The code and URL say "Gloomberb", not Bloomberg. Keep it?

**Suggested ship order:** Wave 0, then Performance, Brief and Pipeline run strip, then Book and FX Today. The remaining surfaces follow, and DigiChat waits on the decision in question 4.