# DigiQuant — Design & Implementation Gap (DigiChat / DigiGraph Vision)

**Audience:** Engineering planning for the “investing copilot” flow: research → user profiling → baseline strategy → iterate/backtest → optimize → compare → export/deploy.  
**Scope:** DigiQuant’s role inside **DigiThings** (DigiChat UI, DigiGraph orchestration, DigiSearch RAG, DigiSmith observability, DigiClaw gateway).  
**Status:** Gap analysis as of repo state (February 2026). Update this doc when capabilities land.

---

## 1. Vision recap (product contract)

### 1.1 User journey (canonical)

1. **Explore** — User asks about an asset class or theme (e.g. gold); system grounds answers in **documentation / peer-reviewed or curated sources** (primarily **DigiSearch**), not in fabricated backtest stats.
2. **Ideate** — System proposes **strategy families** that fit the user’s goals and literature, with honest uncertainty and **no implied performance** until a backtest runs.
3. **Profile** — Structured capture of: horizon, long/short/both, instruments (spot, futures, ETF), risk tolerance, constraints, data availability, jurisdiction — stored as a **versioned intent object**, not only chat prose.
4. **Baseline** — Map intent → **registered strategy + default params** (or approved template); run **initial backtest** on **user- or tenant-provided OHLCV** (or approved data feeds).
5. **Iterate** — User changes ideas; system runs **variant backtests**, surfaces **comparison** (metrics, trade counts, drawdowns).
6. **Optimize** — Grid / random / Bayesian over params with **constraints** (min trades, max DD, etc.).
7. **Export / deploy** — Emit **auditable artifacts**: Python/Nautilus strategy bundle, **Pine** (TradingView), **QuantConnect**, **broker API** wrappers — with **human gates** before live trading (`SECURITY.md`).

### 1.2 System boundaries

| Layer | Owns |
|-------|------|
| **DigiChat** | UX, conversation persistence, displaying tool results & comparisons, tenant config (URLs, health). |
| **DigiGraph** | LangGraph workflows, LLM calls, **when** to call quant vs search, session/workflow state, tool routing. |
| **DigiSearch** | Ingestion, chunking, retrieval, citations for research steps. |
| **DigiQuant** | **Deterministic** backtest/optimize/export, strategy registry, data loading (Polars), Nautilus execution, structured metrics. |
| **DigiSmith** | Traces/metrics for LLM and (optionally) quant spans. |
| **DigiClaw** | Gateway, audit, heartbeat — policy and egress concerns. |

**Rule:** Anything that must not hallucinate (Sharpe, PnL, trade list) belongs in **DigiQuant** (or downstream verified stores), not in the raw LLM transcript.

---

## 2. Current implementation inventory (what exists today)

Use this as the baseline for “reuse vs build.”

### 2.1 Core pipeline (Python package `digiquant`)

| Area | Location | Notes |
|------|-----------|-------|
| Backtest entry | `src/digiquant/backtest.py` | `run_backtest(...)`: Nautilus via `nautilus_runner`; requires `digiquant[nautilus]`; **requires** `data_path` or `data_dir`; supports **`strategy_params`**; in-memory cache keyed by config hash. |
| Nautilus orchestration | `src/digiquant/nautilus_runner.py` | Bar loading, engine wiring, metrics → `BacktestResult`. |
| Optimization | `src/digiquant/optimize.py`, `optimize_bayesian.py` | Grid / random / Bayesian (Optuna); uses `run_backtest` per trial. |
| Constraints | `src/digiquant/constraints.py`, `models.OptimizationConstraints` | Hard filters before scoring. |
| Param specs | `src/digiquant/strategy_specs.py` | Per-strategy bounds; optional **`DIGIQUANT_STRATEGY_SPECS_PATH`** YAML overlay; alias → canonical map. |
| Strategy registry | `src/digiquant/strategies/registry.py` | `register`, `get_strategy`, `list_strategies()` — Nautilus strategy classes + configs. |
| Implemented strategies | `src/digiquant/strategies/*.py` | EMA cross variants, RSI momentum, Bollinger MR, MACD trend (see `digiquant/ARCHITECTURE.md`). |
| Data loading | `src/digiquant/data/loader.py` | Polars OHLCV helpers (`load_ohlcv_csv`, synthetic, etc.). |
| Sweep | `src/digiquant/sweep.py` | Loop over grid calling `run_backtest` (not VectorBT fast path). |
| Export | `src/digiquant/export.py` | Writes **JSON** artifact under constrained dir (`EXPORT_OUTPUT_DIR`); message states platform deploy not implemented. |
| TradingView | `src/digiquant/tradingview.py` | Stubs for PyneCore path. |
| Brokers | `src/digiquant/brokers/stubs.py` | Stub adapters (`NotImplementedError`). |
| ADDM drift | `src/digiquant/addm.py` | Stub `check_drift`. |
| Models | `src/digiquant/models.py` | `BacktestResult`, `OptimizeResult`, `ExportResult` — Pydantic v2. |
| CLI | `src/digiquant/cli.py` | `backtest`, `optimize`, `export`. |

