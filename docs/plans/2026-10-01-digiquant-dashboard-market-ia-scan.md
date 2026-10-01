# DigiQuant dashboard market IA scan

> **Date:** 2026-10-01
> **Status:** Draft plan. Research only. No UI, no routes, no product implementation.
> **Feeds:** the sibling nav-map plan. This file does not draw the final tree.
> **Audience:** Chris. Human-gate questions are at the end.

This scan reads public finance and quant interfaces for navigation, density, and flow, then keeps only what survives DigiQuant’s locks. Sources are help centers, vendor PDFs, official docs, and public product pages fetched on this date. Private terminals were not logged into. Where a public page names a control, this file names it. Where a name was asked for and the public record does not show it, the gap is stated.

Existing vision this scan sits beside:

- [docs/vision/dashboard.md](../vision/dashboard.md) — operator surface for research, portfolio, and execution, with a human gate before live.
- [docs/vision/digiquant.md](../vision/digiquant.md) — research, then portfolio deliberation, then execution. Paper before live. No skipped step.
- [docs/projects/digiquant/COMPETITORS.md](../projects/digiquant/COMPETITORS.md) — strategy-market notes (Composer, QuantConnect, and others). That file is not an information-architecture scan. This one is.
- [ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md) — job words in the product. Olympus, Atlas, Hermes, and Kairos stay out of labels.

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
