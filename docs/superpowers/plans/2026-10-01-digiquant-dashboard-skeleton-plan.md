# digiquant dashboard skeleton plan

**Status:** Human Gate draft. §0.1 is Chris's corrected desk lock (2026-10-01). One file. No UI, no static HTML, no route code.

**Date:** 2026-10-01. Correction same day: a desk is a full spine configuration, not a nav item. The trading-engine slot (Setups) stays off the nav until it is real.

**Issue:** [GitHub #4895](https://github.com/digithings-ai/digithings/issues/4895)

**What this file is.** The single gate document for the ground-up digiquant dashboard. Sections 0–2 are the synergy review, including the corrected desk lock. Sections 3–6 are the four lane documents copied in full. Those four sections were not shortened, paraphrased, or dropped. Tables, route lists, MCP counts, settings controls, and wiring notes are the original lane text. Section 5's five-item sidebar is the baseline house desk, not a chrome that can never change. §0.1 says how.

**How to read it.** §0.1 is locked. §0.2 keeps the earlier defaults wherever they do not fight that lock. Section 1 says where the lanes agree, where they contradict, and which section 0 item that maps to. Do not treat a lane's own "lane 1 / lane 2 / lane 3" numbering as the build order. The build order is phase A, phase B, phase C in section 1.4. Those letters are not [#4761](https://github.com/digithings-ai/digithings/issues/4761) phase numbers.

**Link note.** The market scan was written for `docs/plans/`. It is reproduced in section 6 from this directory, so its four relative links were rewritten from `../` to `../../`. No other lane text was edited.

| Lane | PR | Original path | Full text |
|---|---|---|---|
| Existing-app inventory | [#4904](https://github.com/digithings-ai/digithings/pull/4904) | `docs/superpowers/plans/2026-10-01-dashboard-existing-app-inventory.md` | [Section 3](#digiquant-dashboard-existing-app-inventory-lane-13) |
| Data / backend map | [#4905](https://github.com/digithings-ai/digithings/pull/4905) | `docs/superpowers/plans/2026-10-01-digiquant-dashboard-data-map.md` | [Section 4](#digiquant-dashboard-data-map-rebuild-lane-2) |
| Navigation and surface map | [#4906](https://github.com/digithings-ai/digithings/pull/4906) | `docs/superpowers/plans/2026-10-01-dashboard-navigation-surface-map.md` | [Section 5](#digiquant-dashboard-navigation-and-surface-map-lane-33) |
| Market IA scan | [#4907](https://github.com/digithings-ai/digithings/pull/4907) | `docs/plans/2026-10-01-digiquant-dashboard-market-ia-scan.md` | [Section 6](#digiquant-dashboard-market-ia-scan) |

Vision beside the lanes: [docs/vision/dashboard.md](../../vision/dashboard.md), [docs/vision/digiquant.md](../../vision/digiquant.md).

---

## 0. Human Gate

Chris corrected the desk lock on 2026-10-01. §0.1 is that correction. §0.2 keeps the earlier defaults where they still fit. Phase B uses both. Sections 3–6 stay the evidence and are not rewritten.

An earlier reading of the same addendum put **Desks** in the sidebar in place of Pipeline (`Brief · Portfolio · Desks · House · Settings`) and sent `/pipeline` to a `/desks` page. That reading is withdrawn. A desk is not a section inside a fixed five-item chrome.

### 0.1 Locked — the spine is the desk config

**What a desk is.** A desk is one full configuration of the app. It owns which top-level items exist, the label on each, the order they appear, and which pages sit behind them. Selecting a desk swaps that entire spine. It does not open a page called Desks, and it does not leave Brief, Portfolio, House, and Settings standing while only one slot changes.

Customers will create and customize their own desks. A custom desk is an alternate full configuration: investor preferences, a research layout, a pipeline layout, or some other layout. Those are examples of what a config may emphasize. They are not extra items glued onto the house spine.

**House desk first.** The baseline is the house desk. It is the default config, and it is the only config phase B and phase C ship. Its top-level items are the list in item 1: **Brief · Portfolio · Pipeline · House · Settings**, with that item's tabs, auth outside the frame, and the ticker dossier as a deep link. Pipeline on that config is still the glass box (`/pipeline`). Settings → Pipeline is still the Studio+ knobs. Those two uses of the word stay distinct, as section 1.1 already says.

**Many desks later, without a redesign.** A workspace may hold more than one desk. The frame has a desk switcher that is not itself a spine item. On the house desk it shows House selected. "New desk" is a disabled control on that switcher with a status chip (`Not available`). It is not a sidebar row, and phase B does not draw a second spine full of sample pages. An unknown desk id is an empty state, not a fabricated layout. Phase C implements the house desk as data the shell reads (items, labels, order, routes), not as five labels written only into the sidebar component. Adding a custom desk later is a new config, not a new navigation model.

**What the switcher does not do.** It does not swap the house paper book for a user book, and it does not toggle paper and live (item 12 and item 3). A future custom desk may simply not include the book surfaces. That is a different layout, not a portfolio switcher.

**Routes on the house desk.** No `/desks` product page. `/pipeline` stays the house desk's glass box and keeps `date`, `stage`, and `node`. `/why` still redirects there (item 4). Other legacy redirects in section 5 stay. A future desk may point the same job at a different route. That mapping belongs to the config. This plan does not design those other routes.

**Words that must not collapse.**

| Word | What it is | What it is not |
|---|---|---|
| desk | One full spine configuration: items, labels, order, and the pages behind them. | A sidebar section. A plan tier. A brokerage account. |
| house desk | The default config phase B and phase C ship. Its spine is item 1. | A claim that every future workspace looks like that spine. |
| desk switcher | Frame chrome that selects which config is active. House is the only real row for now. | A nav item labeled Desks. A paper/live switch. A house-book / user-book switch. |
| Pipeline | On the house desk: the glass-box item and the route `/pipeline`. Also the Settings tab name. | The product noun for "a desk". |
| Desk | Plan tier between Brief and Studio. | A desk config. |
| Setups | Future trading-engine surface. Off the house desk nav until it is real. | A desk, Portfolio, FX Hub, or a live order ticket. |
| twelve-x | The source idea for that trading-engine path, and today's separate FX Hub product. | A reason to put FX Hub on the house desk. Item 2 still omits it. |

**Trading engine, coming soon.** Parallel to the investment book (on the house desk that book is Portfolio: holdings, theses, tearsheet, ledger, attribution), the product will have a trading-engine path. Its job is to suggest real potential trade setups. It does not execute live by default. Setups are paper-first. A human gate sits in front of any live use. The source idea is twelve-x. The job word for the future surface is **Setups**. "Trading desk" is not used: it collides with desk-as-config and with the Desk tier. "Engine" is not a nav label. No Olympus, Atlas, Hermes, or Kairos label. Setups is omitted from the house desk nav, the palette, and phase B. It is not a grey row and not a chip on Portfolio. When it is real, a desk config may include it as one of its surfaces. Until then, no config shows it.

### 0.2 Defaults that still stand

Item 1 is the house desk's spine, not a universal chrome. Items 4 and 5 apply to that house desk. They are not a `/desks` route. Items 2, 3, and 6–12 are unchanged, with item 11 and item 12 worded so they follow §0.1.

| # | Decide | Standing answer |
|---|---|---|
| 1 | House desk spine and book tabs | The house desk's sidebar is **Brief · Portfolio · Pipeline · House · Settings**. Portfolio is one item. Its sticky tabs are **Holdings · Theses · Tearsheet · Ledger · Attribution**. House tabs are **Corpus · Book · Profile**. Auth stays outside the frame. The ticker dossier is a deep link, not a sidebar item and not a sixth portfolio tab. This list is the baseline config. It is not a fixed chrome with a Desks section, and Pipeline is not renamed Desks. |
| 2 | FX Hub | **Out of this skeleton.** No sidebar row, no palette entry, no reduced invite screen, no phase B frame. It returns only if the `fx_hub` invite is explicitly in scope for a later pass. twelve-x as the idea behind Setups does not put FX Hub on the house desk. |
| 3 | Paper brokers in Settings, live hidden | **Yes.** On the house desk, Desk and above see Settings → Brokers: Alpaca paper OAuth, Alpaca paper API key, IBKR beta paper, paper fills. Live execute is a disabled control with a `Paper` chip on that page. No header paper/live switch. No live nav item. |
| 4 | `/why` | **Redirect to `/pipeline`** on the house desk. Keep it out of the nav. Keep the page only if "The read" and "Deliberations" still have a job the Pipeline canvas does not cover. |
| 5 | Pipeline below the Desk tier | On the house desk, **omit the Pipeline nav item** for Observer and Brief. Do not grey it and do not open a locked diagram. Desk and above see the glass box. Economics stay a Desk-tier detail inside that page. A future custom desk may include or omit a glass box under its own label. That does not put Pipeline back on Observer's house desk. |
| 6 | Journal on Ledger | **Invisible.** No sidebar row and no "journal later" chip on Ledger. |
| 7 | Published strategy library | **Not on the house desk.** `strategies` / `strategy_tearsheets` stay on the digiquant-web showcase until a later dashboard surface exists. They do not land on the house Tearsheet and they do not become a house-desk sidebar item in phase B or C. |
| 8 | digichat popup | **Phase C does not carry the current iframe.** Embedded digichat stays off the nav until it is a real surface. When it exists, it does not gain an order action. |
| 9 | Tearsheet picture | **Report only** in the mockups: accounting NAV, method line, table. No equity curve on Tearsheet. A labeled LuxAlgo placeholder is allowed on the ticker dossier only. Do not draw lightweight-charts, recharts, or a second curve. Do not blend a strategy backtest into the house NAV. |
| 10 | Ticker dossier in phase B | **One static frame**, opened from a Holdings row, no sidebar item. |
| 11 | Command line | **Out.** No Bloomberg / Koyfin command bar. The palette lists the active desk's items plus that desk's deep links. On the house desk those items are the five in item 1. |
| 12 | House book vs a user-book switcher | **Never merge them into one switcher.** House stays the operator paper book. Studio+ profile is an overlay, not a second anonymous book and not a paper/live toggle. The desk switcher in §0.1 changes the whole spine. It is not this switcher. |

---

## 1. Synergy review

Reviewed together: section 3 (what the app actually ships), section 4 (what the stores and tools can support), section 5 (the target navigation and surfaces), section 6 (which public finance patterns survive the locks). Code checked while comparing the Pipeline tier claim: [`apps/dashboard/lib/nav.ts`](../../../apps/dashboard/lib/nav.ts), [`apps/dashboard/lib/entitlements.ts`](../../../apps/dashboard/lib/entitlements.ts), [`apps/dashboard/components/pipeline/PipelineRunHealth.tsx`](../../../apps/dashboard/components/pipeline/PipelineRunHealth.tsx).

### 1.1 Agreements

These are the same lock in more than one lane. Section 0 does not reopen them except where a later row says a lane still asked for a yes.

**Product split.** The dashboard is the product. It owns the builder, strategies, the journal, the tool catalog, and integrations when those surfaces exist. `apps/digiquant-web` is the showcase. Its `/strategies` and `/strategies/[id]` pages are published tearsheets for marketing. digithings.ai is marketing. Neither showcase nor marketing gets strategy CRUD, the journal, the tool catalog, settings, brokers, calendars, pipelines, profiles, or integrations. [#4895](https://github.com/digithings-ai/digithings/issues/4895) states that split. Sections 3, 4, 5, and 6 all repeat it. [docs/vision/dashboard.md](../../vision/dashboard.md) is the operator surface. [docs/vision/digiquant.md](../../vision/digiquant.md) is research, then portfolio deliberation, then execution, with paper before live.

**Paper book first.** The book the dashboard reads is a research / paper book. Human gate before any live venue. No live-by-default capital story, no guaranteed-alpha claim, no fake live P&L. Missing marks are an em dash. Unknown figures are not `0`. Sample rows are not allowed. Day return is null across a NAV seam or a calendar gap greater than 4 days. Alpha and information ratio need at least 20 overlapping daily pairs. `provenance.contract` is `finalized_accounting` or `legacy_estimate`. A live quote overlay is badged `live` or `close` and does not wear the finalized badge.

**Names.** Jobs are research, portfolio, and execution. UI labels do not use Olympus, Atlas, Hermes, or Kairos. digi* module names stay lowercase in prose and chrome. DigiQuant is allowed as the brand. Storage identifiers that still say `olympus_*` stay storage identifiers. Do not surface them and do not rename them in a UI plan.

**Charts and symbols.** LuxAlgo is the only chart backbone. Gloomberb is the symbol terminal and the display-only bar source behind a LuxAlgo pane. gloom.sh is a visual reference for a later craft pass, not a chart engine and not a third embed. `GET /bars` is display-only and must not feed validate → backtest → optimize → export. Gloomberb is enrichment, not the price source of record. Prices of record are R2 via `GET /v1/market/tickers` and `GET /v1/market/closes`. Empty market config fails closed. There is no Supabase `price_history` fallback. That table was dropped.

**Access.** The operator app is access-gated. Anonymous diagnostics stay removed. Auth routes (`/login`, `/signup`, `/auth/callback`) sit outside the app frame and outside the book-data gate. Effective tier is `max(workspace plan, entitlement grant floor)` via `my_access()`, not the JWT claim alone. Tiers are Observer (`free`), Brief, Desk, Studio, Enterprise. Enterprise matches Studio for these tabs. There is no Custom tier. FX Hub is a `client_product_grants` key (`fx_hub`), not a plan tier. Sealed broker and provider secrets never reach the client. The UI sees fingerprints. Stripe customer ids are not rendered. No private-client names, inboxes, or grant emails in chrome, copy, plans, or fixtures.

**Coming-soon rule, shared.** A destination that is not real is omitted from the sidebar. It is not a grey row. If a control has to remain on a page that already shipped, it is disabled and carries one status chip. It does not navigate. No fake tables, no fake charts, no sample P&L. The slots the lanes all keep off the nav for this spine: strategy builder, journaling, live brokers / execute, embedded digichat, tools catalog, calendars, integrations hub. Where the chip is allowed to sit is item 6 and item 3, because the lanes name different pages.

**Settings shape.** Seven tabs, omit-by-tier, never greyed: Profile, Pipeline, Keys, Brokers, Notifications, Billing, About. `?tab=` wins over `#hash`. A gated or unknown tab is ignored and the page opens on the first visible tab. No free-form model-id picker. Keys seal a provider name only: openai, anthropic, groq, openrouter, xai, gemini. This matches [Settings IA](../../agent-backlog/execution-tenancy/SETTINGS-IA.md) and the live `SETTINGS_TAB_DEFS` in section 3. The matrix itself is reproduced in section 3 and again in section 5. It is not restated here as a shorter table that could drift.

**`/strategy`.** Redirect only. With `?thesis=` it opens that thesis. Otherwise it lands on `/portfolio?tab=theses`. It is not a builder, not a strategy library, and not chat. Section 3, section 5, and section 6 agree.

**Ledger is not a journal.** House `position_events` (`OPEN` | `ADD` | `EXIT` | `TRIM`) are the paper-book fill stream. `strategy_trades` are published backtest fills. `broker_executions` are a venue mirror. `knowledge_notes` and digivault are a shared research corpus. digigraph threads are orchestration history. LuxAlgo `journal_*` is not wrapped. None of those is the trade journal. The journal has no table yet. Section 4 says the future table is access-gated and per workspace. Until that migration exists, the surface is coming-soon and shows no sample trades.

**House tearsheet is not a strategy tearsheet.** `/portfolio/performance` reads `public_accounting_nav_history` plus benchmark closes through dashboard-api `GET /performance`. `TearsheetData` inside `strategy_tearsheets.metrics` is a different object. Strategy Sharpe does not go on the house NAV badge. Closed book events stay on Ledger. The showcase strategy gallery stays on digiquant-web.

**Two different things named Pipeline.** The sidebar route `/pipeline` is the glass box for one run date. Settings → Pipeline is Studio+ overlay knobs (watchlist, themes, research budget, weekday schedule). The house run stays immutable. Mockups have to label both or the word collapses.

**Fail-closed book.** One NAV series for Brief and Tearsheet. Live marks are an overlay badge, not a second set of books. Position fills are never derived from weight diffs. Unknown dashboard-api tables 404. A missing service-role key is `upstream_empty`, not an empty success. `/pipeline` empty means no runs. Inputs with no call telemetry are a typed gap.

**Craft.** Instrument, not SaaS glass. Follow digiquant-web, not a fat shell and not a marketing clone inside the app. Literal sidebar labels, never icon-only. One sticky in-page tab row. No nested sticky bars. Hairline structure, tabular figures, flat panels. Blur only on sticky chrome and overlays. Type pair Inter and JetBrains Mono when craft is applied in phase B and phase C. One primary action per spine surface, listed in section 6's steal list. Density lives in the page, not in extra destinations. Parked #4885, #4892, and #4896 stay reference only.

**Auth and human gates this plan does not touch.** No edits to `digikey/`, no live-trading path, no `digiquant/brokers/` behavior change, no new network exposure. `env = live` may exist as stored vocabulary. Showing it as connected-for-trading waits on a human. `digifetch_ibkr_execute_order` stays disabled.

**#4761 is a different project.** Epic #4761 phase numbers are the house-run move onto Cloudflare Containers and the GitHub Actions cutover. They are documented in [the house-run plan](./2026-09-30-digiquant-house-run-phase3.md) and [the Phase 4 GHA cutover plan](./2026-10-01-digiquant-phase4-gha-cutover.md). Dashboard work uses phase A / B / C only.

### 1.2 Contradictions

Each row is a real disagreement or an internal split. The recommended lock is the matching section 0 item. The lane text that contains the disagreement is reproduced later and was not edited to hide it.

**Sidebar candidate lists.** Section 3's "Web UX" block records a later-lane sidebar of Chat / Strategies / Journal / Research|Portfolio|Signals / Tools|Integrations / Settings. The same section's lab spine, and the whole of section 5, record Brief · Portfolio · Pipeline · House · Settings. Section 6's IA implications name the same five. Today's `NAV` is a third list: Brief, Portfolio, Pipeline, FX Hub, plus an external Gloomberb terminal link, with House only in the command palette. **Item 1 keeps that five-item list as the house desk's baseline config.** Chat, Strategies, Journal, Tools, and Integrations are products the dashboard will own later. They are coming-soon, so they are not items on the house desk. The inventory list is a product-ownership inventory, not the navigation. §0.1 then says the five items are not an immutable chrome: another desk may replace the whole list. Desks is not inserted as a sixth label and does not rename Pipeline.

**Book as five sidebar items vs one item with tabs.** Section 5 locks one Portfolio item and a sticky tab row. Section 6 question 1 asks you to confirm that against five sidebar words, and notes the live `PortfolioSectionNav` already uses the sticky row. Promoting each word to its own sidebar item would copy the kitchen-sink tab problem section 6 tells us to avoid, and it would add a second sticky layer if the tabs remained. **Item 1.**

**Pipeline for Observer and Brief.** Section 5 §2.1 lists Pipeline as one of five primary items with no tier on the row. Section 5 §8 says the glass box is Desk and above and is omitted from the nav below that, rather than opened as a locked diagram. The live app does something else: `NAV` includes Pipeline for every viewer, and `PipelineRunHealth` wraps only the economics block in `glassbox_economics` (Desk+). `entitlements.ts` comments that Brief adds house weights and NAV and "no pipeline," while the page itself still opens. **Item 5** picks the omit-from-nav reading in section 5 §8, and keeps today's economics gate inside the page for tiers that can see it. A locked diagram or a grey Pipeline row would break the coming-soon rule.

**Where a coming-soon chip may sit.** The shared rule is omit, or one disabled chip on a page that already shipped. Section 5 names two chips: Brokers live control (`Paper`) and Billing when Stripe is unset ("not configured"). Journal, builder, tools, calendars, and the integrations hub are omit-only in that section. Section 6 puts a future journal chip on Ledger, a future builder chip on Pipeline, and the live-broker chip in Settings. **Items 3 and 6.** Live-broker chip stays on the Brokers page. Journal stays invisible unless you override item 6. Builder stays off every page until it is real (no Pipeline chip in phase B).

**FX Hub.** Section 3: sidebar item when `canFxHub`; an FX-only invitee sees only FX Hub, and Settings becomes a sign-out / invite card. Section 5: omit from nav, palette, and settings unless the invite is in scope; when it is out of scope, omit the reduced screen too. Section 6 question 2 asks where it goes and does not assign it a job on the spine. **Item 2.**

**`/why`.** Section 3: the page still mounts `WhyClient` with "The read" and "Deliberations". It is not in `NAV`. The sidebar highlights Pipeline when the path is `/why`, because Pipeline absorbed the old destination, but the page does not redirect. `/research` and `/library` do redirect to Pipeline. Section 5: redirect `/why` to `/pipeline` unless you keep the page. Section 6: Pipeline is the only reasoning hub. **Item 4.** The gap to weigh is that "The read" and "Deliberations" are not the same component as the Pipeline canvas. Redirecting without a home for those two tabs drops them.

**Chart libraries on the book.** Section 3 records lightweight-charts on the decision-edge time series, recharts on composition and parts of FX Hub, and SVG tearsheet primitives on the print tearsheet. `@luxalgo/vela` exists only on `/research/vela-spike`. Section 4 says house NAV and tearsheet equity need an explicit LuxAlgo binding before they count as a LuxAlgo chart, and until that binding exists those series stay on their current components or wait. It also says the rebuild plan must not add a second chart library. Section 5 forbids adding lightweight-charts, recharts, or a new canvas stack in the rebuild, keeps NAV as table and KPI, and allows a LuxAlgo pane on the ticker dossier and on Tearsheet only if a curve is required. Section 6 allows a LuxAlgo pane on "Brief drill-down, Tearsheet, or the ticker dossier" and forbids a Charts destination. **Item 9** treats "Brief drill-down" as the dossier you open from Brief, not a chart on the Brief page. Tearsheet does not get a curve in this plan, so the "only if a pane is required" clause is not met. Phase B and phase C do not port lightweight-charts or recharts forward. The current components are inventory, recorded in section 3, not the rebuild stack. The LuxAlgo binding for the NAV series is a later plan. This file does not design it. Section 4's "stay on current components until bound" describes the live app during the wait. It does not authorize those libraries in the new composition.

**Strategy library with no route.** Section 4: migration 046 is the durable library; anon can read published tearsheets today because the showcase does; dashboard product reads should be the access-gated path; the editor and library management live on the dashboard; publish stays an operator path (`--push-supabase`). Section 5 has no Strategies destination. The builder is a future `/builder`, omitted, and digiquant-web `/strategies` is explicitly not that slot. Section 6 says the builder, when it exists, is in the dashboard and is reached from Pipeline, and it is not an IDE home and not a Discover marketplace. **Item 7** leaves the published rows on the showcase for this spine. Putting them on the house Tearsheet would mix `TearsheetData` into accounting NAV, which section 4 forbids. Inventing a Strategies sidebar item now would also break item 1.

**digichat.** Section 3: `DigichatPopup` iframes digichat `/embed?layout=embed` for Desk, Studio, and Enterprise. Observer and Brief get an upgrade CTA and no iframe. It is not a route, not a sidebar Chat item, and not a strategy builder. Section 5: the popup is out of this lane; phase C does not deliver embedded digichat. Section 6: when an embed ships, it sits inside Pipeline and does not gain a deploy action. Section 4: `POST /workflow` is a candidate engine for a later builder; a digigraph thread id is not a saved strategy. **Item 8.**

**Tearsheet contents.** Section 6 question 9 asks whether Tearsheet may show a hypothetical backtest and a paper-fill record as two labeled sections. Section 4 and section 5 say the spine Tearsheet is the house accounting series only. Backtest metrics belong to `TearsheetData`. Paper connection fills belong to Settings → Brokers (`GET /settings/fills`). Book events belong to Ledger. **Item 9** refuses the blend.

**House on the sidebar.** Section 3: House is a real route (`/house?tab=corpus|book|profile`) and it is not in `NAV`. Command palette only. Section 5 puts House on the sidebar. That is current code versus the target spine, not two product theories. **Item 1** follows section 5. Corpus stays wired-partial (sample document keys, fail soft). Book and Profile stay declared chrome. Editable posture stays Settings → Profile for Studio+.

**Gloomberb chrome.** Section 3: an external "Gloomberb Terminal" sidebar link, plus per-ticker links that leave the app. Section 5: in-page embed panes on Holdings, thesis vehicles, and the ticker dossier; blank symbol draws no pane; the pane does not take orders. The external link is not one of the five sidebar items. Phase B draws a labeled placeholder. Phase C hosts the embed. Not a separate Human Gate item unless you want the outbound link kept. The recommendation is to drop it from the sidebar.

**User book switcher.** Section 6 question 8 asks to confirm House and a user book never merge into one portfolio switcher, because that switcher is the Alpaca paper/live pattern with different contents. Section 4: user overlay books exist (`workspaces`, overlay document keys) and are unwired on the main nav; the browser does not choose `workspace_id`; the house pin is server-side. Section 5: profile exclusions do not relabel the house book as the user's live account. **Item 12.**

**Command bar.** Section 6 question 7 asks whether a Koyfin `/` or Bloomberg command line is in a later pass or out of the map. Section 5's command palette is the five labels plus deep links, on desktop and mobile, with no second taxonomy. **Item 11.**

**Lane numbers.** Section 3 calls itself lane 1 of 3 and says lane 2 would be IA and lane 3 would be craft. Section 4 calls itself lane 2 of 3 and says lane 1 is the digiquant-web craft bar and lane 3 composes surfaces. Section 5 calls itself lane 3 of 3 and is the navigation map, not the craft pass. Section 6 says it feeds the nav map and does not draw the tree. Those numbers cannot be executed as written. They remain in the reproduced text so the sources stay intact. **The only build order is §1.4.**

### 1.3 Gaps the lanes leave open

These are missing pieces, not votes for a different spine.

**`/why` content has no named successor.** If item 4 stands, phase C redirects the route. Nobody has listed which Pipeline nodes replace "The read" and "Deliberations". The redirect is still the recommendation. The gap is documentation of those two tabs, not a second hub.

**Strategy library has a store and no operator page.** Item 7 keeps it off this spine. The gap remains for a later issue: access-gated reads of `strategies`, `strategy_tearsheets`, `strategy_signals`, and `strategy_trades`, distinct from the house Tearsheet and from the showcase's anon select.

**Journal has no table.** Section 4 names the columns a future table needs and lists every object people might confuse with it. There is nothing to wire. Item 6 keeps the absence visible by not drawing a chip.

**LuxAlgo binding for NAV is unspecified.** Section 4 refuses to design it. Section 5 allows a pane only if a curve is required. Item 9 says it is not required for phase B. A later plan has to say which LuxAlgo preset, if any, plots `public_accounting_nav_history`.

**Tool catalog is stored and unwired.** 127 digiquant MCP tools, 113 in read scope, 14 full-only, plus 14 `luxalgo_*`, 89 `digifetch_*`, 8 dashboard-api readers, 6 digivault tools. The counts and the name lists are in section 4 and are not repeated here. There is no dashboard page that lists them. The catalog stays off the nav. Inert `digifetch_*` workspace and broker tools stay labeled inert when a catalog eventually exists. `auth_required` and `pro_required` are not empty successes.

**Research memory is service-role.** The families in section 4 §2.4 (corpus pin, evidence, attention, forecasts, outcomes, policy replay, risk registries, `profile_config`) are stored and mostly unwired. Attention in the glass box comes from a `documents` row with `doc_type = Attention Plan`, or it is absent. Policy-replay MCP reads exist. The UI does not call them. A gate evaluation is not a live-trading permission.

**Settings edge deploy.** Section 3: the client in `lib/settings-api.ts` is written against the settings Edge Function, and the README says that deploy is blocked on vault plus `broker_connections` (K3). "Wired" in the surface catalog means the client contract exists. It does not mean production proof of the edge deploy. Phase B can draw the tabs. Phase C should not treat a green UI as proof the function is deployed.

**Pipeline when the book database is down.** Section 4 and section 5 say `/pipeline` stays up. Section 3's exempt-prefix list does not include `/pipeline`, and section 5 says `isDbExempt('/pipeline')` is false today. The comment in `nav.ts` claims the prefix is exempt. The array does not contain it. Phase C makes the route exempt. This plan does not change that code. House static chrome, Settings, Auth, and the broker OAuth callback already stay up. Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, and the ticker dossier show the unavailable panel.

**Profile form vs ProfileConfig.** The fields that save today (investment profile and asset preferences on a versioned overlay, optimistic concurrency, reserved `house` key not editable) are real, per section 3. A full overlay ProfileConfig that does not persist is the guard in section 5. Phase B draws the fields that save. It does not draw a larger form.

**Ledger states.** Section 6's steal from thinkorswim (working, filled, canceled) applies only if those states exist. On the house book they do not. Ledger kinds are `OPEN`, `ADD`, `EXIT`, `TRIM`. Broker order status lives on `broker_orders` and is not the house ledger. Do not add a brokerage state split to Ledger in the mockups.

**Auth flag.** `NEXT_PUBLIC_DASHBOARD_AUTH=1` is off by default. Flag off keeps the anon client and the entitlement helper returns enterprise so the operator UI stays fully visible. Cloudflare Access is the hosting gate until cutover, per section 3. This plan does not change that flag. Phase B still draws sign-in outside the frame so the gate is part of the spine pictures.

**Static export.** Thesis id and ticker stay query params. Dynamic segments 404 after export. Path-form `/portfolio/theses/<id>` is not served. Deep links in section 5 already follow that constraint.

**Screenshot fixtures.** Section 3: 24 PNGs under `apps/dashboard/fixtures/screenshots/`, 70 bytes each. They are not pictures of the product. Phase B does not start from them.

### 1.4 Phases

These letters are this plan's order. They are not #4761 phases. Section 5 §9 is the full version of this table, including the in-app sequence and the non-goals. It is reproduced in section 5 and not cut down here.

| Phase | Delivers | Does not deliver |
|---|---|---|
| A. Plan lock | This document, after section 0 is answered | UI, HTML, route edits, chart code |
| B. Static HTML mockups | Spine only, after the section 0 answers: instrument craft, literal labels, sticky section tabs, honest empties, embed-pane placeholders labeled LuxAlgo or Gloomberb | App routes, greyed soon-nav, fake live P&L, a chart library, showcase pages, the coming-soon slots |
| C. Implement `apps/dashboard` | Shell that reads the active desk config; ship the house desk (item 1) including auth, settings omit-by-tier, Brief, portfolio tabs, Pipeline (including the book-database exemption), House, ticker dossier when a deep link needs it, then the embed panes. The desk switcher shows House only. | Builder, journal, tools, calendars, integrations hub, live execute, embedded digichat, an FX Hub rebuild, `/why` as a second hub, a second desk, Setups, a nav item named Desks |

Phase C order inside the app, after the shell, is the numbered list in section 5 §9. A coming-soon route is not the next step after that list. It waits until the capability exists, then ships as the real surface.

What phase B draws, using §0.1 and §0.2:

- Sign-in, outside the frame, no book chrome.
- The house desk, named in a frame switcher that is not a spine item. The switcher shows House selected. "New desk" is disabled, with a `Not available` chip. No second layout is drawn.
- That desk's sidebar: Brief, Portfolio, Pipeline, House, Settings. Not a Desks item.
- Brief. Figures and links. No chart pane.
- Portfolio with the five tabs. Include one honest empty (no fills, or no thesis) so the empty state is visible.
- Pipeline. One canvas. Stage names are the job words already listed in section 5 §3.7. The route in the mockup is `/pipeline`, not `/desks`.
- House with Corpus, Book, and Profile.
- Settings at more than one tier so omission is visible. Desk shows Brokers, Notifications, Billing, About. A caption or a second frame shows Studio adding Profile, Pipeline, and Keys, and shows Observer / Brief without Brokers (Pipeline omitted, not greyed). Billing unset is the "not configured" block, not fake invoices. Brokers shows the `Paper` chip and no live arming control.
- Ticker dossier, one frame, per item 10. LuxAlgo and Gloomberb are labeled placeholders.
- Redirect notes are not pages. `/strategy` and `/why` are not drawn as products.

What phase B does not draw: a nav item or page named Desks, a custom desk's alternate spine, FX Hub, builder, journal, tools, calendars, integrations hub, Setups, `/why` as a hub, a Strategies library, a digichat panel, a command line, a paper/live switch, a house-book / user-book switch, grey nav rows, sample positions, a starter equity curve.

### 1.5 Market patterns, applied

Section 6 is the evidence: sources, steal list, avoid list, and the ten questions it left open. This subsection only records how those patterns land on the spine so a mockup does not re-litigate them. The full steal and avoid tables stay in section 6.

Applied:

- Brief is a fixed scoreboard, then the book, then a row. It is not a widget canvas, not a chart layout, and not a second portfolio.
- Holdings is the paper book. Attribution is a cut plus a table. Tearsheet is a report with the method on the page. Ledger is the paper fill list.
- One layout per job. Panels that do not earn a place leave. That is why coming-soon modules are overflow.
- A chart sits beside a table and can be maximized later. It is a LuxAlgo pane. Selection drives the pane. The pane does not host an order.
- The dossier opens from a row. One primary action: read that name, with a way back to the book.
- Paper is the environment you are already in. The screen says so. Live is omitted.
- Fills first. Notes and a journal attach later. They do not replace Holdings or Ledger.
- Settings omit the tier. Auth is the gate in front, not a settings tab.
- Empty copy says what is missing. No sample P&L.
- Literal sidebar, one sticky tab row. The live portfolio tab row is the pattern to keep. The collapsed icon-only rail in section 3 is debt.

Refused, including where the source product is good at it:

- Kitchen-sink navigation, an app catalog, a layout library, an IDE home, a strategy marketplace.
- Live-by-default chrome, gamified P&L, trading from the chart, an order ticket on a research row.
- TradingView, Legend, thinkorswim Charts, or Koyfin Graphs as the product. LuxAlgo owns charts.
- paperMoney-style "same ticket as live, different login," and a paper/live switch in the header.
- Builder or tool surface on digiquant-web.
- Grey soon-nav, nested sticky chrome, AI-SaaS glass, a marketing clone inside the app.
- Account aggregation, funding, margin, transfer.
- Hiding closed book events so a number looks cleaner.
- Retired proper nouns as labels. Private-client names.

Section 6's ten questions map onto section 0 as follows. The question text is unchanged in section 6.

| Section 6 question | Section 0 item |
|---|---|
| 1. One book destination with sticky tabs | 1 |
| 2. Where FX Hub goes | 2 |
| 3. Journal chip on Ledger or fully invisible | 6 |
| 4. Builder and digichat later, Pipeline only, no order action | 8, and the builder stays omitted until it is real (no chip in phase B) |
| 5. Paper connection in Settings, live omitted | 3 |
| 6. Ticker dossier in the first map | 10 |
| 7. Command bar | 11 |
| 8. House and the user book never merge | 12 |
| 9. Tearsheet blending backtest and paper P&L | 9 |
| 10. Brief density, no custom panels | Agreement in §1.1. Custom panels are out of the house desk's Brief. A future desk is a different spine, not a widget canvas on Brief. |

### 1.6 Desk correction against the lanes

Section 5 locks a five-item sidebar and says command palette and mobile use those same five labels. That lock stands for the **house desk**. §0.1 adds the rule section 5 does not contain: the shell must be able to swap the entire list when another desk is selected. Phase B still draws only the house list, plus the switcher, so the pictures match section 5's surfaces and do not invent a Desks section those lanes never specified.

What this changes in the earlier synergy, and what it leaves:

- Item 1's book tabs, House tabs, auth, and ticker dossier stay. They are house-desk structure.
- Pipeline stays the house desk's glass-box label and the `/pipeline` route. The withdrawn reading (rename that item to Desks, add `/desks`) is not in the lane text and is not the lock.
- Item 5's omit-below-Desk-tier rule stays on the house desk. A custom desk's own items are future config, not a way around that omit.
- Setups stays off every nav until the trading-engine path is real. twelve-x is the idea. FX Hub stays out (item 2).
- Item 12 stays. The desk switcher replaces the spine. It does not replace the book.

Sections 3–6 are untouched by this correction, including every route table, settings control, MCP count, and market note.

---

## 2. What was merged, and what was not changed

Sections 3–6 are the lane files. Heading text is unchanged, so in-page anchors inside section 5 (for example `#7-chart-and-symbol-panes`) still point at that lane's headings. No two headings in the four lanes slug to the same anchor. The desk correction in §0.1 and §1.6 is appended in the review. It does not replace those lane bodies.

Not merged into the prose, on purpose:

- No React, CSS, or HTML.
- No second copy of a table that already appears in a lane, except the section 0 decision list and the small crosswalks in section 1.
- No edit to `apps/dashboard`.
- The four source PRs stay the history of each lane. This file is the gate artifact that replaces them as the document to approve.

---

## 3. Existing-app inventory (full text)

Source: [PR #4904](https://github.com/digithings-ai/digithings/pull/4904). Original path: `docs/superpowers/plans/2026-10-01-dashboard-existing-app-inventory.md`. The inventory follows in full. It was not shortened.

# DigiQuant dashboard existing-app inventory (lane 1/3)

> **For agentic workers:** This file is an inspection record, not an implementation plan. Do not write React, HTML mockups, or visual polish from it. Later lanes own information architecture and craft. Lane 1 stops at inventory.

**Goal:** Record what the live digiquant dashboard (`apps/dashboard`, public base path `/dashboard`) actually ships today, mapped against the lab spine, so a ground-up rebuild can keep wired research and paper-book behavior and treat missing product surfaces as coming-soon.

**Architecture:** Static Next.js export. One root layout, one app frame (sidebar + main), client pages. Data is a Cloudflare Workers dashboard API plus Supabase Edge Functions for settings. twelve-x (FX Hub) and the digichat embed are separate backends. The browser does not call MCP.

**Tech Stack:** Next.js 15 static export (`output: 'export'`, `basePath: '/dashboard'`, `trailingSlash: true`), React client pages, `@digithings/ui`, Supabase Auth (flagged), Workers API, settings Edge Function, `@luxalgo/vela` on one spike route only.

**Scope of this file:** `apps/dashboard` and the operator product it serves at `digiquant.io/dashboard/`. Marketing showcase `apps/digiquant-web` is out of the product surface and is listed only so it is not mistaken for the dashboard.

**Out of scope:** UI code, HTML mockups, visual polish, live-trading paths, new dependencies.

## Global Constraints

Paste and honor on every later lane. These are product locks, not suggestions.

### Product split

- Dashboard = live product: chat strategy builder, strategies, trade journaling, digiquant tools, and solution integrations in-app.
- digiquant-web = showcase only. It is not the full tool surface.

### Every surface

1. Research + paper book first. No live-trading claims. No guaranteed-alpha claims.
2. Human gate before live. Paper is the default. Coming-soon is acceptable for live paths.
3. Job words only. No Olympus, Atlas, Hermes, or Kairos in UI labels.
4. digi* names stay lowercase in chrome. DigiQuant as a brand name is allowed.
5. LuxAlgo is the charting backbone. Do not add a competing chart stack.
6. The dashboard owns the tool surface. The marketing site only teases it.
7. Craft follows digiquant-web (finance-native ground-up information architecture). Do not re-skin the heavy shell.
8. Access-gated. This is not a public marketing page.
9. Never private-client names in chrome, copy, plans, or fixtures.

### Web UX (later lanes; recorded here so inventory does not invent a different shell)

- Sidebar = top-level only, literal labels, never icon-only: Chat / Strategies / Journal / Research|Portfolio|Signals / Tools|Integrations / Settings.
- Sticky in-page tab bar for within-subject sections. Reference: `packages/design/references/dashboard-subpage-chrome.md`.
- LuxAlgo and Gloomberb are embeds or destinations. Do not rebuild them as competitors.
- Settings taxonomy (SETTINGS-IA): Profile | Pipeline | Keys | Brokers | Notifications | Billing | About.
- Tier rule: omit tabs the plan cannot use. Never grey them and never show a lock tease.
- Observer and Brief: Notifications | Billing | About.
- Desk adds Brokers.
- Studio and above: full set.
- Deep links: `#hash` and `?tab=`. No free-form model-id picker in v0.
- Coming-soon: honest chip or empty state. Prefer omit from nav until the surface is demo-safe. If a row is listed, it is disabled plus one line of status. No fake tables or charts.
- Execution and live trading: coming-soon only.
- Craft: follow digiquant-web `:3910` (#4885), not the fat shell (#4896). Flat `--surface` and hair borders. Blur only on sticky chrome and overlays. Type toward Inter and JetBrains Mono.
- Parked #4885, #4892, and #4896 are reference only.
- No visual polish in this plan.

### Lab spine (cross-check target)

Must-haves to account for, at `apps/dashboard` with base path `/dashboard`:

Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, Pipeline, House, Settings (Profile, Pipeline, Keys, Brokers, Notifications, Billing, About), Auth, optional Ticker.

Explicit flags:

- `/strategy` is a theses redirect, not a strategy builder.
- `/why` is legacy beside Pipeline.
- Coming-soon gaps relative to the product lock: strategy builder, trade journaling, live brokers, digichat as a first-class product surface.

---

## 1. Where the app lives

| Fact | Value |
|------|--------|
| Workspace | `apps/dashboard` (npm package `dashboard`) |
| Public base path | `/dashboard` (`apps/dashboard/next.config.mjs`) |
| Export | `output: 'export'`, `trailingSlash: true`, images unoptimized |
| Production host | `digiquant.io/dashboard/` |
| Root layout | `apps/dashboard/app/layout.tsx` — theme boot script, Geist Mono variable, `AuthProvider` → `AuthGate`. No sidebar here. |
| Shell | `apps/dashboard/components/app-frame.tsx` — sidebar, mobile app bar, command palette, digichat popup, DB-down gate, FX-Hub-only guard. Mounted from `lib/auth-gate.tsx` for signed-in (or auth-off) routes. |
| Auth routes | `/login`, `/signup`, `/auth/callback` render without the app frame. |
| Primary nav source | `apps/dashboard/lib/nav.ts` `NAV` — consumed by desktop sidebar and mobile app bar. |
| In-page section chrome | `apps/dashboard/components/subpage-tab-bar.tsx` (`SubpageStickyTabBar`). Width constant `SUBPAGE_MAX` in `components/layout-constants.ts`. |

There is no `apps/dashboard/ARCHITECTURE.md`. Behavior notes live in `apps/dashboard/README.md`, `apps/dashboard/AUTH.md`, `apps/dashboard/lib/CHARTS.md`, and `apps/dashboard/lib/TABLES.md`.

`apps/digiquant-web` (`/`, `/strategies`, `/strategies/[id]`, `/pipeline`, `/subsystems/[id]`, `/changelog`, `/contact`) is the public showcase. Its strategy library renders published Nautilus tearsheets for marketing. It is not the operator tool surface and must not be rebuilt as one.

---

## 2. Lab spine cross-check

Paths below are app-relative. The browser path prefixes `/dashboard`.

| Lab must-have | App path | File | Verdict |
|---------------|----------|------|---------|
| Brief | `/` | `app/page.tsx` → `components/today/daily-brief-workspace.tsx` | **Present.** Sidebar label "Brief". Wired to Workers API portfolio/brief/performance plus run-health. |
| Holdings | `/portfolio` (default tab) | `app/portfolio/page.tsx` → `PortfolioShellInner` → `AllocationsTab` | **Present.** Section nav label "Holdings". |
| Theses | `/portfolio?tab=theses` | same shell → `ThesesTab` | **Present.** `/portfolio/theses` redirects here (preserves `date`). Thesis detail is `?thesis=<id>` on that query, not a dynamic segment. |
| Tearsheet | `/portfolio/performance` | `app/portfolio/performance/page.tsx` → `PerformanceTearsheetView` | **Present.** Entitled `house_weights_nav` (Brief+). |
| Ledger | `/portfolio/ledger` | `app/portfolio/ledger/page.tsx` | **Present.** Same entitlement. Position events, not a private accounting base table. |
| Attribution | `/portfolio/attribution` | `app/portfolio/attribution/page.tsx` → `AttributionWorkspace` | **Present.** Same entitlement. Views: Decision effectiveness, Book attribution, Audit. |
| Pipeline | `/pipeline` | `app/pipeline/page.tsx` → `PipelineClient` | **Present.** Glass-box topology, artifact ledger, call trace. |
| House | `/house?tab=corpus\|book\|profile` | `app/house/page.tsx` | **Present, not in the sidebar.** Command palette only. Read-only Corpus \| Book \| Profile. Profile pins are declared chrome, not editable Settings. |
| Settings Profile | `/settings#profile` or `?tab=profile` | `app/settings/page.tsx` | **Present, Studio+ only.** Omitted below Studio. |
| Settings Pipeline | `/settings#pipeline` | same | **Present, Studio+ only.** |
| Settings Keys | `/settings#keys` | same | **Present, Studio+ only.** |
| Settings Brokers | `/settings#brokers` | same | **Present, Desk+.** Paper only. |
| Settings Notifications | `/settings#notifications` | same | **Present, every plan.** |
| Settings Billing | `/settings#billing` or `?tab=billing` / `?checkout=success\|cancel` | same | **Present, every plan.** |
| Settings About | `/settings#about` | same | **Present, every plan.** Default when the requested tab is gated. |
| Auth | `/login`, `/signup`, `/auth/callback` | `app/login/page.tsx`, `app/signup/page.tsx`, `app/auth/callback/page.tsx` | **Present.** Supabase Google + GitHub PKCE and email. Flag `NEXT_PUBLIC_DASHBOARD_AUTH=1`. Flag off keeps the anon client. |
| Ticker (optional) | `/portfolio/tickers?ticker=` | `app/portfolio/tickers/page.tsx` | **Present.** Static page, query param, not `[ticker]`. |

### Flags the lab called out

| Path | What it is | What it is not |
|------|------------|----------------|
| `/strategy` | `app/strategy/page.tsx` → `StrategyToAnalysisRedirectPage`. With `?thesis=` it goes to `thesisDetailHref`. Otherwise `/portfolio?tab=theses`. | Not a strategy builder, not a strategy library, not chat. |
| `/why` | `app/why/page.tsx` still mounts `WhyClient` ("The read" \| "Deliberations"). Not in `NAV`. Sidebar highlights Pipeline when the path matches `/why` because Pipeline absorbed the old Why destination, but the page itself still renders. | Not the Pipeline glass-box. Not deleted. Treat as legacy beside Pipeline. |

`/research` and `/library` are named `*ToWhy*` in `components/legacy-spa-redirect.tsx` but their `router.replace` target is Pipeline (`buildPipelineHref`), not `/why`.

### Coming-soon gaps (product lock vs this tree)

| Gap | Current code | Honest status for a rebuild |
|-----|--------------|-----------------------------|
| Strategy builder | No route, no component, no MCP tool call from the dashboard. `/strategy` redirects to theses. | **Missing.** Coming-soon until a demo-safe builder exists. Do not pretend theses are the builder. |
| Trade journaling | No route, no journal model, no nav item. Ledger is pipeline position events (OPEN / ADD / EXIT / TRIM), not a user trade journal. | **Missing.** |
| Live brokers | Brokers tab hard-codes `env: 'paper'` in `lib/settings-api.ts` (`connectBrokerApiKey`, `connectBrokerOAuth`). UI copy is "Connect Alpaca (paper)" and "Save API key (paper)". IBKR is labeled beta for paper/dev. No live-env control. | **Paper wired (Desk+). Live is coming-soon only.** |
| digichat | Not a route. `DigichatPopup` in the app frame iframes digichat `/embed?layout=embed` for Desk / Studio / Enterprise. Observer and Brief get an upgrade CTA and no iframe. Kill switch `NEXT_PUBLIC_DIGICHAT_POPUP=0`. | **Embed exists for entitled plans. Not a sidebar Chat destination and not a strategy builder.** Treat first-class Chat as coming-soon relative to the target spine. |

---

## 3. Full route tree

App-relative paths. Public URL is `/dashboard` + path + trailing slash.

### Live pages

| Path | Role | In sidebar `NAV`? |
|------|------|-------------------|
| `/` | Brief (daily decision workspace) | Yes — "Brief" |
| `/portfolio` | Holdings, or Theses when `?tab=theses` | Yes — "Portfolio" (holdings and theses share this item) |
| `/portfolio/performance` | Tearsheet | No (section tab) |
| `/portfolio/ledger` | Ledger | No (section tab) |
| `/portfolio/attribution` | Attribution | No (section tab) |
| `/portfolio/tickers` | Ticker dossier `?ticker=` | No (links and command palette) |
| `/pipeline` | Pipeline glass-box. Deep link `?date=&stage=&node=` | Yes — "Pipeline" |
| `/why` | Legacy reasoning workspace `?why=read\|deliberations` | No |
| `/house` | House identity `?tab=corpus\|book\|profile` | No |
| `/settings` | Settings tabs | Footer control, not a `NAV` row |
| `/settings/brokers/callback` | Alpaca OAuth return. Posts paper connect, then back to Brokers | No |
| `/twelve-x` | FX Hub client product. Tabs below. Gated by `fx_hub` | Yes — "FX Hub", only when `canFxHub` |
| `/research/vela-spike` | LuxAlgo Vela spike. `?symbol=` (default `BTC-USD`), `?timeframe=` (default `1d`) | No |
| `/login`, `/signup`, `/auth/callback` | Auth, no app frame | No |

### Client redirects (no content of their own)

Implemented in `components/legacy-spa-redirect.tsx` unless noted.

| Path | Lands on |
|------|----------|
| `/strategy` | `/portfolio?tab=theses`, or thesis detail when `?thesis=` is set |
| `/why` | **Does not redirect.** Still a page. See flag above. |
| `/research` | Pipeline, preserving `date` |
| `/research/vela-spike` | **Does not redirect.** Child route stays. |
| `/library` | Pipeline node, preserving `date` and `docKey` |
| `/observability` | `/pipeline` (query string kept) |
| `/architecture` | `/pipeline` (query string kept) |
| `/performance` | `/portfolio/performance` |
| `/portfolio/period` | `/portfolio/performance` |
| `/portfolio/theses` | `/portfolio?tab=theses` (preserves `date`) |
| `/system` | `/pipeline` (`app/system/page.tsx`, local redirect) |

Path-form thesis URLs (`/portfolio/theses/<id>`) are not served. Static export 404s them. In-app links use `thesisDetailHref()`.

### FX Hub tabs (`/twelve-x`)

From `TWELVE_X_TABS` in `components/twelve-x/TwelveXClient.tsx`:

Today, Consensus, Trades, Matrix, Events, How it works.

Brief, idea, and track-record panels are drill-ins (`?brief=`, `?tab=trades`, `?tab=matrix`), not extra sidebar items. An FX-Hub-only invitee (product grant, free tier) sees only FX Hub. Brief, Portfolio, Pipeline, Gloomberb, and desk Settings are hidden. Settings becomes a sign-out / invite card (`FxHubAccount`).

### Portfolio section tabs

`components/portfolio/PortfolioSectionNav.tsx`:

| Label | Href |
|-------|------|
| Holdings | `/portfolio` |
| Theses | `/portfolio?tab=theses` |
| Tearsheet | `/portfolio/performance` |
| Ledger | `/portfolio/ledger` |
| Attribution | `/portfolio/attribution` |

`VALID_PORTFOLIO_TABS` on the shell page is holdings and theses only. Tearsheet, Ledger, and Attribution are separate routes that reuse the same bar.

### Pipeline stages (in-page, not routes)

`lib/pipeline-topology.ts`: Inputs (Preflight, Attention plan) → Research (Alt-data, Institutional, Macro, Asset-classes, Sectors) → Synthesis (Consolidate bias, Daily digest) → Selection (Thesis framing, Screener, Analysts, Deliberation, PM direction, Risk sizing) → Decision (Commit) → Learning (Beliefs fold).

Three inspection surfaces on the same page: topology, All artifacts, Call trace (`run_event_trace`). Inputs call rows are an admitted persistence gap. The UI says so.

### Why tabs (legacy page)

`lib/why-tabs.ts`: The read (`?why=read`), Deliberations (`?why=deliberations`). Documents archive was removed. Per-day documents live on Pipeline.

### House tabs

Corpus, Book, Profile. Book copy is "House ETF paper book" and "Paper book — no live-trading path". Not an editable settings surface.

### Shell chrome that is not a route

| Chrome | File | Behavior |
|--------|------|----------|
| Sidebar | `components/sidebar.tsx` | `NAV` plus external "Gloomberb Terminal" (`GLOOMBERB_TERMINAL_URL`). Collapses to a 72px rail; labels become `md:sr-only` with a tooltip. That is icon-only on desktop when collapsed. |
| Mobile app bar | `components/mobile-app-bar.tsx` | Same `NAV`. |
| Command palette | `components/command-palette.tsx` | ⌘K. Brief, Holdings, Theses, Tearsheet, Ledger, Attribution, House corpus, Pipeline, digest node, selection stage, FX Hub, Settings, theses, tickers, twelve-x drills. |
| digichat popup | `components/digichat-popup.tsx` | Bottom-right launcher. See coming-soon gap. |
| DB-down gate | `components/db-unavailable.tsx` | When `NEXT_PUBLIC_DASHBOARD_API_URL` is missing or the fetch fails, non-exempt routes swap to an unavailable card. Exempt prefixes in `DB_EXEMPT_PREFIXES`: `/system`, `/settings`, `/twelve-x`, `/architecture`, `/library`, `/observability`, `/performance`, `/research`, `/strategy`, `/portfolio/theses`, `/house`. |
| Page chrome comment in README | `app/layout.tsx` | README still describes a `.qn-page-chrome` crumb strip. The current root layout does not render that strip. The frame is sidebar + main. |

Sidebar `NAV` today (literal labels, with icons):

1. Brief → `/`
2. Portfolio → `/portfolio`
3. Pipeline → `/pipeline`
4. FX Hub → `/twelve-x` (product-gated)

Settings is a footer button (`components/sidebar-settings.tsx`), not one of those four.

This is not the target sidebar (Chat / Strategies / Journal / Research|Portfolio|Signals / Tools|Integrations / Settings).

---

## 4. Settings surfaces

Source of truth for visibility: `SETTINGS_TAB_DEFS` in `lib/entitlements.ts`. The page omits tabs the effective tier cannot use. It does not grey them.

| Effective tier | Tabs shown |
|----------------|------------|
| Observer (`free`), Brief | Notifications, Billing, About |
| Desk | those, plus Brokers |
| Studio, Enterprise, creator floor at Studio | Profile, Pipeline, Keys, Brokers, Notifications, Billing, About |

Deep link resolution (`resolveSettingsTab`): `?tab=` and `?checkout=success|cancel` win, then `#hash`, then the first visible tab. A gated hash is ignored.

API client: `lib/settings-api.ts`. Session JWT to the settings Edge Function (`digiquant/supabase/functions/settings`). Billing checkout and portal are sibling functions. README states Edge deploy is blocked on vault + `broker_connections` (K3). The UI is written against that contract anyway.

There is no free-form model-id picker. Keys seal a provider name only: openai, anthropic, groq, openrouter, xai, gemini.

### Profile (Studio+)

Controls a versioned overlay. Saves append a new version. They do not mutate the tip in place and they cannot edit the reserved `house` key. Optimistic concurrency via last-seen version id (409 reloads).

Investment profile (`lib/settings/schemas/investment_profile.v1.json`): `risk_tolerance`, `horizon_years` (1–50), `liquidity_needs`, `base_currency`, `tax_jurisdiction`, `esg_preference` (`none` \| `tilt` \| `strict`), `excluded_sectors`, `experience_level` (`novice` \| `intermediate` \| `expert`).

Asset preferences (`asset_preferences.v1.json`): named `watchlists`, `custom_universe`, `excluded_tickers` (win over inclusion), `excluded_sectors`.

Persistence name in code and README is still the retired `olympus_profile_config` table. That string is a storage identifier, not a UI label. Do not surface it.

### Pipeline (Studio+)

Overlay knobs on the same profile tip: watchlist, themes, `research_budget_usd`.

Schedule: 7 weekdays × 3 stages (`research`, `deliberation`, `execution`) from `pipeline_schedule.v1.json`. Defaults all on.

Execution policy (`execution_policy.v1.json`): `calendar_mode` is fixed to `venue_calendar`. `on_closed_session` is fixed to `defer`. `respect_early_close` defaults true. `permitted_venues` is an optional preference list. A scheduled execution day cannot force a closed session.

Also reads `GET /settings/jobs` (skip reasons such as `no_credentials`). A hop counts as proven only when status is `succeeded`.

### Keys (Studio+)

Seal and revoke BYOK LLM keys. After save the UI shows fingerprint, provider, status, `last_used_at`. House research keeps operator keys. Overlay jobs are the ones that unseal the user key.

### Brokers (Desk+)

- Alpaca OAuth: `env=paper`, `state` in sessionStorage, return path `/settings/brokers/callback`.
- Alpaca API key: paper only.
- IBKR API key: beta copy, still paper.
- List rows: fingerprint, broker, env, status, `last_used_at`. Secrets are stripped (`SAFE_KEYS` in `brokers-tab.tsx`).
- `GET /settings/fills`: paper-fill fingerprints. A fill proves the hop only together with an Alpaca paper OAuth connection. An API-key paper row does not.

Live venue connect is not in this UI.

### Notifications (all plans)

PATCH prefs: `daily_digest`, `holding_change_alerts`, `execution_alerts`. Digest hour is not a free control in the tab (copy says the saved email and toggles are what dispatch uses).

`GET /settings/notifications/log` lists delivery events. The digest remaining-hop needs a `digest:` log key, inbox confirmation, and `daily_digest` on. Inbox confirmation is operator-side, not a checkbox the member can self-prove.

### Billing (all plans)

Links to checkout and customer portal for Brief, Desk, and Studio. Observer is free and is not a Stripe product. Display catalog in README: Brief $10/mo or $96/yr, Desk $30/mo or $288/yr, Studio $100/mo or $960/yr. Default interval is annual. If annual prices are unset and checkout returns `PRICE_NOT_CONFIGURED`, the UI falls back to monthly. "Billing not configured" when Supabase URL is absent or `NEXT_PUBLIC_STRIPE_BILLING_ENABLED=0`.

The About panel must not render Stripe ids.

### About (all plans)

`RemainingHopStatus` plus `SettingsContent` (version, data-source host, command palette). Member-scoped reads. Observer can see unproven hops without being able to write Studio fields.

Remaining hops (`lib/remaining-hops.ts`):

| Hop id | Meaning |
|--------|---------|
| `browser_stripe_checkout` | Studio/enterprise subscription evidence. Brief or Desk checkout does not prove it. |
| `alpaca_paper_oauth_connect` | Active Alpaca paper OAuth. API key does not prove it. |
| `overlay_daily_claimed` | Overlay job `succeeded`. |
| `paper_fill_mirrored` | A fill with a symbol plus Alpaca paper OAuth. |
| `digest_email_received` | Digest log + inbox confirmed + pref on. |

Blockers are a closed vocabulary (`plan_tier_not_studio`, `missing_stripe_ids`, `subscription_not_active`, `alpaca_api_key_not_oauth`, `no_alpaca_paper_oauth`, `overlay_persist_disabled`, `overlay_legacy_book_unique`, `overlay_not_succeeded`, `fill_without_oauth`, `no_paper_fill`, `digest_pref_off`, `no_digest_log`, `digest_inbox_unconfirmed`).

### Settings routes that are not tabs

`/settings/brokers/callback` completes Alpaca paper OAuth and returns to Brokers. It is not a seventh settings section.

---

## 5. Wired vs stub

The dashboard has **no MCP client**. A search of `apps/dashboard` for MCP imports is empty. digiquant tools (`run_backtest`, `optimize_strategy`, and the rest) stay on the digigraph/digiquant side. Nothing in this UI calls them.

| Surface | Backend | Wired or stub |
|---------|---------|----------------|
| Brief, Portfolio holdings/theses, ticker dossier | Workers API. `DashboardProvider` requires `NEXT_PUBLIC_DASHBOARD_API_URL` and loads `getFullDashboardData()` plus `GET /portfolio`, `/brief`, `/performance`. | **Wired** when the worker is configured. Unconfigured or failed fetch trips the DB-down gate (Brief and Portfolio are not exempt). |
| Tearsheet, Ledger, Attribution, run health | Workers allowlisted table reads and specific routes (`/kpis/live`, `/nav-series`, `/benchmarks`, `/ledger`, observability queries). Market marks: `GET /v1/market/closes` and `GET /v1/market/tickers` when `NEXT_PUBLIC_MARKET_DATA_URL` is set. Empty market config fails closed to an em dash. No Supabase price fallback. | **Wired.** Entitlement can lock the page before fetch (`house_weights_nav`). |
| Pipeline topology and call trace | Same worker. Trace view is `run_event_trace` (legacy compat view name dropped). | **Wired** for persisted artifacts. State-only nodes and missing Inputs calls are labeled gaps, not filled with invented rows. |
| twelve-x | Its own Supabase project (`lib/twelve-x/supabase.ts`, `isTwelveXConfigured`). Not the main dashboard API. DB-gate exempt. | **Wired** when that project is configured. Product gate (`ClientProductGate`, invite redeem) in front. |
| Settings writes | Settings Edge Function, JWT. | **Client wired.** Server deploy of the function is documented as blocked on K3. Treat production proof as unconfirmed from this repo read. |
| Billing | Stripe checkout/portal Edge Functions. | **Wired** when Supabase URL is set and billing is not forced off. Otherwise an explicit not-configured state. |
| Auth | Supabase Auth PKCE. | **Wired behind a flag.** Default flag off. Cloudflare Access is the hosting gate until cutover (`AUTH.md`). |
| digichat popup | digichat embed origin, plan-proof HMAC, operator LLM keys. | **Wired for Desk+** when env and CSP `frame-src` allow it. Baseline is an upgrade panel, not a stub chat. |
| Vela spike | `GET /bars` on digiquant (`NEXT_PUBLIC_DIGIQUANT_BASE_URL`, default `http://127.0.0.1:8001`). Keyless Gloomberb history. Headless `@luxalgo/vela` with offline `data`. QuantCharts is an outbound link to `https://app.luxalgo.com/`. | **Wired as a research spike, not the app chart backbone.** Copy says bars must not feed validate → backtest → optimize → export. |
| Gloomberb | External terminal URL in the sidebar. Per-ticker links (`gloomberbTickerUrl`) on holdings, theses vehicles, deliberations, ticker dossier. twelve-x calendar prefers gloomberb rows over forexfactory twins. | **Destination and data source. Not an in-app terminal.** |
| House profile pins | Static constants in `lib/house-identity.ts`. Corpus sample keys come from loaded docs and fail soft. | **Declared chrome.** README says editable profile waits on ProfileConfig DB. Settings Profile is the real editor for non-house overlays. |
| Strategy builder | — | **Absent.** |
| Trade journal | — | **Absent.** |
| Live broker / live execution UI | — | **Absent.** Paper connect is the only broker write. |
| Chart engines on book surfaces | `lightweight-charts` for time series (`lib/lw-chart.tsx`), recharts for categorical/composition, SVG finance-tearsheet primitives for the print tearsheet. | **Wired to book data.** They are the current stack and conflict with the LuxAlgo-backbone lock. See design debt. |
| Screenshot fixtures | `apps/dashboard/fixtures/screenshots/` | **1×1 placeholders** (24 PNGs, 70 bytes each). Not pictures of the product. |

`examples/bff-snapshots-route.example.ts` is an example, not a route in the static export.

---

## 6. Feature state (product lock checklist)

### Strategy builder

Absent. `/strategy` redirects to theses. digiquant-web `/strategies` is a public tearsheet gallery of published backtests. That gallery stays on the showcase. It is not the in-app builder and it is not a second tool surface.

### Chat

digichat popup only, and only as an entitled embed. It sends sanitized page HTML and visible text as prompt prefix. It does not render a dashboard-native transcript, and it does not build or save a strategy. Observer/Brief see a CTA. Target sidebar label "Chat" does not exist.

### Journaling

Absent. Do not rename Ledger to Journal. Ledger is the house paper book's position-event log.

### Charts and LuxAlgo

Book and FX charts do not use LuxAlgo.

| Engine | Where | Notes |
|--------|-------|-------|
| lightweight-charts | `components/portfolio/DecisionEdgeChart.tsx` via `lib/lw-chart.tsx` | Time series. Canon note in `lib/CHARTS.md` is historical for this app. |
| recharts | Sleeve stack, attribution bars, conviction buckets, parts of twelve-x consensus | Categorical or stacked composition. |
| SVG tearsheet | `components/tearsheet/DashboardTearsheetView.tsx` (`TimeSeries`, `SignedBars` from `@digithings/ui`) | Print/PDF path. Not canvas. |
| `@luxalgo/vela` | `components/research/VelaSpikeChart.tsx` on `/research/vela-spike` only | Headless, offline data, attribution link required. |

A rebuild that keeps lightweight-charts or recharts as a second product chart stack violates the LuxAlgo lock. The spike is the only in-app LuxAlgo embed to study. Gloomberb remains the price source for that spike, not a chart to clone.

### Brokers

Desk+ paper Alpaca (OAuth and API key) and IBKR beta API key. Fills list is paper. Live is coming-soon. Human gate before any live cutover stays in force (`docs/vision/digiquant.md`, `docs/vision/dashboard.md`).

### Tearsheets

`/portfolio/performance` is the operator tearsheet: accounting NAV (`public_accounting_nav_history` via `getPerformanceBundle`), benchmark excess, contribution, open-position outcomes. Closed fills stay on Ledger. Legacy `/performance` and `/portfolio/period` redirect here.

This is the house paper book tearsheet. It is not the digiquant-web strategy-library tearsheet.

### Pipelines

`/pipeline` is the operator view of the daily research → portfolio graph (stages in section 3). It is wired to persisted documents and `run_event_trace`. Settings Pipeline is a different thing: weekday schedule and overlay budget for a Studio workspace, not the glass-box.

### Research / portfolio / signals

Job words in the current UI are Brief, Portfolio, Pipeline, Holdings, Theses, Tearsheet, Ledger, Attribution. There is no sidebar item named Research or Signals. Research artifacts are Pipeline nodes and the Why "read" tab. Signals show up inside Brief and deliberations, not as their own destination.

---

## 7. Design debt and reference-only material

Keep these as evidence. Do not re-skin them into the new shell.

| Item | Why it is debt or reference-only |
|------|----------------------------------|
| Current sidebar IA (Brief / Portfolio / Pipeline / FX Hub) | Real product today. Not the target top-level list. |
| Collapsed sidebar (`md:w-[72px]`, label `md:sr-only`) | Icon-only rail. Target lock is literal labels, never icon-only. |
| Icons inside section tabs (Portfolio, Why, twelve-x) | Tab bar reference asks for literal words. Icons are extra, not a substitute, but the collapsed sidebar is the actual violation. |
| `/why` still mounted | Legacy reader next to Pipeline. Bookmarks and the DB-exempt list do not send `/why` to Pipeline. `/research` and `/library` do. |
| `/strategy` name | Implies a builder. It is a theses redirect. |
| Geist Mono as the only voice (`app/layout.tsx`, "BLEND v0.1") | Current app. Craft lock for the rebuild is Inter + JetBrains Mono. |
| `packages/design/references/dashboard-subpage-chrome.md` | Still the sticky-tab and flat-surface reference (blur only on sticky/overlay, `--surface`, `--hair`). Its type section still says Instrument Serif and Geist. That type note loses to the Inter + JetBrains Mono lock. |
| `lib/CHARTS.md` lightweight-charts ruling | Accurate for the current book charts. Superseded as a future chart-stack decision by the LuxAlgo backbone lock. |
| Parked #4885, #4892, #4896 | Reference only. Craft follows #4885 (digiquant-web), not the fat #4896 shell. No visual polish in this lane. |
| `docs/dashboard-audits/DASHBOARD_FRONTEND_AUDIT.md` (2026-06-17) | Historical. It describes empty actions and zeroed metrics from that date. Do not treat it as the current wiring map. Section 5 of this file is the current code map. |
| `docs/superpowers/plans/2026-06-24-twelve-x-dashboard-redesign.md` and other `olympus-*` plan titles | Historical plans. Retired codenames must not re-enter UI labels. |
| Screenshot PNGs under `apps/dashboard/fixtures/screenshots/` | Contract fixtures for Pipeline stages and artifact families (`lib/screenshot-manifest.ts`). All 24 files are 70-byte placeholders. Not visual reference. |
| `apps/digiquant-web` landing `DashboardScene` / `DashboardPortfolioPanel` | Showcase illustration. Not the operator app. |
| Retired identifiers still in code | `olympus_profile_config` table name, `olympus-theme` legacy localStorage key (`components/theme-provider.tsx`, read-and-migrate only), comments and generated DB types that mention the old trace view. UI strings checked in this pass use job words (Brief, Portfolio, Pipeline, research, portfolio, execution). Do not "fix" storage names in a UI rebuild. |
| House page off-nav | Easy to miss in a route audit. It is a lab must-have and it exists. |
| Dual "Pipeline" words | Glass-box route vs Settings tab. A new IA has to keep them distinct. |
| Entitlement copy in page comments | Some comments still say "Baseline+". Product names are Observer / Brief / Desk / Studio. `house_weights_nav` unlocks at Brief. |

What is worth keeping as behavior, regardless of chrome:

- Paper default and calendar veto (`defer` on a closed session).
- Fail closed: missing marks, missing fills, and locked tiers render an em dash or a locked surface, not invented P&L.
- One NAV series for Brief and Tearsheet (`getPerformanceBundle`). Live marks are an overlay badge, not a second set of books.
- Settings tabs omitted by tier, hash and `?tab=` deep links, no model-id picker.
- Static-export query routes for thesis id and ticker (no dynamic segment that 404s after deploy).
- Access gate. Auth flag plus hosting access. FX Hub is a client product, not a public page.
- Gloomberb and LuxAlgo as links or embeds, not cloned terminals.
- No private-client names in chrome.

---

## 8. Screenshot and file inventory

No new screenshots were taken. This lane does not run the UI.

Pipeline glass-box fixture contract (`fixtures/screenshots/manifest.json`):

- Stages × desktop/mobile: inputs, research, synthesis, selection, decision, learning.
- Artifact families: attention-plan, research-segment, fanout-alt-data, fanout-analyst, digest, deliberation, pm-direction, pm-rebalance, commit, beliefs, call-trace, artifact-ledger.
- On disk: 24 PNGs, each 70 bytes. Placeholders until an operator capture replaces them. Vitest only checks path and PNG magic.

Key source files for a later lane (read these, do not clone the shell):

| Concern | Path |
|---------|------|
| Nav | `apps/dashboard/lib/nav.ts` |
| Frame | `apps/dashboard/components/app-frame.tsx`, `components/sidebar.tsx` |
| Redirects | `apps/dashboard/components/legacy-spa-redirect.tsx` |
| Brief | `apps/dashboard/app/page.tsx`, `components/today/daily-brief-workspace.tsx` |
| Portfolio | `apps/dashboard/components/portfolio/PortfolioShellInner.tsx`, `PortfolioSectionNav.tsx` |
| Tearsheet | `apps/dashboard/app/portfolio/performance/page.tsx` |
| Pipeline | `apps/dashboard/app/pipeline/page.tsx`, `lib/pipeline-topology.ts` |
| Legacy Why | `apps/dashboard/app/why/page.tsx`, `lib/why-tabs.ts` |
| House | `apps/dashboard/app/house/page.tsx`, `lib/house-identity.ts` |
| Settings | `apps/dashboard/app/settings/page.tsx`, `lib/entitlements.ts`, `lib/settings-api.ts` |
| Auth | `apps/dashboard/lib/auth-gate.tsx`, `apps/dashboard/AUTH.md` |
| Ticker | `apps/dashboard/app/portfolio/tickers/page.tsx` |
| Vela spike | `apps/dashboard/app/research/vela-spike/page.tsx`, `lib/vela-bars.ts` |
| digichat embed | `apps/dashboard/components/digichat-popup.tsx`, `lib/digichat-popup.ts` |
| Data load | `apps/dashboard/lib/dashboard-context.tsx`, `lib/api-client.ts` |
| Product vision | `docs/vision/dashboard.md`, `docs/vision/digiquant.md` |
| Settings IA | `docs/agent-backlog/execution-tenancy/SETTINGS-IA.md` |
| Subpage chrome reference | `packages/design/references/dashboard-subpage-chrome.md` |

---

## 9. Lane boundary

Lane 1 is this inventory.

Lane 2 (not started here) would propose the new information architecture against the target sidebar and the lab spine, using coming-soon rules for builder, journal, live brokers, and first-class digichat.

Lane 3 (not started here) would be craft, and only after IA is accepted. It follows digiquant-web #4885, LuxAlgo as the chart embed, and Gloomberb as a destination. It does not re-skin #4896.

No implementation tasks belong in this file.

## 4. Data and backend map (full text)

Source: [PR #4905](https://github.com/digithings-ai/digithings/pull/4905). Original path: `docs/superpowers/plans/2026-10-01-digiquant-dashboard-data-map.md`. The data map follows in full. It was not shortened.

# digiquant dashboard data map (rebuild lane 2)

**Status:** plan only. No UI. Written 2026-10-01 against `develop` @ `0b2c2cf10`.

**Lane:** 2 of 3 for the dashboard ground-up rebuild. Lane 1 is the showcase / craft bar on digiquant-web. Lane 3 composes dashboard surfaces. This file is the data inventory those surfaces may wire. It does not authorize a page, a component, or a class-name restyle.

**Issue:** [GitHub #4895](https://github.com/digithings-ai/digithings/issues/4895).

---

## Canon (honor these; do not relitigate)

Cited from #4895, [ADR-0026](../../adr/0026-retire-olympus-atlas-hermes-kairos.md), [`digiquant/AGENTS.md`](../../../digiquant/AGENTS.md), and the LuxAlgo wrap notes in that same guide.

| Lock | What it means for this map |
|------|----------------------------|
| Dashboard owns the product | Strategies, trade journaling, the digiquant tool catalog, and solution integrations are dashboard surfaces. |
| digiquant-web is showcase only | Marketing may display published tearsheets, videos, and a narrative of the workflow. It does not own strategy CRUD, the journal, the tool catalog, or integration connect/revoke. |
| Research and paper first | The book the dashboard reads today is a research / paper book. Live venue cutover stays behind a human gate. |
| No live-trading claims | `ExecutionVenue` lists live values so the vocabulary is complete. Nothing in this map is a license to say a strategy is live, routed, or filled at a venue. |
| Job words, not retired brands | User-facing words are research, portfolio, and execution. This document uses those words. Stored migration filenames and historical ADR bodies keep older names; do not copy them into UI copy. |
| lowercase digi* | digiquant, digigraph, digivault, digichat, digisearch, digikey, digifetch. Code identifiers keep language casing. |
| LuxAlgo is the chart backbone | Chart series for the rebuild are LuxAlgo presets, edge reports, and trackers, plus digiquant series explicitly bound into that backbone. Do not plan a second chart engine. |
| Access-gated | The operator dashboard is not an anonymous product. Public showcase reads are a separate, curated allowlist. |
| No private-client names | This map names tables, product keys, and routes. It does not name people, inboxes, or client organizations. |
| Coming-soon | A surface with no persisted, access-gated read is `coming-soon`. Do not invent rows, fills, or P&L to fill the gap. |

---

## How to read a row

| Status | Meaning |
|--------|---------|
| **wired** | A reader exists today (dashboard, dashboard-api, or the public showcase) and the store is the source of truth. |
| **stored, unwired** | The table or tool exists. The dashboard does not read it as a product surface yet. |
| **coming-soon** | The product lock wants the surface. There is no durable, access-gated store for it. Lane 3 renders an honest empty state, not sample numbers. |
| **human-gate** | Broker, crypto, or live-venue adjacency. Planning may name the shape. Implementation that touches `digiquant/brokers/`, vault envelopes, or a live enum is not this PR and is not agent-mergeable. |

House workspace id (selector, not a secret): `6b753576-ced9-5319-9bfa-c5d0aacd9319` (`houseBook()` / `house_workspace_id()`). System workspace id: `1105372f-4109-5815-be5a-21091ccfc8ad`.

---

## 1. Store topology

Two Supabase projects. Free-tier slot count is the reason there is no third project ([ADR-0021](../../adr/0021-digiquant-supabase-project-topology.md)).

| Store | What it is | Who reads it |
|-------|------------|--------------|
| **core** Postgres (Supabase display name `core`; local alias `project_id "digiquant-research"`) | Shared digiquant backend: house book, documents, strategy store, tenancy, sealed credentials, accounting, run health, R2 pointer registry. Migrations: `digiquant/supabase/migrations/` (`001`–`139`). Narrative inventory: `digiquant/supabase/SCHEMA.md` (prose there still uses older headings; **current object names** are the post-rename names in §2). | Dashboard via `GET /v1/tables/:table` and the eight dashboard-api routes. Showcase via curated `public_*` views and `strategy_tearsheets`. |
| **FX Hub** Postgres (separate project) | Research feed for the existing `/twelve-x` route. Not the strategy store, not the journal, not the tool catalog. | `apps/dashboard/lib/twelve-x/fetch.ts` with that project's own session. The shell DB-gate must not swallow this route. |
| **R2** | Immutable market-data generations and archived document/checkpoint payloads. Pointers live in `archive_objects`. | digiquant price/macro readers; dashboard market API (`GET /v1/market/*`). Not a substitute for the house book. |
| **digivault** | Markdown note corpora. D1 `notes` for one vault, and core `knowledge_notes` for the finance/product corpora. | digivault MCP / HTTP. Dashboard does not query it today. |
| **digigraph** | Orchestration only. LangGraph checkpoints may sit in core. It does not own the book, the strategy store, or the journal. | `POST /workflow`, thread state/history. Dashboard chat popup talks to digichat, not directly to these routes. |
| **digiquant process** | Nautilus validate → backtest → optimize → export. In-memory / job results unless a writer persists them. | HTTP `:8001` and the digiquant MCP server. |
| **Settings edge** | Session-JWT BFF over core for profile, brokers, BYOK keys, billing, invites, jobs, fills. | `apps/dashboard/lib/settings-api.ts`. |

Dropped from core (do not plan a reader): `price_history`, `price_technicals`, `price_history_tickers`, `public_price_latest` (migration 127), and `deliberation_sessions`, `deliberation_rounds`, `deep_dive_triggers` (migration 128). Prices are R2. Deliberation narrative lives in `documents`.

There is no `digistore` service in this repo. digigraph project-mode dataset tools (`digistore_list` and siblings) are session scratch for an agent run, not dashboard product data.

---

## 2. Core tables the dashboard can show

Names below are the **current** names after the phase-B rename (migration 134) and the diagnostics rename (migration 137). Compatibility views with the old prefix may still exist until phase C (migration 135) is applied everywhere. New dashboard readers use the unprefixed name.

### 2.1 House book (wired)

Group A. Readers pin `workspace_id` to house except where the column does not exist.

| Object | Key | Shape the UI may trust | Access |
|--------|-----|------------------------|--------|
| `daily_snapshots` | `date` | `run_type` `baseline` \| `delta`, `baseline_date`, `regime`, `market_data`, `segment_biases`, `actionable`, `risks`, `snapshot`, `digest_markdown` | Shared teaser. Date-only. No `workspace_id`. |
| `positions` | `(workspace_id, date, ticker)` plus legacy `(date, ticker)` | Weight, prices, thesis pointer, rationale. Public view strips notes. | House pin on the API. |
| `position_events` | `(workspace_id, date, ticker)` | `OPEN` \| `ADD` \| `EXIT` \| `TRIM`, fill, weights. Ledger SSOT. Never derive fills from weight diffs. | House pin. |
| `nav_history` | `(workspace_id, date)` | Legacy NAV. Rollback target only. | Prefer accounting views. |
| `portfolio_metrics` | `(workspace_id, date)` | Sharpe, vol, drawdown, exposure. | House pin. |
| `theses` | `(date, thesis_id)`; partial unique `(date, topic_key)` | Daily market opinion. No `workspace_id` in the tenancy wave. | Date-only teaser. |
| `thesis_vehicles` | `(date, thesis_id, ticker)` | Vehicle map. | Date-only. |
| `documents` | `(workspace_id, date, document_key)` | JSONB artifact. `doc_type` allowlist in §6. Overlay keys prefixed `overlay/{workspace_id}/`. | House+system pin on the tables route. |
| `instruments` | ticker | Reference rows. | Date-only / shared. |
| `analyst_coverage` | `(date, ticker)` | Analyst ↔ ticker index. | Shared. |
| `decision_log` | run date + ticker | Decision rows for dossier / observability. | Tables allowlist. |
| `position_attribution` | — | Per-position attribution reads. | Tables allowlist. |
| `macro_series_observations` | `(source, series_id, obs_date)` | FRED / FX / crypto fear-and-greed. Not dropped. | Shared reference. |

Public curated views (showcase **and** dashboard performance). The SELECT list is the privacy allowlist. Base accounting tables are not granted to `anon`.

| View | Backed by | Rule |
|------|-----------|------|
| `public_portfolio_positions` | `positions` | Latest book, performance columns only. Excludes rationale, notes, thesis id, conviction, stops, targets. |
| `public_nav_history` | `nav_history` | Legacy series. Do not silently fall back here when `public_accounting_nav_history` is missing (`PGRST205` fails closed). |
| `public_accounting_period_status` | accounting periods | Tip periods including incomplete. Incomplete stays explicit. |
| `public_finalized_nav` | final tip | `contract = finalized_accounting`. |
| `public_accounting_nav_history` | final tip, else labeled legacy | `series_seam` on a source flip. Same date never mixes sources. |
| `public_daily_realized_attribution` | final tip | Empty when there is no final tip. No lookback substitution. |

Accounting base tables (service role writes; authenticated own-workspace SELECT): `accounting_periods`, `accounting_holdings`, `accounting_contributions`.

NAV contract the dashboard already computes and dashboard-api echoes:

- Day return is equity delta, null across a seam or a calendar gap greater than 4 days.
- Alpha and information ratio need at least 20 overlapping daily pairs. Below that they are null.
- `provenance.contract` is `finalized_accounting` or `legacy_estimate`. Live quote overlays are `live marks` and must not wear the finalized badge.
- `provenance.marks` is `stored` \| `market_api` \| `unavailable`.

### 2.2 Strategy store (wired for publish; dashboard product ownership is the rebuild)

Migration 046. This is the durable strategy library. digiquant-web already reads `strategy_tearsheets` for the showcase. **The product owner is the dashboard.**

| Table | Key | Columns that matter | Access |
|-------|-----|---------------------|--------|
| `strategies` | `id` text | `symbol`, `label`, `engine`, `config` jsonb, `enabled`, `version` | Anon SELECT today (showcase). Dashboard product reads should be the access-gated path, not a second anon app. |
| `strategy_calibrations` | `strategy_id` | Fitted `calibration` jsonb | **Private.** No anon policy. |
| `strategy_trades` | `id` bigint | `entry_ts`, `exit_ts`, `side`, prices, `qty`, `pnl`, `return_pct` | Anon SELECT on the published book. These are backtest/publish trades, not a user journal. |
| `strategy_tearsheets` | `strategy_id` | `metrics` jsonb (full `TearsheetData`), `equity_curve` jsonb, `as_of` | Anon SELECT. Showcase and library. |
| `strategy_signals` | `strategy_id` | `position` `long` \| `flat` \| `short`, `last_signal_date`, `last_price`, `as_of` | Anon SELECT. Delayed public signal, not a live order. |

Code registry (`digiquant.strategies`, `strategy_aliases`) is the compile-time list the engine will run. The table is what publish wrote. A strategy can be registered and not published. A published row can lag the registry. The dashboard shows published rows and may list registry names as runnable; it does not invent a third catalog.

### 2.3 Run health and pipeline trace (wired on `/pipeline`)

| Object | Role |
|--------|------|
| `run_health` | Operator health (renamed from the diagnostics view). |
| `run_diagnostics` | Per-run diagnostic rows. |
| `run_event_trace` | Trace the pipeline page reads. Anon SELECT retained on this one object. |
| `node_runs`, `provider_calls`, `provider_attempts`, `run_events` | Provider/node telemetry. Service-role insert. |
| `job_runs` | Per-workspace job status: `pending` \| `running` \| `succeeded` \| `failed` \| `skipped` \| `budget_exhausted`. Settings `GET /settings/jobs`. |
| `sizing_risk_run_refs` | Sizing-phase risk run pointers. Operator, not a public KPI. |

`/pipeline` stays reachable when the book database is down (DB-exempt). Its empty state is "no runs", not the book-unavailable panel.

### 2.4 Research memory (stored, mostly unwired)

Append-only, RLS on, zero client policies, `service_role` SELECT+INSERT. Several stores are in-memory in unit tests with SQL IO still unwired. **coming-soon** as dashboard surfaces until a reader is access-gated and the writer is actually on the daily path.

Families (current names):

- Corpus pin: `research_corpus` (`corpus_key` is `theme:` / `asset:` / `segment:` only).
- Research state: `research_evidence`, `research_belief_versions`, `research_expected_event_versions`, `research_patches`, `research_legacy_refs`, `research_state_versions`, `research_state_pins`.
- Evidence bundles: `ticker_evidence_bundles`, `evidence_bundle_amendments`, `missing_fact_requests`.
- Attention (shadow, not actuated): `attention_plans`, `attention_decisions`, `attention_decision_attempts`, `attention_context_manifests`, `attention_policy_evaluations`.
- Forecasts: `forecast_assessments`, `forecast_amendments`, `forecast_outcomes`, `forecast_calibrations`, `calibrated_forecasts`.
- Outcomes: `outcome_episodes`, `outcome_lesson_versions`.
- Policy replay: `replay_pairs`, `replay_arm_results`, `replay_input_manifests`, `replay_run_events`, `policy_comparison_reports`, `policy_governance_decisions`, `gate_criteria_versions`, `gate_evaluations`.
- Risk registries: `risk_policies`, `pretrade_risk_reports`, `covariance_snapshots`, `liquidity_snapshots`, `component_attribution_reports`, `action_cost_estimates`, `action_cost_outcomes`.
- Profile pins: `profile_config` (house row is immutable default; overlay rows must not replace it).

`documents` with `doc_type = Attention Plan` is the glass-box artifact the pipeline may publish. Do not fabricate attention rows in the UI when that document is absent.

### 2.5 Tenancy, auth, billing (access gate)

| Table | Shape | Dashboard use |
|-------|--------|----------------|
| `workspaces` | `type` `system` \| `user`. `plan_tier` `free` \| `brief` \| `desk` \| `studio` \| `enterprise`. `subscription_status` `none` \| `active` \| `past_due` \| `canceled`. JSON: `investment_profile`, `preferences`, `rebalancing_policy`, `settings`. Stripe ids exist and **must not** be sent to the client (`has_stripe_subscription` boolean only). | One house workspace is the book the operator surface shows. User workspaces are overlay books. |
| `workspace_members` | `(workspace_id, user_id)`, `role` `owner` \| `member`. `user_id` is the Supabase auth user uuid. | Membership. Not a profile page by itself. |
| `entitlement_grants` | Email → `plan_floor` (`brief` and above). Effective tier is max(workspace tier, floor). | Ops/creator floors. Direct table reads revoked. Use `my_access()`. |
| `client_product_grants` | `(email, product_key)`. Known key in schema comments: `fx_hub`. | Hides or shows the FX Hub route. Do not render grant emails. |
| `stripe_events` | Webhook idempotency. | Not a UI table. |
| `audit_log` | `action`, `metadata`, workspace, user. | Connect/revoke trail. Settings may show a redacted slice later. **coming-soon** as a full audit surface. |
| `product_invite_codes` | Invite redemption (migrations 112, 126, 138). | `POST /settings/access/redeem-invite`. |

Auth session is Supabase Auth (`apps/dashboard/lib/auth-context.tsx`): OAuth, email/password, signup. Flag `NEXT_PUBLIC_DASHBOARD_AUTH=1` turns the gate on. The session JWT is what the settings edge expects in `Authorization`. digikey JWT is the service-to-service plane (digigraph, digiquant HTTP). This map does not change either plane.

Plan ladder the UI may badge: Observer (`free`, teaser) → Brief → Desk → Studio → Enterprise (invoice). Do not revive the retired `baseline` / `custom` tier ids. House-run `run_type = baseline` is a different word (Sunday book vs delta) and stays.

### 2.6 Integrations storage (wired at settings; live is human-gate)

| Table | What is stored | What the client may see |
|-------|----------------|-------------------------|
| `broker_connections` | AES-256-GCM envelope. `broker` `alpaca` \| `ibkr`. `env` `paper` \| `live`. `auth_kind` `oauth` \| `api_key`. Ciphertext, nonce, key id, 8-hex fingerprint. `status` `active` \| `revoked` \| `expired`. | Fingerprint, broker, env, status, timestamps. Never plaintext. Reconnect is revoke + insert. |
| `broker_orders` | Append-only mirror. Side, qty or notional, type, status, external id, optional order-intent id. | Settings fills are a separate read (`GET /settings/fills`). Not a live blotter claim. |
| `broker_executions` | Fill mirror. Id is `uuid5(connection_id, external_fill_id)`. | Same. Broker is authoritative for venue fills. digiquant does not forge paper fills from this table. |
| `broker_position_snapshots` | Point-in-time venue position snapshot. | **coming-soon** as a dashboard blotter. Human-gate before any live env is shown as connected-for-trading. |
| `workspace_provider_credentials` | Same envelope as brokers. `provider` `openai` \| `anthropic` \| `groq` \| `openrouter` \| `xai` \| `gemini`. AAD is `workspace_id:provider:llm`. | Fingerprint only. `GET/POST /settings/keys`. |

`env = live` is a stored vocabulary value. The dashboard may show that a row exists only after a human has approved live connectivity. Default product posture is **paper**. `digifetch_ibkr_execute_order` is disabled; preview mints a local ticket and does not submit.

### 2.7 Archive and notes

| Object | Role | Dashboard |
|--------|------|-----------|
| `archive_objects` | `source_table`, `source_key`, `r2_key`, `sha256`, compressed `size`, `owner`, `status`. | Pointer registry. Not a browser table. |
| `knowledge_notes` | `(vault, vault_path)` unique. `vault` default `finance`. Body markdown, tags, wikilinks, frontmatter. | **stored, unwired** on the dashboard. digivault is the API. |
| LangGraph checkpoint tables | Thread checkpoints. Retention in migration 061. | digigraph. Not a journal. |

---

## 3. R2

Market data of record after the Postgres price drop.

| Key | Payload |
|-----|---------|
| `market-data/manifest.json` | Universe manifest. |
| `market-data/price/{TICKER}/{as_of}.parquet` | Immutable OHLCV generation. |
| `market-data/price/{TICKER}/latest` | Pointer at the current generation. |
| `market-data/price/{TICKER}/{as_of}--{sha12}.parquet` | Same-day restatement. Old key stays. |
| `market-data/macro/{SOURCE}__{SERIES}/{as_of}.parquet` | Macro generation (includes sealed econ series). |
| Checkpoint / document offload keys | Payload archived only after put-verify **and** `archive_objects` insert. |

Dashboard reads closes through `GET /v1/market/tickers` and `GET /v1/market/closes` (worker cap; over-cap is HTTP 400, not a silent truncate). Empty market API does not fall back to Supabase `price_history` (that table is gone).

Gloomberb (`digifetch_*`) is enrichment. It is not the price source of record. Equity free tier may be delayed up to 15 minutes. `GET /bars` on digiquant is display-only OHLCV and must not feed validate → backtest → optimize → export.

---

## 4. digivault

| Store | Schema | Tools |
|-------|--------|-------|
| D1 `notes` | `vault_path` PK, title, note_type, summary, body, frontmatter JSON, tags, wikilinks, parent_doc, segment_index | Filesystem/D1 vault tools. |
| Postgres `knowledge_notes` | §2.7 | Same product, namespaced `vault` column. |

MCP names (`digivault/src/digivault/tool_dispatch.py`):

| Name | Side |
|------|------|
| `digivault_search_notes` | read |
| `digivault_get_note` | read |
| `digivault_search_tag` | read |
| `digivault_backlinks` | read |
| `digivault_lint` | read |
| `digivault_create_note` | write |

**Journal is not digivault.** A trade journal is an access-gated, per-workspace ledger of the user's own trades and notes. `knowledge_notes` is a shared research corpus. Wiring the journal to vault notes would mix tenants into one markdown corpus. Status: **coming-soon** (§6.5, §9).

---

## 5. digigraph

digigraph coordinates. It does not own dashboard product rows.

| Route | Role for the dashboard |
|-------|------------------------|
| `GET /healthz` | Liveness. |
| `POST /workflow` | Idea → tool calls → digiquant backtest. Candidate engine for the chat strategy builder. |
| `GET /threads/{id}/state`, `GET /threads/{id}/history`, `POST /threads/{id}/resume` | Orchestration thread. Not a strategy record and not a journal. |
| `POST /v1/chat/completions` | OpenAI-compatible. digichat is the client. |
| `POST /v1/orchestrator_invoke` | How digigraph calls digiquant / digisearch. Dashboard does not call this directly today. |

digisearch is not imported by `apps/dashboard`. Semantic search over research docs is a digigraph/digisearch path. A dashboard "search the book" box that calls digisearch is **coming-soon** until an access-gated route exists. Do not put the service-role key in the static bundle.

---

## 6. Domain shapes

### 6.1 Pipeline run

One civil day is one `daily_snapshots` row plus the documents and book rows for that date.

`documents.doc_type` allowlist (migration 077, the latest check):

`Daily Digest`, `Daily Delta`, `Weekly Rollup`, `Monthly Summary`, `Deep Dive`, `Research Delta`, `Research Baseline Manifest`, `Document Delta`, `Research Changelog`, `Rebalance Decision`, `Asset Recommendation`, `Deliberation Transcript`, `Deliberation Session Index`, `Market Thesis Exploration`, `Thesis Vehicle Map`, `PM Allocation Memo`, `PM Direction Memo`, `Commit Run`, `Sector Report`, `Evolution Sources`, `Evolution Quality Log`, `Evolution Proposals`, `Pipeline Review`, `Custom Research`, `Beliefs`, `Attention Plan`.

Pipeline phases the portfolio graph actually runs, in job words: thesis, market, vehicle_map, screener, analyst, deliberation, direction, sizing, commit. Direction does not emit weights. Sizing sizes. Commit is the portfolio terminal.

`run_type` on the snapshot is `baseline` or `delta`. That is cadence, not a second product.

Phase health the pipeline page can chart is derived from snapshot breakdown keys `phaseN_output(s)` with `{ok, failed, carried}` (`apps/dashboard/lib/run-phase-health.ts`). Missing breakdown is an empty list, not a fake phase.

### 6.2 Strategy

Three layers. Do not collapse them.

| Layer | Where | Identity |
|-------|--------|----------|
| Registry | Python `register()` + `STRATEGY_ALIASES` | Engine name (`btc_sdca`, `ema_cross`, …). Aliases resolve before Nautilus. |
| Run result | `BacktestResult` / `OptimizeResult` / `ExportResult` (`digiquant/models.py`) | `run_id`, `strategy_name`, `symbols`, window, `total_pnl`, `total_return_pct`, `sharpe_ratio`, `max_drawdown_pct`, `num_trades`, `status` `ok` \| `partial` \| `error`. Sharpe, P&L, and drawdown are legal only on these models (or a published tearsheet built from a real run). |
| Published library | `strategies` + `strategy_tearsheets.metrics` | `TearsheetData` (§6.3). |

`ExportResult.target`: `nautilus` \| `tradingview` \| `alpaca` \| `quantconnect`. Export is an artifact path, not a live deployment.

Chat strategy builder (#4895) has no `strategy_drafts` table. The durable output of a builder session is either a `BacktestResult` the user has not saved, or a row the publish path writes. Unsaved sessions are **coming-soon** as a persisted object. digigraph thread ids are a possible key later; they are not that table today.

### 6.3 Tearsheet

`TearsheetData` (`digiquant/tearsheet_data.py`) is the payload inside `strategy_tearsheets.metrics`.

| Group | Fields |
|-------|--------|
| Identity | `schema_version`, `strategy`, `symbol`, `engine` (`pine` \| `nautilus`), `generated_at`, `data_source`, `label`, `kind` |
| Window | `period_start`, `period_end`, `bars`, `initial_capital`, `final_equity`, `signal_delay_days` |
| Headlines | `net_profit`, `net_profit_pct`, `max_drawdown_pct`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `profit_factor`, `win_rate_pct`, `total_trades`, `avg_trade`, `avg_trade_pct` |
| Sides | `overall`, `long`, `short` stat blocks |
| DCA book | `dca`, `current_signal`, `rails`, `risk_curve`, `cost_basis_curve`, `capital_deployed_curve`, `lump_equity_curve`, `flat_dca_equity_curve`, `allocated_pct_curve`, `fill_markers`, `indicator_curves`, `indicator_weights`, `curve_knees`, `beats_flat_dca_oos` |
| Series | `equity_curve`, `drawdown_curve`, `ohlc_bars`, `trades`, `notes` |

Honesty the data already encodes:

- `signal_delay_days` lags the public end date. Zero means an internal run.
- `beats_flat_dca_oos` false or absent is not an out-of-sample win. Full-sample vs-flat-DCA is not that flag.
- DCA `kind=dca` leaves trade KPIs null on purpose.
- Flat-DCA equity is not a public comparable KPI.
- Showcase pages may render this payload. They do not become the editor.

House-book performance tearsheet (Brief / portfolio) is a **different** object: `public_accounting_nav_history` + benchmark closes + the dashboard-api `GET /performance` bundle. Do not mix strategy `TearsheetData.sharpe_ratio` into the house NAV badge.

### 6.4 Broker

Pydantic contracts in `digiquant/brokers/contracts.py` (no I/O in that module):

| Model | Fields that matter |
|-------|--------------------|
| `ExecutionVenue` | `paper_internal`, `alpaca_paper`, `ibkr_paper`, `alpaca_live`, `ibkr_live`. Live values are vocabulary. Dispatch to them is human-gated. |
| `BrokerOrderRequest` | symbol, side `buy` \| `sell`, qty or notional, `market` \| `limit`, time in force `day` \| `gtc` \| `opg` \| `ioc`, `client_order_id` |
| `BrokerOrderStatus` | `submitted`, `accepted`, `partially_filled`, `filled`, `canceled`, `rejected`, `expired` |
| Connection row | §2.6. Client view: `BrokerConnectionView` (`id`, `broker`, `env`, `auth_kind`, `fingerprint`, `status`, `last_used_at`). |

Settings routes already called by the dashboard (`apps/dashboard/lib/settings-api.ts`):

| Method | Path |
|--------|------|
| GET, PATCH | `/settings/profile` |
| GET | `/settings/brokers` |
| POST | `/settings/brokers/connect`, `/settings/brokers/revoke` |
| GET | `/settings/keys` |
| POST | `/settings/keys/connect`, `/settings/keys/revoke` |
| GET, PATCH | `/settings/notifications` |
| GET | `/settings/notifications/log` |
| GET | `/settings/jobs`, `/settings/fills`, `/settings/app-urls` |
| POST | checkout session, customer portal, `/settings/access/redeem-invite` |
| GET | `/settings/access/invite-brand`, `/settings/access/twelvex-session` |

Alpaca OAuth callback route exists (`apps/dashboard/app/settings/brokers/callback`). Do not redesign that callback in a visual slice. Paper is the default env the product copy may describe.

### 6.5 Journal

**coming-soon.** Searched schema, MCP registration, and dashboard queries.

What people might confuse with a journal:

| Thing | Why it is not the journal |
|-------|---------------------------|
| `strategy_trades` | Published backtest fills for a library strategy. |
| `position_events` | House paper-book ledger. One shared book, not the user's trade diary. |
| `broker_executions` | Venue mirror. Human-gate. Not a notebook. |
| `digifetch_note_add` / `digifetch_thesis_add` | Inert workspace-shaped tools. No verified write route. Read-scope registration is not a write. |
| LuxAlgo `journal_*` | Explicitly not wrapped. Separate package. `broker_*` keys are never sent to the LuxAlgo MCP. |
| `knowledge_notes` / digivault | Shared markdown corpus. |
| digigraph threads | Orchestration history. |

A future journal needs its own access-gated table (workspace, user, instrument, side, qty, price, time, note, optional link to a `strategies.id` or a backtest `run_id`). Until that migration exists, the journal surface is coming-soon. No sample trades.

---

## 7. MCP tools on the digiquant server

Source: `digiquant/src/digiquant/mcp_server.py`. Counted from `@_maybe_tool` registrations and `READ_SCOPE_TOOLS` at `0b2c2cf10`.

| Scope | Count | Who it is for |
|-------|------:|---------------|
| Full server | **127** | Operators and pipeline agents. |
| `scope="read"` | **113** | Dashboard chat. Omits runners, fetchers that write caches, tearsheet generation, and policy-replay execution. |
| Full only | **14** | Listed below. |

Prefixes:

| Prefix | Count | Category |
|--------|------:|----------|
| `digifetch_` | 89 | Gloomberb enrichment, local calculators, inert workspace/broker stubs. |
| `digiquant_` | 19 | Engine, research cache, SDCA, tearsheet publish helpers. |
| `luxalgo_` | 14 | Chart backbone (library metadata, edge, trackers). |
| `dashboard_` | 5 | Policy replay / gate reads and one runner. |

### 7.1 Full-only (not in dashboard read scope)

`digiquant_run_backtest`, `digiquant_run_optimize`, `digiquant_export`, `digiquant_run_pipeline`, `digiquant_fetch_coinbase_ohlcv`, `digiquant_fetch_bitview_series`, `digiquant_fetch_bgeometrics_series`, `digiquant_fetch_coinmetrics_series`, `digiquant_fit_btc_power_law`, `digiquant_build_sdca_risk_index`, `digiquant_fit_sdca_weights`, `digiquant_generate_slapper_tearsheet`, `digiquant_validate_slapper_vs_tradingview`, `dashboard_run_policy_replay`.

The chat strategy builder needs backtest/optimize. That is a **gated** dashboard action (session + plan tier), not an anon read tool. Wiring it is later work. This lane only records that the tools exist on the full server.

### 7.2 `digiquant_*` (19)

Read-scope: `digiquant_list_strategies`, `digiquant_get_price_technicals`, `digiquant_get_macro_series`, `digiquant_get_trade_levels`, `digiquant_query_research`, `digiquant_list_coinmetrics_catalog`.

Full-only: the 13 engine/write names in §7.1.

`digiquant_query_research` stamps house-book reads. It is not a cross-tenant query.

### 7.3 `dashboard_*` policy tools (5)

Read-scope: `dashboard_get_policy_replay`, `dashboard_get_policy_comparison`, `dashboard_evaluate_policy_gate`, `dashboard_get_policy_gate_evaluation`.

Full-only: `dashboard_run_policy_replay`.

These read the policy-replay tables in §2.4. The dashboard UI does not call them today. Surface: **stored, unwired**. Do not present a gate evaluation as a live-trading permission.

### 7.4 `luxalgo_*` (14) — chart backbone

All 14 are read-scope, keyless, default-on behind `LUXALGO_ENABLED`.

| Tool | Data |
|------|------|
| `luxalgo_library_search` | Concept/indicator search. |
| `luxalgo_library_get_concept` | Concept metadata. |
| `luxalgo_library_get_indicator` | Indicator **metadata only**. |
| `luxalgo_library_list_concepts` | List. |
| `luxalgo_library_list_indicators` | List. |
| `luxalgo_library_list_tags` | Tags. |
| `luxalgo_library_list_families` | Families. |
| `luxalgo_library_get_family` | One family. |
| `luxalgo_edge_symbols` | Symbols the edge presets cover. |
| `luxalgo_edge_presets` | Preset catalog. |
| `luxalgo_edge_report` | Preset report for one symbol. Carries the stats honesty disclaimer. |
| `luxalgo_trackers_datasets` | CC0 tracker dataset list. |
| `luxalgo_trackers_latest` | Latest rows. |
| `luxalgo_trackers_ticker` | Per-ticker tracker history. |

Not wrapped, on purpose: library source code (license), live `trackers_query` (dumps stay the source of record), `journal_*`, `propfirms_*`, and any `broker_*` key.

Library payloads state `commercial_license` / `license_state`. The commercial flag defaults off; the dispatcher refuses source-bearing tools while it is off. Charts in the rebuild bind to edge reports and trackers (and to digiquant series a preset can plot). They do not embed indicator source.

### 7.5 `digifetch_*` (89)

Entitlement is exactly one of `free`, `session`, `preview`, `pro`, `venue_session` (`data/gloomberb/entitlements.py`). Session tools need `GLOOMBERB_SESSION_COOKIE`. Pro tools need that cookie from a Pro account. The dashboard must badge entitlement, not hide a 402 as an empty success.

Groups (all registered; read-scope includes the inert writes because they return typed errors rather than mutating):

| Group | Count | Names |
|-------|------:|-------|
| Quote and reference | 13 | `quote`, `quotes_batch`, `price_history`, `ticker_financials`, `options_chain`, `sec_filings`, `holders`, `analyst_research`, `corporate_actions`, `earnings_calendar`, `exchange_rate`, `search`, `news` |
| Macro, filings, social | 16 | `econ_calendar`, `econ_series`, `yield_curve`, `cds`, `research_search`, `congress_trades`, `transcripts`, `statements`, `ticker_tweets`, `tweet_search`, `venues`, `saved_searches`, `screener`, `13f_funds`, `13f_holdings`, `shiller` |
| Filings and diagnostics | 6 | `proxy_statements`, `filing_events`, `risk_reports`, `short_interest`, `equity_diagnostic`, `prediction_markets` |
| Local calculators | 7 | `options_calculator`, `bond_calculator`, `kelly_sizer`, `dividend_yield`, `fx_cross_rates`, `vix_term_structure`, `options_scenario` |
| Composed math | 10 | `compare_performance`, `correlation_matrix`, `relationship_graph`, `relative_valuation`, `fundamental_graph`, `valuation_graph`, `custom_chart`, `market_valuation`, `money_markets`, `rate_path` |
| Session / pro market reads | 24 | `time_and_sales`, `quote_recap`, `estimate_revisions`, `short_volume`, `hiring`, `central_bank_rates`, `cdx`, `sovereign_cds`, `options_flow`, `cot`, `crypto_markets`, `iv_screen`, `iv_history`, `iv_surface`, `debt_maturities`, `session_movers`, `trending`, `substack`, `ipo_calendar`, `fear_greed`, `polls`, `treasury_auctions`, `market_halts`, `hacker_news` |
| Inert workspace and broker | 13 | `portfolio_view`, `watchlist_add`, `watchlist_remove`, `portfolio_add`, `portfolio_remove`, `alert_add`, `alert_list`, `note_add`, `thesis_add`, `view_add`, `broker_positions`, `ibkr_preview_order`, `ibkr_execute_order` |

`digifetch_custom_chart` is local math over supplied series. It is not the LuxAlgo backbone. `digifetch_ibkr_execute_order` stays disabled. `digifetch_broker_positions` is a read stub, not the house book.

Pipeline agents see a filtered subset (equity / macro / portfolio-manager, 16 names each) only when Gloomberb is enabled and the cookie is present for gated tools. MCP advertises the gated tools and returns `auth_required` / `pro_required`. The dashboard tool catalog should do the same: show the tool, show the entitlement, do not pretend the call succeeded.

### 7.6 dashboard-api MCP (separate, 8)

`apps/dashboard-api/src/mcp.ts` exposes the read API as JSON-RPC on `POST /mcp`, gated by `MCP_EDGE_KEY` (`x-digi-mcp-key`). Unset key fails closed.

`get_portfolio`, `get_allocations`, `get_nav_series`, `get_brief`, `get_performance`, `get_kpis_live`, `get_benchmarks`, `get_ledger`.

These are book readers, not the 127-tool catalog.

### 7.7 digivault MCP

Six tools, §4. Not part of the digiquant 127.

---

## 8. APIs the dashboard calls or could call

### 8.1 Called today

| Client | API | Data |
|--------|-----|------|
| `lib/api-client.ts` | `GET /v1/tables/:table` | Allowlist in §8.2. House pin applied server-side. Bare row array. |
| `lib/market-data.ts` | `GET /v1/market/tickers`, `GET /v1/market/closes` | R2 closes. |
| `lib/snapshot-fetch.ts` | Supabase `daily_snapshots`, optional `/api/snapshots` BFF | Brief snapshot. The BFF route is an example file, not a shipped `app/api` route. |
| `lib/vela-bars.ts` | `{base}/bars` | Display bars. |
| `lib/settings-api.ts` | Settings edge, §6.4 | Profile, brokers, keys, billing, invites. |
| `lib/twelve-x/fetch.ts` | FX Hub Supabase | Tables below. Separate project. |
| `lib/digichat-popup.ts` | digichat `GET /api/deploy/chrome`, `POST /api/plan-proof` | Embed chrome and plan proof. |
| `lib/auth-context.tsx` | Supabase Auth | Session. |
| Realtime hook | `postgres_changes` on `prices_live` | Live marks overlay only. |

FX Hub tables the dashboard already selects: `fx_consensus_snapshot`, `fx_daily_digest`, `fx_confluence_snapshot`, `fx_events_snapshot`, `fx_research_history`, `fx_trade_ideas_snapshot`, `fx_idea_eval`, `fx_consensus_eval`, `fx_relevance_ledger`, `fx_smart_bias`, `fx_market_snapshots`, plus `economic_calendar` and `macro_series_observations` on that project. Access is that project's session and `client_product_grants.product_key = fx_hub`. This route is not the strategy product and not the journal.

`apps/dashboard` has **no** `app/api/**/route.ts`. The static export talks to workers and Supabase. Do not plan a secret into the client bundle.

### 8.2 dashboard-api (implemented reader)

Contract: `apps/dashboard-api/CONTRACT.md`. Worker: `apps/dashboard-api/src/index.ts`. All specific routes are GET, read-only, with `data` + `as_of` + `retrieval_pin` + `provenance`.

| Route | Replaces | Store |
|-------|----------|-------|
| `GET /portfolio` | Per-page house book + invested envelope. Includes book-as-of. | `daily_snapshots`, `positions`, accounting NAV tip. |
| `GET /allocations` | Reconciled weights + marks. | Same book + market API for missing marks. |
| `GET /brief` | Morning scoreboard. | NAV tip, day return, since-inception, session `position_events`. |
| `GET /performance` | House tearsheet bundle. | `public_accounting_nav_history`, benchmark closes. |
| `GET /kpis/live` | Point-in-time live overlay. Not a stream. | Latest quotes vs entry. |
| `GET /nav-series` | Shared NAV series. | Accounting history. |
| `GET /benchmarks` | Benchmark universe. | R2 market API. |
| `GET /ledger` | Fill stream. | `position_events` only. |
| `GET /v1/tables/:table` | Long-tail reads. | Allowlist below. |
| `GET /healthz` | Liveness. | None. |
| `POST /mcp` | The eight readers as tools. | Same. |

Tables allowlist: `daily_snapshots`, `positions`, `instruments`, `theses`, `portfolio_metrics`, `documents`, `position_events`, `macro_series_observations`, `decision_log`, `run_health`, `position_attribution`, `run_event_trace`, `public_accounting_nav_history`, `thesis_vehicles`, `analyst_coverage`, `public_daily_realized_attribution`.

Unknown table → 404. No service-role key → 502 `upstream_empty`, never an empty success.

House pin is forced for `positions`, `position_events`, `portfolio_metrics`. House+system pin for `documents`. Callers cannot override it.

Out of scope of this worker: FX Hub, Realtime, billing, Alpaca. Those stay on their current clients.

### 8.3 digiquant HTTP the dashboard could call (not called by the pages today)

`digiquant/src/digiquant/server.py`. digikey JWT. Default bind loopback `:8001`.

| Route | Model | Product note |
|-------|--------|----------------|
| `GET /health`, `GET /healthz` | liveness | Safe. |
| `GET /strategies` | registry list | Tool/strategy catalog. |
| `GET /bars` | `BarsResponse` | Display only. Gloomberb delay. Not a backtest input. |
| `GET /check_drift` | drift result | Stored signal. Heartbeat action is not productized. |
| `POST /run_backtest`, `POST /backtest/start`, `GET /backtest/{id}/progress`, `GET /backtest/{id}/result` | `BacktestResult` | Strategy builder. Access-gated. Linux Nautilus may abort (#42); the UI must surface `status=error`, not a zero Sharpe. |
| `POST /run_optimize` | `OptimizeResult` | Same gate. |
| `POST /run_export` | `ExportResult` | Artifact, not a deploy button. |
| `POST /run_pipeline` | pipeline | Operator. Not a marketing CTA. |

### 8.4 digigraph routes the builder could call

§5. Access-gated. Not wired in `apps/dashboard` pages.

---

## 9. Product surface × data (lane 3 cheat sheet)

Dashboard owns these. digiquant-web may **show** a published artifact and must not grow the write path.

| Surface | Status | Read | Write | Lane 3 rule |
|---------|--------|------|-------|-------------|
| House brief, portfolio, performance, ledger | **wired** | dashboard-api §8.2 | none | Research/paper book. Badge contract and seam. |
| Pipeline / run health | **wired** | `daily_snapshots`, `documents`, `run_event_trace`, `run_health` | none | Reachable when the book DB is down. |
| Published strategies and tearsheets | **wired** store, **dashboard-owned** product | `strategies`, `strategy_tearsheets`, `strategy_signals`, `strategy_trades` | Publish path is operator (`--push-supabase`), not the showcase | Showcase may render. Editor and library management live on the dashboard. |
| Chat strategy builder | **coming-soon** as a saved object | `GET /strategies`, `BacktestResult` | `POST /run_backtest` (full MCP / HTTP, gated) | Run results from a real engine only. Unsaved thread is not a strategy. |
| Trade journal | **coming-soon** | — | — | Empty state. Do not reuse house `position_events` or `strategy_trades`. |
| Tool catalog | **stored, unwired** as a page | 113 read-scope tools + 14 full-scope names | full-scope calls are gated actions | List name, category, entitlement. Inert broker/journal tools stay labeled inert. |
| Integrations | **wired** at settings | broker + provider fingerprints, plan, invites | connect/revoke via settings edge | Paper by default. Live env is human-gate. No live-trading sentence. |
| LuxAlgo charts | **wired** as tools, **unwired** as dashboard charts | 14 `luxalgo_*` tools | none (no source, no journal) | Chart backbone. House NAV and tearsheet equity need an explicit binding into that backbone before they are "a LuxAlgo chart". Until bound, those series stay on their current data components or wait. Do not add a second chart library in the rebuild plan. |
| Gloomberb panels | **stored, unwired** on the dashboard | 89 `digifetch_*` | inert stubs do not write | Badge delay and entitlement. Not the price source of record. |
| FX Hub | **wired**, access-gated | FX Hub tables §8.1 | none in this lane | Separate project. Not the journal. Do not print grant emails. |
| Research memory, attention, policy replay | **stored, unwired** | service-role tables; four policy reads are MCP | replay runner is full-scope | coming-soon until a published `documents` row or an access-gated reader exists. |
| User overlay book | **stored, unwired** on the main nav | `workspaces` + overlay `documents` keys | profile PATCH; overlay persist flag | House remains the operator book. Overlay is not a second anonymous book. |
| Audit log | **coming-soon** as a page | `audit_log` | settings actions already write | Redacted slice later. |
| digivault browser | **coming-soon** | `knowledge_notes`, D1 `notes` | `digivault_create_note` | Not the trade journal. |
| digisearch over the book | **coming-soon** | digisearch index | none | No dashboard client today. |
| Live broker blotter | **human-gate** | `broker_position_snapshots`, `broker_executions` | execute path disabled | Do not claim live. Paper mirror may be described as paper. |

---

## 10. Access gate (summary)

1. Anonymous showcase may read the curated public views and published strategy tearsheets. That is digiquant-web.
2. The dashboard session is Supabase Auth when `NEXT_PUBLIC_DASHBOARD_AUTH=1`.
3. Book routes pin house (or house+system for documents) on the server. The browser does not choose `workspace_id`.
4. Effective plan is `max(workspaces.plan_tier, entitlement_grants.plan_floor)` via `my_access()`. Tiers: `free`, `brief`, `desk`, `studio`, `enterprise`.
5. Extra products are `client_product_grants.product_key` (FX Hub is `fx_hub`). Absence hides the route. It does not 500.
6. Sealed credentials never leave the server. UI sees fingerprints.
7. dashboard-api adds no new auth surface. Missing service role fails closed.
8. digiquant and digigraph HTTP stay on digikey scopes. Dashboard pages do not embed those tokens.

---

## 11. What lane 3 must not invent

- A live-trading status, fill, or P&L that is not a `BacktestResult`, a published `TearsheetData`, a house accounting row, or a broker mirror row.
- A journal by renaming `position_events` or `strategy_trades`.
- Strategy ownership on digiquant-web.
- A chart stack beside LuxAlgo for new dashboard charts. Existing house NAV components stay until a LuxAlgo binding is specified; this file does not design that binding.
- Sample MCP results for tools that return `auth_required`, `pro_required`, or disabled.
- Private-client names, grant emails, or Stripe customer ids.
- Retired product names in any new label.
- Writes on the dashboard-api contract. It is read-only on purpose.

---

## 12. Sources

| Topic | Path |
|-------|------|
| Product split | GitHub issue 4895 |
| Job-word naming | `docs/adr/0026-retire-olympus-atlas-hermes-kairos.md` |
| Supabase topology | `docs/adr/0021-digiquant-supabase-project-topology.md` |
| Schema narrative | `digiquant/supabase/SCHEMA.md` |
| Migrations | `digiquant/supabase/migrations/` |
| Strategy store DDL | `digiquant/supabase/migrations/046_strategy_store.sql` |
| Rename to current table names | migrations `134`, `135`, `137` |
| Tearsheet model | `digiquant/src/digiquant/tearsheet_data.py` |
| Backtest model | `digiquant/src/digiquant/models.py` |
| Broker contracts | `digiquant/src/digiquant/brokers/contracts.py` |
| MCP registry | `digiquant/src/digiquant/mcp_server.py` |
| Dashboard read contract | `apps/dashboard-api/CONTRACT.md` |
| Dashboard queries | `apps/dashboard/lib/queries.ts`, `lib/api-client.ts`, `lib/settings-api.ts` |
| R2 layout | `digiquant/src/digiquant/data/prices/r2_history.py` |
| Vault | `digivault/src/digivault/d1_schema.sql`, migration `118` |

## 5. Navigation and surface map (full text)

Source: [PR #4906](https://github.com/digithings-ai/digithings/pull/4906). Original path: `docs/superpowers/plans/2026-10-01-dashboard-navigation-surface-map.md`. The navigation map follows in full. It was not shortened.

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

## 6. Market IA scan (full text)

Source: [PR #4907](https://github.com/digithings-ai/digithings/pull/4907). Original path: `docs/plans/2026-10-01-digiquant-dashboard-market-ia-scan.md`. The scan follows in full. It was not shortened. Four relative links were rewritten from `../` to `../../` so they resolve from `docs/superpowers/plans/`.

# DigiQuant dashboard market IA scan

> **Date:** 2026-10-01
> **Status:** Draft plan. Research only. No UI, no routes, no product implementation.
> **Feeds:** the sibling nav-map plan. This file does not draw the final tree.
> **Audience:** Chris. Human-gate questions are at the end.

This scan reads public finance and quant interfaces for navigation, density, and flow, then keeps only what survives DigiQuant’s locks. Sources are help centers, vendor PDFs, official docs, and public product pages fetched on this date. Private terminals were not logged into. Where a public page names a control, this file names it. Where a name was asked for and the public record does not show it, the gap is stated.

Existing vision this scan sits beside:

- [docs/vision/dashboard.md](../../vision/dashboard.md) — operator surface for research, portfolio, and execution, with a human gate before live.
- [docs/vision/digiquant.md](../../vision/digiquant.md) — research, then portfolio deliberation, then execution. Paper before live. No skipped step.
- [docs/projects/digiquant/COMPETITORS.md](../../projects/digiquant/COMPETITORS.md) — strategy-market notes (Composer, QuantConnect, and others). That file is not an information-architecture scan. This one is.
- [ADR-0026](../../adr/0026-retire-olympus-atlas-hermes-kairos.md) — job words in the product. Olympus, Atlas, Hermes, and Kairos stay out of labels.

Chrome today, for contrast only: `apps/dashboard/lib/nav.ts` is Brief, Portfolio, Pipeline, FX Hub. Inside Portfolio, `PortfolioSectionNav` already uses sticky tabs for Holdings, Theses, Tearsheet, Ledger, and Attribution. House is a separate route with Corpus, Book, and Profile. This scan does not treat today’s sidebar as the target.

---

## Locks

Every steal below is already filtered through these. A pattern that fails a lock is on the avoid list even if the source product is good at it.

### Product

- The dashboard is the live product: strategy builder (digichat-led), strategies, trade journal, tools, and solution integrations stay in-app.
- digiquant-web is the showcase. Full tools do not move onto the marketing site.
- Research and the paper book come first. Live capital stays behind a human gate. The product does not tell a live-by-default story.
- Job words in labels. No Olympus, Atlas, Hermes, or Kairos.
- Module names in chrome stay lowercase (`digichat`, `digiquant`). DigiQuant is fine as the brand.
- LuxAlgo is the charting backbone. Panel patterns wrap LuxAlgo. DigiQuant does not grow a second chart stack.
- The product is access-gated. The shell follows digiquant-web craft: finance-native, flat, not an overweight app frame.
- Coming-soon placeholders are allowed for future solutions.
- No private-client names in the product or in this plan.

### Spine this scan is written against

Locked destinations:

| Surface | Job in this scan |
|---|---|
| Brief | Dense scoreboard. Start of the day. |
| Holdings | The paper book. |
| Theses | The case for a name. |
| Tearsheet | Performance, read as a report. |
| Ledger | Fills and activity. Paper fills are first-class. |
| Attribution | What contributed. |
| Pipeline | The only reasoning hub. |
| House | The house paper book. Separate from the user book. |
| Settings | Omit by tier. Not a gray catalog. |
| Auth | The gate. Not a product module. |
| Ticker dossier | Optional drill-down from a row. Not a home. |

Coming soon, and therefore not spine peers: strategy builder, journaling, live brokers, digichat embed, and other future solutions.

### Lab feed

Steal:

- Dense Brief scoreboard, then the book, then drill-down.
- Stage the work as research, then paper, then journal, then settings.
- Tier gating omits what the reader cannot use.
- Paper fills are a first-class activity, not a footnote under a chart.

Avoid:

- Bloomberg-style kitchen-sink navigation.
- Robinhood-style gamification and a live-by-default story.
- Treating TradingView as the whole product. LuxAlgo owns charts.
- Fake live-broker chrome.
- Putting the builder on the marketing site.

### Web craft feed

Steal:

- Bloomberg density on the page: mono labels, tabular numbers, hairline borders, flat panels. digiquant-web already uses this grammar (`font-mono`, `border-hair`, `tabular-nums` in `apps/digiquant-web`).
- A literal sidebar, plus sticky tabs inside the page. Linear and Cursor are the reference for that chrome shape. They were supplied as craft constraints for this scan. This file does not claim a fresh audit of either product.
- One primary action on each surface.
- Settings that omit a tier the way Stripe omits unpaid capabilities, instead of showing a locked pile. Same caveat: craft constraint, not a Stripe screenshot audit.
- Empty states that say what is missing.
- LuxAlgo as first-class embed panes inside a surface.

Avoid:

- AI-SaaS glass, hero cards, and purple.
- A fat clone of the marketing site inside the app.
- Fake live profit-and-loss.
- Nested sticky chrome (a sticky bar inside a sticky bar).
- Gray “soon” rows in the nav. Omit the row, or use one disabled control with a chip.
- Any chart UI that competes with LuxAlgo.

---

## How a class was read

For each product the notes cover, where the public record supports it:

- Primary navigation.
- The workspaces a person actually opens.
- How research, an order or a paper book, a journal, and settings are staged.
- Empty states.
- How deep settings go.
- Whether the chart is the product or a pane.
- Multi-panel versus a single column.
- What happens to a module that is not available yet.

---

## 1. Terminal and pro research density

### Bloomberg Terminal, and bloomberg.com beside it

Public record: Yale’s Bloomberg guide, the University of Zurich student PDF, university keyboard cards, and Bloomberg Professional’s own note on Instant Bloomberg, Worksheets, and Launchpad (`bloomberg.com/professional/insights/technology/bloomberg-terminal-essentials-ib-worksheets-launchpad/`, 2024-10-12). bloomberg.com is a different, thinner product. Its help center documents a subscriber Watchlist under Markets, not the Terminal.

What is public about the Terminal:

- Login opens up to four panels. Each panel is its own workspace: toolbar, command line, function area. The panel key moves between them.
- Discovery is a command line with autocomplete, plus menus grouped by market sector. `MENU` walks back. `LAST` recalls recent functions. Help once explains the current function.
- Launchpad (`BLP`) is the custom layout: monitors, charts, news, and function panels on pages, linked in groups, saved as a view.
- Settings are Terminal Defaults, not a product section. The surface assumes you already have the whole catalog.

What is public about bloomberg.com:

- Markets navigation is a short list: Stocks, Commodities, Rates & Bonds, Currencies, Futures, Sectors, Economic Calendar.
- The Watchlist is subscriber-only. A subscriber can keep many lists. The page offers themed starter lists (“Start this list”) and a news strip under the list you are on. Alerts are an explicit opt-in on the list, not a separate app.

Steal toward DigiQuant:

- Density: one row, one number, hairline, no card. That is the Brief scoreboard and the Holdings table.
- A command line is a later accelerator, not version-one chrome. Koyfin documents the same idea more honestly for the web (see class 5).
- bloomberg.com’s short markets list is the shape of a literal sidebar. The Terminal’s function catalog is not.

Avoid:

- Kitchen-sink nav. Four panels plus an unbounded function menu is the anti-pattern the lab feed names.
- Making “coming soon” look like a Terminal function the reader cannot run.

### FactSet

Public record: Rotman and Emory quick-start PDFs, the Stanford FactSet libguide, and university notes on Portfolio Analysis.

- The workspace is a row of application tabs. The blue F menu inserts components. Search launches a security, a report, or an app (apps are marked with `@`).
- A new user lands in a saved workspace or a FactSet preset, not a blank marketing page.
- Portfolio work is its own application family: Portfolio View, Portfolio Analysis, Portfolio Dashboard. Inside it, a chart is a tile next to the table you are reading. Portfolio Analysis documents default, suggested, and custom charts, and a control that flips a tile from chart back to table.
- You add the apps you use. Apps you have not added are absent, not grayed.

Steal:

- Chart beside the table, with a way back to the table. That is a LuxAlgo pane on Tearsheet or a ticker dossier, not a chart home.
- Preset workspace instead of an empty canvas.

Avoid:

- An insert-anything app catalog as the navigation model. DigiQuant’s spine is fixed.

### LSEG Workspace (formerly Refinitiv)

Public record: LSEG Workspace quick-start PDF and the Eikon-to-Workspace migration guide on `lseg.com`.

- One window. Key chrome: workspace menu, home, tabs, search, bookmarks, alerts, help, app menu.
- A layout is several apps side by side. Presets exist. The vendor’s own best practice is one layout per job (one sheet per portfolio), not a sheet per feature.
- Search and a launcher (`Ctrl+Shift+Space` in the student card) find data or apps.
- Help is F1 on the current context.
- The migration guide has an explicit overflow step: panels that do not fit are reviewed and saved aside, not left as a broken layout.

Steal:

- One layout per job. Brief is a layout. The book is a layout. Pipeline is a layout.
- Overflow is a design rule: if a panel does not earn its place, it leaves. That is how coming-soon stays off the sidebar.

Avoid:

- An App Library as a second navigation system next to the spine.

---

## 2. Chart-first platforms

### TradingView

Public record: TradingView Help Center articles on layouts, multi-chart, Supercharts, and watchlists (solutions 43000746975, 43000692404, 43000629990, 43000746464, 43000745825).

- The chart layout is the product. A layout holds 1 to 16 charts, depending on plan. Watchlists and alerts are deliberately not stored in the layout.
- Chrome is a top symbol bar, a left drawing toolbar, a right toolbar (watchlist, details, news, alerts, Pine Editor, Help), and a bottom trading panel that connects a broker.
- Multi-chart can sync symbol, interval, and crosshair. One chart can be maximized. Indicators on the first chart copy onto the others. Chart settings do not.
- Pine strategies are scripts on the chart. They simulate orders on the chart. That is chart-as-strategy, which DigiQuant does not copy. Strategies live in the product, and the chart is LuxAlgo.
- Empty behavior is “pick a symbol.” There is no research scoreboard in front of the chart.

Steal:

- A pane can be maximized without leaving the surface. Useful when a LuxAlgo pane sits on Brief or a dossier.
- Symbol changes in one pane can follow the selected row. That is drill-down, not a new destination.
- Watchlist data (Holdings) stays outside the chart layout, which matches “chart is not the book.”

Avoid:

- TradingView as the whole product. No 16-chart home, no bottom broker ticket, no Pine-style strategy layer beside LuxAlgo.
- A right rail of every tool. DigiQuant’s tools that are not ready are omitted.

### thinkorswim (Schwab)

Public record: the thinkManual Getting Started page (`toslc.thinkorswim.com/center/howToTos/thinkManual/Getting-Started`) and the left-sidebar, charts, and flexible-grid articles. The Getting Started page says the main window has eight tabs and then documents six by name: Trade, Monitor, Analyze, Scan, MarketWatch, Charts. The learning-center index also lists Tools. A Schwab tutorial video names nine, adding Education and Help. This scan treats the six named in the manual as the documented workflow and does not depend on the video for a requirement.

- Left sidebar: balances plus gadgets (watchlist, news, quick charts). Gadgets are added from a plus button, capped, and the sidebar can hide.
- The documented path is staged. Analyze and Scan research a name. Charts are their own tab. Trade writes an order into an entry tool at the bottom. Monitor is where the fill shows up, under Activity and Positions, split into working, filled, and canceled, with positions underneath.
- paperMoney is a separate simulated environment that mirrors the live platform. Schwab tells a new user to fund a live account, and mentions paperMoney as a place to practice. The chrome is the live product’s chrome.
- Setup (upper right) holds notifications, order defaults, and display. Support is separate from Setup.
- Scan results can open a quote, a chart, or a trade from the row. That is drill-down done well, and it is also how a research screen becomes an order screen too quickly for DigiQuant.
- Charts and Flexible Grid are multi-cell. The manual warns that too many cells hide axes and studies. That is a density ceiling.

Steal:

- Monitor’s split of working, filled, and canceled is the right shape for Ledger. Paper fills belong there as the activity, not as a badge on a chart.
- One symbol selected in a list, then a focused surface, matches Brief to dossier.
- A hideable context column, if anything sits beside the scoreboard. Not a second navigation.

Avoid:

- Eight or nine top tabs. That is kitchen-sink nav with a chart product inside it.
- paperMoney’s “same chrome as live, different login.” DigiQuant’s paper book is the book. It does not wear a live ticket.
- A Trade tab as a peer of research. Live order entry is behind the human gate and is coming soon as a broker integration, not a tab.

### Interactive Brokers TWS and Client Portal

Public record: IBKR’s TWS QuickStart, the Mosaic layout guide (`ibkrguides.com/traderworkstation/mosaic-layout.htm`), Traders’ Academy “Getting Started with TWS,” and Client Portal guides for Portfolio, Transaction History, Statements, and Transfer & Pay (portfolio guide marked updated 2026-05-26).

TWS Mosaic, from IBKR’s own quick start:

- First login asks for a template. Mosaic is the recommended one. Classic TWS is a separate tab. A plus opens the Layout Library of presets.
- Default Mosaic is color-linked windows: watchlist, order entry, and an activity panel that swaps among Orders, Trades, Trade Summary, and Portfolio.
- Clicking a symbol updates every window in the color group.
- Account, market-data subscriptions, and statements live under an Account menu. They are not the trading mosaic.

Client Portal, from the user guides:

- Portfolio shows positions, cash by currency, performance periods (7D, MTD, 1M, YTD, 1Y), and balances.
- Performance & Reports holds Transaction History (filter by type or symbol, configurable columns) and Statements.
- Transfer & Pay is funding. It is a different job from the book.

Steal:

- Client Portal’s split is the book. Holdings, then Ledger (transaction history), then Tearsheet (a statement you run). TWS Mosaic is not the model.
- Color-linking is the same idea as TradingView sync: the selected name drives the panes on that surface. Use it inside a dossier. Do not use it to snap an order ticket to the scoreboard.
- Preset layouts exist so a person does not design a workspace on day one. DigiQuant ships one layout per spine surface.

Avoid:

- Mosaic order-entry as the center of the screen.
- Offering Classic and Mosaic and a layout library. One spine.
- Client Portal still assumes a live brokerage account. DigiQuant does not copy funding, margin, or transfer chrome.

---

## 3. Quant and backtest platforms

### QuantConnect

Public record: QuantConnect docs v2, Cloud Platform Getting Started and the IDE page (`quantconnect.com/docs/v2/cloud-platform/getting-started` and `.../projects/ide`), plus QuantConnect’s own 2020 migration note.

- Getting Started is a numbered path: create a project, Build, Backtest, Deploy Live, and on that deploy page pick Paper Trading from a brokerage dropdown, then Deploy. Live results are the next page. A different brokerage is a later doc.
- The IDE is the product. Left is the file tree. Right navigation opens Ask Mia (edits files, runs backtests, can deploy live) and a Resources panel of backtest, research, and live nodes.
- Docs sidebar itself is the map: Research, Backtesting, Live Trading, Optimization, Research Pipeline. Research notebooks and the algorithm IDE are different rooms.
- Quantopian’s community platform was turned off on 14 November 2020. QuantConnect’s announcement describes an uploader into Zipline-shaped projects and a docs section for people coming from Zipline. It does not claim to be the only successor.

Steal:

- The path is visible: research, then a backtest result, then a paper deployment. Pipeline can show that sequence as the reasoning hub.
- Paper is a named environment. The mistake is where they put the control.

Avoid:

- Paper Trading as one item in a brokerage dropdown on “Deploy Live.” On DigiQuant, paper is the book you are already in. Live is a later, gated destination, omitted until the human gate says otherwise.
- An IDE as the dashboard. Strategy building is digichat-led and coming soon. It opens from Pipeline when it exists. It is not a code editor home, and it is not on digiquant-web.
- A right-hand agent that can deploy live from the same pane as research. Pipeline reasons. It does not send capital.

### Quantopian successors

Public record: QuantConnect’s migration announcement; QuantRocket’s own “How You Can Still Use Quantopian” page; the libraries those pages name (Zipline, Alphalens, Pyfolio). A third-party stack article also names zipline-reloaded, alphalens-reloaded, and pyfolio-reloaded. This scan uses the vendor pages for product claims and treats the stack article as a pointer, not as UI evidence.

- There is no Quantopian UI left to copy. The public heirs split three ways: a hosted IDE (QuantConnect), a self-hosted research stack that kept Zipline (QuantRocket), and the open libraries (tearsheets and factor analysis).
- What survived in the open is the tearsheet and the factor report, not a trading mosaic.

Steal:

- Tearsheet and Attribution are reports with a method, in the lineage of pyfolio and Alphalens. They are not broker screens.
- A tearsheet is allowed to be a document: period, benchmark, and the bridge from start value to end value.

Avoid:

- Rebuilding a notebook IDE to look like 2019 Quantopian. That job is Pipeline plus the coming-soon builder.

### Composer

Public record: `composer.trade`, the starter guide, and Knowledge Center articles on creating a symphony, backtest basics, and Discover (articles 54, 67, 55).

- A symphony is the strategy. The editor is visual and no-code. AI can draft one from a sentence. The editor is in the logged-in product.
- Discover is a top-nav destination of ready-made symphonies. Each fact sheet has a backtest, logic, and risk stats. The public article lists three next steps: Watch, Invest, or Edit.
- Watch adds the symphony to a list and assigns a simulated $1,000 “just like paper trading.” Invest puts real money into Composer’s own brokerage. Edit opens the visual editor. Edits to a copied symphony stay in the account.
- Backtest basics are unusually honest in public docs: hypothetical, hindsight, daily adjusted closes, default slippage of 1 basis point, and the Trading Pass fee left out of the backtest unless the reader opts in. The docs say live fills use real-time quotes and will differ.
- The marketing site is the brokerage pitch: automated execution, fund an account. The editor is not a public toy on the homepage in the sources above. The homepage describes it.

Steal:

- Watch before capital. A strategy can sit on a paper book with an explicit simulated notion, and the screen says so.
- Backtest copy that states what the number is not. Tearsheet should be able to say “paper fills” or “hypothetical backtest” in the same voice Composer uses for slippage and hindsight.
- One primary action on a fact sheet. Composer actually offers three (Watch, Invest, Edit). DigiQuant should keep one: open the paper book, or open the thesis. Invest-style capital is not on the page.

Avoid:

- Composer is the brokerage. Auto-rebalance into a funded account is the live-by-default story.
- A Discover marketplace of other people’s strategies. Out of scope for this spine.
- A visual strategy editor on the marketing site. When the builder exists, it is in the dashboard, digichat-led, reached from Pipeline.

---

## 4. Portfolio, journal, and paper books

### Morningstar Portfolio

Public record: Morningstar help center, Portfolio section (`morningstar.com/help-center/portfolio`), including Holdings, X-Ray, intro, and rebalance articles.

- The tool is a portfolio you create, import, or link. Manual holdings and linked accounts are different modes, documented as a choice.
- Holdings is a table with preset views (Portfolio Summary, Gain/Loss) or a custom column set.
- X-Ray is a dropdown of cuts (asset class, sector, region, style, fees) against a benchmark, with a holdings-breakdown table under the chart so a row explains the bar.
- Performance charting is separate. Stock Intersection is named in the intro video page as an overlap view.
- Rebalance is documented as a loop between Holdings (enter a buy or sell via Manage Transactions) and X-Ray (see the benchmark gap). There is no order ticket and no chart stack.
- Empty state is “create a portfolio,” then add or import. The tool does not invent positions.

Steal:

- Holdings is the book. Attribution is the X-Ray pattern: a cut, a benchmark, and a table of which names drove it.
- Column sets instead of a new page per metric.
- Transactions change the book. On DigiQuant those transactions are paper fills in Ledger, not a pretend broker.

Avoid:

- Account-linking chrome (aggregators, bank credentials). Out of scope, and it reads as live wealth software.
- A rebalance button that implies an order. DigiQuant’s human gate is not a Morningstar share edit.

### Sharesight

Public record: Sharesight help on the performance report, and the Sharesight blog posts on that report and on figures that “look wrong.”

- Performance is a report you run from a Reports or Tools area. You pick a range, a grouping (sector, industry, custom, or none), a label filter, a graph type, and open positions versus open plus closed. Then you run it.
- The graph can be a percentage comparison or a benchmark treemap. It can be hidden.
- The blog tells readers that a “wrong” number is often the date range, the open-versus-closed toggle, or annualization. The methodology is part of the screen’s job.
- Settings that change returns live on the portfolio, not in a global junk drawer.

Steal:

- Tearsheet is a report with its assumptions on the page: range, open versus closed, grouping, and a sentence on the method.
- Closed paper trades stay available. Sharesight’s own support notes that hiding them changes the number. Ledger and Tearsheet should not drop them quietly.
- Labels as a filter, later, if journaling needs them. Not a new nav item.

Avoid:

- A report builder as the home screen. One tearsheet, with a few honest controls, is enough.

### Portfolio Performance

Public record: `portfolio-performance.info` and the manual pages for the performance dashboard, performance views, security accounts, and the calculation view (`help.portfolio-performance.info`).

- Navigation is a View menu plus a sidebar: accounts on one side, reports on the other.
- The performance dashboard is a configurable one-page report of widgets (return lines, earnings, taxonomy pies, a small performance chart).
- A security account is a dual pane: the list on top, and a bottom pane with Statement of Assets, Transactions, Chart, and Holdings.
- The calculation view is a bridge: assets at start, earnings, taxes, fees, assets at end. Categories expand.
- Data stays in a local file. There is no broker ticket. Historical prices are loaded from named providers.
- Taxonomies are how attribution is grouped. A widget can show actual versus target allocation.

Steal:

- The start-to-end bridge belongs on Tearsheet. It is the honest version of a performance number.
- The bottom pane (holdings, transactions, chart) is the drill-down from a book row: dossier or a Ledger filter, plus one LuxAlgo pane.
- Taxonomies are Attribution’s grouping control, not a settings maze.

Avoid:

- A widget canvas the reader assembles. DigiQuant ships the scoreboard. Custom dashboards are a FactSet habit, not this spine.
- A chart tab that is a homemade price chart. If a chart is on that pane, it is LuxAlgo.

### Edgewonk-class trade journals

Public record: Edgewonk’s journaling course outline (`edgewonk.com/course`), the help articles on setups and on preparing an import, and the public import-platform page.

- The first-run path is taught: enter or import trades, then tag setups, then settings, then custom statistics, then screenshots and trade management.
- Import is a journal action: pick a platform, optionally assign one setup to the batch, upload. Platforms that are missing use a generic spreadsheet. Manual entry remains.
- Setups can be disabled. The help article says they are not deleted.
- Qualitative notes and screenshots are a second pass after the fill exists. The vendor’s own line is that the broker file cannot supply them.
- Analytics (they market an “Edge Finder”) run on the journal. The journal is not a chart product and not a broker.

Steal, when journaling leaves coming-soon:

- Fills first, tags second. Ledger can stand in until the journal exists. The journal, when it ships, attaches to fills. It does not replace Holdings.
- Disable a setup rather than pretending it was never there.
- An empty journal says “no fills yet” and offers import or manual entry. It does not show a sample equity curve.

Avoid:

- Shipping the journal early as a gray nav item.
- A statistics playground with no fills under it.

### Alpaca paper

Public record: Alpaca’s paper-trading docs (`docs.alpaca.markets/us/docs/paper-trading`), the learn article “How to Start Paper Trading,” the options dashboard article, and an Alpaca staff reply on the community forum (2023-10-18) about where history lives.

- Paper and live are separate accounts. The dashboard’s account control, described at the top left in both learn articles, switches between them. The docs say to check you are on the right one before sending an order.
- A paper-only account exists. Paper uses the same API shape as live and a different base URL. Fills are simulated against quotes. The docs list a table of differences: no borrow fees on paper (marked coming soon in that table), slippage and partial fills not fully simulated.
- The learn article points at Portfolio, Orders, and Activity as the places to see a paper trade.
- Staff on the forum: Portfolio shows current holdings only. Past orders are under Accounts, then Orders. A liquidated name disappears from Portfolio. A reader called out that performance history is not on the dashboard.

Steal:

- Paper is a real account with its own fills, not a theme toggle on a live ticket.
- Activity is a destination. That is Ledger. Current holdings staying on Holdings while history stays on Ledger matches the staff description, except DigiQuant should not make the reader hunt through an Account menu to find the fill.

Avoid:

- The same order ticket and the same top-left switch as live. That is fake live-broker chrome the moment the paper book looks like a brokerage.
- Dropping a closed name so thoroughly that the book cannot explain yesterday. Tearsheet and Ledger keep the history Alpaca’s portfolio view does not.
- Copying Alpaca’s “coming soon” borrow-fee cell into our navigation. Their docs can mark a table cell. Our nav omits or uses one chip.

---

## 5. Modern fintech research UI

### Koyfin

Public record: Koyfin help, “Getting started” (updated 2024-08-26), My Dashboards, My Screens, Watchlist News, and hotkeys.

- Left navigation, documented as: My Watchlists, My Screens, My Portfolio (lots, cost, P/L, FX), Model Portfolios, a news section, Graphs, My Dashboards, plus market dashboards, analytics, and security analysis.
- The top command bar opens with `/`. Help text explicitly compares it to Bloomberg and Reuters shortcuts. A ticker plus a feature code jumps to that page. Saved dashboards and chart templates can have their own codes.
- Security analysis is the dossier: a snapshot for one stock, ETF, fund, or series.
- My Dashboards is a canvas of widgets (table, historical graph, performance graph, news). Drag a ticker from the table onto the graph.
- Screens are a filter over a large universe, with columns that match the filters, and an export to a watchlist. A screen rescans. It is not a portfolio.
- Watchlist News is a mode on the watchlist, not a separate product. Sources and filing types can be turned down.
- Empty dashboards start blank or from a template.

Steal:

- The dossier. Optional ticker surface: identity, a LuxAlgo pane, news or filings if we have them, and a link back to the book row that opened it.
- Screens, if they ever exist, belong near Pipeline as research, and they write candidates. They do not place orders.
- A command bar is the Bloomberg idea made small enough for this product. It is not version-one chrome. Open question below.
- Model portfolios are paper-like allocation objects. House is the closer DigiQuant idea: a declared paper book with a profile, not a public model marketplace.

Avoid:

- A personal widget canvas as the home. Brief is a fixed scoreboard.
- Graphs as a top-level chart product. Koyfin can do that because Koyfin is the chart. DigiQuant’s chart is a LuxAlgo pane.

### Robinhood Legend

Public record: `robinhood.com/us/en/legend/` and the support article “Layouts on Legend.” StockBrokers.com’s 2026 Robinhood versus Public comparison is used only for the claims it tabulates (paper trading and journal marked absent on both). It is a review site, not Robinhood.

- Legend is a separate desktop-style web product for Robinhood brokerage customers. The marketing page centers on charts, trading from the chart, preset layouts, and widget linking across layouts and monitors.
- Support: up to nine layouts, start from scratch or from a template, add and drag widgets, automatic save, open a second layout in a new tab. Linking is documented in a sibling article.
- The product story is speed to an order. There is no paper-first path on these pages.
- The comparison table’s “no paper trading” and “no trade journal” cells match what the official pages fail to offer. This scan does not need the rest of that table.

Steal:

- Almost nothing structural. A template so the first session is not a blank grid is already covered by FactSet and LSEG, with less order-ticket attached.
- Widget linking is the same selected-symbol idea, and it is already stolen in a narrower form.

Avoid:

- Gamified, live-default trading chrome. Confetti, one-click buy, and P/L as a score do not belong on Brief.
- Legend’s layout playground. Nine user-built layouts fight a locked spine.
- Trading from the chart. A LuxAlgo pane does not host an order.

### Public.com

Asked class: “Public.com Power.” This scan did not find a public product under that name.

What the public FAQ and product pages do show (fetched 2026-10-01):

- “Explore the new investing experience on the web” (Public FAQ, updated 2025-07-30): a web portfolio, a left sidebar that moves between the portfolio and an inbox, a top search, and a symbol page with key facts and news. Premium is called out for advanced charts. Some mobile features are absent on the web, and the FAQ says so.
- Trade FAQ: buy and sell from the symbol page or from the portfolio row. Markets is a discovery page (movers, earnings).
- Options Hub markets a strategy builder, a customizable chain, a Queue for staged orders, and an education toggle on strategy cards. That builder is an options-order builder, not a quant strategy builder.

Steal:

- A symbol page that is a dossier, reached from the book, with one trade action omitted until live exists.
- Saying, in the empty or partial state, which surfaces are not on this tier. Public’s web FAQ does that in prose. DigiQuant should do it by omitting the control.

Avoid:

- Calling a retail brokerage “Power” and copying an order-centric symbol page.
- An options strategy builder. Different product. DigiQuant’s builder, when it exists, is the digichat-led strategy builder inside the dashboard.
- Community and social feeds. Not on the spine.

---

## Steal list

Patterns that survive the locks, and the surface they land on.

| Pattern | Where it showed up | DigiQuant surface |
|---|---|---|
| Dense scoreboard, then the book, then a row | bloomberg.com watchlist, Morningstar holdings, Client Portal portfolio | Brief, then Holdings, then optional ticker dossier |
| Paper activity is a list of fills with state | thinkorswim Monitor, Alpaca Orders and Activity, Client Portal transaction history | Ledger. Working, filled, canceled if we have them. Paper is the default label on the row |
| Performance is a report with a method | Sharesight performance report, Composer backtest basics, Portfolio Performance calculation bridge, pyfolio-style tearsheets | Tearsheet. Range, open versus closed, and a sentence on what the number is |
| Contribution is a cut plus a table | Morningstar X-Ray holdings breakdown, Portfolio Performance taxonomies | Attribution |
| The case sits next to the name, not in a chat log | Morningstar has no equivalent; DigiQuant’s own theses already do this job | Theses. Pipeline is where the reasoning is produced |
| One layout per job, panels that do not fit leave | LSEG Workspace best practice and migration overflow, FactSet “add the app or it is absent” | The spine. Coming-soon modules are overflow, not tabs |
| Chart beside the table, maximize one pane, selection drives the pane | FactSet portfolio tiles, TradingView maximize and sync, IBKR color groups, Koyfin drag-ticker-to-graph | A LuxAlgo embed pane on Brief drill-down, Tearsheet, or the ticker dossier. Not a Charts destination |
| Selected row opens a dossier | Koyfin security analysis, Public symbol page, thinkorswim symbol selector | Optional ticker dossier. One primary action: return to the book, or open Theses for that name |
| Paper before capital, and the screen says “simulated” | Composer Watch ($1,000 simulated, labeled as such), Alpaca paper-only accounts, DigiQuant’s own house copy (“Paper book — no live-trading path”) | Holdings and House. Never a live P/L figure on an empty or paper book |
| Fills first, notes second | Edgewonk import, then setups and screenshots | Ledger now. Journaling stays coming-soon and attaches to fills later |
| Settings omit the tier | FactSet and LSEG hide apps you did not add. Stripe-style omission is the craft rule. thinkorswim keeps Setup in the corner, not in the workflow | Settings. A tier the reader does not have is absent. Auth is the gate in front, not a settings tab |
| Honest empty | Morningstar “create a portfolio,” Edgewonk first-run course, bloomberg.com “Start this list,” Alpaca’s empty portfolio | Say what is empty: no paper book yet, no fills yet, no thesis yet. Offer the one action that fills it. No sample P/L |
| Mono, tabular numbers, hairline, flat panels | Terminal density, already in digiquant-web | Every spine surface. The marketing site keeps this look and does not gain the tools |
| Literal sidebar, sticky tabs in the page | Current `PortfolioSectionNav` already does the tabs. Linear and Cursor are the craft reference | Sidebar stays short. Book sections stay sticky tabs on one surface. Do not add a second sticky bar |

One primary action, so the sibling nav-map has something to protect:

| Surface | Primary action |
|---|---|
| Brief | Read the scoreboard |
| Holdings | Read the paper book |
| Theses | Read the case |
| Tearsheet | Read the report |
| Ledger | Read paper fills |
| Attribution | Read contribution |
| Pipeline | Open the reasoning |
| House | Read the house paper book |
| Settings | Change something this tier includes |
| Auth | Sign in |
| Ticker dossier | Read one name |

---

## Avoid list

| Anti-pattern | Where it is normal | Why it fails a lock |
|---|---|---|
| Kitchen-sink nav | Bloomberg function menus, thinkorswim’s tab row, FactSet’s insert menu, TWS layout library | The spine is locked. Extra products wait in overflow |
| Live-by-default, and gamified P/L | Robinhood Legend, Composer’s Invest path, retail buy buttons | Research and the paper book come first. No fake live P/L |
| The chart is the product | TradingView, Legend, thinkorswim Charts, Koyfin Graphs | LuxAlgo owns charts. A competing study library, drawing toolbar, or broker-on-chart is out |
| Fake live-broker chrome | thinkorswim paperMoney mirroring live, Alpaca’s shared ticket with an account switch, TWS order entry | Paper is a book and a ledger, not a costume on a brokerage |
| Builder on the marketing site | Composer’s homepage describes the editor and keeps it in-product. The failure mode is the inverse | digiquant-web is the showcase. The builder, when it ships, is in the dashboard |
| Gray soon-nav | Easy to copy from “coming soon” docks | Omit the destination. If the flow must mention it, one disabled control with a chip |
| Nested sticky chrome | App shells that pin a sidebar, a subnav, and a toolbar | One literal sidebar, one sticky tab row inside the book |
| AI-SaaS glass, hero cards, purple | Generic agent products | Conflicts with digiquant-web’s flat finance craft |
| A fat marketing clone inside the app | Landing pages rebuilt as the signed-in home | The showcase and the product are different surfaces. They share craft, not pages |
| Paper as a choice on a live-deploy form | QuantConnect Deploy Live brokerage dropdown | Paper is the environment you are in. Live is omitted until the human gate |
| An IDE, a widget canvas, or a strategy marketplace as the home | QuantConnect IDE, Koyfin My Dashboards, Composer Discover | Pipeline is the only reasoning hub. Brief is a fixed scoreboard |
| Account aggregation, funding, margin, transfer | Morningstar link-account, IBKR Transfer & Pay, Alpaca Add Funds | Not this product |
| Order from a research row | thinkorswim Scan, TradingView trading panel, Legend | Drill-down opens a dossier or a thesis, not a ticket |
| Hiding closed trades so the number looks cleaner | Alpaca Portfolio, Sharesight’s default open-only toggle | Tearsheet states the toggle. Ledger keeps the fills |
| Olympus, Atlas, Hermes, Kairos as labels | Retired names in older docs | Job words only |
| Private-client names | — | Never |

---

## IA implications for the sibling nav-map

These are constraints for that plan, not the plan.

1. The sidebar is literal and short. Candidates that match the locks: Brief, the book, Pipeline, House, Settings. Auth stays off the sidebar.
2. Holdings, Theses, Tearsheet, Ledger, and Attribution are one book with one sticky tab row. That is already how `PortfolioSectionNav` is built. Promoting each word to its own sidebar item would copy thinkorswim’s tab problem and add a second sticky layer if the tabs remained.
3. Brief is the scoreboard in front of the book. A row drills into Holdings, a thesis, or the optional dossier. Brief is not a second portfolio and not a chart layout.
4. Pipeline is the only reasoning hub. The coming-soon builder and the coming-soon digichat embed hang off Pipeline when they exist. They do not get sidebar rows now.
5. House stays separate from the user book. It is the digithings house ETF paper book, already labeled that way, with read-only profile pins. It is not a second Holdings.
6. Settings omits by tier. Paper connection can live there when that tier exists. Live broker setup is omitted until the human gate. Do not mirror Alpaca’s paper/live switch in the header.
7. The ticker dossier is optional and has no sidebar slot. It opens from a row. Its chart pane is LuxAlgo.
8. FX Hub is on the sidebar today and is not in the locked spine. The nav-map has to place it or retire it from chrome. This scan does not give it a new job.
9. Coming soon (builder, journaling, live brokers, digichat embed, other solutions) uses overflow: omit, or one disabled control with a chip on the surface where the action will eventually sit. Journaling’s future chip belongs on Ledger. The builder’s future chip belongs on Pipeline. Live brokers’ future chip belongs in Settings. None of them belong on digiquant-web.
10. Empty states are copy, not illustration. “No paper fills yet” on Ledger. “No thesis on this name” on Theses. No starter equity curve, no themed fake book that looks funded.
11. Density stays in the page, not in the number of destinations. Mono labels, tabular numbers, hairline borders, flat panels. One primary action. No glass cards.
12. Do not put a chart destination on the sidebar. LuxAlgo panes are embedded where a number needs a picture: Brief drill-down, Tearsheet, dossier.

Staged flow the nav has to keep obvious:

```text
Brief (research scoreboard)
  → Holdings (paper book)
    → Ledger (paper fills)
      → journal, later, attached to those fills
        → Settings (tier that exists)
Pipeline (reasoning that produced the thesis and the book)
live brokers omitted until the human gate
```

---

## Coming soon, in practice

| Future module | Public patterns that justify the treatment | Treatment under the locks |
|---|---|---|
| Strategy builder | Composer keeps the editor in the logged-in product. QuantConnect’s IDE is the whole product, which we do not copy | Omitted from nav. Later, one entry on Pipeline. Never on digiquant-web |
| Journaling | Edgewonk is a whole product that starts from fills | Omitted. Ledger is the honest activity surface until then. A chip on Ledger is enough if the flow must mention it |
| Live brokers | QuantConnect puts paper and live on one deploy control. Alpaca shares a ticket | Omitted from Settings. No header switch. No order ticket |
| digichat embed | QuantConnect’s Ask Mia sits in the IDE and can deploy | Omitted. Later, inside Pipeline, and it does not gain a deploy action |
| Other solutions | LSEG overflow, FactSet “not added, so not shown” | Omit, or one disabled chip. Not a gray row per solution |

---

## Open questions for Chris

1. Confirm the book is one sidebar destination with sticky tabs (Holdings, Theses, Tearsheet, Ledger, Attribution), rather than five sidebar items. The locked list names all five. The craft feed says one sticky row. Current code already uses the sticky row under Portfolio.
2. Where does FX Hub go? It is top-level today and outside the locked spine.
3. Is Ledger allowed to carry the “journal, later” chip, or should journaling be fully invisible until it ships?
4. When the builder and the digichat embed ship, is Pipeline the only door, with no order action inside the embed?
5. Should a paper-broker connection (Alpaca paper, already a real integration in the dashboard) appear in Settings for the tiers that have it, while live stays omitted? This scan says yes. It needs an explicit yes before anyone draws the settings map.
6. Is the ticker dossier in the first nav-map, or held until LuxAlgo embed panes are specified? If it is in, it has no sidebar item.
7. Is a command bar (Koyfin `/`, Bloomberg command line) in scope for a later pass, or out of the nav-map entirely?
8. House and the user book: confirm they never merge into one portfolio switcher. A switcher is the Alpaca paper/live pattern with different contents.
9. Tearsheet honesty: confirm it may show a hypothetical backtest and a paper-fill record as different labeled sections, and that it must not blend them into one live-looking P/L.
10. Density ceiling on Brief: one scoreboard plus drill-down, not a Launchpad the reader assembles. Confirm custom panels are out of scope.

---

## Source log

Fetched or searched 2026-10-01. Re-check before quoting a control in UI copy. Vendor pages move.

- Bloomberg Terminal: Yale Library Bloomberg basics guide; University of Zurich “Getting started on the Bloomberg Terminal” PDF; Bloomberg Professional Services, “Bloomberg Terminal Essentials: IB, Worksheets & Launchpad,” 2024-10-12.
- bloomberg.com: Help Center watchlist articles; Markets watchlist page (subscriber lists, themed “Start this list”).
- FactSet: Rotman Quick Start Guide PDF (2022); Emory QuickStart PDF; Stanford Libraries FactSet overview; university Portfolio Analysis notes.
- LSEG Workspace: LSEG Workspace quick-start PDF; Eikon-to-Workspace migration quick-start PDF; Aston and Manchester library cards.
- TradingView Help Center: layouts, multi-chart, Supercharts getting started, watchlists (solution ids cited above).
- thinkorswim Learning Center: Getting Started, Left Sidebar, Charts, Flexible Grid, Workspaces.
- IBKR: TWS QuickStart; Mosaic layout guide; Traders’ Academy getting started; Client Portal guides for Portfolio, Transaction History, Statements, Transfer & Pay.
- QuantConnect docs v2: Cloud Platform Getting Started; IDE; QuantConnect announcement “Migrating to QuantConnect” (Quantopian shutdown context, platform off 2020-11-14).
- QuantRocket: “How You Can Still Use Quantopian” (vendor page, Zipline and lectures).
- Composer: composer.trade; starter guide; Knowledge Center articles 54, 67, and 55.
- Morningstar help: Portfolio intro, Holdings, X-Ray, rebalance.
- Sharesight help: Performance Report; blog posts on the report and on figures that look wrong.
- Portfolio Performance manual: performance dashboard, performance views, security accounts, calculation.
- Edgewonk: course outline, setup article, import-settings article, public import-platform list.
- Alpaca docs: Paper Trading; learn articles on starting paper trading and on options in the dashboard; Alpaca community forum thread “Can I see history of positions,” staff reply 2023-10-18.
- Koyfin help: Getting started (updated 2024-08-26), My Dashboards, My Screens, Watchlist News, hotkeys.
- Robinhood: Legend marketing page; “Layouts on Legend” support article.
- Public: FAQ “Explore the new investing experience on the web” (2025-07-30); trade FAQ (2025-09-05); Options Hub and strategy-builder FAQ. No public page found for a product named Public.com Power.
- In-repo: `docs/vision/dashboard.md`, `docs/vision/digiquant.md`, `docs/projects/digiquant/COMPETITORS.md`, `apps/dashboard/lib/nav.ts`, `apps/dashboard/components/portfolio/PortfolioSectionNav.tsx`, `apps/dashboard/lib/house-identity.ts`.

Linear, Cursor, and Stripe appear only as craft constraints supplied with this scan. They are not finance products and were not given a UI audit here.