### 2.2 HTTP API (`src/digiquant/server.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness. |
| `GET /check_drift` | Stub drift API. |
| `POST /run_backtest` | Sync backtest (`BacktestRequest`). |
| `POST /backtest/start`, `GET /backtest/{id}/progress` (SSE), `GET /backtest/{id}/result` | Async backtest. |
| `POST /v1/jobs/backtest`, `GET /v1/jobs/{id}/status` | Versioned async job surface. |
| `POST /run_optimize` | Optimization. |
| `POST /run_export` | JSON export. |
| `POST /run_pipeline` | Backtest → optimize → export chain. |

Cross-cutting: **rate limits**, optional **`DIGI_API_KEY`** Bearer auth, **`X-Request-ID`**, **digibase** error envelope, optional OTEL (`digibase[otel]`).

### 2.3 DigiGraph integration today (`digigraph/src/digigraph/graph/nodes.py`)

- **`backtest_node`** calls DigiQuant with **`strategy_name`**, **`symbols`**, **`data_dir`** from env **`DIGIQUANT_DATA_DIR`** only.
- Prefers **`POST /v1/jobs/backtest`** + poll **`GET /v1/jobs/{id}/status`**, then **`GET /backtest/{id}/result`**; falls back to legacy paths and finally **`POST /run_backtest`**.
- **`strategy_validator_node`** checks `strategy_name` and non-empty `symbols`.
- **Does not** pass **`strategy_params`**, **`data_path`**, **`constraints`**, or **`tearsheet_path`** from workflow state.

### 2.4 DigiChat integration today

- **Health / config**: `digichat/src/lib/ecosystem.ts`, connections sheet — operator can set **DigiQuant base URL**; `GET /api/health` pings DigiQuant.
- **No first-class “quant run” UI** beyond generic tool/collapsible parts in chat (no comparison matrix, no run history from DigiQuant).

### 2.5 Architecture docs

- `ARCHITECTURE.md` states **MCP-first** and “DigiGraph exposes major nodes as MCP tools”; DigiQuant is described as invoked **by DigiGraph**, not directly by the user.
- `digiquant/ARCHITECTURE.md` Phase 2 is accurate for **backtest/optimize/export HTTP**; it notes **DigiGraph still calls HTTP** and full **MCP exposure from DigiQuant** is not the current primary integration.

---

## 3. Gap analysis by capability

For each area: **goal**, **today**, **gap**, **leverage existing code**, **options**, **recommended direction**.

### 3.1 Research & knowledge (literature, “what works on gold”)

