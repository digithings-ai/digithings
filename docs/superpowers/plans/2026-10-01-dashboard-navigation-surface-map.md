# digiquant dashboard — navigation and surface map (lane 3/3)

**Status:** plan lock only. No app UI, no static HTML, no route additions in this document's PR.

**Date:** 2026-10-01

**App:** `apps/dashboard`. Browser prefix `/dashboard/` (`basePath`). Paths below are app-relative.

**Reads with this map:**

- [docs/vision/dashboard.md](../../vision/dashboard.md) — operator surface for research, portfolio, and execution
- [docs/vision/digiquant.md](../../vision/digiquant.md) — research, then paper, then a human gate before live
- [ADR-0026](../../adr/0026-retire-olympus-atlas-hermes-kairos.md) — job words, not retired proper nouns
- [Settings IA](../../agent-backlog/execution-tenancy/SETTINGS-IA.md) — omit-by-tier tabs (this map does not reopen that matrix)

This is the information architecture for a ground-up dashboard. Current pages are the behavior inventory. They are not a layout to restyle.

---

## 0. Locked canon

| Lock | Rule |
|---|---|
| Product vs showcase | The dashboard is the product. `apps/digiquant-web` is the showcase. digithings.ai is marketing. Neither showcase nor marketing owns builder, journal, tools, settings, brokers, calendars, pipelines, profiles, or integrations. |
| Book | Research and the paper book ship first. Live venue cutover stays a human gate. |
| Names | Product names are digithings and digiquant, always lowercase in prose. Jobs are research, portfolio, and execution. Do not put olympus, atlas, hermes, or kairos in nav, titles, or empty-state copy. |
| Strategies on the showcase | `apps/digiquant-web` `/strategies` and `/strategies/[id]` are showcase tearsheets. They are not the strategy builder and not this app's strategy library. |
| `/strategy` in the dashboard | Redirect only, to portfolio theses. Never label it Builder. |
| Access | The app is access-gated. Anonymous diagnostics stay removed. |
| Clients | No private-client names in chrome, empty states, or coming-soon copy. |
| Charts | One chart surface: LuxAlgo. One symbol surface: Gloomberb. No competing chart stack. See [§7](#7-chart-and-symbol-panes). |
| #4761 | Epic [#4761](https://github.com/digithings-ai/digithings/issues/4761) Phase 3 is the house-run move onto Cloudflare Containers (`standard-2`), documented in [the house-run plan](./2026-09-30-digiquant-house-run-phase3.md) and [the Phase 4 GHA cutover plan](./2026-10-01-digiquant-phase4-gha-cutover.md). That phase number is not this dashboard's build order. |

---

## 0.1 Web craft locks

These bind phase B mockups and phase C implementation. This PR still ships no CSS and no HTML.

| Lock | Rule |
|---|---|
| Instrument, not SaaS glass | Dense operator surface: hairline structure, literal figures, no glass blur, no marketing hero, no bento, no gamified scores. |
| Literal sidebar labels | The words in [§2](#2-navigation). No metaphors ("Desk", "Cockpit", "Alpha") as the nav label. |
| Sticky in-page section tabs | Portfolio, House, and Settings keep their section tabs stuck to the top of the page column while the body scrolls. Tabs are not a second sidebar. |
| Settings gates | A tab the effective tier cannot use is omitted. It is not a locked card, not an upgrade teaser, and not a greyed tab. |
| Honest empty | Missing data is an empty state or an em dash. Never `0` for an unknown mark. Never sample rows. |
| Embed panes | A price chart is a LuxAlgo pane. A symbol terminal is a Gloomberb pane. Both sit in the page. They are not a new chart library and not a trip out to the showcase. |
| Soon-nav | Do not grey a future destination into the sidebar. Omit it. If a control must stay on a page the user is already on, it is disabled and carries a status chip (`Paper`, `Not available`). It does not navigate. |
| P&L | No fake live P&L. Paper figures come from the accounting NAV. A live mark, when the feed actually has one, is badged `live` or `close`. Unavailable is an em dash. |
| Type and color | Single-color black craft and the type pair (Inter, JetBrains Mono) follow the digiquant-web craft lane later. Not specified here. |

**Gloomberb vs gloom.sh.** Gloomberb is the symbol terminal and the bar source behind LuxAlgo panes (`gloomberbTickerUrl`, Vela bars `source: gloomberb`). gloom.sh is a visual reference for a later craft lane. It is not a chart engine and not a third embed.

---

## 1. Lab product spine

Shipped destinations. Everything else in [§5](#5-coming-soon-guards) is omitted from navigation until it is real.

| # | Surface | Route | Role |
|---|---|---|---|
| 1 | Brief | `/` | Daily decision, KPIs, paper-book glimpse |
| 2 | Holdings | `/portfolio` (`?tab=holdings`) | Paper book and exposure |
| 3 | Theses | `/portfolio?tab=theses` and `?thesis=` | Conviction list and detail |
| 4 | Tearsheet | `/portfolio/performance` | NAV and returns, single source of truth |
| 5 | Ledger | `/portfolio/ledger` | Paper fills and book events |
| 6 | Attribution | `/portfolio/attribution` | Whether decisions worked |
| 7 | Pipeline | `/pipeline` | Glass box from research through commit. Sole reasoning hub |
| 8 | House | `/house?tab=corpus\|book\|profile` | Corpus, book, and profile chrome |
| 9 | Settings | `/settings` | Profile, Pipeline, Keys, Brokers, Notifications, Billing, About |
| 10 | Auth | `/login`, `/signup`, `/auth/callback` | Session. Outside the data gate |
| 11 | Ticker dossier | `/portfolio/tickers?ticker=` | Optional early deep link from Brief and Holdings. Not a nav item |

Portfolio sections 2–6 share one sticky tab bar. House sections share one sticky tab bar. Settings sections share one sticky tab bar.

**Arc the spine already encodes:** Brief → book (holdings, theses, tearsheet, ledger, attribution) → drill-down (thesis detail, ticker dossier, pipeline node). Journal and settings sit later in the product arc; journal is still a guard ([§5](#5-coming-soon-guards)), settings is shipped.

**Not the spine:**

- Strategy builder, journaling, tools, calendars, a standalone integrations hub, live execute, embedded digichat. The dashboard owns them when they exist. They are not routes yet.
- FX Hub (`/twelve-x`). Omit unless this session's invite scope includes the `fx_hub` grant.
- `/why`. Pipeline is the reasoning hub. Keep `/why` only if Chris explicitly keeps the page; otherwise it redirects to `/pipeline` and stays out of the nav.
- Showcase strategies on digiquant-web.

---

## 2. Navigation

### 2.1 Primary

Literal labels, in this order. Settings is pinned to the account end of the sidebar, not dropped into the work list.

| Label | Href | Active when |
|---|---|---|
| Brief | `/` | path is `/` |
| Portfolio | `/portfolio` | path is `/portfolio` or `/portfolio/*` except the ticker dossier, which still counts as Portfolio |
| Pipeline | `/pipeline` | path is `/pipeline` |
| House | `/house` | path is `/house` |
| Settings | `/settings` | path is `/settings` or `/settings/*` |

Five items. Do not add Builder, Journal, Tools, Live, Why, or FX Hub to this list under a grey style.

Command palette and mobile use the same five labels plus the deep links in [§2.3](#23-deep-links). They do not grow a second taxonomy.

### 2.2 Secondary (sticky in-page tabs)

**Portfolio** — `aria-label` "Portfolio sections":

| Label | Href |
|---|---|
| Holdings | `/portfolio` |
| Theses | `/portfolio?tab=theses` |
| Tearsheet | `/portfolio/performance` |
| Ledger | `/portfolio/ledger` |
| Attribution | `/portfolio/attribution` |

Ticker dossier does not add a sixth tab. It shows the Portfolio bar with Holdings current and a dossier title in the page.

**House** — `aria-label` "House sections":

| Label | Href |
|---|---|
| Corpus | `/house?tab=corpus` |
| Book | `/house?tab=book` |
| Profile | `/house?tab=profile` |

**Settings** — `aria-label` "Settings sections". Render only the tabs [§4](#4-settings-taxonomy) allows for the effective tier. Query `?tab=` wins over hash `#`. A gated or unknown tab is ignored; the page opens on the first visible tab.

**Pipeline** has no section tabs. Stage and node are deep links on one canvas (`?date=&stage=&node=`).

**Brief** has no section tabs. Blocks stack on one page.

### 2.3 Deep links

| From | To | Params |
|---|---|---|
| Brief KPI / book glimpse | Holdings, Tearsheet, Ledger, Theses | existing book date when the brief has one |
| Brief signal | Thesis detail, or the pipeline digest node when Pipeline is in the nav | `?thesis=`, or `node=digest&stage=synthesis` at Desk and above |
| Holdings row | Ticker dossier | `/portfolio/tickers?ticker=` |
| Holdings row | Gloomberb pane | symbol pane for that ticker ([§7](#7-chart-and-symbol-panes)) |
| Thesis vehicle | Ticker dossier and Gloomberb pane | same |
| Theses list | Thesis detail | `/portfolio/theses?thesis=` (static export: one page, query param, not a dynamic segment) |
| Tearsheet | Holdings / Ledger | same book date |
| Pipeline node | Document in the node detail | `?date=&stage=&node=` |
| Any book page | Pipeline for that run date | date preserved |
| Settings CTAs | A visible settings tab | `#billing`, `#notifications`, `#about`; Desk adds `#brokers`; Studio+ adds `#profile`, `#pipeline`, `#keys` |
| Stripe return | Billing | `?tab=billing` or `?checkout=success\|cancel` |
| Command palette | Thesis, ticker, pipeline node | same hrefs as the rows above |

Auth routes and `/settings/brokers/callback` (Alpaca paper OAuth return) are not palette entries.

### 2.4 Data gate

When the book backend is down:

| Stays up | Shows the honest unavailable panel inside main |
|---|---|
| Pipeline (run health must remain reachable), Settings, House static chrome, Auth, broker OAuth callback | Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, ticker dossier |

The panel says live data is temporarily unavailable and offers reload. It does not say the app reconnects itself. It does not invent a flat P&L.

Today's code still gates Pipeline (`isDbExempt('/pipeline')` is false). Phase C makes Pipeline exempt. This plan does not change that code.

### 2.5 Legacy redirects

Keep these working so old links do not 404. Do not put them in the nav. Do not describe them as products.

| Route | Lands on |
|---|---|
| `/strategy` | `/portfolio?tab=theses`, or thesis detail when `?thesis=` is set. **Not the builder.** |
| `/system`, `/architecture`, `/observability` | `/pipeline` (query preserved where it already is) |
| `/library`, `/research` | Pipeline node or pipeline (date / doc key preserved) |
| `/performance` | `/portfolio/performance` |
| `/portfolio/period` | `/portfolio/performance` |
| `/why` | `/pipeline` unless Chris keeps the page |

`/research/vela-spike` stays a lab route, off the nav. It is the existing LuxAlgo embed spike, not a Tools product.

---

## 3. Surface catalog

**Data words**

| Word | Means |
|---|---|
| wired | Reads a store or API that exists today |
| wired-partial | Some blocks are wired; the rest is static or fail-soft |
| static | Declared chrome, not a saved user record |
| local | Browser only |
| coming-soon | Honest guard on a shipped page. No sample data |
| omit | Not rendered for this viewer |

Shared loading, empty, and error behavior is [§6](#6-states). A row below only adds what is specific to that surface.

### 3.1 Brief — `/`

**Purpose.** The morning decision: what the run concluded, the paper book's headline figures, and a way into the book.

**Content blocks**

| Block | Data | Notes |
|---|---|---|
| Decision / daily read | wired | Research digest and run record for the book date |
| KPI strip | wired | Accounting NAV (`public_accounting_nav_history`), same series as Tearsheet. Provenance badge `live`, `close`, or `unavailable` |
| Book glimpse | wired | Allocation and movers. Names and weights the tier may see |
| Signals to resolve | wired | Link to a thesis. Link to the pipeline digest node only when Pipeline is in the nav (Desk and above) |
| What could break the view | wired | Risks from the run, not a scored game |
| Run health | wired | Research-run diagnostics for the book date. Failure is a quiet miss, not a zero book |

**Settings that affect it.** Notifications do not change the page. Pipeline watchlist and themes (Studio+) change later runs, not the historical brief already on screen. Billing does not change figures.

**States.** Loading: page skeleton. Error or no snapshot: empty state, no zero KPIs. Unavailable mark: em dash. Backend down: unavailable panel ([§2.4](#24-data-gate)).

**Tier.** Observer: digest conclusions and a names-only glimpse. Brief and above: house weights and NAV. Do not pad a teaser with fake weights.

### 3.2 Holdings — `/portfolio`

**Purpose.** The paper book: weights, positions, exposure. Paper fills are first-class; the reconciliation strip links to Ledger.

**Content blocks**

| Block | Data |
|---|---|
| Command band (book date, reconciliation) | wired |
| Allocations and positions | wired |
| Symbol pane affordance per ticker | wired as a Gloomberb target; phase C hosts it as an embed pane ([§7](#7-chart-and-symbol-panes)) |
| Row link to ticker dossier | wired route, optional early |

**Settings.** House book is the default. Studio+ profile exclusions and watchlist change overlay work; they do not relabel the house book as the user's live account. Broker connection does not turn this table into a live brokerage blotter.

**States.** Empty book: honest empty, no sample positions. Cash is cash, not a hole. Backend down: unavailable panel.

### 3.3 Theses — `/portfolio?tab=theses`

**Purpose.** Conviction spine for the paper book.

**List blocks:** thesis rows (name, id, status, vehicles). **Detail** (`/portfolio/theses?thesis=`): command band, thesis statement, validity and exit, bull/bear and deliberation summary, vehicles with weights, links to ticker dossier and pipeline nodes that produced the thesis.

| Block | Data |
|---|---|
| Thesis list and detail | wired from the book snapshot |
| Vehicle weights | wired |
| Gloomberb symbol pane | embed target, same rule as Holdings |
| Missing thesis id | empty state that names the id and returns to the list |

**Settings.** Same as Holdings. Profile exclusions can explain why a name is absent; they do not invent a thesis.

**States.** No `?thesis=`: list, or the existing redirect onto `?tab=theses` from the detail route when no id is present. Unknown id: empty, not a blank dossier. Backend down: unavailable panel. Detail stays a query param under static export (one page, any id).

### 3.4 Tearsheet — `/portfolio/performance`

**Purpose.** NAV and returns for the paper book. Single source of truth with Brief KPIs. In-sample language stays when the series is in-sample. This is not a showcase strategy tearsheet and not a live P&L.

**Content blocks**

| Block | Data |
|---|---|
| NAV headline and period returns | wired, accounting NAV |
| Drawdown and related return figures | wired from that same series |
| Honesty line | static copy bound to the series (paper, in-sample when that is what the run is) |
| Chart pane | only if a pane is required: LuxAlgo embed of this series ([§7](#7-chart-and-symbol-panes)). The table and KPI remain the source of truth |

**Settings.** None change the formula. Date deep links select a window; they do not switch the series to a broker feed.

**States.** No history: empty, not a flat zero curve. Unavailable point: em dash, gap, or omitted point — never a fabricated live print. Backend down: unavailable panel.

### 3.5 Ledger — `/portfolio/ledger`

**Purpose.** Paper fill and book-event stream. This is the fills surface.

**Content blocks**

| Block | Data |
|---|---|
| Event table (ticker, date, kind, size) | wired |
| Row detail | wired |
| Link back to holdings | wired |

**Settings.** Broker paper fills in Settings → Brokers are the connection's fill list. This ledger is the book. Do not merge them into one "live executions" table.

**States.** No events: honest empty. Backend down: unavailable panel.

### 3.6 Attribution — `/portfolio/attribution`

**Purpose.** Did the decisions help? Position contribution and recommendation quality against the paper book. Not a leaderboard.

**Content blocks**

| Block | Data |
|---|---|
| Contribution / decomposition | wired |
| Decision quality | wired where a scored decision exists |
| Link to the thesis or ledger row | wired |

**Settings.** None.

**States.** No scored decisions in the window: empty. Do not show a zero-alpha trophy. Backend down: unavailable panel. One `<main>` for the page; the shell already provides it.

### 3.7 Pipeline — `/pipeline`

**Purpose.** Sole reasoning hub. Glass box from inputs through commit for one run date. `/why` is not a second hub.

**Content blocks**

| Block | Data |
|---|---|
| Canvas | wired topology: Inputs → Research → Synthesis → Selection → Decision → Learning |
| Command band (date, run health) | wired |
| Node detail | wired when the node has a document. State-only nodes do not open an empty essay |
| Artifact ledger and trace ledger | wired |
| Accessible title | "Pipeline" (the visible band can stay compact; the page still has one heading for the export) |

Stage labels stay the job words already on the graph: Preflight, Attention plan, Alt-data, Institutional, Macro, Asset-classes, Sectors, Consolidate bias, Daily digest, Thesis framing, Screener, Analysts, Deliberation, PM direction, Risk sizing, Commit, Beliefs fold.

**Settings.** Studio+ Pipeline tab (watchlist, themes, research budget) changes what later overlay runs ask for. It does not edit the house graph. The house run stays immutable.

**States.** No run for the date: empty canvas with the date, not a fake graph. Inputs with no call telemetry: typed gap, not a failure badge. Backend down: this page stays up and shows its own empty or stale run state ([§2.4](#24-data-gate)).

### 3.8 House — `/house`

**Purpose.** Read-only identity for the shared corpus, the house paper book, and the house profile. Not Settings.

**Content blocks**

| Tab | Data |
|---|---|
| Corpus | wired-partial. Sample keys from documents when present; fail soft when absent. Key shape `theme:`, `asset:`, `segment:` |
| Book | static identity: digithings house ETF paper book, always-on, not a live book |
| Profile | static pins until ProfileConfig is real ([§5](#5-coming-soon-guards)). Read-only. Editable posture lives in Settings → Profile for Studio+ |

**Settings.** Settings → Profile is the editable overlay. House → Profile does not duplicate that form.

**States.** Corpus with no keys: empty, not invented documents. Book and profile render from the static contract even when the book DB is down.

### 3.9 Settings — `/settings`

**Purpose.** Account and workspace controls. Tabs and gates: [§4](#4-settings-taxonomy).

**Per tab**

| Tab | Purpose | Blocks | Data | States |
|---|---|---|---|---|
| Profile | Investment posture and exclusions | Posture, exclusions, save | wired-partial for Studio+ (`profile` tip). Full overlay ProfileConfig is the [§5](#5-coming-soon-guards) guard, not a fake form | Load error is an error, not an empty profile. Below Studio: tab omitted |
| Pipeline | Overlay research knobs | Watchlist, themes, research budget | wired for Studio+ on the same tip. Does not edit the house run | Empty watchlist is a real empty, not a sample list. Below Studio: omitted |
| Keys | BYOK provider keys | Provider choice, seal, revoke, fingerprint | wired for Studio+. Secret is not shown again after save | Load error. No free-form model-id picker. Below Studio: omitted |
| Brokers | Paper connections | Alpaca paper OAuth, IBKR beta key, revoke, paper fills | wired for Desk+. Paper only | Live execute is not a button ([§5](#5-coming-soon-guards)). Below Desk: omitted. OAuth return `/settings/brokers/callback` is a behavior route, not a tab |
| Notifications | Digest and holding alerts | Prefs | wired for every member | Load error |
| Billing | Plan and checkout | Interval, checkout / portal links | wired when Stripe is configured. When Stripe is unset: coming-soon guard inside this tab, no fake invoices | Tab stays visible on every tier. Unset is an honest "not configured" block |
| About | Build and appearance | Status, theme, build | local / public env | Theme is local. No book data |

FX Hub-only invitees, when that grant is in scope, see a reduced account screen (invite status, sign out) instead of this tab set. When the grant is out of scope, FX Hub is omitted entirely, including this reduced screen.

**States.** No token: the page cannot call settings APIs; show the session-required state, not a skeleton that never ends.

### 3.10 Auth

| Route | Purpose | Data | States |
|---|---|---|---|
| `/login` | Sign in | auth | Error from the provider, inline. No book chrome |
| `/signup` | Register | auth | Same |
| `/auth/callback` | Session return | auth | No visual experiment. Errors from the callback query or hash are shown; success enters the app |
| `/settings/brokers/callback` | Alpaca paper OAuth return | broker connection | Success or failure returns to Settings → Brokers. Not a marketing page |

These routes are outside the book-data gate. No unavailable panel.

### 3.11 Ticker dossier — `/portfolio/tickers?ticker=`

**Purpose.** One symbol's book context. Optional in the first implementation slice; required as soon as Brief or Holdings link a ticker. Not a primary nav item. Not a sixth portfolio tab.

**Content blocks**

| Block | Data |
|---|---|
| Command band (symbol, back to Holdings) | wired |
| Position, weight, related thesis | wired when the book holds it |
| Gloomberb symbol pane | embed |
| LuxAlgo chart pane | embed, bars from digiquant `GET /bars` (Gloomberb, display-only). Off until the slice includes it; absence is not a broken image |

**Settings.** None beyond the book the viewer may see.

**States.** Unknown or blank ticker: empty, and do not open Gloomberb on a default symbol. No `?ticker=`: empty prompt to pick a symbol from Holdings. Static export: one page, query param, any symbol. Backend down: unavailable panel.

---

## 4. Settings taxonomy

Effective tier is `max(workspace plan, entitlement grant floor)`, not the JWT claim alone. There is no Custom tier. Overlay work is Studio and Enterprise. Enterprise matches Studio for these tabs.

| Tab | Observer (free) | Brief | Desk | Studio / Enterprise |
|---|---|---|---|---|
| Profile | omit | omit | omit | show |
| Pipeline | omit | omit | omit | show |
| Keys | omit | omit | omit | show |
| Brokers | omit | omit | show (paper) | show (paper) |
| Notifications | show | show | show | show |
| Billing | show | show | show | show |
| About | show | show | show | show |

Omitted means the tab is not in the strip and a direct `#` or `?tab=` for it is ignored. The server still refuses the write. Do not render a lock, a blurred preview, or an upgrade card in the hole.

**Where the other owned nouns live**

| Noun | Shipped home | Not |
|---|---|---|
| Profiles | House → Profile (read-only house pins) and Settings → Profile (Studio+ posture) | A second profile product |
| Pipelines | Pipeline page (the run) and Settings → Pipeline (Studio+ knobs) | A pipeline marketplace |
| Brokers | Settings → Brokers, paper | A live ticket |
| Integrations | Keys + Brokers | A separate shipped hub |
| Appearance | Settings → About (local theme) | A theme gallery |
| Account | Auth plus Settings | A parallel account app |
| Notifications | Settings → Notifications | |
| Billing | Settings → Billing | |

Calendars, tools, builder, and journal are [§5](#5-coming-soon-guards), not hidden settings tabs.

---

## 5. Coming-soon guards

A guard is a slot in this map plus, later, an honest empty state. It is not a route in `apps/dashboard/app` that looks finished. Phase B may draw one guard frame, labeled as a guard. Phase C does not add the route until the capability is real.

**Nav rule.** Omit. Do not grey the item in the sidebar. A disabled control with a status chip is allowed only on a page that already shipped (the Brokers live control, the Billing unset block).

| Slot | Owned by | What the guard says | What it must not show |
|---|---|---|---|
| Strategy builder | dashboard, future `/builder` | Not available yet. Ideas are not run from the showcase | A chat transcript, a backtest, a deploy button. digiquant-web `/strategies` is not this slot |
| Journal | dashboard, future `/journal` | Not available yet | Sample trades, a streak, a fake P&L |
| Tools | dashboard, future `/tools` | Not available yet | A second chart library. LuxAlgo stays the chart pane on spine pages that need one |
| Calendars | dashboard, future, under tools | Not available yet | A fake macro calendar. (`economic_calendar` stays inside FX Hub when that product is in scope) |
| Integrations hub | dashboard, future | Not available yet | A grid of logos. Keys and Brokers remain the real surface |
| Live brokers / execute | Settings → Brokers, disabled chip `Paper` | Paper only. Live needs an explicit human decision | A live toggle that appears to arm, live fill rows, live P&L |
| Embedded digichat | shell slot, not a page | Not available yet | The builder, and not a second nav item. Today's research popup is not the builder and is out of this lane |
| ProfileConfig DB | House → Profile and Settings → Profile | House pins are read-only. Studio+ may save the posture fields that exist today | A full overlay form that does not persist |
| Billing, Stripe unset | Settings → Billing | Billing is not configured | Prices, invoices, or a checkout button that 404s |
| FX Hub | `/twelve-x` | Omit from nav, palette, and settings unless the invite is in scope | A greyed "FX Hub" row. When in scope, the existing grant gate stays; this lane does not rebuild it |
| `/why` | — | Prefer no page. Redirect to Pipeline | A second reasoning hub "coming soon" |

Copy for a guard is one or two sentences. No illustration of the future product, no sample numbers, no private-client names.

---

## 6. States

Every shipped surface uses these. Guards in [§5](#5-coming-soon-guards) use only the coming-soon row.

| State | Behavior |
|---|---|
| Loading | Skeleton in the page column. One heading where the export requires it (Pipeline). No flash of zero figures |
| Empty | Say what is missing and the next real step (pick a date, open Holdings, check back after a run). No sample rows |
| Error | The load failed. Retry. Do not replace the body with a zero book |
| Unavailable mark | Em dash. Badge `unavailable`. Never render `0` |
| Live or close mark | Badge `live` or `close` only when the valuation source says so. Not a second P&L |
| Backend down | [§2.4](#24-data-gate) |
| Coming soon | The guard sentence. No chart, no table of examples |
| Omit | The control is absent |

---

## 7. Chart and symbol panes

| Pane | Engine | Where it is allowed | Data |
|---|---|---|---|
| Price / series chart | LuxAlgo (Vela) embed | Ticker dossier, and Tearsheet only if a curve is required | digiquant `GET /bars`, Gloomberb, display-only. No Pine, no second provider inside the pane |
| Symbol terminal | Gloomberb embed | Holdings, thesis vehicles, ticker dossier | The symbol already on the row. Blank symbol: no pane |
| NAV / returns | Table and KPI | Brief, Tearsheet | Accounting NAV. Not a reimplementation of the curve in another library |
| Contribution, weights | Table | Holdings, Attribution | Not a chart |

Do not add lightweight-charts, recharts, or a new canvas stack in the rebuild. Do not rebuild LuxAlgo. The lab route `/research/vela-spike` proves the embed; it is not a nav destination and not a Tools page.

Gloomberb links that open a new tab today are the inventory. The target is an in-page embed pane so the book stays on screen. The pane is display-only. It does not take orders.

---

## 8. Access

- Sign-in required. The five primary items assume a session.
- Presentation follows the tier matrix in [§4](#4-settings-taxonomy) and the artifact classes already in `apps/dashboard/lib/entitlements.ts` (teaser, house weights and NAV, glass box, paper brokers, overlay). RLS remains the hard gate.
- FX Hub is a client-product grant, not a plan tier, and it is omitted unless the invite is in scope for that slice.
- Pipeline glass box is Desk and above. Below that, Pipeline is omitted from the nav rather than opened as a locked diagram. Brief still links to book surfaces the tier may see.
- No private-client names anywhere in this chrome.

---

## 9. Build phases

These letters are this lane's order. They are not #4761 phases.

| Phase | Delivers | Does not deliver |
|---|---|---|
| A. Plan lock | This document | UI, HTML, route edits, chart code |
| B. Static HTML mockups | Spine screens only, instrument craft, literal labels, sticky section tabs, honest empties, embed-pane placeholders labeled LuxAlgo or Gloomberb | App routes, greyed soon-nav, fake live P&L, a chart library, showcase pages |
| C. Implement | `apps/dashboard` against this map: shell and five-item nav, auth, settings omit-by-tier, then Brief, portfolio tabs, Pipeline, House, ticker dossier when a deep link needs it | Builder, journal, tools, calendars, integrations hub, live execute, embedded digichat, FX Hub rebuild, `/why` as a second hub |

Phase C order inside the app, after the shell:

1. Auth and Settings (omit-by-tier, Billing unset guard, Brokers paper-only chip).
2. Brief.
3. Portfolio tabs: Holdings, Theses and detail, Tearsheet, Ledger, Attribution.
4. Pipeline, including the backend-down exemption.
5. House.
6. Ticker dossier if Brief or Holdings still needs the deep link.
7. Embed panes (LuxAlgo, Gloomberb) on the surfaces in [§7](#7-chart-and-symbol-panes).

A coming-soon route is not step 8. It waits until that capability exists, then ships as the real surface, not as a mock that was left in the app.

Craft (black, Inter, JetBrains Mono) is applied in B and C from the digiquant-web craft lane. It does not change this map.

---

## 10. Non-goals

- digiquant-web showcase: home, `/strategies`, `/strategies/[id]`, subsystems, changelog, contact. No builder there.
- digithings.ai marketing.
- Restyling the current dashboard in place. Phase C is a new composition against this inventory.
- Rebuilding charts, or shipping a second chart stack.
- Live trading, `digiquant/brokers/` behavior changes, or a live execute control. Human gate. This plan does not arm anything.
- digikey auth, JWT, or crypto.
- #4761 container cutover, cron, or secrets.
- FX Hub visual rebuild.
- Turning `/strategy` into a builder.
- Private-client names, gamified scores, glass marketing chrome, fake live P&L.
- Release-please.

---

## 11. Defaults this map already decided

| Question | Decision |
|---|---|
| Is `/why` in the nav? | No. Redirect to Pipeline unless Chris keeps the page |
| Is the builder in the sidebar as Soon? | No. Omitted until it is real |
| Where do paper fills live? | Ledger for the book. Settings → Brokers for the paper connection's fills |
| What is the returns source of truth? | Tearsheet / accounting NAV. Brief KPIs read that series |
| What happens to Custom? | Retired. Overlay is Studio+ |
| What is `/strategy`? | A redirect to theses |
