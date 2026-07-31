# RUNBOOK — digiquant-atlas (DB-first, JSON-first)

This is the **single authoritative** run instruction for digiquant-atlas.

## Schedules: GitHub Actions vs Co-work

| Layer | When | What runs | Supabase impact |
|--------|------|-----------|-----------------|
| **GitHub — Daily Price Update** | Weekdays **00:00 UTC** (~**8:00 PM Eastern** during EDT, ~**7:00 PM Eastern** during EST; after NYSE close; GitHub cron is UTC-only) | [`preload-history.py`](scripts/preload-history.py) (stale refresh) → [`compute-technicals.py`](scripts/compute-technicals.py) → macro ingest ([`ingest_fred.py`](scripts/ingest_fred.py), [`ingest_fx_frankfurter.py`](scripts/ingest_fx_frankfurter.py), [`ingest_crypto_fng.py`](scripts/ingest_crypto_fng.py), [`ingest_treasury_curve.py`](scripts/ingest_treasury_curve.py)) → [`refresh_performance_metrics.py`](scripts/refresh_performance_metrics.py) `--fill-calendar-through` **UTC today** | `price_history`, `price_technicals`, **`macro_series_observations`**, plus **`positions`** performance columns, **`nav_history`**, **`portfolio_metrics`** (script rows), **`position_events`** cumulative-return fields — **no** digest, no agent research |
| **Co-work / operator — research & portfolio** | Typically **pre-market** (e.g. 8:00 AM local) or per [`config/schedule.json`](config/schedule.json) | Agent validates + publishes JSON to Supabase (`materialize_snapshot.py`, `publish_document.py`, …) → operator runs [`run_db_first.py`](scripts/run_db_first.py) (optional disk checks → metrics → `execute_at_open.py` → [`validate_db_first.py`](scripts/validate_db_first.py)) | `daily_snapshots`, `documents`, `positions`, `theses`, `position_events`, etc. |

### Daily portfolio continuity (post-close)

The weekday GitHub job runs [`refresh_performance_metrics.py --fill-calendar-through`](scripts/refresh_performance_metrics.py) to **today (UTC)** so you get a **dense calendar** in Supabase even when no digest ran:

1. Refreshes performance columns on the **latest** existing `positions` date (same weights; closes from `price_history`).
2. For each **calendar day** after that through the target date: if `positions` has no rows for that date, **clones** the prior day (carry-forward), then updates per-position metrics, `nav_history`, and **`portfolio_metrics`** with `computed_from='refresh_script'`.
3. **Does not overwrite** `portfolio_metrics` rows written by `update_tearsheet.py` (`computed_from='tearsheet'`). Sharpe / vol / drawdown / alpha on script-written days are **carried forward** from the previous metrics row until the next tearsheet recompute.

**Manual backfill** (e.g. fill gaps after prices exist):  
`python3 scripts/refresh_performance_metrics.py --supabase --fill-calendar-through YYYY-MM-DD`

**Limitation:** `--fill-calendar-through` advances from the **latest** `positions` snapshot date forward only; it does not scan for **holes** on earlier dates. For a missing day *before* your latest snapshot, run once with `--date YYYY-MM-DD` (after `price_history` has that day).

**GitHub — manual “Daily Price Update”:** Uses the same steps as the weekday schedule — **`preload-history.py --supabase --supabase-sync`** (per ticker: gap-fill from latest `price_history` date through UTC today; tickers with no rows get a full-history pull, default **`--new-ticker-period max`**). No workflow inputs. For a one-off local run without Actions: `python3 scripts/preload-history.py --supabase --supabase-sync`.

**Macro + Treasury (automated):** After technicals, the workflow runs FRED (if **`FRED_API_KEY`**), Frankfurter, crypto Fear & Greed, and **Treasury yields** (`us_treasury` from Treasury XML when the feed returns data — often empty from CI; plus **`treasury_market`** from Yahoo ^IRX/^FVX/^TNX/^TYX for reliable 3M/5Y/10Y/30Y). Migrations: [`015`](supabase/migrations/015_macro_series_observations.sql); [`016`](supabase/migrations/016_sec_recent_filings.sql) / [`017`](supabase/migrations/017_drop_sec_recent_filings.sql) — **`sec_recent_filings`** is **dropped** by 017 (batch SEC ingest retired). Run **`supabase db push`** (or apply `017` in the SQL editor) so the table no longer exists. **One-time deep backfill:** manual workflow **backfill macro** (Treasury: Yahoo **`max`** for `treasury_market`; **`ingest_treasury_curve --backfill`** skips the Treasury.gov XML month crawl for speed — use **`--xml-months N`** locally if you need official XML rows). **Smoke tests:** `ingest_treasury_curve.py --dry-run`. Extra FRED series: [`config/macro_series.yaml`](config/macro_series.yaml); bad IDs log a warning and continue.

