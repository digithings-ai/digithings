# digiquant.io rebuild — content inventory

Status: read-only inventory of `apps/digiquant-web` at `origin/develop` 0800efa38.
Purpose: WHAT TO SHOW. Every claim below is copied from shipped source; the rebuild
may reword for density but must not add claims that are not listed here.

## Routes (keep all; static export, `trailingSlash`)

| Route | Today | Rebuild |
| --- | --- | --- |
| `/` | mesh hero, ticker, odometer, pipeline x2, live book, strategy deck, WordReveal claim, pricing + FAQ | **Rebuilt first** (this pass) |
| `/strategies` | library index (live, Supabase `strategy_tearsheets`) | later |
| `/strategies/[id]` | tearsheet (`btc_slapper`, `eth_slapper`, `sol_slapper`, `btc_sdca`) | later; keep `tearsheet/*` + print |
| `/subsystems/[id]` | research / portfolio / execution poster pages | later |
| `/changelog` | `@digithings/design/releases.json` (13 tagged releases, digichat/digiskills) | later |
| `/contact` | two-tier self-hosted / managed | later |
| `/pipeline` | client redirect to `/#pipeline` (also `_redirects`) | keep as redirect |
| `/dashboard/` | separate app (`apps/dashboard`), linked as "Open dashboard" | link only |
| `sitemap.ts`, `robots.ts`, `manifest.ts`, `_redirects`, `_headers`, `not-found` | | KEEP untouched |

## Claims (verbatim sources)

Identity / hero (`layout.tsx`, `page.tsx`):
- "A quant research desk in a glass box you own"
- "The research stack an institutional desk would build — research runs daily and portfolio sizes the risk, through backtest to a tearsheet. Open-source and self-hosted, so work that once needed a team runs for one."
- meta: "every run writes a decision log under its own run id, redacted on the way out"
- install: `git clone https://github.com/digithings-ai/digithings.git`; CTA "Open dashboard" -> `/dashboard/`

By the numbers (`page.tsx`, `MetricsOdometer.tsx`) — all structural or live:
- subsystems: `subsystems.length` (3) · pipeline stages: 7 · backtested trades: live sum over `strategy_tearsheets.total_trades` · live orders: 0 ("nothing is sent to a venue yet")

Pipeline, 7 stages (`ResearchPipeline.tsx` FLOW): 01 Research (chat · LLM) · 02 Indicators (MA, RSI, ADF, DPSD; indicators lib) · 03 Strategy (strategy spec) · 04 Signals (deterministic, reproducible) · 05 Optimize (Optuna; in-sample, tearsheets say so) · 06 Backtest (NautilusTrader, Pine-faithful RSI Wilder / Bollinger population sigma, trade ledger, tearsheet) · 07 Export (TradingView Pine v5; live trading not on; paper/live venues wait on a human gate). Bodies live in that file.

Desk phases (`PipelineScene.tsx`): research phases 00-09 (Preflight, Triage, Alt-data, Institutional, Macro, Asset class, Equities, Consolidate, Synthesis, Publish) · portfolio phases h1-h9 with **no h8** by design (Thesis review, Market thesis, Vehicle map, Screener, Asset analyst, Deliberation, PM direction, Risk sizing, Commit run) · execution "in development for live venues".

Subsystems (`packages/ui/src/data/subsystems.ts`): Research ("Research, persisted — structured views, not prose."), Portfolio ("Delivery, not deliberation theatre."), Execution ("Paper adapters ship. Live tokens never leave the router."), each with role, summary, stack, `docker compose up -d digiquant`.

Live book (`DashboardPortfolioPanel.tsx`): "The research book, valued live." Client island; degrades to "connects on deploy" without Supabase env.

Live ticker (`LiveTickerRow.tsx`): crypto via keyless Coinbase WS, equity majors seeded from daily-close view.

Strategies (`StrategySuite.tsx`, `strategy-*`, `honesty.tsx`): "Browse calibrated backtests from the digiquant library — equity, drawdown, trade logs, and full tearsheets for every release." Each run: Nautilus backtest on Coinbase daily OHLCV. Honesty chips: "Backtest only", "Not OOS vs flat DCA". Published: BTC L/S, ETH L/S, SOL L/S, BTC-SDCA. Tearsheet footer: "backtest · illustrative, in-sample".

Pricing (`_pricing.ts`, approved copy, no invented caps): Self-hosted Free · MIT; Managed "Coming soon" (waitlist, mailto `contact@digiquant.io`); Enterprise "Contact". FAQ x4 (self-host needs, NautilusTrader license, BYO keys, usage limits).

Footer (`_nav.tsx`): Pipeline · Desk · Strategies · Pricing · Changelog · Built on digithings (digithings.ai) · GitHub (github.com/digithings-ai); meta "© 2026 digithings AI · open core".

## Data seams to keep (no visual coupling)

`lib/live/*` (Supabase reads, quote transforms, nav seam), `components/tearsheet/*` + finance-tearsheet print, `CloneRepoButton` behaviour (copy command) — rebuild consumes, does not restyle.

## Do-not-carry list

HeroMesh, HeroGraph, AmbientMesh, PipelineScene, DashboardScene, ResearchPipeline (scroll-fill), StrategySuite deck, MetricsOdometer styling, SiteNav-as-impl, `dq-*`/`dqhero-*`/`dqss-*` families, grain/glow layers, WordReveal claim.

## Home `/` composition plan (short page, kit-only)

1. NavShell (kit) — brand, Pipeline / Desk / Strategies / Pricing / Changelog / digithings.ai, Open dashboard.
2. Title block: h1 claim + lede + clone cmdline + Open dashboard (one loud control).
3. Numbers strip (4 real figures).
4. Pipeline: 7 stages as a dense hairline ledger.
5. Desk: 3 subsystems x phase ranges as ledger rows, links to `/subsystems/*`.
6. Strategies: 4 published rows (live metrics when Supabase set; honest placeholder otherwise) + "Backtest only" chip.
7. Pricing: 3 tiers as one table + FAQ.
8. Footer (kit).

Kit parts to look for first (promote to `packages/ui` + reference specimen if missing): DocumentFrame/Section/PageTitle/GlyphList, Table (numeric/density), Badge, Figure, FooterCells, NavShell, OdometerStrip/StatCounter, PricingMatrix.
