# Atlas Full Migration — Wave 1 Decomposition

> **Historical note (2026-06):** Written for the pre-migration `apps/digiquant-atlas/` layout. Runtime Atlas code is `digiquant/src/digiquant/olympus/atlas/`; the UI is `frontend/olympus/`. Paths below are archival.

**Scope:** Complete the Atlas → DigiGraph migration (research + portfolio + deliberation), add LiteLLM batch-API optimization, add GitHub Actions scheduling, migrate price pipeline to DigiQuant, and deploy to production.

**Confirmed decisions:**
- Scheduling: GitHub Actions first. DigiClaw/OpenClaw deferred.
- Persistence: **new first-class tables** for thesis + deliberation (migration 024).
- Batching: LiteLLM Anthropic Batches pass-through. Provider-independent deferred.
- Scope: research + thesis validation + vehicle mapping + deliberation + PM memo + rebalance + deep-dive recess.

---

## System context (survey findings)

**Live tables (12, post-023):** `daily_snapshots`, `positions`, `theses`, `position_events`, `documents`, `nav_history`, `benchmark_history`, `portfolio_metrics`, `price_history`, `price_technicals`, `macro_series_observations`, `price_history_tickers`.

**`theses` table already exists** with `(date, thesis_id)` unique key. Wave 1 extends it with thesis_vehicles + deliberation session/round tables.

**Doc_types already registered (through migration 023):** `deliberation_transcript`, `deliberation_session_index`, `thesis_vehicle_map`, `market_thesis_exploration`, `pm_allocation_memo`, `asset_recommendation`. These stay as `documents` rows (full payloads) AND land in first-class tables (structured subset for queries/joins).

**Dual persistence rationale:** keep `documents` for rich blob retrieval + backward-compat with current frontend; add first-class tables for indexed queries (dashboards, historical thesis tracking, deliberation analytics).

**DigiGraph LLM client** (`digigraph/src/digigraph/llm.py`, 601 lines) already routes through LiteLLM with `cache_control: ephemeral`. No batch API yet.

**No Atlas-scheduled workflows exist.** CI workflows exist; cron workflows are org-maintenance only.

