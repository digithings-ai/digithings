# DigiQuant dashboard — production wire-up plan

**Date:** 2026-10-02  
**Audience:** One, spawning parallel Cursor / OpenCode implement seats.  
**Status:** plan only. No app code in this change.  
**Base:** `develop` (tip when this doc was written: `8540d815b`). Do not branch implement work off PR #4911.  
**Visual aid:** remock canvas on draft PR [#4911](https://github.com/digithings-ai/digithings/pull/4911), branch `cursor/digiquant-dashboard-skeleton-mocks-67ef`.  
**Related:** #4895 (product split), #4900 (digiquant.io showcase, open), #4908 (skeleton plan), #4911 (static mocks, HOLD), #4941 (canvas polish).

This document is the handoff. An implement seat should not re-discover routes, clients, or which mock commit is the picture.

---

## 0. Locks (do not renegotiate in a slice)

These are product locks. They override the approved mock’s information architecture where the two disagree (see §1).

1. **One viewport per page.** The document does not scroll. Panes rearrange and resize. Overflow scrolls inside the pane, or the page splits into sidebar sub-routes. Never grow the page taller or shorter than the viewport to fit content.
2. **Nested collapsible sidebar owns all navigation.** Kill horizontal in-page section tabs (`PortfolioSectionNav`, settings tab strips, Brief section chips). Chart interval tabs inside a chart pane stay local.
3. **Top chrome is path only.** Example: `house / portfolio / holdings`. `house` is a desk name, not the `/house` Corpus / Book / Profile page. The path tree mirrors DigiCon / component paths (`/book`, `/movers`, and the real routes in §4).
4. **Pane column priority + fullscreen.** Narrow panes drop columns in a fixed priority order (keep identity and the number that matters; drop provenance and long text first). Every pane has fullscreen. `Esc` leaves fullscreen and does not navigate away.
5. **Desk picker** is a dropdown / popover wider than the rail, plus a fullscreen overlay of the same menu. Choosing a desk replaces the whole spine. Three desks exist in the mock: `house`, `rates watch`, `FX Hub`.
6. **DigiChat is the right rail.** DigiQuant content stays on the left (rail + panes). The current popup is the wrong chrome.
7. **Every data block maps to a DigiCon path.** Remock numbers are visual aids. No orphan visualization and no second fake book.
8. **DigiQuant Vela theme.** Up is DigiQuant teal `#3dd6c4`. Down is DigiQuant red `#e5533e`. Full pane color scale comes from `@digithings/design` tokens (`--up`, `--down`, `--warn`, `--accent`, `--ink*`, `--hair`). Do not ship stock TradingView green/red, and do not copy the mock stylesheet’s `--up: #52d296` / `--down: #f06a5e`.
9. **Chart vertical wheel** moves the pane column (the in-viewport scroller), not the chart’s vertical scale, when that interaction exists. Horizontal wheel stays on the chart (pan / zoom). This must not reintroduce document scroll (lock 1).

Also locked:

- Paper and research posture. No live-trading claims, no order ticket, no live broker control.
- HOLD hatch on #4911. Do not merge, undraft, or push more remock HTML onto that branch from an implement seat.
- Do not use the live digiquant dashboard or digiquant.io as a design source.
- Do not touch `digikey/`, `digiquant/brokers/`, or digivoice.
- Locks 1 and 9 apply to `apps/dashboard` only. digiquant.io is a scrolling marketing page. Its approved scroll behavior is tip `1b2c9002d` (slice I). Do not impose the dashboard one-viewport rule on it.
- Do not rebuild the rest of the digiquant.io marketing site. The only in-scope marketing work is slice I (landing hero sequence on #4900).

Layered build order from the implement brief: atoms, then Brief sections, then the terminal shell is the *composition* order inside a seat. Across seats, the shell contract in §6 lands first so pane seats do not invent chrome. Slice I does not wait on that shell.

---

## 1. What to look at, and the drift

| Tip | What it is |
|---|---|
| `051f13ec44fb8dabdf8fe8e12a8ba97c2b2cacd2` | Chris-approved **visual aid**. Lighter-gray `.sec > h2.eyebrow` headers, window hairlines, lifted type, full-bleed, Inter + JetBrains Mono in the mock. |
| `a574277a65c8b1378babadc47feed27870d7f6ef` | Latest cook on the #4911 branch when this plan was written. |
| `29463fbf2` … `d5e0193c6` | Rejected dense remock (one-viewport squeeze, `mock-nav.js`, drag, Vela colors in CSS). Reverted by `3207a28ae`. **Do not copy that HTML.** |

`git diff --stat 051f13ec a574277a -- docs/dashboard-mocks/canvas` is one file: `CLAUDE-HANDOFF.md` (+111). HTML and `mock.css` are identical. There is no look drift between the historical visual tip and the latest cook. Behavior drift is in the handoff prose, not in the pixels.

Serve for humans (on a checkout of that branch, not on `develop` — the canvas is not on `develop`):

```bash
git fetch origin cursor/digiquant-dashboard-skeleton-mocks-67ef
cd docs/dashboard-mocks/canvas && python3 -m http.server 3920
```

Open `http://127.0.0.1:3920/brief.html`. Hard-refresh. Read `CLAUDE-HANDOFF.md` on that branch. The verbatim canvas-comments file named in the handoff (`chris-dashboard-canvas-comments-verbatim-2026-10-01.md`) is **not in git**. Locks in §0 are the user brief plus that handoff plus the #4911 comments. If Message D adds a lock that is not here, stop and ask Chris.

### Look-and-feel to copy from the HTML/CSS

- Black canvas, radius 0, hairline window frames, numbered eyebrows (`01 / Decision`) on a light gray wash (`--wash`).
- Top band ~44px: wordmark, market strip, as-of, paper / research chip. Implement path-only chrome (lock 3) in that band; the mock still prints a page title in `.band h1` — the title moves into the path, the band stays.
- Left rail ~208px, collapsible. Desk picker at the top of the rail.
- 12-column pane grid (`.sec.s4` … `.s12`). Density is terminal, not a marketing page.
- Type in the mock: Inter for prose, JetBrains Mono for chrome, tables, and numbers. The live app is Geist Mono only (`app/layout.tsx`, “BLEND v0.1”). See Human Gate §9 before swapping fonts.
- Empty, loading, and error frames exist and must be real states, not a blank pane: `brief-empty.html`, `brief-loading.html`, `brief-error.html`, `holdings-empty.html`, `ledger-error.html`, `pipeline-loading.html`, `pipeline-error.html`, `fx-empty.html`, `fx-loading.html`, `fx-error.html`.

### Look in the mock that implement seats must not copy

| Mock fact | Why it loses |
|---|---|
| `--up: #52d296`, `--down: #f06a5e` | Green/salmon. Lock 8 and `packages/design/tokens.css` (`--accent-digiquant: #3dd6c4`, `--up` follows it; down is `#e5533e` in `packages/ui` chat tokens and `apps/dashboard/lib/chart-colors.ts` dark fallback). |
| Horizontal sticky tabs on Portfolio (Holdings / Theses / Tearsheet / Ledger / Attribution) | Lock 2. Nest those items under Portfolio in the rail. |
| Settings horizontal tabs (Desk / Brokers / Integrations / Keys / Theme / Prefs / FX) | Lock 2. Nest under Settings. |
| Document can grow with the pane stack | The approved HTML does not demonstrate one viewport. Lock 1 still applies. Do not “match the mock’s page height.” |
| Placeholder figures (SPY 610.40, NAV 1,011,846.20, thesis ids T-007) | Visual aids. Wire real house-book reads. Fail closed to `—`. Never invent P&L. |
| Gloomberg and LuxAlgo drawn as if they were feeds | Labeled placeholders. Own charting is Vela with DigiQuant colors, fed by digiquant bars. Do not embed a third-party terminal as the data SoT. |
| House Corpus / Book / Profile | Removed from the mock on purpose. `house` is a desk name. |

---

## 2. Where the real app is

| Path | Role |
|---|---|
| `apps/dashboard` | Next.js operator app. npm name `dashboard`. Public path `/dashboard/` (`basePath`). This is the implement target. |
| `apps/dashboard/lib/api-client.ts` | Browser client. `apiGet` for specific worker routes. `apiTable` / `apiMaybeSingle` for `GET /v1/tables/:table`. |
| `apps/dashboard/lib/api-query.ts` | `apiDb.from().select().eq()` shim. **This is what the UI actually calls today.** |
| `apps/dashboard/lib/queries.ts` | `getFullDashboardData()` and dossier / library / ledger reads. Local computation on table rows. |
| `apps/dashboard/lib/market-data.ts` | `GET /v1/market/tickers`, `GET /v1/market/closes`. Env `NEXT_PUBLIC_MARKET_DATA_URL`. Empty when unset. |
| `apps/dashboard/lib/chart-colors.ts` | Sanctioned chart colors. Dark fallback up `#3DD6C4`, down `#E5533E`. |
| `apps/dashboard/lib/vela-bars.ts` | `fetchVelaBars()` against the digiquant bars URL. |
| `apps/dashboard/lib/nav.ts` | Flat spine: Brief, Portfolio, Pipeline, FX Hub. |
| `apps/dashboard/components/app-frame.tsx` | Shell. `main` is `overflow-y-auto`. DigiChat is a popup. |
| `apps/dashboard/components/sidebar.tsx` | Collapsible rail, no nest, no desk picker. |
| `apps/dashboard-api` | Cloudflare worker. Contract `CONTRACT.md`. Routes in `src/index.ts`. MCP `POST /mcp` (`src/mcp.ts`). |
| `apps/digithings-stack-cloudflare/src/dashboard-api.ts` | Same handlers folded under `/dashboard-api/*`. |
| `packages/design` | Tokens. `@digithings/design/tokens.css`, `quant-native/styles.css`. |
| `packages/ui` | Kit. `TabStrip` (do not use it for section nav after lock 2), finance tearsheet CSS, gloomberb mark URL. |
| `apps/dashboard/components/research/VelaSpikeChart.tsx` | Only Vela mount. `theme: 'dark'`, no custom bull/bear colors. Route `app/research/vela-spike/page.tsx`. |

There is **no** package, route, or doc on `develop` named DigiCon. This plan uses that name for the data plane in §4. If Chris means a different service, the Human Gate in §9 stops the data seats.

`apps/dashboard` has no `AGENTS.md` or `ARCHITECTURE.md`. Read this plan, `apps/dashboard/README.md`, `apps/dashboard/lib/TABLES.md`, `apps/dashboard/lib/CHARTS.md`, and `apps/dashboard-api/CONTRACT.md` before editing.

---

## 3. Gap inventory

Status words: **exists** (real and usable), **stub** (route or banner with no product behavior), **missing**, **wrong** (present, but contradicts a lock or the visual aid).

### 3.1 Shell

| Remock | App today | Status |
|---|---|---|
| One viewport, pane-internal scroll | `AppFrame` `main` scrolls the page (`overflow-y-auto`) | **wrong** |
| Nested rail: Brief children, Portfolio children, Tools group, Settings children | `NAV` is four flat links. Portfolio children are `PortfolioSectionNav` sticky tabs. Settings uses in-page tabs. | **wrong** |
| Desk picker, three spines | No desk model | **missing** |
| Path-only top (`house / portfolio / holdings`) | No path chrome. `README.md` still describes `.qn-page-chrome`; `app/layout.tsx` does not render it. | **missing** |
| DigiChat right rail | `components/digichat-popup.tsx` floating popup (`#3422`) | **wrong** |
| Pane drag, resize, fullscreen, `Esc` | Not present | **missing** |
| Column priority when a pane is narrow | Tables hide columns ad hoc, not by a shared priority | **missing** |
| Paper / research chip, as-of, market strip in the top band | Scattered badges inside Brief | **wrong** (data exists, chrome does not) |
| Inter + JetBrains Mono | Geist Mono only | **wrong** vs mock; see §9 before changing |
| `/house` Corpus / Book / Profile | `app/house/page.tsx` + `components/house/*` still mounted | **wrong** — desk name only; redirect, do not restyle |

### 3.2 Brief (`brief.html` and empty / loading / error)

Mock sections, in order:

| Pane | App | Status |
|---|---|---|
| Decision / daily digest | `components/today/daily-brief-workspace.tsx` narrative | **exists**, wrong chrome (page section, not a pane) |
| Signals to resolve | same file, `brief-signals-link` | **exists**, wrong chrome |
| Book · allocation | book strip / holdings panel in the same workspace; `lib/book-reconciliation.ts` | **exists**, wrong chrome |
| Book · movers | “Allocation and movers” in the same workspace, client-derived | **exists**, no `/movers` route |
| What could break the view | `brief-risk-thesis` | **exists**, wrong chrome |
| Gloomberg quote strip + tape | `components/gloomberb-mark.tsx` is a mark/link, not a quote board | **stub** |
| LuxAlgo · SPY | `VelaSpikeChart` on `/research/vela-spike` only, not on Brief | **stub** |
| Run health | `components/today/brief-pipeline-health.tsx` and Pipeline | **exists**, wrong chrome |
| KPI strip above the panes | Brief scoreboard inside the workspace; mock still has `.kpis` | **wrong** vs later brief (“kill top KPI strip” was on the rejected remock). **Keep a compact as-of / provenance badge. Do not add a second hero KPI band.** Scoreboard numbers that already exist move into the Decision pane or the path meta. |
| empty / loading / error frames | `DbUnavailable`, page skeleton. Not per-pane. | **stub** |

### 3.3 Portfolio

| Pane / frame | App | Status |
|---|---|---|
| Holdings table (sleeve groups, in-cell weight, symbol pane) | `components/portfolio/*`, `AllocationsPositionsTable` | **exists**, horizontal tabs, page scroll |
| Holdings empty | partial empty copy | **stub** |
| Theses list + kill conditions | `app/portfolio/theses/*`, thesis story components | **exists**. Nav link is `/portfolio?tab=theses` while `app/portfolio/theses/page.tsx` also exists — two entry styles. Pick the nested route. |
| Tearsheet | `app/portfolio/performance`, `components/tearsheet/*`, lightweight-charts | **exists**, report layout is page-scrolled, charts are not Vela |
| Ledger + cash ledger | `app/portfolio/ledger` | **exists** |
| Ledger error | generic error | **stub** |
| Attribution (sleeve + name) | `app/portfolio/attribution`, `AttributionWorkspace` | **exists** |
| Ticker dossier | `app/portfolio/tickers` | **exists**, deep link, not a spine item (correct) |
| Sticky tabs | `PortfolioSectionNav` | **wrong** — move into the rail |

### 3.4 Pipeline

| Pane | App | Status |
|---|---|---|
| Run health | `PipelineRunHealth` | **exists** |
| Canvas inputs → learning | `PipelineCanvas` | **exists**, tall page |
| Node document | `PipelineNodeDetail` | **exists** |
| Call trace | `PipelineTraceLedger` | **exists** |
| Artifact ledger | `PipelineArtifactLedger` | **exists** |
| loading / error frames | partial | **stub** |

### 3.5 Settings

| Mock section | App | Status |
|---|---|---|
| Desk / plan posture | not a settings pane | **missing** |
| Paper brokers | `components/settings/brokers-tab.tsx` | **exists**. Keep paper. Do not extend into `digiquant/brokers/` or live connect. |
| Integrations (Gloomberg, LuxAlgo keys) | not the mock’s integration table | **stub** |
| API keys | `keys-tab.tsx` | **exists** |
| Theme | `theme-provider.tsx` (system / light / dark) | **exists**, not a rail child |
| Prefs | `profile-tab.tsx` nearby | **exists** |
| Billing | `billing-tab.tsx` | **exists** in app, not a first-class mock pane. Keep; nest it. Do not invent new billing. |
| FX API stubs | `fx-hub-account.tsx` | **stub** |
| Paper-only frame | no dedicated paper-only posture page | **missing** |

### 3.6 FX Hub desk

| Mock | App | Status |
|---|---|---|
| Hub / Ideas / Watch / Settings spine | `app/twelve-x`, `components/twelve-x/*`, `lib/twelve-x/*` | **exists**, own layout, not the remock desk shell |
| Pairs, ideas, levels, paper exposure | real twelve-x Supabase reads (separate project) | **exists** — do not re-fetch through dashboard-api (CONTRACT §7 says twelve-x stays direct) |
| empty / loading / error | partial | **stub** |
| Coming-soon banner on the house spine’s FX Hub item | FX Hub is a live nav item, not `[soon]` | **wrong** vs the house-spine tag. On the house desk, FX Hub navigates to the FX Hub desk (or opens it). It is not a fake banner if the suite already runs. |

### 3.7 Strategies and Tools (vision)

| Frame | App | Status |
|---|---|---|
| Strategies catalog, detail, deploy | `app/strategy/page.tsx` redirects away | **missing**. Ship `[wip]` / coming-soon with disabled controls. No estimated track record. |
| Tools → Terminal (Gloomberg) | mark only | **stub** |
| Tools → LuxAlgo | vela spike | **stub** |
| Tools → Charts | no own-charting page | **missing** (Vela atom from slice B covers the pane; the page is a composition) |
| Tools → digichat fullscreen | popup only | **missing** as a rail mode; fullscreen chat is a later composition of the right rail |
| Rates watch desk (Digest, Watchlist, Theses, Run, Config) | not a desk | **missing**. Canvas only redraws Digest and Watchlist; the rest still point at skeleton frames. Do not invent a second book. |

### 3.8 Data wiring (the important gap)

The worker already serves the contracted reads. The UI does not call them.

`apiGet('/portfolio' | '/brief' | '/allocations' | …)` appears in `lib/api-client.test.ts` only. Production pages go through `getFullDashboardData()` → `apiDb` → `GET /v1/tables/:table`, then recompute book, brief, and tearsheet in the client. That is **wrong** relative to lock 7 and `CONTRACT.md` (“dashboard surfaces become thin renderers”).

Envelope routes (`/portfolio`, `/brief`, …) have a stub lane when `SUPABASE_SERVICE_ROLE_KEY` is unset. `GET /v1/tables/:table` does not: it returns `upstream_empty` (502). Pane seats must handle both.

---

## 4. API map (DigiCon)

**DigiCon, in this repo, means:**

1. `apps/dashboard-api` HTTP routes, also mounted at `/dashboard-api/*` on the stack worker.
2. MCP tools on `POST /mcp` (same handlers, header `x-digi-mcp-key` = `MCP_EDGE_KEY`). Fail closed when the secret is unset.
3. Market data worker: `GET /v1/market/tickers`, `GET /v1/market/closes`.
4. Allowlisted table reads: `GET /v1/tables/:table` (`CONTRACT.md` §7). Use these only when no specific route exists.

There is no `/book` route and no `/movers` route. `/book-date` was folded into `GET /portfolio` as `book_as_of`. Path chrome may still say `/book` and `/movers`; the client functions must call the real routes below. Do not add a parallel mock JSON file.

### 4.1 Env and auth

| Env | Where | When missing |
|---|---|---|
| `NEXT_PUBLIC_DASHBOARD_API_URL` | browser, inlined at build | `ApiError` `not_configured`. Pages that are not DB-exempt show `DbUnavailable`. |
| `NEXT_PUBLIC_MARKET_DATA_URL` | browser | closes empty; marks `unavailable`; fail closed, no Supabase price fallback |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | worker only | envelope routes serve `src/stubs.ts`; tables route 502 |
| `MCP_EDGE_KEY` | worker only | `POST /mcp` denies |
| `DASHBOARD_API_ALLOWED_ORIGINS` | worker CORS | default allowlist includes digiquant.io, digithings.ai, localhost |

Auth stays as it is. Browser reads do not send a user JWT to these routes; the worker uses the service role and pins `workspace_id` to the house book `6b753576-ced9-5319-9bfa-c5d0aacd9319` (`HOUSE_WORKSPACE_ID` in `apps/dashboard-api/src/index.ts`, `houseBook()` in `apps/dashboard/lib/house-workspace.ts`). Do not put the service role in the client. Do not add digikey scopes. twelve-x keeps its own Supabase session (`lib/twelve-x/supabase.ts`).

Live vs mockable:

- **live** — returns house data when the worker has the service-role key and the table has rows.
- **stub** — worker doubles in `apps/dashboard-api/src/stubs.ts` when the key is absent (envelope family only).
- **client-derived** — no route; seat computes from a live route and must label provenance.
- **missing** — no route and no honest client derivation yet. Render the mock’s empty/wip state. Do not invent numbers.
- **direct** — not DigiCon. Existing client stays.

`retrieval_pin` is an opaque echo (`CONTRACT.md` §4). Pass it through; do not interpret it.

### 4.2 Path registry (implement `lib/desk/paths.ts` from this table)

Chrome path is what the top bar shows. Endpoint is what the client calls.

| Chrome path | Pane | Call | Mode |
|---|---|---|---|
| `/house/brief` | Decision, digest, since-inception, day | `GET /brief` (`get_brief`). Overlay `auto`. Badge from `overlay.badge`. | live + stub |
| `/house/brief/book` | Book allocation | `GET /portfolio` (`get_portfolio`) positions + invested envelope. CASH out of the name count. | live + stub |
| `/house/brief/movers` | Movers | **No route.** Derive top day moves from `GET /allocations` rows (`current_price` / marks) plus `GET /v1/market/closes` for the book tickers. Unavailable mark → em dash, as the mock does for DBC. Do not add `GET /movers` in the first seats. | client-derived |
| `/house/brief/signals` | Signals to resolve | `GET /v1/tables/theses` filtered to the brief date (allowlist). State and note from the row. Empty array is a real empty pane. | live (502 without key) |
| `/house/brief/breaks` | What could break the view | Same theses read, kill / validity fields already on the thesis model (`lib/queries.ts` `mapThesisRow`). | live |
| `/house/brief/run` | Run health | `GET /v1/tables/run_health` + `run_event_trace` (allowlist). Pipeline page already has this shape. | live |
| `/house/brief/gloomberg` | Quote strip, tape, rates, crosses | **missing** as a feed. Pane is a labeled placeholder. Marks for symbols that are book names may reuse `/allocations` + market closes. Tape headlines have no endpoint — empty state, not lorem. | missing + partial marks |
| `/house/brief/luxalgo` | SPY (or selected symbol) chart | `fetchVelaBars()` (`lib/vela-bars.ts`) into the Vela atom. Not a LuxAlgo cloud feed. | live when bars URL set, else empty |
| `/house/portfolio/holdings` | Positions | `GET /allocations` (`get_allocations`, `include_marks=true`). | live + stub |
| `/house/portfolio/holdings/:ticker` | Symbol pane + dossier | `GET /allocations` row + `fetchTickerDossier()` (`lib/queries.ts`) + `fetchVelaBars()`. | live |
| `/house/portfolio/theses` | Thesis list | `GET /v1/tables/theses` + `thesis_vehicles`. | live |
| `/house/portfolio/tearsheet` | Performance, drawdown, exposures | `GET /performance?benchmark=SPY&window=inception` (`get_performance`) and `GET /nav-series`. Alpha/IR stay null under 20 overlap days. | live + stub |
| `/house/portfolio/ledger` | Fills + cash | `GET /ledger` (`get_ledger`). Types `OPEN\|ADD\|EXIT\|TRIM` only. | live + stub |
| `/house/portfolio/attribution` | Sleeve and name contribution | `GET /v1/tables/position_attribution` and `public_daily_realized_attribution`. No envelope route. | live |
| `/house/pipeline` | Health, node doc, trace, artifacts | `run_health`, `documents`, `run_event_trace` via `GET /v1/tables/:table`. Existing `components/pipeline/*` already render these. | live |
| `/house/settings/brokers` | Paper connections | Existing settings brokers client. Read-only posture in this program. | direct |
| `/house/settings/keys` | Desk keys | Existing keys tab. Masked. | direct |
| `/house/settings/theme` | Theme | `localStorage` `dashboard-theme`. No API. | direct |
| `/fx-hub` `/ideas` `/watch` | FX desk | `lib/twelve-x/fetch.ts` (own Supabase). Movers inside twelve-x (`Mover` in `lib/twelve-x/types.ts`) are **not** the house `/movers` pane. | direct |
| `/house/strategies` and deploy | Catalog | **missing**. WIP banner, disabled controls, zero deployments. | missing |
| `/rates-watch/digest` `/watchlist` | Rates desk | **missing** as its own book. Do not point it at the house book and pretend it is a second product. | missing |

Market strip in the top band (SPY, TLT, GLD, …) is `GET /v1/market/closes` for a fixed display universe. It is chrome, not a book.

### 4.3 Client functions to add (slice B owns the file)

Add typed wrappers next to `apiGet` in `apps/dashboard/lib/desk/digicon.ts` (new). One function per row in §4.2 that has an endpoint. Return the `CONTRACT.md` `data` object plus `provenance`. Map `ApiError` to the pane error state. Do not catch and render zeros.

Suggested names: `getPortfolio`, `getAllocations`, `getBrief`, `getPerformance`, `getNavSeries`, `getKpisLive`, `getBenchmarks`, `getLedger`, `getTable`. `getKpisLive` (`GET /kpis/live`) is the live-marks overlay only. It must never wear a `finalized accounting` badge (`CONTRACT.md` §5, §6.5).

`getFullDashboardData()` stays until Brief and Portfolio panes no longer import it. Do not delete it in the shell slice.

---

## 5. Component tree

Stack stays React / Next in `apps/dashboard`. Design hooks:

- Tokens and quant grammar: `@digithings/design` (already imported from `app/globals.css`).
- Kit primitives: `@digithings/ui` for buttons, tooltips, alerts. **Pointer cursor stays on the kit part.** Do not add app-local `cursor-*` utilities.
- Tables: a new desk table atom. Do not force `@digithings/ui` `SortableTable` — `lib/TABLES.md` already records why portfolio tables cannot use it (grouping, drilldown, money tone).
- Charts: Vela (`@luxalgo/vela`, already a dependency of the spike) for price panes. lightweight-charts stays for NAV / drawdown until a seat explicitly replaces a tearsheet series; colors still come from `useChartColors()`.
- Tearsheet print grammar: `@digithings/ui/styles/finance-tearsheet.css` (already imported).

```
apps/dashboard/
  lib/desk/
    paths.ts              # chrome path → endpoint, from §4.2
    digicon.ts            # typed getters
    movers.ts             # client-derived movers
    column-priority.ts    # ordered column ids per table
    layout-store.ts       # sessionStorage pane order + sizes
  components/desk/
    shell/
      DeskShell.tsx       # 100dvh grid: top, left rail, panes, right chat
      PathChrome.tsx      # path segments only
      DeskRail.tsx        # collapsible, nested
      DeskPicker.tsx      # popover + fullscreen
      ChatRail.tsx        # slot; slice A renders the existing popup inside it
      PaneFrame.tsx       # title, drag handle, resize, fullscreen, Esc
      PaneGrid.tsx        # 12-col, one viewport
    atoms/
      DeskTable.tsx       # group rows, weight bar, column priority, empty/error
      DeskChart.tsx       # Vela, DigiQuant theme, wheel behavior
      DeskFeed.tsx        # tape / trace rows
      DeskState.tsx       # loading | empty | error | ready
    panes/                # one folder per slice, no cross-imports of pane internals
      brief/
      portfolio/
      pipeline/
      settings/
      fx/                 # wraps existing twelve-x views
      vision/             # strategies, tools banners
```

`DeskShell` replaces the scroll behavior of `AppFrame` for desk routes. Keep `AuthGate`, `FxHubOnlyGuard`, and `DbUnavailable` outside the pane grid so a down worker still shows the shell.

`PaneFrame` contract (frozen — pane seats code against this, they do not restyle the frame):

```ts
type PaneState = 'loading' | 'empty' | 'error' | 'ready';

type DeskPaneModel = {
  id: string;
  title: string;          // "Book · movers"
  chromePath: string;     // "/house/brief/movers"
  eyebrow: string;        // "04"
  state: PaneState;
  errorMessage?: string;
  columns?: number;       // 4 | 5 | 6 | 7 | 8 | 12
};
```

Column priority default for holdings, applied by `DeskTable` when the pane width crosses thresholds: drop `Source`, then `Thesis`, then `Shares`, then `Value`, then `Name`. Always keep `Ticker`, `Weight`, `Day`, `Mark`.

Vela theme (slice B), pass explicit colors matching `chart-colors.ts` dark fallback — do not rely on `theme: 'dark'`:

- up / bull candle `#3dd6c4`
- down / bear candle `#e5533e`
- warn `#e0b341`
- background from `--bg` (app canvas, not the mock’s pure `#000` if the app token differs — use the token)

Confirm the installed `@luxalgo/vela` option names against the package types in the seat that touches `DeskChart`. The spike constructs `new Vela(host, { data, timeframe, theme: 'dark', live: false, drawings: false })`.

Chart wheel: on `wheel`, if `deltaY` dominates, `preventDefault` and scroll the pane column. If `deltaX` dominates, leave the event to Vela.

---

## 6. Slice plan

File ownership is exclusive. A seat edits only its files plus the route file named in the slice. Shared types live in slice A and B; later seats import them and do not restyle them.

Suggested order: **A and B in parallel** (B does not import the shell), then **C, D, E, F in parallel**, then **G**, then **H**. **Slice I runs parallel with A** on a different tree. First three dashboard seats One should spawn: **A, B, C**. Spawn **I** in the same wave; it does not share files with them.

Each dashboard seat branches from current `develop` as `task/<N>-<slug>` when an issue exists, or `cursor/<slug>` with `Refs #4895` in the PR. Do not stack on #4911. Slice I branches from PR #4900 (`task/4895-dqweb-3910-message`), not from `develop`.

### Slice A — Desk shell

**Goal.** One viewport. Nested rail. Path chrome. Desk picker popover + fullscreen. Pane frames with resize, reorder, fullscreen, `Esc`. DigiChat right rail slot. No new data.

**Files.** `components/desk/shell/*`, `lib/desk/layout-store.ts`, `components/app-frame.tsx` (delegate desk routes), `lib/nav.ts` (spine becomes desk-aware), `app/house/page.tsx` (redirect to `/`). Tests beside the new components.

**Do not edit.** `lib/queries.ts`, pane components, `dashboard-api`, settings tab bodies, twelve-x fetch.

**Acceptance.**

- At 1280 and 1920, `document.scrollingElement` does not scroll on `/`, `/portfolio`, `/pipeline`.
- Portfolio children are rail links, not `PortfolioSectionNav` on those routes.
- Path reads `house / portfolio / holdings` on holdings (desk, section, page).
- Desk picker lists house, rates watch, FX Hub. Rates watch and unfinished tools show `[wip]` or `[soon]` and an honest banner, not a blank page.
- Fullscreen a pane, press `Esc`, the pane returns and the route does not change.
- Chat occupies the right column when open; left rail remains. Existing popup content may render inside the slot.
- `/house` redirects to Brief. Corpus / Book / Profile are not in the rail.
- Keyboard: shortcut or command palette can jump by path; arrow cycle is a follow-up only if the palette already supports it. Do not block the slice on new shortcuts.

**Depends on.** Nothing.

### Slice B — Atoms and DigiCon client

**Goal.** Table, chart, feed, state atoms. Typed client for §4.3. Movers derivation. Vela DigiQuant colors. Column priority.

**Files.** `components/desk/atoms/*`, `lib/desk/digicon.ts`, `lib/desk/paths.ts`, `lib/desk/movers.ts`, `lib/desk/column-priority.ts`, `components/research/VelaSpikeChart.tsx` only if the theme must be shared (prefer the new `DeskChart` and leave the spike calling it). Tests with mocked `fetch`.

**Do not edit.** Shell chrome, page routes, worker routes. Do not add `GET /movers`.

**Acceptance.**

- `getBrief` / `getPortfolio` / `getAllocations` / `getLedger` / `getPerformance` hit the paths in §4.2 and surface `ApiError` without coercing to `0`.
- Movers: a fixture with one missing mark renders `—` and still sorts the others. No invented percent.
- `DeskTable` drops columns in the holdings order as width shrinks.
- `DeskChart` candles are teal up / red down. Vertical wheel scrolls a test scroller; horizontal is not stolen.
- Loading, empty, and error stories exist for `DeskState`.
- `npm run test --workspace dashboard -- lib/desk components/desk/atoms` passes.

**Depends on.** The types in §5 (this doc). Can land before slice A.

### Slice C — Brief panes

**Goal.** Compose Brief as panes inside `DeskShell`: Decision, Signals, Book allocation, Book movers, Breaks, Gloomberg placeholder, LuxAlgo chart, Run health. Wire §4.2. Empty / loading / error match the three brief frames.

**Files.** `components/desk/panes/brief/*`, `app/page.tsx` (render the composition). May read `daily-brief-workspace.tsx` for copy and fail-closed rules; do not keep the long scrolling page as the primary view.

**Do not edit.** Portfolio pages, shell internals, worker.

**Acceptance.**

- Each pane shows its chrome path and calls the mapped function (test by mocking `lib/desk/digicon`).
- Gloomberg pane says it is a layout placeholder and does not render fake tape headlines.
- LuxAlgo pane renders `DeskChart` for the book’s focus symbol or an empty state when bars are absent.
- Provenance badges (`live marks` vs `finalized accounting`) follow CONTRACT rules.
- One viewport with the shell from A. If A has not merged, the pane module still exports a list of `DeskPaneModel` + renderers so A can mount it without a rewrite.

**Depends on.** A (mount), B (atoms + client).

### Slice D — Portfolio panes

**Goal.** Holdings, theses, tearsheet, ledger, attribution, ticker dossier as rail children and panes. Kill `PortfolioSectionNav` on these routes. Symbol pane on the selected holdings row.

**Files.** `components/desk/panes/portfolio/*`, thin wrappers in `app/portfolio/**`. Reuse tearsheet math by calling `GET /performance` rather than recomputing in the pane.

**Do not edit.** Brief, pipeline canvas, `lib/performance-ssot.ts` formulas (call them or the API; do not fork the math).

**Acceptance.**

- Holdings uses `GET /allocations`. CASH is not a holding row. Weights match the envelope rules in CONTRACT §6.2 (fail closed when marks are missing).
- Ledger uses `GET /ledger`. Realized % only with fill and cost basis.
- Tearsheet alpha and IR render `—` when overlap &lt; 20. Excess is Rp − Rb.
- Dossier is a deep link from a row, not a spine item.
- Empty holdings matches `holdings-empty.html` honesty (no estimated book).
- Existing portfolio vitest still passes or is updated in the same slice because the tab bar moved.

**Depends on.** A, B.

### Slice E — Pipeline panes

**Goal.** Fit the current pipeline glass box into one viewport: run health, canvas, node document, call trace, artifact ledger. Overflow becomes pane scroll or a rail sub-item (trace vs artifacts), not a taller page.

**Files.** `components/desk/panes/pipeline/*`, `app/pipeline/page.tsx`. Prefer wrapping `components/pipeline/*` over rewriting the canvas camera.

**Do not edit.** Pipeline topology (`lib/pipeline-topology.ts`) or Python producers.

**Acceptance.**

- The five panes from `pipeline.html` are visible without document scroll at 1280px height.
- Loading and failed-node frames (`pipeline-loading.html`, `pipeline-error.html`) map to real `run_health` states, not a spinner over stale success data.
- Node document still opens the existing document body components.

**Depends on.** A. Data can stay on current table reads if B’s `getTable` is not ready; switch to `getTable` before merge if it is.

### Slice F — Settings nest (paper only)

**Goal.** Settings children live in the rail: Desk, Brokers, Integrations, Keys, Theme, Prefs, Billing, FX stubs. Brokers stay paper. Integrations table is honest status, not new key issuance.

**Files.** `components/desk/panes/settings/*`, `app/settings/page.tsx`, `components/settings/*` only to export the existing panels into panes.

**Do not edit.** `digikey/`, `digiquant/brokers/`, billing provider calls, Alpaca live connect.

**Acceptance.**

- No control submits a live order or toggles a live broker.
- Keys remain masked (`dgk_••••`).
- Theme still writes `dashboard-theme` and follows the existing provider.
- Paper-only posture matches `settings-paper.html`: live brokers are absent.

**Depends on.** A.

### Slice G — FX Hub desk in the shell

**Goal.** Put the existing twelve-x Hub / Ideas / Watch surfaces into `DeskShell` under the FX Hub spine. Keep `lib/twelve-x/fetch.ts`.

**Files.** `components/desk/panes/fx/*`, `app/twelve-x/page.tsx` layout only.

**Do not edit.** twelve-x SQL, consensus math, or dashboard-api to proxy twelve-x.

**Acceptance.**

- An FX-hub-only invitee still sees only FX Hub (`useFxHubOnlyInvitee` in `sidebar.tsx`).
- Empty, loading, and unavailable frames exist (`fx-empty`, `fx-loading`, `fx-error`).
- Paper exposure copy does not claim a live send.

**Depends on.** A. Independent of C–F.

### Slice H — Vision banners (Strategies, Tools, rates watch)

**Goal.** Rail entries from the mock’s product block with `[wip]` / `[soon]`, disabled deploy flow, no track record, no fake catalog performance.

**Files.** `components/desk/panes/vision/*`, `app/strategy/page.tsx` (stop redirecting into a void; render the banner).

**Do not edit.** Nautilus backtest, live deploy, broker connect.

**Acceptance.**

- Strategies catalog renders an empty deployment list from a typed empty state, not mock ids S-01… as if they were live.
- Deploy controls are disabled and say they do not place an order.
- Rates watch Digest does not call `GET /portfolio`.

**Depends on.** A.

### Slice I — digiquant.io landing hero (separate from the dashboard)

**Goal.** Production craft for the digiquant-web landing hero on PR #4900. Two parts, already named by Chris:

1. **Scroll behavior is approved** at remock tip `1b2c9002d8552efa127943ea3f24e1577f3f4a47` on `task/4895-dqweb-3910-message`. Keep it. Do not redesign the wheel.
2. **Loading sequence** (Chris, refined): about **5 seconds**, hard cap **10 seconds**, from first paint to the last indicator finishing. Four beats, one motion, no long pause:
   1. Chrome — logo, text, and buttons — with a short handoff into the chart.
   2. X-axis draws left to right, the right-hand Y-axis draws bottom to top, then the grid.
   3. Candles and volume sweep left to right together. Each volume bar arrives with its candle, not as a histogram that pops in after the candles.
   4. Indicators sweep left to right. They may stream on one pass together.

This slice does not touch `apps/dashboard`, DigiCon, or the desk shell.

**Where the code already is.** `develop` still has the older mesh/graph hero (`apps/digiquant-web/components/landing/HeroMesh.tsx`). The live craft is on #4900:

| Commit | What it locked |
|---|---|
| `550235c12` | Wheel: Vela may zoom-out while the gesture is live. After settle (`WHEEL_IDLE_MS` 140) or after `ZOOM_OUT_BUDGET` 720 of downward `deltaY`, the next wheel scrolls the page. Horizontal / shift stays on the chart. At the top, scrolling up re-arms zoom. `touch-action: pan-y`. |
| `1b2c9002d` | **Approved tip for scroll.** Section rail stays hidden on the hero (band 0) and fades in once section 2 owns the viewport midpoint (`active >= 1`). |
| `bf6730256` | Earlier attempt. It waits on `COPY_DONE_MS`, grows candles with Vela `intro`, and pops SMA, then EMA, then an overlay. That is not this sequence. Keep the wheel code. Replace the build. |

The seat starts from the current #4900 head and makes the hero pass the acceptance criteria below. It does not open a second hero off `develop`.

**Files.** Only under `apps/digiquant-web`:

- `app/_bands/top.tsx` — foreground: `QuantWordmark`, `h1`, lede, both `CtaLink`s.
- `app/_chrome/QuantField.tsx` — Vela mount, indicator timing, wheel capture.
- `app/_chrome/QuantWordmark.tsx` — only if the wordmark clock must finish with the other copy.
- `app/_chrome/SectionRail.tsx` — do not change the `active >= 1` rule.
- `lib/hero-build.ts` and `lib/hero-build.test.ts` — phase durations.
- `app/globals.css` — `.hero-rise` only.

**Do not edit.** Other bands, `apps/dashboard`, `packages/design` demos, dashboard Vela spike, Coinbase provider wiring beyond what #4900 already uses (`@luxalgo/vela/providers/coinbase`). Hero candle colors stay the #4900 remock (`#3DFF9A` / `#FF5C6C`). Dashboard lock 8 (teal `#3dd6c4` / red `#e5533e`) does not retint this page.

**Feasible staged reveal (real Vela).** Vela’s `animations.intro` (`style: "grow"`) grows a series. It does not draw the x-axis, then the right price axis, then the grid, then per-bar volume. Do not fake that with a clip-path over a finished chart, and do not keep the `bf6730256` schedule (full wordmark clock, then a 520ms host fade, then three indicator pops).

Clock, from first paint. Target about 5s. Stop by 10s even if a beat wants to run long. Suggested split when the feed is healthy: chrome ~0.7s, handoff under 0.3s, axes and grid ~0.8s, candles and volume ~2s, indicators ~1.2s. Do not insert silence to pad a short beat up to 5s.

1. **Chrome, short handoff.** Wordmark, headline, lede, and both buttons enter together and stay readable. The handoff is the moment axes start, under 300ms after that group is on screen. The wordmark’s last cells may still be rising. Waiting for `BUILD_DONE_MS` (~1.9s plus cell jitter) before any axis is the long pause this beat forbids.
2. **Axes, then grid.** Mount Vela immediately so its plot rect is real, with series and volume hidden and `gridColor` transparent. Animate two strokes in that rect: the time axis left to right, then the right price axis bottom to top, then the grid lines. When the grid beat ends, turn Vela’s own grid and axes on (or leave the strokes if they match) and remove the overlay. This is construction, not a mask over candles.
3. **Candles and volume, one left-to-right sweep.** Reveal bar `i`’s candle and bar `i`’s volume rect on the same x. If `volume: true` paints the whole histogram at once, leave it off for the sweep and drive volume from the loaded bars in the same progress loop as the candles (Vela data update or a series that appends). A grow intro is acceptable only when a recording shows volume locked to each candle. No second fade of the plot.
4. **Indicators, one left-to-right sweep.** SMA 20, EMA 50, and the one overlay (Bollinger, VWAP, or SuperTrend, chosen once per reload) may draw on the same pass. Stream points from the left. `addNativeIndicator` of a complete line is a pop; use it only if that call itself draws left to right. Caption text names a layer when that layer is actually visible.

`prefers-reduced-motion: reduce`: skip the sweeps, show the finished chart once the chrome is visible, keep page scroll. If Coinbase fails, chrome still completes, the axis beat may run on an empty plot, and the caption reads chart unavailable. The feed must not block the logo. A slow feed does not add a second pause: axes and grid still run, candles start when bars arrive, and the 10s cap still applies.

**Scroll acceptance (do not regress `1b2c9002d`).**

- At the top of `#top`, the first downward wheel zoom-outs the chart. After the gesture idles 140ms, or after 720px of downward `deltaY`, the next downward wheel scrolls the page to `#dashboard`.
- Horizontal wheel and shift-wheel pan the chart and do not scroll the page.
- Scrolling back to `scrollY <= 1` and wheeling up zooms in again.
- Touch can pan the page vertically (`touch-action: pan-y` after Vela attaches).
- The left section rail is not visible and not tabbable while the hero owns the midpoint. It is visible from the dashboard band downward.
- Dashboard lock 1 does not apply: the marketing page scrolls.

**Sequence acceptance.** Record a cold load with motion allowed, `scrollY` forced to 0 (no restored scroll, no hash).

- The four beats happen in order. Chrome is on screen before the x-axis starts. The x-axis completes left to right before the right Y-axis completes bottom to top. The grid starts after that Y-axis. No candle is visible during the axis beat. Volume for bar `i` is visible only once candle `i` is, and not before. Indicators start after the candle and volume sweep has begun, and they travel left to right. SMA, EMA, and the overlay may share that sweep.
- From first paint to the last indicator finishing is about 5s and under 10s on a healthy feed. The gap between chrome settling and the x-axis starting is under 300ms. A hold on the wordmark pixel clock fails.
- There is no clip-path wipe of a finished chart, and no opacity fade of the whole plot that hides the sweep.
- **Frame.** On that raw load the chart fills the viewport. `window.scrollY` is 0. The plot is not clipped by the top bar (candles and the price axis remain visible below or above the bar; the bar does not cut them). The time axis sits on the bottom of the visual viewport. No empty band under the chart. Tolerance is 1px. Check at a desktop height (900px) and a short laptop height (700px).
- Reduced motion shows the settled chrome and a complete chart, still full-viewport, with no sweep.
- Feed failure still shows the chrome and an honest caption.
- `npm run test --workspace digiquant-web -- lib/hero-build.test.ts` passes. Durations in `lib/hero-build.ts` sum to the 5s target and stay under the 10s cap. The assertion sits inside the `describe`.

**Depends on.** Nothing in slices A–H. Depends on PR #4900 still being the showcase branch. HOLD hatch on #4900 stays; this slice pushes to that branch or a child stacked on it. It does not merge #4900.

---

## 7. How a seat proves it

From repo root, with `.venv` irrelevant for this app:

```bash
npm run test --workspace dashboard -- <slice paths>
npx tsc -p apps/dashboard --noEmit   # if the seat touches types; repo script may wrap this
```

Do not run `make test-unit` for a UI slice if it pulls Nautilus (Linux SIGABRT, #42). Dashboard vitest is the gate for slices A–H.

Slice I:

```bash
npm run test --workspace digiquant-web -- lib/hero-build.test.ts
```

Browser check for any dashboard slice that changes chrome or panes: load the local dashboard, walk the changed route, confirm one viewport, empty and error (shut the API URL or mock a 502), and `Esc` on fullscreen. Screenshot the pane, not only the first paint.

Slice I browser check is the marketing hero on the #4900 dev server. Record the load at `scrollY` 0 and confirm the four beats, the 5s target, the 10s cap, and the full-viewport frame (no top-bar clip, no bottom gap) at 900px and 700px heights. Then wheel from the hero into the dashboard band and back to the top.

---

## 8. Risks and non-goals

**Non-goals**

- Merging or restyling PR #4911. The canvas stays a visual aid.
- Rebuilding digiquant.io beyond slice I. Other #4900 bands, digithings.ai home, and digivoice stay out.
- New dashboard-api routes (`/book`, `/movers`) in the first wave.
- Replacing `getFullDashboardData()` everywhere in one PR.
- Live trading, broker adapters, order tickets, digikey, new public hostnames.
- Copying placeholder NAV, weights, or thesis ids into fixtures that tests treat as production truth. Tests use small typed fixtures.
- Rewriting twelve-x research math to match FX mock numbers.
- OpenWiki page edits.

**Risks**

| Risk | What to do |
|---|---|
| Seats restyle `PaneFrame` differently | Only slice A edits `components/desk/shell/*`. |
| Seats wire `getFullDashboardData()` into new panes | Reject in review. New panes use §4.2. |
| Mock green P&amp;L copied from `mock.css` | Lock 8. Tokens win. |
| One-viewport implemented as `overflow: hidden` that clips with no inner scroll | Acceptance fails. Inner pane scroll or a sub-route. |
| Chart wheel handler calls `preventDefault` on all wheels | Horizontal zoom dies. Only steal dominant `deltaY`. Dashboard panes and the marketing hero use different handlers. Do not share them. |
| Slice I waits out the wordmark clock, or pops volume and indicators as whole layers | Chrome hands off in under 300ms. Axes, then grid, then per-bar candle and volume, then one indicator sweep. Keep the approved wheel and section-rail code. |
| A dashboard seat “fixes” the marketing hero to teal/red or one-viewport | Lock 8 and lock 1 are `apps/dashboard`. Slice I keeps `#3DFF9A` / `#FF5C6C` and page scroll. |
| Font swap fights BLEND / CSP | `layout.tsx` comment: Geist is self-hosted for CSP. A font change needs the same treatment. Ask §9 first. |
| House book UUID treated as a secret | It is a public selector (`CONTRACT.md` §3). Still do not log service-role keys. |
| Paying user sees a half-migrated shell | Feature-flag the shell (`NEXT_PUBLIC_DESK_SHELL=1`) until A+C cover Brief, or ship A behind the flag default off. **Recommend the flag default off** until C merges, so production `/dashboard/` does not lose the current brief in a shell-only deploy. |
| `PortfolioSectionNav` tests and mobile chip row | Slice D updates them. Mobile rail must remain usable; the old hamburger regression is #1570. |
| Static export cannot read request-time env | `NEXT_PUBLIC_*` is build-time. Document that in the slice PR. Do not add a Node-only BFF for DigiCon. |

---

## 9. Human Gate questions for Chris

These do not block writing the plan. They block the seats named.

1. **DigiCon name.** Confirm §4: dashboard-api + market data + `GET /v1/tables/:table`. There is no DigiCon package on `develop`. If DigiCon is a different host, slices B–D wait.
2. **Path aliases.** Confirm chrome may say `/book` and `/movers` while the client calls `GET /portfolio` and a derived movers list. First seats will not add routes.
3. **Type.** Adopt Inter + JetBrains Mono from the mock, or keep Geist Mono and copy only hairlines, eyebrows, and density? CSP today depends on `next/font` self-hosting.
4. **Shell flag.** Agree the new shell is default-off until Brief panes (slice C) mount, so the paying dashboard does not ship an empty terminal.
5. **Rates watch and Strategies.** Agree they are banners only in this program (slice H), not a second book.
6. **Verbatim comments file** cited by the handoff is not in the repo. If Message D has a lock missing from §0, send it before slice A merges.
7. **Gloomberg / LuxAlgo.** Agree the quote board stays a labeled placeholder and the chart is Vela on digiquant bars, not a live vendor embed.

No Human Gate box in the PR template applies to this docs PR. Implement slices that touch brokers, auth, or a new hostname still stop.

---

## 10. First three slices (for One)

1. **Slice A — shell.** Unblocks every pane seat and removes the horizontal tabs. Ship behind a default-off flag unless Chris answers §9.4 with “default on.”
2. **Slice B — atoms + DigiCon client.** Unblocks real numbers. Parallel with A.
3. **Slice C — Brief.** First page that is both the remock layout and live house data (`/brief`, `/portfolio`, derived movers, Vela, run health). Gloomberg stays a placeholder on purpose.

After those three, spawn D, E, F, G together. H last.

**Slice I** (digiquant.io hero) is not one of those three. Spawn it in the same wave as A. It branches from PR #4900, keeps scroll tip `1b2c9002d`, and replaces the `bf6730256` build with the four-beat sequence (chrome, axes and grid, candles with per-bar volume, indicators) inside a full-viewport chart. About 5 seconds, under 10.
