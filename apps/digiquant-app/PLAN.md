# digiquant-app: gap analysis and build plan (v2)

Scope of "done": the **baseline desk** and the **FX hub (12x)**, end to end: real data, tier/group gating on app and MCP, every block bound to a worker route, writes where scoped. Charts, Terminal (Bloomberg) and LuxAlgo are sidebar entries tagged `[soon]` only.

Principles: never invent numbers (fail closed, "—"); one catalog (`access.ts`) drives sidebar, page guard, HTTP gate and MCP tools; new schema is drafted as files, never applied (human gate); no new public hostname.

## 1. Status

| Layer | State |
|---|---|
| App shell, desks, nav, search, grid, locked states | Done. |
| Atoms (Phase 0) | Done: DataTable v2 (sort/filter/row click/sticky/pagination), AreaChart (+underwater), BarChart, RangeTabs, Drawer, gallery at `/blocks/atoms`. |
| Worker foundation (Phase 0) | Done: real tier ladder, `routes/` registry (+`{param}` templates), `tableRead()` enveloped reader, twelve-x reader (fails closed without key), PUT/POST/DELETE plumbing (401 without `x-digi-user`), catalog-generated MCP tools, edge identity key, brief+ gate on raw `/v1/tables/*`. |
| Live data | Worker runs against live core Supabase locally (`.dev.vars` populated from the main checkouts). Real `/portfolio` verified. |
| Routes | Phases 1–4 registered in `src/routes/` and the catalog. Phase 4 adds strategies (core `strategies` store), shell desks/features (the access catalog), settings reads (typed empty until the edge function is wired), and chat (502 until digichat is wired). Flags, paper exposure, and directives stay a typed empty state. Draft SQL is in `apps/dashboard-api/migrations-draft/` and is not applied. |
| Blocks | Strategies, settings, chat, and shell pages have layouts. The brief page also shows signals, movers (em dash when the day return is missing), and run health. DigiChat is a docked rail plus `/tools/chat`. |
| Phase 5 | Catalog routes generate MCP tools (including `get_access_manifest`, documented in `apps/dashboard-api/README.md`). The app defaults to local `wrangler dev` at `http://127.0.0.1:8788`. The `?as=` mock impersonation is gone. Real-data screenshots are blocked in this environment (no browser session against live books). Docker, LuxAlgo/Bloomberg live data, and the CONTRACT.md merge stay deferred. |

### Review findings from Phase 0 (all fixed unless noted)
- Identity headers were spoofable on a directly reachable worker → `DASHBOARD_EDGE_KEY` + `x-digi-edge-key`. **Deploy requirement: set it on every deployed worker and have the edge send it** (unset = headers trusted, dev only).
- `/v1/tables/*` bypassed the catalog → brief+ only.
- Uncatalogued registry GETs were served → now forbidden.
- Open: the gate is per **path**, not per query variant (`/theses?needs_resolution=1`, `/theses?desk=rates`) → Phase 1 gives these distinct paths (`/theses/signals`, `/rates/theses`).
- Open: `workers_dev = true` keeps a public URL; decide with the edge work (human gate).

## 2. Gaps (unchanged core)

**Backend:** 49 GET + 6 write routes missing, grouped portfolio extras (3), pipeline (7), strategies (10), markets (4), FX (11), rates (3), chat (4), settings (10), shell (3).

**Sources**
- *Exist in core now:* theses, thesis_vehicles, position_attribution, run_health, run_event_trace, documents, instruments, decision_log, prices_live, macro_series_observations, accounting_periods, position_events, strategies*.
- *Need a reader:* all FX (twelve-x project; schema not in repo), intraday FX, pipeline graph (`node_runs` + static graph), chat (digichat DB), settings (edge function).
- *No source:* FX flags, paper exposure, directives, pairs bid/offer; rates summary/signals; strategy deployments/targets; cash ledger events; sleeve column; equity bars/indicators; tape; fx-feed settings; `/desks`, `/features`.
- *Corrections:* `/v1/market/tickers` is a list, not quotes; bars close-only; no `desk` column on theses; run cost/tokens operator-only; graph not in `run_event_trace`.

## 3. Redesign program (ranked; each ships with its route)

1. Drawdown: underwater chart + episodes table (depth, start, trough, recovery, days).
2. NAV vs benchmark: rebased chart, range tabs, period-returns table (1D/WTD/MTD/QTD/YTD/1Y/ITD).
3. Ticker dossier drawer from any row click (thesis, vehicles, P&L, stop→target, events, documents).
4. Decision effectiveness scorecard (hit rate, alpha, calibration, resolved decisions).
5. Holdings: live-vs-close provenance, weight-change badge, risk envelope, thesis link.
6. Attribution: bars + waterfall, window selector, top/bottom contributors.
7. Brief: signals, movers, allocation, run health, freshness strip, "what changes today".
8. Thesis spine + detail.
9. Tearsheet: exposures, benchmark selector, risk-adjusted metrics.
10. Reconciliation strip: NAV vs sum of positions, stale marks.
11. Pipeline: run pager, node walkthrough, duration bars, freshness banner.
12. Library/document viewer.
13. FX depth: consensus matrix, events, trades, track record.
14. Layouts: strategies, settings, chat (+ docked DigiChat rail), desk page.

## 4. Phases

**Phase 0: foundations. DONE.**

