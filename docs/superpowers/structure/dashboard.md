# digiquant dashboard — ground-up structure

Status: **structure skeleton, for owner sign-off before any refinement.**
Branch `feat/groundup-dashboard` off `origin/feat/ui-groundup` @ `d59b586f4`.
Plan: [`docs/superpowers/plans/2026-09-18-sites-rebuild-from-reference.md`](../plans/2026-09-18-sites-rebuild-from-reference.md) §0, §6, §8, §11.
Reference models: **Bloomberg and Linear** for information density and hierarchy.
Worked examples: `docs/superpowers/structure/digithings.md` (opencode.ai) and
`docs/superpowers/structure/digiquant.md` (gloom.sh).

This is the checklist the owner signs off **before** a refinement pass adds design
detail. It is deliberately plain: structure and content only, kit primitives at
their default dress, no bespoke visual design. "This is what each route is made
of, in order, and why" — nothing about how it looks yet.

The dashboard is an **operator** surface, not a marketing site, so the "most
relevant first, honest about results" doctrine is the organising rule: lead with
what the operator actually decides on, state plainly where data is absent or
stale, and let a route that shows nothing say why.

---

## 0. Method (what "ground-up" means here)

1. **Existing pages were a content source, not a design source.** The route set,
   the data adapters and the product surfaces were carried over; the *page
   grammar* (page container, header, section rhythm) was written fresh. No old
   `font-display text-2xl tracking-tight` header block, no `font-mono text-[11px]
   uppercase` eyebrow, no `backdrop-blur` chrome survives in the layer this pass
   owns.
2. **Plain structure first.** Each route is a page container, an optional page
   header (one eyebrow, one h1, one lede — never two of any), and its product
   surface. Hierarchy is h1 → h2.