**SEC / EDGAR (ad hoc, not in Supabase):** The watchlist is **ETF-heavy**, so batch filings ingest was low-signal. **Research / daily delta / deep dives** should **optionally** check **major operating companies** (8-K, 10-Q, 10-K, material items) when relevant to a sector, segment, or thesis — use [sec.gov](https://www.sec.gov/edgar) or the Cursor **`sec-edgar`** MCP (set **`SEC_EDGAR_USER_AGENT`** in [`config/mcp.secrets.env`](config/mcp.secrets.env); see [`.cursor/mcp.json`](.cursor/mcp.json)). No GitHub secret required for the daily price job.

**Claude Cowork:** project briefing and scheduled task recipes live under [`cowork/`](cowork/) — see [`cowork/README.md`](cowork/README.md) and paste [`cowork/PROJECT-PROMPT.md`](cowork/PROJECT-PROMPT.md) into the Cowork project instructions. **First-time setup:** [`cowork/SETUP-ATLAS-COWORK.md`](cowork/SETUP-ATLAS-COWORK.md) (agent-driven wizard → `cowork/OPERATOR-COWORK.md` + `config/schedule.json` → `cowork_operator`).

**Olympus daily chain:** `python -m digiquant.olympus.hermes.chain --cadence daily` (`.github/workflows/pipeline-olympus.yml`). Sunday cron sets `refresh_scope=all` for operator full refresh; weekdays use edit-mode continuity (`skip`/`edit`/`full` per artifact). Beliefs distillation: `--refresh-scope beliefs` or automatic when `decision_log` backlog exceeds `OLYMPUS_BELIEFS_BACKLOG` (default 20).

## Two tracks (research vs portfolio)

- **Track A — Generic research** (positioning-blind): macro, sectors, crypto, sentiment, etc. **Do not** load `config/preferences.md` or `config/investment-profile.md`. Each research run **ends** with the **`digest`** — `documents.digest` + materialized `daily_snapshots` for the date — as the **single overview** of all sub-segments (`python -m digiquant.olympus.hermes.chain --cadence daily` through Atlas A0–A4). Run [`run_db_first.py --skip-execute --validate-mode research`](scripts/run_db_first.py) after publish.
- **Track B — Portfolio manager & analyst** (user-specific): **reads** the research **`digest`** from Supabase (does **not** compile it) + [`config/preferences.md`](config/preferences.md) + [`config/investment-profile.md`](config/investment-profile.md); Hermes H1–H9 produces thesis artifacts, deliberation, PM direction, sized book, and `commit_run` booking. Timing is controlled by [`config/schedule.json`](config/schedule.json) (`portfolio_manager_cadence`, `execution_assumption`, `rebalance_source_for_opens`). Run full validation: `--validate-mode full` or `pm`.

### Track B — fresh vs delta artifacts (thesis-first)

| Payload `doc_type` | Typical `document_key` | Fresh vs delta |
|--------------------|----------------------|----------------|
| `market_thesis_exploration` | `market-thesis-exploration/{{DATE}}.json` | Full publish per day; refinements may use `document_delta` targeting the same key |
| `thesis_vehicle_map` | `thesis-vehicle-map/{{DATE}}.json` | Same pattern as exploration |
| `asset_recommendation` | `asset-recommendations/{{DATE}}/{{TICKER}}.json` | Fresh when materially new; optional `document_delta` for incremental analyst revisions |
| `deliberation_transcript` | `deliberation-transcript/{{DATE}}/{{TICKER}}.json` | **Always fresh** per conference session |
| `deliberation_session_index` | `deliberation-transcript-index/{{DATE}}.json` | **Always fresh** per session |
| `pm_allocation_memo` | `pm-allocation-memo/{{DATE}}.json` | **Always fresh** after deliberation |
| `rebalance_decision` | canonical key per publish scripts | Fresh per publish |

Apply migration [`020_track_b_thesis_doc_types.sql`](supabase/migrations/020_track_b_thesis_doc_types.sql) so `documents.doc_type` accepts the new labels. Use `--doc-type-label` on `publish_document.py` with the **Title Case** label from that migration when inserting.

**Step validation:** After research close-out or each Track B publish batch, run [`scripts/validate_pipeline_step.py`](scripts/validate_pipeline_step.py) (`--step …` or `--chain research|track_b|full`, plus `--date`). See [`docs/ops/SCRIPTS.md`](docs/ops/SCRIPTS.md). Requires `jsonschema` for schema checks.

## Historical backfill (simulated replay)

To replay historical days as if the pipeline had run with correct date-bounded research:

```bash
# 1. Export current state (backup before any rewrites)
python3 scripts/backfill_export_state.py --start YYYY-MM-DD --end YYYY-MM-DD

# 2. Normalize schema violations in existing rows
python3 scripts/backfill_normalize_schemas.py --start YYYY-MM-DD --end YYYY-MM-DD

# 3. Get as-of date context + agent prompt for a specific date
python3 scripts/backfill_context.py --date YYYY-MM-DD --print-prompt

# 4. After publishing new snapshots, validate all dates
python3 scripts/backfill_simulated_runs.py --validate-all
```

**As-of date constraints:** all web research must use `before:DATE` query constraints; prices/macro come from Supabase filtered to `<= DATE` (see `backfill_context.py`). The `cowork/tasks/backfill-historical-day.md` recipe is the canonical task definition for each historical day.

**Pre-executed:** Apr 5–14, 2026 backfill completed 2026-04-14 (468 documents, all days OK).

## Market-open execution and price backfill

### Activity tab / `position_events` stops at an old date

**New ledger rows are not created by the weekday GitHub “Daily Price Update” job.** That workflow runs [`refresh_performance_metrics.py`](scripts/refresh_performance_metrics.py), which can update **`cumulative_return_since_event_pct`** on existing `position_events` but does **not** insert ledger rows. Rows come from [`execute_at_open.py`](scripts/execute_at_open.py), normally after a `rebalance_decision` publish via [`run_db_first.py`](scripts/run_db_first.py). That script records **HOLD** as well as OPEN/EXIT/**TRIM**/**ADD** so no-trade days still appear in the Activity ledger. The `position_events.event` vocabulary is **TRIM** / **ADD** (sizing changes), not a generic “REBALANCE”.

If the Activity table in the app ends on e.g. **April 6**, run execution for each **missing trading day** (after `rebalance_decision` + `price_history.open` exist for that story):

```bash
python3 scripts/execute_at_open.py --date YYYY-MM-DD
# If the decision was published the prior session:
python3 scripts/execute_at_open.py --date YYYY-MM-DD --prior-trading-day-rebalance
```

Or run the full post-publish chain: `python3 scripts/run_db_first.py` (omit `--skip-execute` so `execute_at_open` runs). Then, if opens were missing at insert time: `python3 scripts/backfill_execution_prices.py --date YYYY-MM-DD`.

Pre-market runs publish a **same-day** `rebalance_decision` before **that day’s** `price_history.open` exists. [`execute_at_open.py`](scripts/execute_at_open.py) may record `position_events` with **`price: null`**. After the session opens (or after prices sync), run:

```bash
python3 scripts/backfill_execution_prices.py --date YYYY-MM-DD
```

Optional **T−1 model:** execute **yesterday’s** rebalance at **today’s** open:

```bash
python3 scripts/execute_at_open.py --date YYYY-MM-DD --prior-trading-day-rebalance
```

**Bulk gap-fill** after an outage (runs `execute_at_open` per trading day from the day after `max(position_events.date)` through `--through`):

```bash
python3 scripts/backfill_position_events.py --through YYYY-MM-DD
```
Use `--from YYYY-MM-DD` when there is no prior ledger row or you need an explicit range. `--dry-run` prints the planned commands.

**Full repair through today** (carry `positions` forward for missing calendar days, then backfill ledger + reconcile HOLD):

```bash
python3 scripts/ensure_position_activity_through_today.py --through YYYY-MM-DD
```

Use `--no-refresh` if `positions` already has rows for every day in range. Audit max dates: `scripts/sql/audit_activity_coverage.sql`.

**Reconcile Activity with `positions`:** if the book snapshot has tickers with no ledger row (for example they were missing from `rebalance_table`), insert missing **HOLD** rows without overwriting existing events:

```bash
python3 scripts/reconcile_position_events_from_positions.py --from YYYY-MM-DD --through YYYY-MM-DD
```

**Reason text** on existing `position_events` rows: the script prefers per-ticker **`asset-rec/{TICKER}.json`** (verdict rationale / bull case) and **`deliberation-transcript/{DATE}/{TICKER}.json`** (`final_decisions`), then falls back to **`rebalance-decision.json`** (`rebalance_table`).

```bash
python3 scripts/backfill_position_event_reasons.py --dry-run
python3 scripts/backfill_position_event_reasons.py                      # fill null/empty only
python3 scripts/backfill_position_event_reasons.py --repair-placeholders
python3 scripts/backfill_position_event_reasons.py --enrich-existing   # replace short generic rebalance-only lines
```

Use `--force` only if you intend to overwrite non-empty `reason` values for every row. Use **`--no-enrich`** to skip asset-rec / deliberation and use the rebalance JSON only.

## Compiled daily view (no extra permanent storage)

Do **not** store a third “full compiled markdown” copy per weekday. The UI should **derive** the effective view by folding **Sunday baseline** + **delta ops** Mon→as-of (see [`docs/agentic/COMPILED-RESEARCH-VIEW.md`](docs/agentic/COMPILED-RESEARCH-VIEW.md)).

### Two “baseline” concepts (do not confuse)

1. **`snapshot.baseline_date` / `delta-request.baseline_date`** — the week’s **anchor** (typically the latest `run_type=baseline` snapshot on or before the run date, usually **Sunday**). Used for reporting, manifests, and “which week this delta belongs to.”
2. **`materialize_snapshot.py --baseline-date`** — which **`daily_snapshots` row** to **load as JSON** before applying weekday ops. On weekdays this must be the **previous calendar day’s** materialized snapshot when that row exists (day-over-day chain). If that day is missing (gap), use the **latest** `daily_snapshots.date` **strictly before** the target date. [`scripts/run_db_first.py`](scripts/run_db_first.py) prints both values on delta runs.

Per-document research deltas (`document_delta`, manifest) use the same **week anchor** in their envelope; digest ops still chain through `materialize_snapshot` as above.

## Canonical principles
- **Supabase is the source of truth** for daily snapshots, documents, positions, theses, NAV, and metrics.
- **JSON payloads are canonical**. Markdown is always **derived** for display. Agents should **`validate_artifact.py -`** and **`publish_document.py --payload -`** (stdin) so hosted and Cowork runs need **no** repo-local cache. Normal operation does **not** require `data/agent-cache/` — see [`data/README.md`](data/README.md). That tree exists only for **migration/backfill**, optional **fetch-script** temp files, or **recovery** (`update_tearsheet.py` scanning legacy markdown).
- **Daily operator run** publishes structured artifacts → validates DB state → optionally records position events as executed at **market open (Mon–Fri)** (see backfill above).
- **Disk migration:** if you have an external export of old daily folders, copy them into `data/agent-cache/daily/` (gitignored) before running backfill scripts — see below — this is **not** part of day-to-day tasks.
- **Retired `outputs/` path:** the repo must not depend on an `outputs/` directory (it is **gitignored** if recreated). Before deleting any local copy, confirm Supabase is canonical: `python3 scripts/verify_supabase_canonical.py` and optional `--date YYYY-MM-DD` for days you care about.

## Cost structure (#696)

Target: **< $1/day** in xAI usage *without reducing capability* — trim
redundancy and misallocated effort, never research breadth or freshness.
Agentic searches dominate cost (~$0.005 per server-side tool invocation — one
`web_search` pre-pass spawns dozens), tokens are second.

Capability-preserving reductions in place:

| Mechanism | Where | Effect |
|---|---|---|
| Per-phase shared-context filtering | `_node_factory._shared_context(context_keys=…)`, `SegmentNodeSpec.extra_context_keys` | Each node receives only the prior documents it consumes (own segment + declared extras) instead of the full latest-per-key dump (every segment + `analyst/*` + `pm-rebalance` + digests) — same information where it's used, large token cut where it isn't |
| **Per-phase `data_layer` allowlist (#935)** | `_node_factory._shared_context(data_layer_scope=…)`, `SegmentNodeSpec.data_layer_scope` | The whole `data_layer.market_context` (every ETF's 12 technicals + every macro series) was dumped into *every* node. Now scoped: cross-asset phases (macro / asset-class / sector / equity / synthesis) keep `full`; the **PM** gets `portfolio` (macro + regime signals, no per-ticker ETF dump — it reads the book + prices via the data tools); **analyst / debate** nodes get `ticker` (compact regime signals only — they fetch their own ticker's technicals via tools). Freshness probes are scalars and always kept. Same data where it's used; large cut where the node fetches its own |
| **Delta-aware snapshot history (#935)** | `_node_factory._shared_context(slim_snapshots=…)` (auto-on for `run_type=delta`) | On a **delta** run, the full `last_snapshots` history is collapsed inside shared_context to the latest snapshot's compact **bias row** (regime + per-asset bias) plus the **changed-segment** slugs from triage — a delta node still sees yesterday's stance without re-serializing the fat digest snapshot N times. **Baseline** runs keep the full history (the weekly baseline reviews the whole prior week). The phases that genuinely consume the history (triage / phase9 / monthly) read `state.prior_context.last_snapshots` into their own `phase_inputs`, so dropping the shared_context copy is lossless |
| Hermes focus list | `hermes/candidates.py` (`HERMES_FOCUS_TOP_N`, default 5) | 7C/7CD deliberate current holdings + top-scored opportunity candidates instead of the first `ATLAS_MAX_ANALYSTS` tickers of the watchlist file — same depth, applied where signal is; explicit `--watchlist` overrides |
| `snapshot_lookback` 5 → 2 | `atlas/supabase_io.py` | Prior digests are re-serialized into every node's shared context; baseline + latest delta preserves continuity without 3 redundant copies |

The shared-context block stays the **first (stable)** prompt content part with
unchanged keys, so the diet does **not** disturb the stable→volatile prompt-cache
ordering in `digigraph.graph.research_agent._format_scope_block` (#935).

Deliberately **not** used (they reduce capability): higher triage carry
thresholds, lower `max_search_results`, blanket fan-out caps. The remaining
search-cost work is structural — free-source ingestion replacing paid agentic
searches — not narrowing. That program is **Phase D**: see
[`PHASE-D.md`](PHASE-D.md) for the full architecture, PR sequence, and the
retained paid fallbacks. PR-1 converts `alt-options-derivatives` to read the
FRED vol complex (VIX/VIX3M/VXN/GVZ/OVX, in `config/macro_series.yaml`) via
`get_macro_series` instead of a paid `web_search` (#708).

`atlas_run_diagnostics.est_cost_usd` tracks each run; verify after changes.

### OpenRouter model tiers (`config/olympus_models.yaml`)

As of Jun 2026 the pipeline pins **open-weight** models per capability tier. The Jun 19
delta run (**$11.95** / 147 calls) used bare Auto Router + `openai/*` (GPT-5.5) — that path
is blocked: `cost_quality_tradeoff=10`, open-weight `allowed_models` only, no frontier pins.

| Env | Values | Effect |
|---|---|---|
| `OLYMPUS_MODEL_TIER` | `cheap` (default) / `balanced` / `quality` | Selects pinned models from `config/olympus_models.yaml` |
| `OPENROUTER_API_KEY` | GitHub secret | Required — all LLM calls + web grounding (`openrouter:web_search`) |

`apply_olympus_openrouter_env()` (Hermes chain startup) sets **`OPENROUTER_ALLOWED_MODELS`**
and **`OPENROUTER_COST_QUALITY_TRADEOFF`** from the active tier + `openrouter_defaults`.
No other OpenRouter env vars are required in CI (`olympus-pipeline.yml`).

#### OpenRouter routing knobs (digillm → `extra_body`)

| Knob | Where set | Semantics |
|---|---|---|
| **`cost_quality_tradeoff`** | `OPENROUTER_COST_QUALITY_TRADEOFF` (always **10**) | Auto Router plugin dial **0–10**: 0 = most capable, **10 = cheapest** |
| **`allowed_models`** | `OPENROUTER_ALLOWED_MODELS` | `plugins[{id:auto-router, allowed_models}]` — candidate pool for `openrouter/auto` only |
| **`provider.require_parameters`** | digillm default ON | Routes structured-output / tool calls to providers that honor `response_format` / `tools` |
| **`models` + `route=fallback`** | `OPENROUTER_FALLBACK_MODELS` (optional) | Price-sorted fallback chain — not set in Olympus CI |
| **`openrouter:web_search`** | `tools` on grounding pre-pass | Exa engine, `$0.005`/search; uses `grounding_model` from tier config |

Phases pass **pinned** `openrouter/<vendor>/<model>` strings (not `openrouter/auto`). Auto
Router knobs still apply to any auto/fallback path and keep operator overrides bounded.

**Web grounding** uses OpenRouter's `openrouter:web_search` server tool via `grounding_model`.
**Structured JSON** phases use pinned open-weight models with `strict:true` json_schema.

Per-phase override: `config/model_modes.yaml` → `phase_models` — **frontier models are
rejected** (`openai/*`, `anthropic/*`, GPT-5.x, Claude Opus/Sonnet, o-series); see
`digigraph.model_config.is_flagship_openrouter_model`.

**Pool changes are endpoint-verified in CI (#1622):** any PR touching
`config/olympus_models.yaml` / `config/model_modes.yaml` triggers
`validate-olympus-pools.yml`, which runs `scripts/validate_olympus_pools.py` against live
OpenRouter — per pooled slug: endpoint metadata (tools + structured_outputs supported,
context ≥ 64k), one real function-tool call, one strict `json_schema` call. Model-page
claims are not trusted (#987 mistral-small: page said tools, every endpoint 404'd). Run
manually anytime: `OPENROUTER_API_KEY=… python3 scripts/validate_olympus_pools.py`.


When the scheduled Atlas pipeline fails (`atlas baseline`, `atlas delta`, or `atlas monthly`), the workflow opens or appends to a deduped tracking issue titled `atlas-{baseline,delta,monthly}-failure` with `ci:failure` label. Each comment lists the failing step, the last successful run timestamp, the run URL, and the last 200 log lines.

**Owner:** Chris (sole on-call). New failure issues should be triaged within one business day.

**First-look checklist:**
1. Open the **Workflow run** URL from the issue body and scroll to the failing step (named in the issue).
2. Read the last 200 log lines in the issue body for the immediate error before clicking through to the full run log.
3. Classify the failure:
   - **Transient** (rate limit, provider 5xx, network blip, missing/expired secret): comment on the issue with the cause, then re-run via `gh workflow run "<workflow name>"` (or the workflow_dispatch button). Confirm the next run is green.
   - **Code regression** (assertion error, schema mismatch, new exception): file or update the linked task issue, fix on a `task/<N>-…` branch, and gate landing on a successful manual workflow_dispatch.
   - **Provider/model change** (e.g. Ollama Cloud capacity, Gemini quota): update [`config/litellm.yaml`](../../config/litellm.yaml) routing or the workflow `env:` block; document in commit message.
4. **Closing:** leave the issue open until the next scheduled run is green. The dedupe-by-title logic re-opens a new issue automatically on the next failure, so closing prematurely does not lose state — a transient that recurs surfaces a fresh issue.

### OpenRouter empty completions (degraded book, "empty completion from …" in logs)

Every phase uses **pinned open-weight models** from `config/olympus_models.yaml` (via
`get_model_for_phase`). Legacy `openrouter/openrouter/auto` paths are blocked from frontier
providers. Every research call is a **structured-output** (`response_format` json_schema) or
**tool** request. The pipeline degrades to an empty/zero-weight book when those calls come
back with empty bodies. Contract and levers, in order of cause:

1. **Account state first.** An empty body can be the Auto Router silently degrading on a key with no credit/over a limit. Check OpenRouter `GET /api/v1/credits` (balance) and `GET /api/v1/key` (daily/weekly/monthly spend + limits) with the `OPENROUTER_API_KEY` as a Bearer token. This is the cheapest first check.
2. **Strict structured outputs are sent correctly** (digigraph `research_agent`): `strict: true` + a strict-legal schema (`additionalProperties:false`, all-required, unsupported keywords stripped). A strict request carrying Pydantic's raw schema is rejected by the provider and surfaces as an empty body (not an error).
3. **`provider.require_parameters` is forced on** for any request carrying `response_format`/`tools` (digillm, independent of the `OPENROUTER_REQUIRE_PARAMETERS` toggle) so the Auto Router only routes to a provider that honors the param. Do **not** disable it for the pipeline.
4. **Capable-model fallback (operator lever).** The Auto Router is *best-effort* for structured outputs — OpenRouter's own docs do not recommend the bare auto router for json_schema. If empties persist after (1)–(3), pin a capable allowlist via **`OPENROUTER_FALLBACK_MODELS`** (comma-separated, cheap→capable) in the workflow `env:`; digillm routes among them with `route=fallback` and the empty-retry self-heal swaps off a flaky primary. Pick current slugs from the OpenRouter models page filtered by **`supported_parameters=structured_outputs`** (slugs churn — keep them in config, never hard-coded). Restoring this list also restores a cost ceiling if you re-add `OPENROUTER_MAX_*_PRICE`.

## Environment requirements
1. Python 3.11+ recommended.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Supabase credentials (service role required for publishing):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

4. **FRED API key** (free): [`FRED_API_KEY`](https://fred.stlouisfed.org/docs/api/api_key.html) — required for `ingest_fred.py` and for the GitHub **Daily Price Update** job to load FRED series. If unset in Actions, FRED is skipped with a warning; Frankfurter and Fear & Greed still run.

5. **Unified local secrets (optional):** [`config/mcp.secrets.env`](config/mcp.secrets.env) (gitignored; copy from [`config/mcp.secrets.env.example`](config/mcp.secrets.env.example)) can hold **`FRED_API_KEY`**, optional **`COINGECKO_API_KEY`** / **`ALPHA_VANTAGE_API_KEY`**, and **`SEC_EDGAR_USER_AGENT`** (for **`sec-edgar`** MCP / ad-hoc EDGAR lookups only). Ingest scripts load it automatically next to `supabase.env`. For **GitHub Actions**, add repository secret **`FRED_API_KEY`**. **Cursor MCP** uses **`${env:…}`** in [`.cursor/mcp.json`](.cursor/mcp.json) — see [`config/MCP-SETUP.md`](config/MCP-SETUP.md).

Recommended: keep `SUPABASE_*` in `config/supabase.env`; add API keys to `config/mcp.secrets.env` or export them before launching Cursor.

**Script index (grouped by role):** [`docs/ops/SCRIPTS.md`](docs/ops/SCRIPTS.md)

## One command entrypoint (the only supported start)
For both manual and scheduled runs:

```bash
python3 scripts/run_db_first.py
```

(`./scripts/new-day.sh` is a thin wrapper around the same command.)

Common flags:
- `--date YYYY-MM-DD`
- `--baseline` (force baseline mode)
- `--delta` (force delta mode)
- `--dry-run` (print what would happen; no writes)
- `--skip-execute` (skip `execute_at_open.py` — use after **Track A** research-only runs)
- `--skip-sync-positions` (skip [`sync_positions_from_rebalance.py`](scripts/sync_positions_from_rebalance.py); default is to run for `--validate-mode` `full` or `pm`)
- `--validate-mode {full,research,pm}` (passed to [`validate_db_first.py`](scripts/validate_db_first.py); default `full`)

**Default:** after optional JSON validation under `data/agent-cache/daily/<date>/` (only if you keep local mirrors during migration), the entrypoint runs [`sync_positions_from_rebalance.py`](scripts/sync_positions_from_rebalance.py) when mode is `full` or `pm`, then [`refresh_performance_metrics.py --supabase --fill-calendar-through <date>`](scripts/refresh_performance_metrics.py). Run [`update_tearsheet.py`](scripts/update_tearsheet.py) separately when recovering from disk-backed markdown or partial publishes.

## What gets produced (canonical artifacts)
### Daily baseline/delta (stored in Supabase)
- **Daily snapshot** (canonical): `templates/digest-snapshot-schema.json`
  - stored in `daily_snapshots.snapshot` and mirrored to `documents` as payload for `document_key='digest'`
- **Delta ops** on weekdays: `templates/delta-request-schema.json`
- **Per-document research pipeline** (optional Track B): `templates/schemas/research-baseline-manifest.schema.json`, `templates/schemas/document-delta.schema.json`, `templates/schemas/research-changelog.schema.json` — publish manifest on baseline; weekdays publish `document-deltas/…` then run [`scripts/fold_document_deltas.py`](scripts/fold_document_deltas.py) to materialize targets + `research-changelog/{{DATE}}.json`.

### Hermes deliberation layer (auto-published by the pipeline, #698)
The Hermes phases publish their per-run reasoning to `documents.payload` so the
dashboard can show *why* a decision was made — no operator step required:
- `analyst/{TICKER}` — Phase 7C 4-axis analyst synthesis (`category=deep-dive`).
- `deliberation/{TICKER}` — Phase 7C-D bull/bear `DebateSummary` (rounds + theses
  + net_stance + conviction_delta; `category=deep-dive`, `segment=deliberation`).
- `risk-debate` — Phase 7D aggressive-vs-conservative `RiskDebateSummary`
  (`category=portfolio`, `segment=deliberation`).
- `pm-rebalance` — Phase 7D `RebalanceDecision` (`category=portfolio`).

These render natively in the Research Library via `render-pipeline-payloads.ts`.

### Paper portfolio (auto-materialized by Phase 9D, #700)
The pipeline owns the paper book — no operator step. After publish, Phase 9D
(`hermes/portfolio_materialize.py`) turns the PM's `phase7d_rebalance` into:
- **`positions`** — one row per `recommended_portfolio` target weight for the
  run date (+ a `CASH` residual row), upserted on `(date, ticker)`.
- **`nav_history`** — a base-100 normalized index, upserted on `date`:
  `nav(D) = nav(prev) × (1 + Σ wᵢ(prev)·deltaᵢ)`, where `deltaᵢ` is the freshest
  completed single-trading-day return from `query_price_deltas` (CASH = 0). The
  first run seeds `nav = 100`. Because runs fire intraday (before today's close
  lands), the index advances on the most recent available close pair — a
  one-trading-day phase lag, standard for an EOD-priced paper index.

Monthly runs skip it; paper only — no broker, no real money, no FX (normalized
index). Disabled by leaving `ChainDeps.materialize` unset (dry-run / legacy).

### Portfolio layer (operator-produced, stored in Supabase documents.payload)
- `asset_recommendation` (`templates/schemas/asset-recommendation.schema.json`)
- `deliberation_transcript` (`templates/schemas/deliberation-transcript.schema.json`)
- `rebalance_decision` (`templates/schemas/rebalance-decision.schema.json`)

### Weekly/monthly rollups (published to `documents`)
- Weekly: `doc_type: weekly_digest` — schema `templates/schemas/weekly-digest.schema.json`; publish with `publish_document.py` (stdin or temp file), stable `document_key` e.g. `weekly/2026-W15.json`.
- Monthly: `doc_type: monthly_digest` — `templates/schemas/monthly-digest.schema.json`; `document_key` e.g. `monthly/2026-04.json`.

### Deep dives (JSON → Supabase)
- Payload `doc_type: deep_dive` (`templates/schemas/deep-dive.schema.json`). Validate + `publish_document.py --payload -` with an appropriate `document_key` under `deep-dives/…`.
- Optional scaffold: `./scripts/scaffold_deep_dive.sh YYYY-MM-DD "Title Slug"` (local scratch only; still publish to DB).

### Evolution post-mortem (JSON → Supabase)
- `evolution_sources`, `evolution_quality_log`, `evolution_proposals` — schemas under `templates/schemas/evolution-*.schema.json`.
- Optional scaffold: `./scripts/scaffold_evolution_day.sh [YYYY-MM-DD]` then publish each JSON with `publish_document.py`.
- **Pipeline review (per-track post-mortem):** `doc_type: pipeline_review` — [`templates/schemas/pipeline-review.schema.json`](templates/schemas/pipeline-review.schema.json). Canonical keys:
  - `pipeline-review/research/{YYYY-MM-DD}.json` (Track A close-out)
  - `pipeline-review/portfolio/{YYYY-MM-DD}.json` (Track B close-out)
  - Validate with `scripts/validate_artifact.py`, publish with `publish_document.py` (`documents.doc_type` = **Pipeline Review**).
- Sync findings to GitHub Issues: [`scripts/pipeline_review_to_github.py`](scripts/pipeline_review_to_github.py) (after publish).
- **Full roadmap:** [`docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md`](docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md).

## What `run_db_first.py` does (post-publish)
After artifacts are already in Supabase, `run_db_first.py`:
1. Prints run-type guidance (baseline Sunday vs weekday delta).
2. Optionally validates any JSON files present under `data/agent-cache/daily/<date>/` via `scripts/validate_artifact.py` (skip if you have no local mirror — DB-only runs rely on Supabase only).
3. If `--validate-mode` is `full` or `pm` (and not `--skip-sync-positions`): runs `scripts/sync_positions_from_rebalance.py --date <date>` so **`positions`** matches **`rebalance_decision.body.proposed_portfolio`** when that document exists (no-op otherwise).
4. Runs `scripts/refresh_performance_metrics.py --supabase --fill-calendar-through <date>`.
5. Runs `scripts/execute_at_open.py` unless `--skip-execute`.
6. Runs `scripts/validate_db_first.py --date <date> --mode <full|research|pm>` and exits non-zero if checks fail (`run_db_first.py` exposes this as `--validate-mode`).

**Publishing** (agent / operator, before this script): `materialize_snapshot.py`, `publish_document.py`, and related validators — see [`docs/ops/SCRIPTS.md`](docs/ops/SCRIPTS.md).

## Backfill disk → Supabase (migration / recovery only)

If you have a **local** tree under `data/agent-cache/daily/` (gitignored), you can replay into Supabase:

1. **Markdown-era exports:** populate `data/agent-cache/daily/` (manually or by setting **`LEGACY_ROOT`** to a directory that contains `YYYY-MM-DD/` folders when you run the copy step), then materialize and refresh documents/metrics:
   - [`scripts/backfill-historical-daily-to-supabase.sh`](scripts/backfill-historical-daily-to-supabase.sh) — copies from **`LEGACY_ROOT`** unless **`SKIP_COPY=1`**, then runs [`scripts/backfill-db-first-digest.sh`](scripts/backfill-db-first-digest.sh), then `update_tearsheet.py`.
   - Override **`BASELINE_DATE`**, **`LAST_DATE`**, or use **`SKIP_COPY=1`** if `data/agent-cache/daily/` is already populated.
2. **Requires** `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (e.g. `config/supabase.env`).
3. Afterward: `python3 scripts/validate_db_first.py --mode full`.

**Note:** `delta-request.json` is applied to the **previous calendar day’s** row in `daily_snapshots` (`--baseline-date`); ops must match that chain. Stub `snapshot.json` files are ignored when a rich `delta-request.json` exists (see backfill script).

**Retrofit markdown deltas:** Copy `DIGEST-DELTA.md` into `data/agent-cache/daily/<date>/`, then generate colocated `delta-request.json` with:

`python3 scripts/retrofit_delta_requests.py`

Re-run with `--force` to overwrite. Uses [`scripts/legacy_delta_to_ops.py`](scripts/legacy_delta_to_ops.py) (regex + narrative/sector pointer fixes). To copy from an external daily export into `data/agent-cache/daily/` first, set **`LEGACY_ROOT`** when running [`scripts/backfill-historical-daily-to-supabase.sh`](scripts/backfill-historical-daily-to-supabase.sh).

## DB validation modes ([`validate_db_first.py`](scripts/validate_db_first.py))

- **`full` (default):** `daily_snapshots` + `documents.digest` + positions sanity + `nav_history` / `portfolio_metrics` non-empty.
- **`research`:** `daily_snapshots` + **`digest` or `research_delta`** (or **`document_delta` / `research_changelog` / `research_baseline_manifest`**) document with payload; positions zero-weight rule skipped; nav/metrics tables still non-empty.
- **`pm`:** `full` plus a `rebalance_decision` document for `date` (portfolio layer present).

**No-change days:** Prefer a **delta request** with empty `ops` (see [`templates/delta-request-schema.json`](templates/delta-request-schema.json)) and materialize as usual, **or** set `"no_change": true` on the digest snapshot (see [`templates/digest-snapshot-schema.json`](templates/digest-snapshot-schema.json)) after materialization so the day is still indexed in `daily_snapshots`.