**Phase 1: baseline portfolio** (writer A)
- Routes (all enveloped via `tableRead`, each added to the catalog with its gate, MCP tool generated automatically):
  - enrich `/allocations` (name, sleeve from a versioned code mapping over `instruments`, value, day change)
  - `/performance` + drawdown series and episodes (computed from NAV points)
  - `/attribution`, `/theses`, `/theses/signals` (brief), `/ledger/cash` (accounting_periods + position_events, "—" where absent)
  - `/brief` decision + risks (decision_log, documents)
  - `/dossier/{ticker}`
- UI: redesigns 1–3, 5–10, 14 (portfolio part).
- Acceptance: each page renders real data locally; every block either shows data or an honest empty state; per-tier vitest for each route.

**Phase 2: pipeline** (writer B)
- Routes: `/pipeline/runs/latest` (+`?date=`), `/health`, `/graph` (static graph + node_runs), `/nodes/{node}/document`, `/narrative`, `/trace`, `/artifacts`.
- UI: redesigns 4, 11, 12.
- Acceptance as above.

**Phase 3: FX hub, 12x** (writer C)
- Routes: `/fx/summary|pairs|levels|sessions|ideas|ideas/{pair}|pairs/{pair}/path`, `/rates/summary|curve|watchlist`, `/rates/theses` over the twelve-x reader, `fx_intraday_observations`, `macro_series_observations`.
- Flags, paper exposure and directives: routes exist and return a typed empty state until tables exist. **Draft migrations** (files only, in `apps/dashboard-api/migrations-draft/`, not applied) for those three tables plus RLS, for Chris to review.
- UI: redesign 13, existing layouts filled.
- Gate: group `12x` (edge maps product grant `fx_hub`).

**Phase 4: shell, settings, chat, strategies** (writer D). DONE, with the blocks below.
- Reads: `/desks`, `/features`, `/settings/*` (edge function), `/chat/sessions*`, `/strategies*` (strategies tables).
- Writes (identity-required, fail closed): settings prefs PUT, FX directives PUT (writes to the draft table only once Chris applies it; until then 503 typed "not provisioned"), chat session create/rename.
- UI: layouts + DigiChat rail; deploy flow stays "coming soon".

**Phase 5: MCP parity and live.** Catalog tools, `get_access_manifest`, and the wrangler default are done. Screenshots are blocked (no live browser). Docker, LuxAlgo/Bloomberg, and the CONTRACT.md merge stay deferred.
- Verify every catalog route has a generated tool and tier test; `get_access_manifest` documented; local `wrangler dev` default for the app; retire the mock API; real-data screenshots for each page.
- Deferred after: Docker packaging, LuxAlgo/Bloomberg live-MCP data, CONTRACT.md merge of `contracts/*.md`.

## 5. Execution shape
- Phases 1–3 run in parallel as writers with **disjoint file ownership**: each owns `src/routes/<domain>.ts` + tests, its blocks under `components/blocks/<domain>`, its page layouts. Shared files (`access.ts` catalog, `routes/index.ts` module list, `lib/pages.ts`) are edited **only by the coordinator** at merge, from a small per-writer patch file, to avoid conflicts.
- Phase 4 starts after 1–3 merge (it consumes the same registries).
- After each phase: read-only reviewer (gate bypass, fail-closed, a11y, secrets), coordinator fixes, commit, push.
- Workflow size: under 5 agents per run.
- Every route ships with: vitest per tier, catalog entry + gate, CONTRACT.md entry, a real-data browser check.

## 6. Decisions (confirmed 2026-10-02)
1. Tiers: real ladder `free|brief|desk|studio|enterprise`; `12x` = `fx_hub`.
2. FX: separate twelve-x reader; new-table migrations drafted as files only, not applied.
3. Writes in scope (prefs, directives PUT); fail closed without verified user from the edge; no auth/session changes.
4. Phase 0 first, then parallel phases with read-only reviewers.

## 7. Risks and open items
- Edge shim (digikey → identity headers + edge key) is outside this slice; until it exists the app runs on the dev caller. Needs an owner.
- twelve-x schema is not in the repo: Phase 3 route shapes follow the reader; flags, paper exposure, and directives stay draft SQL.
- Settings writes and chat are fail-closed: 401 without `x-digi-user`, 503 `not_provisioned` until the settings edge function and the digichat database are wired. No migration was applied.
- `workers_dev` public URL: decide with the edge work.
- Needs Chris: review of drafted migrations; approval before any schema is applied; deploy-time `DASHBOARD_EDGE_KEY`.
- Real-data screenshots for each page: blocked here (no browser against the live book).

## 8. Slice consolidation (2026-10-02)

The other session's dashboard wire-up (shell, desk atoms, fail-closed Brief panes on `apps/dashboard`) is folded into this catalog terminal. Entitlements stay in `apps/dashboard-api/src/access.ts` only.

Folded in:

- Fail-closed em dashes. Movers keep a held name when the day return is missing and render "—". They do not drop the row and do not substitute zero.
- House-book reads and the envelope `{ data, as_of, retrieval_pin, provenance }` were already the worker contract. The app client now types `retrieval_pin` and surfaces the worker's error message.
- No invented strategy P&L. A tearsheet curve is shown only when every point has a date. Deploy steps stay `todo`.
- Brief seat uses the existing catalog blocks (decision, signals, risks, movers, run health) on the 12×12 grid.

Left on `apps/dashboard` (not ported):

- `BriefDesk` / `DeskChart` one-viewport pane chrome. The terminal grid already covers that seat. Gloomberg quotes, the tape, and LuxAlgo stay sidebar `[soon]` entries, matching this plan.
- Slice A shell and slice B desk-atom restyles of `apps/dashboard`. This app already has the shell, DataTable, charts, and drawer. A second utilitarian skin would be a parallel product.