| | |
|--|--|
| **Goal** | Grounded answers with citations; separate *theory* from *empirical results on user data*. |
| **Today** | DigiQuant has **no RAG** and no paper index. DigiGraph runs **research_inner** + **research_brief_builder** with a typed **`ResearchBrief`** (`digigraph/research_brief_models.py`) and **`rag_sources`**; DigiSearch stores tier-tagged chunks and structured filters (see `digisearch/ARCHITECTURE.md`). |
| **Gap** | Registry validation of **`suggested_catalog_strategies`** against live **`list_strategies`** remains a product hardening step. |
| **Leverage** | Keep all literature in **DigiSearch** + DigiGraph prompts; DigiQuant exposes **`list_strategies`** + **`StrategySpec.metadata`** for catalog-aware briefs and backtests only. |
| **Options** | (A) Duplicate a small “quant FAQ” corpus in DigiQuant — **avoid** (split brain). (B) **DigiSearch collections** per asset class + `digisearch` tool — **prefer**. |
| **Direction** | Tighten **brief → validate_strategy → backtest**: reject unknown `strategy_name`, surface registry aliases in prompts, and keep **no performance claims** in RAG prompts until DigiQuant runs. |

### 3.2 User profiling & intent (investment period, products, long/short)

| | |
|--|--|
| **Goal** | Deterministic mapping from user answers to **backtest constraints** and **instrument universe**. |
| **Today** | `WorkflowState` includes `trading_profile`, `research_brief`, `rag_sources`, `profiling_questions`, plus `strategy_name` / `symbols` / `backtest_result`. DigiQuant has **`OptimizationConstraints`**. |
| **Gap** | No persisted **`TradingProfile` / `StrategyIntent`** shared across DigiChat session and DigiGraph checkpoint. |
| **Leverage** | Extend **`WorkflowState`** (or a nested dict) with a versioned profile; mirror summaries into **DigiChat Postgres** (`conversations`) or **Graphiti** per `ARCHITECTURE.md`. |
| **Options** | (A) Profile only in LLM memory — **weak** (drift, no audits). (B) **Pydantic profile** required before `backtest_node` — **strong**. |
| **Direction** | Add **`digigraph/models/profile.py`** (or under `digiquant` only if you want quant-owned validation): horizon, allowed sides, max leverage, instrument types, tax considerations — **validate** against what Nautilus strategies actually support. |

### 3.3 Strategy catalog vs “custom strategy” story

| | |
|--|--|
| **Goal** | Baseline from catalog; later “tweak” indicators; final **deployable** artifact. |
| **Today** | Small **registry**; **unknown** HTTP strategies rejected in `backtest.py` (`_KNOWN_STRATEGIES` from `strategy_specs`). |
| **Gap** | No **parametric templates** for “user-named” variants; no safe **arbitrary Python** from chat. |
| **Leverage** | **`strategy_specs.py`** + **`DIGIQUANT_STRATEGY_SPECS_PATH`** for tenant-specific param ranges; **`list_strategies()`** for discovery. |
| **Options** | (A) **Catalog-only** for v1 — fast, auditable. (B) **Signed plugins** in isolated container — enterprise path. (C) **LLM codegen** to disk — **high risk**; needs review pipeline and sandbox. |
| **Direction** | **Phase 1:** catalog + YAML overlays per tenant. **Phase 2:** “compose” strategies from **lego blocks** (existing nodes) with codegen *only* from approved templates. **Phase 3:** sandboxed custom strategies. |

### 3.4 Data provisioning (gold OHLCV, symbols, sessions)

| | |
|--|--|
| **Goal** | Chat says “gold”; system resolves to **correct CSV / feed** and bar size. |
| **Today** | Operator sets **`DIGIQUANT_DATA_DIR`**; files must be **`{symbol}.csv`**. **`scripts/fetch_real_ohlcv.py`** exists for ad hoc fetch. Chat has **no** upload flow to DigiQuant volume. |
| **Gap** | No **session-scoped dataset registry** linking `X-Digichat-Session` → approved data refs (Digistore / blob URI). |
| **Leverage** | `data/loader.py` and env **`DIGIQUANT_DATA_DIR`**; `WorkflowState.stored_datasets` hook exists in state typed dict but is **not** wired to DigiQuant paths in `backtest_node`. |
| **Options** | (A) Pre-load tenant datasets on volume — ops-heavy. (B) **DigiChat upload** → object store + **signed path** passed as `data_path` — product-friendly. (C) **Data catalog service** — longer-term. |
| **Direction** | Minimal: extend **`backtest_node`** to accept **`data_path`** or **`dataset_ref`** from state populated by an upload/metadata tool. DigiQuant adds **`POST /datasets/register` (optional)** only if BFF cannot map refs to paths. |