3. **No app-local design.** No new app-local components, no new app-local CSS
   class families, no colour or type decisions in the pages. The only new
   structural file is `components/layout-constants.ts` (extended — the
   dashboard's `lib/layout.ts` equivalent): `PAGE`, `PAGE_HEADER`, `EYEBROW`,
   `H1`, `LEDE`, `SECTION`, `SECTION_HEAD` — token utilities only. The existing
   `SUBPAGE_MAX` container and `mainOffsetClass` offset stay in the same module.
4. **Utilitarian simplicity.** Flat surfaces, small mono type, kit primitives at
   default dress. The chrome lost its backdrop blur, its hand-rolled
   `rounded-none border border-hair` button dress, its `qn-sidebar-*` /
   `acct-session-*` app-local families and its oversized brand row. If a
   flourish did not earn its place it was cut (§1).
5. **Honesty and correctness constraints do not relax.** The DB gate states
   *why* live data is unavailable (unconfigured vs unreachable); the stale-vs-live
   contract (`lib/live-valuation.ts`, `lib/snapshot-staleness.ts`,
   `lib/performance-ssim.ts`) and every badge render point are untouched; every
   performance figure keeps its in-sample/backtest or live-marks label; nothing
   promises live trading.
6. **The product surfaces are kept whole.** The dashboard's structure lives
   mostly *inside* its product components (the Brief workspace, the pipeline
   canvas, the tearsheet, the FX Hub suite, the settings tabs). Rebuilding their
   internals is a product job, not this structural pass — exactly as the
   digiquant.io pass kept the tearsheet and the two live panels. §2 marks which
   blocks are kept surfaces and which were re-composed.

The kit surface used by the rebuilt layer: `Button`, `Tooltip`, `Separator`,
`Alert`, `EmptyState`, `Skeleton`/`SkeletonGroup`, `AuthCard`, `Card`, `Table`,
`Tabs` (chrome and content). The `lib/layout.ts`-equivalent strings live in
`components/layout-constants.ts`.

---

## 1. Global chrome (every route)

- **Sidebar** — `components/sidebar.tsx`, rebuilt. A fixed, out-of-flow rail on
  desktop and a drawer under `md`. The owner spine is `NAV` (`lib/nav.ts`:
  Brief / Portfolio / Pipeline / FX Hub) plus the flat external Gloomberb
  Terminal entry (#4204) and `SidebarSettings`. `aria-current` is set from the
  canonical `navItemForPath` — a live non-destination (`/why`) resolves to
  `null`, never a silent collapse onto Pipeline.
- **Mobile app bar** — `components/mobile-app-bar.tsx`, rebuilt. The small-screen
  counterpart of the rail: reserved row, brand, nav toggle, command-palette
  trigger. Same `min-h-[72px]` as the sidebar header.
- **Frame** — `components/app-frame.tsx`, **kept**. It owns the single `<main>`
  landmark and the explicit desktop offset (`mainOffsetClass`), asserted by
  `components/app-frame.test.tsx`. This is the critical #4426 regression guard
  and was not touched.
- **DB gate** — `components/db-unavailable.tsx`, **kept** (only its container
  string moved to `PAGE`). Honest, styled, reasons distinguished; static and
  DB-exempt routes stay readable. The gate exempt set is derived in `lib/nav.ts`
  (`DB_EXEMPT_PREFIXES` + `LEGACY_REDIRECTS`), pinned by `lib/nav.test.ts`.
- **Skip link / theme** — unchanged. `AuthGate` still emits the real shell during
  prerender so `check:static-export` sees each route's `<h1>`.
- **Command palette, digichat popup, auth screens** — kept (functional overlays /
  auth surfaces; `LoginScreen` already composes the kit `AuthCard`).

### Cut globally from the old chrome

| Cut | Where it lived | Why |
|---|---|---|
| `backdrop-blur-md` + `bg-surface/95` chrome | `sidebar.tsx`, `mobile-app-bar.tsx` | glass on an operator surface; flat `bg-surface` is the new default |
| hand-rolled `rounded-none border border-hair` button dress | every sidebar/mobile control | the kit `Button` owns its dress; the app was re-specifying it |
| `qn-sidebar-link-active` / `qn-sidebar-label` families | `sidebar.tsx` | app-local class families in a page file; replaced by token utilities |
| `acct-session-rail` / `acct-session-email` / `acct-session-meta` | `sidebar.tsx` | same — an app-local identity family for two text nodes |
| `font-display text-xl/2xl font-normal tracking-tight` h1s | page headers, ledger, settings | the old display grammar; replaced by `H1` (small mono) |
| `font-mono text-[11px]/[0.72rem] uppercase` eyebrows | page headers | replaced by `EYEBROW` |
| bordered collapse-toggle box + double-rendered header | sidebar header | chrome decoration; the toggle is a default kit icon button |

---

## 2. Route by route

24 route files (`app/**/page.tsx`), counted from disk and pinned by
`app/route-smoke.test.ts` and `lib/route-map.test.ts`. Section counts are content
blocks excluding chrome.

### `/` — Brief (1 composition, 4 internal sections)

| # | Section | Shows |
|---|---|---|
| 1 | Daily investment brief | `DailyBriefWorkspace` — command, scoreboard, monitor, book |

The route's job is the operator's morning decision: the regime/confidence
command line, the scoreboard (since-inception, day, vs-benchmark, alpha, IR,
invested, with live-marks badges when the overlay is on), the monitor (latest
decision, signals to resolve, pipeline health), and the book (allocation and
movers). **Kept product surface** — the page is the workspace; this pass moved
the page container to the shared `PAGE` grammar and left the workspace internals
for refinement. **Content source:** `app/page.tsx` + `components/today/`.

### `/portfolio` (1 composition, 2 tabs)

Section nav (Holdings · Theses · Tearsheet · Ledger · Attribution) + a page
header (`Portfolio`) + the active tab (`AllocationsTab` | `ThesesTab`).
**Re-composed:** the route previously rendered no `<h1>` at all; the page header
was added. The tab bodies are kept product surfaces. **Content source:**
`components/portfolio/PortfolioShellInner.tsx`.

### `/portfolio/attribution` (1 composition, 3 views)

Section nav + page header (`Attribution`) + the entitled workspace (Decision
effectiveness · Book attribution · Audit). Tier-gated `house_weights_nav`
(fail-closed). **Re-composed:** the sr-only h1 became a real page header.
**Content source:** `components/portfolio/AttributionWorkspace.tsx`.

### `/portfolio/ledger` (2 blocks)

Page header (`Ledger`) + the position-event activity table, or the honest empty
(`No position events recorded yet.`) or the tier lock (`LockedSurface`,
fail-closed before loading chrome). Private append-only ledger tables are
explicitly out of view. **Re-composed** onto the shared grammar; the fail-closed
tier gate and the "public event stream only" statement are kept. **Content
source:** `app/portfolio/ledger/page.tsx`.

### `/portfolio/performance` (1 composition)

Section nav + the persisted performance tearsheet (cumulative returns and stored
holding-attribution windows, via the same `getPerformanceBundle` NAV adapter as
the Brief). Tier-gated `house_weights_nav`; the `.ts-page` print geometry is
kept. **Kept product surface.** **Content source:**
`components/tearsheet/DashboardTearsheetView.tsx`.

### `/portfolio/period` — retired (redirect)

Period inspect was retired (#3060); the route redirects to
`/portfolio/performance`. See §6.1.

### `/portfolio/theses` — query-param detail (1 composition)

`?thesis=<id>` renders the thesis detail view (criteria, story spine, holdings
expressing it, provenance); no param falls through to the hub redirect
(`/portfolio?tab=theses`). A single static route reading a client param is
deliberate (#1760: a dynamic segment 404s every thesis created since the deploy).
**Kept product surface.** **Content source:**
`components/portfolio/theses/ThesisDetailPageInner.tsx`.

### `/portfolio/tickers` — query-param dossier (1 composition)

`?ticker=<symbol>` renders the ticker dossier (analyst cards, conviction
history). Same static-route reasoning as `/portfolio/theses` (#1562). **Kept
product surface.** **Content source:**
`components/portfolio/tickers/TickerDossierView.tsx`.

### `/pipeline` (3 blocks)

Command band (day selector, artifact/call-trace counts, run date) above the
zoomable workflow canvas, plus the node detail panel. The route is genuinely
DB-exempt (it reads run telemetry and falls back to the expected topology when
there is no run). **Kept product surface**; the command band is product, not
decoration. The sr-only `<h1>` is pinned by `app/pipeline/page.test.ts` and
`check:static-export`. **Content source:** `components/pipeline/`.

### `/why` (3 tabs)

The reasoning surface: The read · Deliberations · Documents. **Kept product
surface.** **Content source:** `components/why/why-client.tsx`.

### `/house` (3 panels)

Corpus · Book · Profile — the shared-corpus and house-identity contracts. DB-exempt
because the corpus sample keys fail soft. **Kept product surface.** **Content
source:** `components/house/`.

### `/twelve-x` (tab bar + 1 active tab)

The FX Hub suite: Today · Matrix · Events · Consensus · Trades · Track record ·
How it works · Briefs · Ideas. Product-gated (`fx_hub`) and DB-exempt (reads its
own research feed). **Kept product surface.** **Content source:**
`components/twelve-x/`.

### `/settings` (3 blocks)

Page header (`The desk, not the product.`) + the tier-visible tab strip
(Profile · Pipeline · Keys · Brokers · Notifications · Billing · About) + the
active tab body, or the FX-Hub-only account variant. **Re-composed** onto the
shared grammar; tab visibility and deep-link hydration are kept. **Content
source:** `app/settings/page.tsx` + `components/settings/`.

### `/settings/brokers/callback` (2 blocks)

Page header (`Broker connect`) + the Alpaca OAuth exchange status line. The
client secret never enters this page. **Re-composed** onto the shared grammar.
**Content source:** `app/settings/brokers/callback/page.tsx`.

### `/login`, `/signup` (1 block)

The kit `AuthCard` (compact): mark, email/password, OAuth row, switch link.
`/signup` opens the same card in create-account mode. **Kept.** **Content
source:** `components/login-screen.tsx`.

### `/auth/callback` (1 block, no chrome)

PKCE callback settle — runs even with a session; `AuthGate` deliberately renders
no shell here. **Kept.** **Content source:** `app/auth/callback/`.

### Retired aliases (redirect, no content sections)

`/architecture`, `/library`, `/observability`, `/performance`, `/research`,
`/strategy`, `/system` — plus `/portfolio/period` above. Each rides the shared
`legacy-spa-redirect` grammar and preserves its deep-link params
(`/library?date=…&docKey=…` → the pipeline node; `/strategy?thesis=…` → the
thesis detail; `/research?date=…` → the pipeline day). They are **not nav
destinations** and are pinned as redirects by `lib/route-map.test.ts`. See §6.1.

---

## 3. Plumbing retained (untouched)

- `next.config.mjs`: `output: "export"`, `basePath: /dashboard`, `trailingSlash`,
  `transpilePackages`, `images.unoptimized`.
- `public/_headers` CSP (including the `/dashboard*`-scoped digichat frame-src).
- `app/manifest.ts`, `app/robots.ts`, `app/sitemap.ts`.
- The stale-vs-live contract and its render points: `lib/live-valuation.ts`,
  `lib/snapshot-staleness.ts`, `lib/performance-ssim.ts`, the `as-of` badge,
  `components/shared/`.
- The DB gate, the auth gate (`lib/auth-gate.tsx`), the frame
  (`components/app-frame.tsx`), `mainOffsetClass`.
- The whole `lib/**` data layer (queries, snapshot fetch, twelve-x, settings API,
  entitlements, portfolio/ticker/thesis derivations) and every product component
  under `components/**` not named above.
- `app/globals.css` kit imports and the `ts-*` print geometry.

---

## 4. Content provenance (single source of truth)

| Content | Source |
|---|---|
| Nav spine + DB-exempt set + legacy redirect registry | `apps/dashboard/lib/nav.ts` |
| Brief data | `lib/dashboard-context.tsx` + `lib/queries.ts` |
| Performance SSOT | `lib/performance-ssot.ts` + `lib/observability-queries.ts` |
| Portfolio / thesis / ticker derivations | `lib/portfolio-*`, `lib/thesis-*`, `lib/twelve-x/*` |
| Pipeline topology + telemetry | `lib/pipeline-topology.ts`, `lib/pipeline-graph-data.ts` |
| Settings schemas | `lib/settings/schemas/*.json` |
| All prose/claims | the existing `app/**` pages (carried verbatim) |

No claim was added or reworded in this pass. Wording changes are content-audit
workstream C, not structure.

---

## 5. Verification

Run on `feat/groundup-dashboard`:

```
python3 scripts/check_frontend_canon.py                  # frontend canon guard: clean
cd apps/dashboard && npx tsc --noEmit                     # 67 errors, ALL in *.test.ts (pre-existing; 0 in app source)
cd apps/dashboard && npx vitest run                       # 219 files: 217 passed, 1 failed, 1 skipped; 1743 tests passed, 2 failed (pre-existing app-shell-context)
cd apps/dashboard && npx next build --webpack             # exit 0, 27 static pages
cd apps/dashboard && npm run check:static-export          # "passed (426 route artifacts)"
cd apps/dashboard && npx vitest run app/route-smoke.test.ts lib/route-map.test.ts   # 12 passed
```

**24-route smoke** (dev server from `apps/dashboard`, `curl -L`, `/dashboard`
basePath, `trailingSlash`): every one of the 24 routes → **200**; a bogus path →
**404**.

**Dark + light, desktop (1440×900) and narrow (390×844):** `--bg` resolves to
`#0a0e0c` dark / `#fbfbf9` light, `body` background follows, `#app-sidebar-nav`
renders, the mobile app bar renders under `md`, exactly **one** `<main>`, no
horizontal overflow, and `main` carries the explicit `padding-left: 260px`
offset. Verified on `/`, `/pipeline`, `/portfolio`, `/portfolio/ledger`,
`/settings`.

**Screenshots** (representative set, saved under
`/Users/chrisstefan/Code/digithings/.playwright-mcp/`):
`groundup-home-gate-{light,dark}-1440`, `groundup-pipeline-{light,dark}-1440`,
`groundup-settings-light-1440`, `groundup-settings-narrow-light-390`,
`groundup-home-narrow-dark-390`.

Note: in a build without `NEXT_PUBLIC_SUPABASE_*` (this dev run), gated routes
render the honest DB-unavailable panel — which is the correct behaviour and what
the home screenshots show. `/pipeline`, `/settings`, `/twelve-x` and `/house`
render their real surfaces.

---

## 6. Decisions, cuts and open questions (read this before sign-off)

1. **The eight retired aliases stay redirects, not new pages.** The brief says
   "one page per route" and "no silent redirect"; this pass keeps
   `/architecture`, `/library`, `/observability`, `/performance`, `/research`,
   `/strategy`, `/system` and `/portfolio/period` as client redirects, because
   they are **load-bearing deep-link resolvers**, not dead stubs:
   `/library?date=…&docKey=…` maps to a specific pipeline node,
   `/strategy?thesis=…` to a thesis detail, `/research?date=…` to a pipeline day.
   Making them static pages would break those links. They are also the #4426
   route-integrity mechanism: `lib/route-map.test.ts` asserts the redirect
   registry matches the routes that actually redirect, and that no *advertised*
   nav destination is one. **If the owner wants them to be honest retirement
   pages instead**, the change is: drop the route from `LEGACY_REDIRECTS`
   (`lib/nav.ts`), replace its `page.tsx` with a static header + "moved to X"
   panel, and update `lib/nav.test.ts` + `lib/route-map.test.ts` — but the
   deep-link params must be carried by the panel's links, and the
   `legacy-spa-redirect` query-preservation tests move to the new panels.
2. **The product surfaces are kept, not rebuilt.** The Brief workspace, the
   pipeline canvas, the tearsheet, the FX Hub suite, the settings tabs and the
   portfolio/ticker/thesis views still carry their own internal `font-display`
   headers and `font-mono` micro-labels. Rebuilding those internals is the
   refinement pass (or a dedicated product pass); this pass owns the shell, the
   page grammar and the routes that had no header at all. Stated plainly so it is
   not mistaken for "the old design survives by accident".
3. **`/portfolio` had no `<h1>`.** It rendered only the section nav + tabs. The
   page header was added; the tab bodies were left alone.
4. **The DB gate is untouched by design.** #4426's gate and #4452's narrow-width
   contract (fluid card, wrap-safe message) are the honesty surface; only the
   container string moved. If the gate should be restyled, that is a refinement
   decision, and it must keep the `data-db-status` reason distinction.
5. **`tsc` is red on the base branch** — 67 errors, every one in a `*.test.ts`
   file (fixtures missing required fields, a removed export, tuple types). This
   pass added zero errors to `app/`/`components/`/`lib/` source. Left as-is: the
   rebuild did not change those contracts.
6. **Two known-failing dashboard tests** (`components/app-shell-context.test.tsx`,
   `localStorage.clear is not a function`) are pre-existing and unchanged by this
   pass: 2 failed tests before and after.
7. **Refinement pass** — the design detail (type scale, spacing, the kit's
   richer primitives, motion) lands here, on this approved structure.
