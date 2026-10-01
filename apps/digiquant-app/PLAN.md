# digiquant-app: gap analysis and build plan

Scope of "done": the **baseline desk** and the **FX hub (12x)**, end to end: real data, tier/group gating on the app and the MCP, every block bound to a worker route. Charts, Terminal (Bloomberg) and LuxAlgo are listed in the sidebar as `[soon]` only.

Evidence: three read-only audits (wiring, data sources, old dashboard + canvas mock coverage).

## 1. Where we are

| Layer | State |
|---|---|
| App shell, desks, sidebar, search, grid, locked states | Built. Desk picker, manifest-driven nav, page guard, locked blocks. |
| Block library | ~76 blocks. 13 pages have default layouts (brief, portfolio x5, pipeline, fx x5). |
| Worker routes | 8 live (`/portfolio /allocations /nav-series /brief /performance /kpis/live /benchmarks /ledger`) + `/access/manifest` + `/v1/tables/*` (bare rows, not enveloped). All GET. |
| Access gate | One policy for HTTP and MCP (tier + group). Identity from `x-digi-tier`/`x-digi-groups`: **nothing injects them yet**. |
| MCP | 8 tools + manifest tool, filtered by caller. |
| Real data | Not yet seen. Needs `SUPABASE_SERVICE_ROLE_KEY` locally. |

Block status: 12 implemented, 7 partial (fields missing), ~57 with no worker route.

## 2. Gaps

### A. Backend routes (49 GET + 6 writes missing)
Groups: portfolio extras (3), pipeline (7), strategies (10), markets (4), FX (11), rates (3), chat (4), settings (10), shell (3).

### B. Real-source reality check (changes the contracts)
- **Servable from existing tables now:** theses (`theses`, `thesis_vehicles`), attribution (`position_attribution`), run health (`run_health` view), call trace (`run_event_trace`), node documents/narrative (`documents`), names (`instruments`), brief decision/risks (`decision_log`, `documents`), rates curve (`macro_series_observations`, tenors unverified), drawdown (computed from NAV points), quotes (`prices_live`).
- **Needs a new reader/proxy:** all FX reads (separate **twelve-x** Supabase project, schema not in this repo), intraday FX (`fx_intraday_observations`, service-role), pipeline graph (`node_runs` is service-role + static graph in `research/graph.py`), strategies (`strategies*` tables exist), chat (separate digichat DB), settings (Supabase edge function `settings`).
- **No source exists:** FX flags, paper exposure, directives (+PUT), pairs board bid/offer; rates summary/signals; strategy deployments/targets/deploy flow; cash ledger events; sleeve column; equity intraday bars + indicators; market tape; `/settings/fx-feed`; `/desks`, `/features`.
- **Contract corrections:** `/v1/market/tickers` is a ticker list, not quotes; bars are close-only (no OHLCV); `theses?desk=rates` has no desk column; run health cost/tokens are operator-only; the pipeline graph is not in `run_event_trace`.
- **Identity mismatch:** real tiers are `free | brief | desk | studio | enterprise`; the 12x group is `client_product_grants.product_key = 'fx_hub'`. Our `free|pro|max` and `12x` have no mapping.

### C. Front-end redesign opportunities (ranked)
1. Drawdown: underwater chart + episodes table (today two KPIs).
2. NAV vs benchmark chart with date axis, range tabs, period-returns table (today a sparkline + "Points").
3. Ticker dossier drilldown (row click from holdings/attribution).
4. Decision effectiveness scorecard (hit rate, alpha, calibration, resolved decisions): the old app's most distinctive view.
5. Holdings: live-vs-close provenance, weight-change badge, stop→target envelope, thesis link.
6. DataTable: sort, filter, row click, sticky column, pagination (affects every block).
7. Attribution charts (bars, waterfall, window selector).
8. Brief: place signals, movers, allocation, run-health, ticker strip; "what to change today".
9. Thesis story spine + detail (confidence, horizon, criteria, vehicles with weight/P&L).
10. Layouts for strategies, settings, chat (+ docked DigiChat rail), desk picker page.
11. Pipeline: run-date pager, node walkthrough, per-node duration bars, cost row, freshness banner.
12. Tearsheet: exposures, benchmark selector, risk-adjusted metrics, PDF.
13. Library/document viewer behind node documents.
14. Reconciliation + freshness strip (NAV vs sum of positions, stale marks).
15. FX depth from twelve-x (consensus matrix, events, trades, track record).