### 3.5 Backtest parameterized from chat

| | |
|--|--|
| **Goal** | User says “slow EMA 30, fast 12”; backtest uses those params. |
| **Today** | **`run_backtest(..., strategy_params=...)`** exists in Python. **`BacktestRequest`** in **`server.py` omits `strategy_params`**. **`backtest_node`** never sends params. |
| **Gap** | End-to-end **param tunnel** from chat → graph state → HTTP → `run_backtest`. |
| **Leverage** | Single field addition + JSON serialization; align with CLI `-p key=value`. |
| **Direction** | Add **`strategy_params: dict | None`** to **`BacktestRequest`** and job payload; document in OpenAPI; update **`backtest_node`** to read from `WorkflowState`. **High priority quick win.** |

### 3.6 Optimization from graph / chat

| | |
|--|--|
| **Goal** | “Tune my gold strategy” triggers **`run_optimize`** with profile-aligned constraints. |
| **Today** | HTTP **`/run_optimize`** exists; **no** `optimize_node` in `nodes.py` (graph ends at research + backtest for the Phase 1 path). |
| **Gap** | LangGraph node + state keys (`optimize_result`, `best_params`); tool wiring in orchestration. |
| **Leverage** | `run_optimize`, `OptimizationConstraints`, audit logging in server. |
| **Options** | Sync only vs async jobs (mirror backtest job pattern for long Bayesian runs). |
| **Direction** | Add **`optimize_node`** + **`POST /v1/jobs/optimize`** (future) if trials exceed timeout; start with sync for small grids. |

### 3.7 Compare runs & run history

| | |
|--|--|
| **Goal** | Side-by-side metrics for A/B variants; reproducibility. |
| **Today** | Each `BacktestResult` has `run_id`; **no** persistent run store in DigiQuant; in-memory **backtest cache** only. |
| **Gap** | **Artifact store** (Postgres/JSONL/S3) with `session_id`, `strategy_name`, `params`, `data fingerprint`, metrics. |
| **Leverage** | `audit.py` JSONL pattern (`dq_audit_log`); **`run_id`** already generated. |
| **Options** | (A) **DigiChat DB** tables `quant_runs` — UI-native. (B) **DigiQuant-owned** `results/` SQLite/Postgres — better for non-chat clients. (C) **Blob + checksum** per `ARCHITECTURE.md` “opaque URI”. |
| **Direction** | Define **canonical run record** (Pydantic) emitted by DigiQuant and stored by **DigiChat or shared DB**; add **`GET /runs/{run_id}`** only if DigiQuant is source of truth. |

### 3.8 Export: Python script, Pine, QuantConnect, brokers

| | |
|--|--|
| **Goal** | “Final script” and platform-specific outputs. |
| **Today** | **JSON** export with deploy message “not implemented”; **Pine/broker stubs**. |
| **Gap** | Real **Pine codegen** (subset of strategies), **QC C# or Py** export, **Nautilus runnable module** layout, **broker OAuth** — large surface. |
| **Leverage** | `export.py` path validation and `SUPPORTED_TARGETS`; **registry** holds enough to generate parameter blocks. |
| **Options** | (A) **Template-based codegen** per strategy class — maintainable. (B) **LLM writes Pine** — inconsistent; use only with **lint + simulator gate**. |
| **Direction** | **Per-target milestones:** (1) Nautilus **zip** with strategy file + `config.yaml`. (2) Pine for **EMA + RSI** only. (3) QC template. Broker adapters **after** paper trading story. |

### 3.9 MCP vs HTTP for DigiGraph