**Price pipeline (for #149):** 9 scripts under `apps/digiquant-atlas/scripts/` — `fetch-quotes.py`, `compute-technicals.py`, `preload-history.py`, `fetch-macro.py`, `ingest_fred.py`, `ingest_fx_frankfurter.py`, `ingest_crypto_fng.py`, `backfill_execution_prices.py`, `fill-entry-prices.py`. Existing `digiquant/src/digiquant/data/loader.py` is Polars-only CSV loader — minimal, safe landing spot.

---

## Wave 1 units (4 parallel worktree agents)

Every unit targets its own module branch. Each unit ends with a PR to its module branch; module branches PR to `develop` after Wave 1 lands.

---

### UNIT W1-B — Supabase schema audit + migration 024 (first-class thesis/deliberation tables)

**Branch:** `module/digiquant-atlas` → `task/w1b-schema-024`
**Module:** `apps/digiquant-atlas/`
**Complexity:** M
**Depends on:** nothing — fully parallel.

**Deliverables:**

1. **ADR-0010** (`docs/adr/0010-atlas-first-class-thesis-deliberation.md`) — records:
   - Why dual persistence (structured rows + JSON documents).
   - Which doc_types get first-class tables (listed below) and why.
   - Which doc_types stay documents-only (large narrative, infrequent query — e.g., `deep-dive`, `pipeline_review`).
   - Supersedes nothing; complements ADR-0009.

2. **Migration 024** (`apps/digiquant-atlas/supabase/migrations/024_thesis_deliberation_first_class.sql`):
   - **`thesis_vehicles`** — `(date, thesis_id, ticker)` PK; columns: `rationale TEXT`, `exclusion_reasons JSONB`, `candidate_rank INT`, `user_mandate_notes JSONB`, `source_exploration_key TEXT`, `created_at TIMESTAMPTZ DEFAULT now()`. FK on `(date, thesis_id)` → `theses`.
   - **`deliberation_sessions`** — `session_id UUID PK`; `date DATE NOT NULL`, `kind TEXT CHECK IN ('baseline','delta_scoped','monthly')`, `all_converged BOOLEAN`, `roster JSONB`, `started_at TIMESTAMPTZ`, `finished_at TIMESTAMPTZ`, `pipeline_run_id UUID`. Unique `(date, kind, pipeline_run_id)`.
   - **`deliberation_rounds`** — `id BIGSERIAL PK`; `session_id UUID FK → deliberation_sessions`, `ticker TEXT NOT NULL`, `round_number INT NOT NULL`, `label TEXT`, `sections JSONB NOT NULL` (analyst/PM section pairs), `converged BOOLEAN DEFAULT false`, `recess_triggered BOOLEAN DEFAULT false`, `deep_dive_document_key TEXT NULL`, `created_at TIMESTAMPTZ`. Unique `(session_id, ticker, round_number)`. Index on `(ticker, session_id)`.
   - **`analyst_coverage`** — `(date, ticker) PK`; `thesis_ids JSONB` (array of linked theses), `analyst_role TEXT`, `current_recommendation_key TEXT` (pointer into documents), `last_updated TIMESTAMPTZ`. Cross-reference for frontend "which analyst covers AAPL" query.
   - **`deep_dive_triggers`** — `id BIGSERIAL PK`; `session_id UUID FK`, `ticker TEXT`, `triggered_by TEXT CHECK IN ('pm_recess','delta_watch','manual')`, `trigger_reason TEXT`, `deep_dive_document_key TEXT`, `resolved_at TIMESTAMPTZ NULL`. Audit log for "deliberation forced a deep-dive."
   - **RLS** policies matching existing tables (service-role full, authenticated read).

3. **Schema docs update** — `apps/digiquant-atlas/supabase/SCHEMA.md` (create if missing) — ERD diagram + per-table purpose.

4. **Dead doc_type audit** — scan `apps/digiquant-atlas/src/digiquant_atlas/`, frontend, scripts for references; produce `docs/adr/0010-atlas-first-class-thesis-deliberation.md` appendix listing any orphaned doc_types. **Do not drop in this migration** — freeze for 1 sprint, drop in migration 025.

**Tests:**
- `apps/digiquant-atlas/tests/test_migration_024.py` — psycopg against a throwaway Postgres; asserts tables exist with correct columns, PKs, FKs, CHECK constraints, RLS policies.
- Schema round-trip: write a minimal row to each new table, read it back, validate.

**Out of scope:** writing Python adapters (that's unit W2-A). This unit is SQL + docs only.

**Acceptance:** migration applies cleanly on fresh Supabase and on a DB at state-023; rollback script present; ADR approved.

---

### UNIT W1-D — GitHub Actions scheduler workflows

**Branch:** `develop` → `task/w1d-atlas-schedulers`
**Module:** root (`.github/workflows/`)
**Complexity:** S
**Depends on:** nothing.

**Deliverables:**

1. **`.github/workflows/atlas-baseline.yml`**
   - `cron: '0 12 * * SAT'` (Saturday 12:00 UTC = pre-market Sunday Asia session).
   - Also `workflow_dispatch` for manual trigger with `run_date` input.
   - Job: checkout, setup Python 3.12, `pip install -e apps/digiquant-atlas`, run:
     ```bash
     python -m digiquant_atlas.graph --run-type baseline --run-date $(date -u +%Y-%m-%d)
     ```
   - Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `LITELLM_PROXY_API_KEY`, `OPENAI_API_KEY` (BYOK override).
   - Timeout: 120 min.
   - On failure: open/update a GitHub issue `atlas-baseline-failure-YYYY-MM-DD` with the tail of logs.

2. **`.github/workflows/atlas-delta.yml`**
   - `cron: '0 12 * * MON-FRI'` (weekdays 12:00 UTC).
   - Same job shape, `--run-type delta --baseline-date` auto-resolves to last baseline in Supabase (new CLI flag `--auto-baseline`).
   - Timeout: 45 min.

3. **`.github/workflows/atlas-monthly.yml`**
   - `cron: '0 14 28-31 * *'` + guard step that only runs on actual last-weekday-of-month.
   - `--run-type monthly`.

4. **`.github/workflows/test-atlas-graph.yml`** (CI-only, no schedule)
   - Path filter `apps/digiquant-atlas/**`; runs `pytest -m unit` + `ruff check` on push/PR.

5. **`apps/digiquant-atlas/scripts/entrypoint.py`** (or extend existing `graph.py __main__`):
   - Add `--auto-baseline` flag that queries Supabase `documents` for latest `research_baseline_manifest` and uses its date.
   - Add `--dry-run` flag (already implied in plan) that serializes run state to stdout without LLM calls.

**Tests:**
- `apps/digiquant-atlas/tests/test_cli.py` — argparse smoke tests for all new flags.
- Workflow-lint: `actionlint` step in CI.

**Secrets handling:** document in `apps/digiquant-atlas/docs/DEPLOYMENT.md` how to populate repo secrets. Do not commit `.env` example with real keys.

**Acceptance:** all three cron workflows pass `actionlint`; `workflow_dispatch` manual run with a test Supabase project completes end-to-end with dry-run.

---

### UNIT W1-E — Atlas price pipeline → DigiQuant (#149)

**Branch:** `module/digiquant` → `task/w1e-price-pipeline-migration`
**Module:** `digiquant/`
**Complexity:** M
**Depends on:** nothing.

**Deliverables:**

1. **New `digiquant/src/digiquant/data/prices/` package:**
   - `fetchers.py` — yfinance adapter (ported from `apps/digiquant-atlas/scripts/fetch-quotes.py`). Polars-only (no pandas).
   - `technicals.py` — 35+ indicator computation (ported from `compute-technicals.py`). Pure Polars.
   - `history_cache.py` — local OHLCV CSV cache under `data/price-history/` (ported from `preload-history.py`).
   - `macro_ingest.py` — FRED, Frankfurter FX, crypto FNG ingestors (ports `ingest_fred.py`, `ingest_fx_frankfurter.py`, `ingest_crypto_fng.py`).
   - `supabase_writer.py` — upserts to `price_history`, `price_technicals`, `macro_series_observations` (thin — reuse `digibase.audit.redact_mapping`).

2. **New CLI `digiquant.cli.prices`** — entrypoints:
   - `digiquant prices fetch-quotes --watchlist apps/digiquant-atlas/config/watchlist.md`
   - `digiquant prices compute-technicals --date YYYY-MM-DD`
   - `digiquant prices fetch-macro --sources fred,frankfurter,fng`
   - `digiquant prices preload-history --tickers TSLA,AAPL --years 2`

3. **`.github/workflows/pipeline-digiquant-prices.yml`**:
   - `cron: '*/15 13-20 * * MON-FRI'` (every 15 min during market hours UTC; 13:00–20:00 UTC ≈ 09:00–16:00 ET).
   - One consolidated job: fetch-quotes → compute-technicals → upsert.
   - Separate `cron: '0 21 * * MON-FRI'` for EOD macro ingest (FRED is day-delayed).

4. **Freeze legacy Atlas scripts** — add `# FROZEN — see digiquant.data.prices. Do not edit.` banner to the 9 migrated scripts; add `.claude/hooks` guard matching the pattern used by `publish_document.py`.

5. **Atlas reads stay unchanged** — `DataLayerSnapshot` already reads `price_technicals`, no integration change needed.

**Tests:**
- `digiquant/tests/dq/data/test_fetchers.py` — mocked yfinance, asserts Polars schema, unit handling, missing-day tolerance.
- `digiquant/tests/dq/data/test_technicals.py` — golden-fixture: feed known OHLCV, assert SMA/EMA/RSI/MACD values match reference.
- `digiquant/tests/dq/data/test_macro_ingest.py` — mocked FRED/Frankfurter/FNG responses.
- `digiquant/tests/dq/data/test_supabase_writer.py` — FakeSupabaseClient (port from Atlas test suite).

**Acceptance:** `digiquant prices fetch-quotes` against a real ticker produces a correct `price_history` row; full-run dry mode on a test watchlist completes; Atlas `phase3_macro.py` still passes its tests (no regression).

---

### UNIT W1-A-PLAN — Hermes deliberation sub-graph architecture spec (planning-only PR)

**Branch:** `module/digiquant-atlas` → `task/w1a-plan-hermes-subgraph`
**Module:** `apps/digiquant-atlas/`
**Complexity:** S (writing only — no code)
**Depends on:** nothing, but **informs Wave 2 implementation**.

This unit writes the detailed architectural spec that Wave 2 implementers execute. Separating planning from implementation (a) lets Wave 2 split into parallel subgraph-nodes-at-once, (b) gets architectural review before any code lands.

**Deliverables:**

1. **`apps/digiquant-atlas/docs/agentic/HERMES_SUBGRAPH.md`** — the living spec:

   **1.1 Topology (detailed):**
   ```
   phase6_consolidate (existing) ──► phase_h1_thesis_review
                                          │
                                          ▼
                                     phase_h2_market_thesis_exploration
                                          │
                                          ▼
                                     phase_h3_thesis_vehicle_map
                                          │
                                          ▼
                                     phase_h4_opportunity_screener
                                          │
                         ┌─ fan-out per ticker ─┐
                         ▼                      ▼
                   phase_h5_asset_analyst (×N)  (batched when W3-C lands)
                         │
                         └── fan-in ──┐
                                       ▼
                         ┌─ fan-out per ticker ─┐
                         ▼                      ▼
                   phase_h6_deliberation (×N) — round loop per ticker
                         │   (round loop internal to each ticker's node)
                         │   ├─ PM challenge
                         │   ├─ analyst defend
                         │   ├─ (optional) recess → deep_dive sub-graph
                         │   └─ converge check
                         └── fan-in ──┐
                                       ▼
                                phase_h7_pm_allocation_memo
                                       │
                                       ▼
                              phase7d_rebalance (existing)
   ```

   **1.2 Deep-dive recess semantics:**
   - When a deliberation round sets `recess_triggered=True` with `reason`, the node returns a `RecessRequest(ticker, reason, trigger_round_number)` marker.
   - A pipeline-level collector batches all recess requests across all tickers.
   - After fan-in barrier, a deferred `deep_dive_batch` phase dispatches them via Anthropic batch API (relies on W3-C; until then, synchronous parallel).
   - Results land back as `deep_dive_document_key`s; deliberation continues in a second round of the round loop.

   **1.3 State additions to `AtlasResearchState`:**
   - `phase_hermes.thesis_review: ThesisReviewOutput`
   - `phase_hermes.market_thesis_exploration: MarketThesisExploration`
   - `phase_hermes.thesis_vehicle_map: ThesisVehicleMap`
   - `phase_hermes.opportunity_screen: OpportunityScreen`
   - `phase_hermes.asset_recommendations: Annotated[dict[str, AssetRecommendation], _merge_analyst_dict]`
   - `phase_hermes.deliberation_sessions: Annotated[dict[str, DeliberationSession], _merge_session_dict]`
   - `phase_hermes.pm_allocation_memo: PMAllocationMemo`
   - `phase_hermes.recess_requests: list[RecessRequest]` (mutable list built during deliberation)

   **1.4 Pydantic output-model list** (one per H-phase) — for each: field list, validation rules against `apps/digiquant-atlas/templates/schemas/<name>.schema.json`.

   **1.5 Persistence mapping** — each H-phase's write adapter:
   - H3 (`thesis_vehicle_map`): `documents` row + `thesis_vehicles` rows (one per vehicle).
   - H6 (`deliberation`): `documents` per-ticker transcript + session index + `deliberation_sessions` row + N `deliberation_rounds` rows + optional `deep_dive_triggers` rows.
   - H7 (`pm_allocation_memo`): `documents` row only (narrative-heavy).

   **1.6 Round-loop design:**
   - Implemented as a **cyclic LangGraph sub-graph** inside the per-ticker deliberation node. Conditional edge on `converged`.
   - Safety cap: `MAX_ROUNDS = 6` (overrideable via env `ATLAS_DELIBERATION_MAX_ROUNDS`). Escalation on cap: mark `meta.escalated=true`, emit warning to Phase 9.
   - PM persona/analyst persona injected via two separate skill loads (`portfolio-manager/SKILL.md` + `asset-analyst/SKILL.md`) to keep them honest.

   **1.7 Delta-run behavior:**
   - Triage extended with Hermes-tier rules: thesis-review runs daily (thesis-drift is material). Deliberation scoped to tickers whose asset-recommendation changed OR who have a challenged thesis. PM memo runs only if any deliberation actually ran.

2. **`apps/digiquant-atlas/docs/agentic/WAVE2_UNIT_SPECS.md`** — prepared list of 8 Wave 2 worker units (each with file list, test targets, acceptance). Spawning Wave 2 is a copy-paste from this file.

3. **Update `apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md`** to reference HERMES_SUBGRAPH.md and add the new topology diagram.

**Tests:** none (spec PR).

**Acceptance:** Spec reviewed + approved; `WAVE2_UNIT_SPECS.md` yields 8 ready-to-spawn agent prompts.

---

## Wave 2 preview (gated on Wave 1 + approval)

8 parallel worker units derived from W1-A-PLAN:
- **W2-A**: Python adapters for migration 024 tables (`supabase_io.py` extensions + tests).
- **W2-B**: `phase_h1_thesis_review` + `thesis` CRUD.
- **W2-C**: `phase_h2_market_thesis_exploration`.
- **W2-D**: `phase_h3_thesis_vehicle_map` + `phase_h4_opportunity_screener`.
- **W2-E**: `phase_h5_asset_analyst` (fan-out + blinding rule; likely already exists in phase7c — reconcile).
- **W2-F**: `phase_h6_deliberation` (cyclic round loop + recess + deep_dive trigger).
- **W2-G**: `phase_h7_pm_allocation_memo` + integration with existing `phase7d`.
- **W2-H**: Delta-triage extensions for Hermes tier.

## Wave 3 preview (gated on Wave 2)

- **W3-C**: LiteLLM Anthropic Batches pass-through + `NodeSpec.batch=True` + pipeline_builder barrier batching. Rollout targets: phase1×4, phase2×2, phase4×5, phase5×11 sectors, phase7c×N tickers, Hermes asset-analyst×N, Hermes deliberation×N, deep-dive recess batch.
- **W3-F**: Atlas frontend wiring — `segment_freshness` badge, deliberation transcript view, thesis vehicles table, deep-dive trigger audit log.

## Cost/quality guardrails (applied uniformly)

- **Cache-control** on all shared-context blocks (system prompt, phase inputs that don't change within a run). Already implemented in `research_agent`.
- **Batch dispatch** for any fan-out ≥ 3 members (W3-C).
- **Triage carry-forward** on delta runs — verified `Carried` paths skip LLM entirely.
- **LLM routing by urgency** — `DIGI_LLM_MODE` per phase: `test` for triage/evolution, `medium` for analyst, `best` for PM + deliberation.
- **Max-rounds safety caps** on all cyclic loops.
- **Per-run cost telemetry** — Phase 9 consumes per-phase token counts + $USD estimates, surfaces cost trends in the post-mortem.

## Spawn plan

Wave 1 launches **4 parallel worktree agents** (W1-A-PLAN, W1-B, W1-D, W1-E). Each produces one PR into its module branch. After all four merge, one `module/* → develop` PR per module.

Estimated Wave 1 duration: 2–4 hours agent time; ~1 day wall clock including review/fix cycles.

Estimated Wave 2 duration: 6–10 hours agent time; ~2–3 days wall clock.

Estimated Wave 3 duration: 4–6 hours agent time.

**Total production path: ~1 week of parallel agent work to get Atlas + Hermes fully scheduled, batched, and deployed.**
