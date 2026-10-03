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