| | |
|--|--|
| **Goal** | Discoverable tools with schemas for LLM tool-calling. |
| **Today** | **HTTP** from `backtest_node`; DigiGraph **MCP server** may expose other tools — DigiQuant is **not** yet a first-class MCP server in this repo. |
| **Gap** | Duplication risk if both HTTP and MCP drift. |
| **Leverage** | Implement **`digiquant/mcp_server.py`** (or shared **thin wrapper**) calling the **same** functions as FastAPI handlers: `run_backtest`, `run_optimize`, `run_export`, `list_strategies`, `get_strategy_spec`. |
| **Options** | (A) MCP-only to graph — **clean** for agents. (B) HTTP for ops + MCP for graph — **pragmatic**; generate MCP schemas from Pydantic. |
| **Direction** | **Single service layer** (`digiquant/service.py`) invoked by **both** FastAPI routes and MCP tool handlers — **refactor** to avoid two implementations. |

### 3.10 Performance & scale (VectorBT, remote workers)

| | |
|--|--|
| **Goal** | Fast sweeps; offload heavy Bayesian jobs. |
| **Today** | Each trial is full Nautilus backtest — fine for small grids; slow at scale. |
| **Gap** | VectorBT Pro path, job queue worker (`digiquant-worker`), artifact storage. |
| **Direction** | Per `digiquant/ARCHITECTURE.md` roadmap; **after** correct product semantics (profile, compare, export v1). |

### 3.11 Security & compliance

| | |
|--|--|
| **Goal** | No arbitrary code execution from chat; least privilege; audit trail. |
| **Today** | **`EXPORT_OUTPUT_DIR`** path confinement; optional **API key**; strategies are **repo-controlled**. |
| **Gap** | Uploaded data **PII/market data licensing**; **tenant isolation** on shared DigiQuant instance; **secrets** in export artifacts. |
| **Direction** | Tenant-scoped **`DATA_ROOT`**, per-tenant API keys, **no secrets in export JSON**, **SSE/job IDs** not enumerable across tenants without auth. |

---

## 4. Refactor candidates (reduce duplication, clarify boundaries)

1. **`service` module** — Extract `backtest_service`, `optimize_service`, `export_service`, `catalog_service` from `server.py`/`cli.py` entrypoints so **CLI, HTTP, and MCP** share one path.
2. **Strategy discovery API** — Expose `list_strategies()` + param JSON Schema (generate via Pydantic v2) for **tool definitions** and **DigiChat** docs.
3. **Align registry vs `_KNOWN_STRATEGIES`** — `backtest.py` uses `strategy_specs` keys; **`get_strategy`** uses `registry`. Ensure **every** registered strategy has specs (or explicit “no optimize” flag).
4. **Workflow state typing** — Replace raw `dict` for `backtest_result` with **serialized `BacktestResult`** validation on load (optional) to catch drift.
5. **Async symmetry** — Backtest has v1 jobs; optimize/pipeline do not — add when UX needs it.

---

## 5. Phased roadmap (suggested)

### Phase A — “Chat can run real parameterized quant” (4–8 engineering days, rough order)

1. Add **`strategy_params`** to **`BacktestRequest`** + async job body; thread through `_run_backtest_job`.
2. Extend **`WorkflowState`** + **`backtest_node`** to pass **`strategy_params`**, optional **`data_path`**, optional **`tearsheet_path`** (off by default for speed).
3. Add **DigiGraph tool or node** `optimize` calling **`POST /run_optimize`** with constraints from **`TradingProfile`** (new model).
4. Document **symbol ↔ file** convention for GOLD (e.g. `XAUUSD.csv`) in **`digiquant/ARCHITECTURE.md`** and DigiChat onboarding.

### Phase B — “Catalog + research bridge”

1. HTTP **`GET /strategies`** or MCP **`digiquant_list_strategies`** (+ optional JSON Schema per strategy).
2. **DigiSearch** collection tags aligned with **`StrategySpec`** tags.
3. **Profile builder subgraph** in DigiGraph before first backtest.

### Phase C — “Compare + persistence”