## 3. Decisions (recommended defaults; change any before Phase 0)
1. **Tiers:** adopt the real ladder `free | brief | desk | studio | enterprise` in `access.ts` (replace `free|pro|max`); map pro→`brief`, max→`desk`. Group `12x` = product `fx_hub`.
2. **Identity:** a small edge shim resolves `my_access()` (tier + product grants) from the caller's JWT and injects `x-digi-tier`/`x-digi-groups`; the worker stays header-only.
3. **Sleeves:** derived in the worker from `instruments.sector/asset_class` via a versioned mapping table in code (no DB column exists).
4. **Cash ledger:** from `accounting_periods` (opening/closing cash, pnl) + `position_events` fills; honest "—" where absent.
5. **FX:** a separate twelve-x reader (its own key as a worker secret). Flags/paper exposure/directives have no source: ship read blocks with typed empty states first; directives PUT and flags get a new twelve-x table in a later slice (human gate: schema change).
6. **Writes:** worker gains PUT/POST/DELETE + CORS for them, per-user routes only behind real identity. Until then write blocks stay read-only ("writable: false").
7. **Strategies/chat/settings:** read paths over `strategies*`, digichat DB and the settings edge function; deployments/deploy flow stay "coming soon" (no source).
8. **Equity bars:** close-only line charts now; OHLC/indicators wait for a bars source. Charts page stays `[soon]`.

## 4. Plan (phases, each shippable)

**Phase 0: foundations** (one agent, blocking)
- Worker: route-module layout (`src/routes/<domain>.ts`), shared enveloped `tableRead()` helper over the tables proxy, write-method plumbing + CORS, tier rename + shim contract, per-route access tests.
- App: DataTable v2 (sort/filter/click/pagination), chart atoms (area/underwater, bar, benchmark rebase, crosshair), `Dossier` drawer pattern.
- Catalog: add missing blocks to the manifest and fix manifest/layout mismatches; one generated MCP tool per catalog route (replace the hand-written list).

**Phase 1: baseline portfolio** (real data first)
- Routes: `/allocations` enrich (name, sleeve, value, day), `/brief` decision+risks, `/performance` drawdown + episodes, `/theses`, `/attribution`, `/ledger/cash`.
- UI: redesigns 1, 2, 5, 7, 9, 12, 14; ticker dossier (3); brief completion (8).

**Phase 2: pipeline**
- Routes: `/pipeline/runs/latest[/health|/graph|/nodes/*/document|/narrative|/trace|/artifacts]`, date pager param.
- UI: redesign 11; node walkthrough; decision scorecard (4); library viewer (13).

**Phase 3: FX hub (12x)**
- Routes: `/fx/*` and `/rates/*` over the twelve-x reader + `macro_series_observations` + `fx_intraday_observations`.
- UI: layouts exist; add depth items from 15 in order consensus, events, trades.

**Phase 4: shell, settings, chat, strategies (read)**
- `/desks`, `/features`, `/settings/*` (via edge function), `/chat/sessions*`, `/strategies*`; layouts + DigiChat rail; coming-soon pages for deploy/charts/terminal/luxalgo.

**Phase 5: MCP parity + live**
- Tool per route, `get_access_manifest` first, tool tests per tier; local `wrangler dev` against live Supabase; remove the mock API from the default dev path.

### Execution shape
Phases 1-3 are independent after Phase 0: run as parallel **worktree-isolated** agents (max 4), one per phase, each owning its worker routes + tests + blocks + layouts, merged by me; read-only review agents between phases. Every route ships with: vitest per tier, contract entry, mock parity, and a browser check against real data.

## 5. Needs from Chris
- Confirm decisions 1, 5, 7.
- Local `SUPABASE_SERVICE_ROLE_KEY` (core) and, for FX, the twelve-x project key as a secret.
- OK to add a twelve-x table (flags/directives) later: schema change is a human gate.