1. **Run record** schema + storage (prefer DigiChat Postgres or shared DB).
2. **DigiChat UI**: comparison table component for `BacktestResult[]`.
3. Optional **DigiQuant `GET /runs/{id}`** if multi-client.

### Phase D — “Export that is actually deployable”

1. **Nautilus bundle** export (zip/layout).
2. **Subset Pine** codegen from templates.
3. **Broker stub → paper** path with explicit human gate.

### Phase E — “Scale & ML”

VectorBT Pro sweeps, Qlib/FinRL, remote workers — per original `digiquant/ARCHITECTURE.md` research track.

---

## 6. Suggested MCP tool surface (for DigiGraph)

Names are illustrative; align with `digigraph` orchestration registry conventions.

| Tool | Args (summary) | Returns |
|------|----------------|---------|
| `digiquant_list_strategies` | optional `tag` filter | list of `{ name, description, params_schema, aliases }` |
| `digiquant_get_strategy_spec` | `strategy_name` | defaults, bounds, asset notes |
| `digiquant_run_backtest` | `strategy_name`, `symbols`, `data_path`/`data_dir`, `strategy_params`, optional `session_id` | `BacktestResult` |
| `digiquant_run_optimize` | same + `method`, `n_trials`, `constraints`, `param_grid?` | `OptimizeResult` |
| `digiquant_run_pipeline` | profile-minimal subset | `{ backtest, optimize, export }` |
| `digiquant_export` | `strategy_name`, `params`, `target` | `ExportResult` |
| `digiquant_compare_runs` | `run_ids[]` *(may live in DigiChat/BFF if store is there)* | comparison DTO |

**Implementation note:** Prefer **one** Pydantic request model per tool shared with HTTP `POST` bodies to prevent schema drift.

---

## 7. How operators integrate the stack (reference deployment)

1. **Compose / k8s**: DigiQuant **service** on **8001**; mount **volume** for `DIGIQUANT_DATA_DIR` (or per-tenant subdirs).  
2. **DigiGraph** env: **`DIGIQUANT_URL`**, **`DIGIQUANT_DATA_DIR`**, **`DIGI_API_KEY`** aligned with DigiQuant middleware.  
3. **DigiChat**: set **`digiquantUrl`** in ecosystem config; health badge green.  
4. **DigiSearch**: index papers/docs; DigiGraph **research** tool points here — **not** DigiQuant HTTP.  
5. **Observability**: propagate **`X-Request-ID`** from DigiChat (`X-Digichat-Session` / session id) through DigiGraph to DigiQuant for support correlating traces (`digibase` OTEL optional).

---

## 8. Document maintenance

- When a gap closes, **update this file** and **`digiquant/ARCHITECTURE.md`** Phase / interface sections.  
- When adding HTTP routes, update **`ARCHITECTURE.md`** compatibility matrix if breaking.  
- Keep **security** notes in sync with **`SECURITY.md`** (human gates, loopback-only defaults).

---

## 9. Appendix — Resolved / remaining mismatches

| Issue | Status |
|-------|--------|
| **Params on HTTP backtest / jobs** | **Resolved:** `BacktestRequest.strategy_params`, async job thread, `PipelineRequest.strategy_params`. |
| **Graph passes params** | **Resolved:** `WorkflowState.strategy_params`, `backtest_node` payload, research JSON extraction. |
| **Optimize after backtest** | **Resolved:** `optimize_node`, routing + `agents.enabled` / `DIGI_GRAPH_OPTIMIZE_AFTER_BACKTEST`. |
| **Strategy catalog HTTP/MCP** | **Resolved:** `GET /strategies`, `digiquant.mcp_server` tools calling `digiquant.service`. |
| **Export bundle** | **Partial:** `nautilus_bundle` zip for `ema_cross` only; expand strategies later. |
| **Pipeline vs full profiling** | **Open:** `run_pipeline` still does not thread full `TradingProfile` into every step (use workflow body fields). |
| **Research vs metrics** | **Open:** enforce wording templates in DigiGraph prompts so RAG never implies live performance. |

---

*End of gap document.*
