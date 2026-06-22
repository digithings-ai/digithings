# Olympus Architecture Audit — Step 1 (Backend Map)

> **SUPERSEDED (2026-06-20).** This audit reflects the **pre-#930** graph (7C/7CD/7D, `run_type`
> baseline/delta/monthly, chain-terminal materialize). **Do not use for current topology.**
>
> **Canonical references:**
> - [`digiquant/ARCHITECTURE.md`](../../digiquant/ARCHITECTURE.md) § Atlas + Hermes
> - [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../superpowers/specs/2026-06-20-olympus-daily-thesis-design.md) §13–§14
> - [`digiquant/src/digiquant/olympus/hermes/docs/ARCHITECTURE.md`](../../digiquant/src/digiquant/olympus/hermes/docs/ARCHITECTURE.md)
>
> **Current entry point:** `python -m digiquant.olympus.hermes.chain --cadence daily`
> (`.github/workflows/pipeline-olympus.yml`). Hermes terminal = **H9 `commit_run`**.

> **Scope (historical).** A read-only, end-to-end map of the Olympus backend as of 2026-06-16.

---

## 1. Entry points & run shapes

Cron entry point: **`python -m digiquant.olympus.hermes.chain --run-type {baseline|delta|monthly}`**
(`digiquant/src/digiquant/olympus/hermes/chain.py::cli_main`).

| Run type | Cron (`.github/workflows`) | Shape |
|----------|----------------------------|-------|
| `baseline` | `atlas-baseline.yml` — `Sat 12:00 UTC` | full research → Hermes → book |
| `delta` | `atlas-delta.yml` — `Mon–Fri 12:00 UTC` | same + a triage phase after preflight |
| `monthly` | `atlas-monthly.yml` — month-end `14:00` | preflight → monthly-synthesis only (no Hermes, no book) |

Data ingestion cron (separate): `digiquant-prices.yml` — intraday `*/15 13–20 Mon–Fri`
(fetch-quotes + compute-technicals), EOD `21:00` (sync-calendar + fetch-macro), and `14:35`
(`execute_at_open.py --prior-trading-day-rebalance`).

There is also a standalone Atlas CLI (`python -m digiquant.olympus.atlas.graph`) that runs
research-only and publishes — used by tests/dry-runs; production uses the chain.

---

## 2. The live pipeline (ordered node graph)

`run_atlas_then_hermes` composes **three** things: the Atlas graph, the Hermes graph, and a
set of *terminal chain phases* run **outside** either graph. `_usage.start()` wraps the whole
run; the `finally` block always writes the diagnostics row.

### Atlas graph — `build_atlas_graph` (research only)

| # | Phase (file) | LLM? | Calls / grounding | Produces |
|---|--------------|------|-------------------|----------|
| 1 | **preflight** (`phases/preflight.py`) | no | Supabase reads only | `config`, `prior_context` (+`decision_lessons`), `data_layer` (`market_context` = latest `price_technicals` per ticker + latest 2 `macro_series` obs; freshness probes; opt-in on-demand technicals recompute) |
| 2 | **preflight_reflect** (`preflight.py`) | LLM (only for *due* rows) | `decision-reflector` skill | resolves due `decision_log` rows → alpha-vs-SPY + lesson; closes the learning loop |
| 3 | **triage** *(delta only)* (`triage_phase.py`) | no/LLM **(verify)** | price-delta signal | `state.triage` carry/regen decisions per segment |
| 4 | **phase1_altdata** (`phase1_altdata.py`) | **5 parallel LLM** | sentiment-news *(web_search)*, cta-positioning *(web_search)*, options-derivatives *(data tools)*, politician-signals *(web_search)*, ai-portfolios *(x_search)* | 5 `SegmentReport` subclasses (sentiment, CTA, options/VIX, congressional, AI-portfolio tilt) |
| 5 | **phase2_institutional** (`phase2_institutional.py`) | **2 parallel LLM** | inst-flows *(web_search)*, hedge-fund-intel *(web_search)* | `InstitutionalFlowsReport`, `HedgeFundIntelReport` |
| 6 | **phase3_macro** (`phase3_macro.py`) | **1 LLM** | `macro` *(FRED data tools primary; web_search only if FRED layer stale)* | `MacroRegimeReport` (4-factor: growth/inflation/policy/risk_appetite + label) |
| 7 | **phase4_assetclass** (`phase4_assetclass.py`) | **5 parallel LLM** | bonds, commodities, forex, crypto *(data tools)*; international *(data tools + web_search)* | 5 asset-class `SegmentReport`s (consume macro + phase1) |
| 8 | **phase5_equity** (`phase5_equities.py`) | **1 LLM** | `equity` *(data tools)* | `EquityOverviewReport` (SPY/QQQ/IWM top-down) |
| 9 | **phase5_sectors** | **11 parallel LLM** | `sector-research` skill × 11 sectors *(data tools)*, from `config/sectors.yaml` | 11 `SectorReport`s (RS-vs-SPY, conviction, drivers) |
| 10 | **phase5_scorecard** | no | deterministic | `SectorScorecard` (per-sector stance OW/UW/N → aggregate bias) |
| 11 | **phase6_consolidate** (`phase6_consolidate.py`) | no | deterministic | `Phase6BiasRow` (the `daily_snapshots` bias row). **`fed_odds` hardcoded `None`** |
| 12 | **phase7_synthesis** (`phase7_synthesis.py`) | **1 LLM** | `digest` skill — **no tools, no web**; synthesizes from upstream bodies | `DigestSnapshot` (regime/alt/inst/asset/equity summaries, actionable items, risk radar, deterministic `segment_freshness`) |

### Hermes graph — `build_hermes_graph` (analysis → debate → PM → reflection)

Fan-out is over a **focus watchlist** (`select_focus_tickers`: holdings + top-scored
candidates, `candidates.py`) — narrower than the Atlas research scope. `ATLAS_MAX_ANALYSTS`
caps it.

| # | Phase (file) | LLM? | Per ticker | Produces |
|---|--------------|------|-----------|----------|
| 13 | **phase7c_specialists** (`hermes/phases/phase7c_analyst.py`) | **4×N LLM** | technical / sentiment / news / fundamental, each *(market-data tools, blinded to the book)* | `SpecialistPayload` ×4 (axis conviction 0–1 + stance) |
| 14 | **phase7c_join** | no | deterministic | `AnalystPayload` (conviction −5..+5, stance, thesis; **`risks` always empty — TODO**) |
| 15 | **phase7cd bull / bear** (`phase7cd_debate.py`) | **2N LLM/round** | bull then bear, *(market-data tools, blinded)* | `DebateRoundContribution` ×2 |
| 16 | **phase7cd research_manager** | **N LLM** | judge | `DebateSummary` (bull/bear thesis, `net_stance`, `conviction_delta` −2..+2) |
| 17 | **phase7d_risk_aggressive** (`phase7d_pm.py`) | **1 LLM** | portfolio-level *(market-data tools)* | `RiskCase` (growth case) |
| 18 | **phase7d_risk_conservative** | **1 LLM** | portfolio-level | `RiskDebateSummary` (aggressive + conservative + key_tension) |
| 19 | **phase7d_pm** | **1 LLM** | the decision *(FULL tools — may read positions/nav/theses)* | `RebalanceDecision` (recommended_portfolio, actions, notes). Empty = deliberate 100% cash |
| 20 | **phase9_evolution** (`phase9_evolution.py`) | **1 LLM** + DB write | — | `persist_pending` → `decision_log` rows; `Phase9Artifacts` (sources scorecard, quality post-mortem, improvement proposals) |

### Terminal chain phases — in `run_atlas_then_hermes`, **outside both graphs**

| # | Phase | LLM? | Produces / writes |
|---|-------|------|-------------------|
| 21 | **phase7e risk-sizing** (`hermes/phases/phase7e_risk_sizing.py`) | no | **overwrites** `recommended_portfolio` with `size_portfolio()` output + rebuilt actions + breaker note |
| 22 | **publish** (`atlas/phases/publish_phase.py`) | no | upserts `documents` (segments, macro, digest, `analyst/{t}`, `deliberation/{t}`, `pm-rebalance`, `risk-debate`) + `daily_snapshots`. Skips carried + degenerate |
| 23 | **materialize** (`hermes/portfolio_materialize.py`) | no | upserts `nav_history`, `positions` (+CASH row), `theses`, `thesis_vehicles` |
| — | **diagnostics** (`finally`) | no | `atlas_run_diagnostics` row (segment counts, token/cost from `digigraph.usage`, errors) |

**Per-baseline LLM call count** ≈ `26 + 7N` (N = focus-watchlist size) + due reflections. The
`7N` term (4 specialists + bull + bear + manager per ticker) is the dominant cost driver and
matches the prior cost forensics (input-token-bound, ~$8 baseline).

---

## 3. The research-agent call (what every LLM call actually is)

`digigraph/src/digigraph/graph/research_agent.py::run_research_agent` is the single LLM entry
for **every** segment/analyst/debate/PM/reflection node.

- **System prompt:** `ANALYST_SYSTEM` (material-only, evidence-bound, cite, quantify, grade
  `data_quality`, refuse-to-hallucinate).
- **User message = 4 ordered parts** (stable→volatile for prompt-cache hits): `SHARED_CONTEXT`
  (run-wide; `cache_control: ephemeral`) → `RESEARCH_SCOPE` (the SKILL.md body; cached) →
  `PHASE_INPUTS` (today's volatile inputs; **not** cached) → `OUTPUT_SCHEMA` (cached).
- **Structured output:** `response_format=json_schema` from the Pydantic model; providers that
  ignore it fall back to the prompt-embedded schema; Pydantic `field_validator`s are the third
  defense (e.g. bias-synonym normalization, `data_quality` soft-coerce).
- **Tool loop:** when `tools`+`execute_tool` are supplied, `run_tools` (≤5 rounds) lets the
  model call data tools before emitting final JSON (mutually exclusive with `response_format`).
- **Retry:** 1 validation retry (re-emit on validation error).
- **Layering:** `research_agent → digigraph.llm_client (completion_text / run_tools) → digillm`.
  Cost controls (OpenRouter allowlist + price ceiling + `sort`) and the `EmptyResponseError`
  self-heal live in **digillm**; usage telemetry is observed into `digigraph.usage`.

### The two web-grounding pre-passes (`_node_factory.build_grounding`)
- **`web_search`** (xAI Live Search) — curated-domain pre-pass for soft segments
  (`live_search=True`). For `macro` it's a **stale-only paid fallback** (`live_search_is_fallback`):
  skipped entirely when the ingested FRED layer is fresh (the Phase-D cost cut).
- **`x_search`** (`ai_portfolios=True`) — reads tracked AI-portfolio X accounts.
- Output of either is a cited summary injected as `phase_inputs["web_grounding"]`.

---

## 4. API & call-output catalog (what each produces, who benefits)

### LLM calls
| Call | Skill | Output | Consumed by |
|------|-------|--------|-------------|
| 12 Atlas research segments | per-segment SKILL.md | `SegmentReport` subclasses | phase6 bias row, phase7 digest, Hermes 7C axis inputs |
| master digest | `digest` | `DigestSnapshot` | published doc + `daily_snapshots`; dashboard "Morning Brief"; risk debaters' context |
| 4×N specialists | `{axis}-analyst` | `SpecialistPayload` | deterministic join |
| N debates (bull/bear/mgr) | `research-debate`,`research-manager` | `DebateSummary` | PM `debate_summaries`; sizer conviction delta; published `deliberation/{t}` |
| risk debate ×2 | `risk-aggressive`,`risk-conservative` | `RiskDebateSummary` | PM `risk_debate`; published `risk-debate` |
| PM | `pm-rebalance-decision`→`portfolio-manager`→`pm-allocation-memo` | `RebalanceDecision` | phase7e sizer (direction); materialize (book); published `pm-rebalance` |
| reflector | `decision-reflector` | `ReflectorOutput` | `decision_log.reflection`; feeds next run's PM `past_context` |
| evolution | `pipeline-evolution` | `Phase9Artifacts` | `state.phase9_evolution` (dashboard "improvement" surface) |

### Data tools (analyst-callable, `atlas/data/tools.py` → `queries.py`)
`query_data` (whitelisted tables), `get_macro_series`, `get_market_breadth`,
`get_sector_relative_strength`, `get_vix_term_structure`, `get_etf_flows_proxy` (volume proxy,
**not** true flows), `get_fed_rate_probabilities` (Kalshi ladder→25bp distribution + Polymarket
cross-check). Each returns JSON the model grounds claims on. **Analysts/debaters are scoped to
`MARKET_DATA_TABLES`** (blinded to the book); the **PM gets full scope**.

### External HTTP ingestion (crons, not in the graph)
FRED (`ingest_fred`), FX (`ingest_fx_frankfurter`), crypto FNG, treasury curve, Kalshi +
Polymarket (`fed_probabilities.py`), price quotes + technicals (`digiquant prices …`).
These populate the tables the tools read.

---

## 5. Persistence map (table → writer → reader → populated in prod?)

| Table | Written by | Read by | Populated? |
|-------|-----------|---------|-----------|
| `documents` | publish (in-chain) | frontend (19×), library | ✅ |
| `daily_snapshots` | publish (in-chain) | frontend (8×) | ✅ |
| `positions` | **materialize** (sole automated writer); operator/recovery scripts also upsert (`sync_positions_from_rebalance`, `update_tearsheet`, `refresh_performance_metrics.carry_forward_positions`) | frontend (3×) | ✅ |
| `nav_history` | materialize | frontend, breaker, backtest | ✅ |
| `theses` / `thesis_vehicles` | materialize | frontend (2×) | ✅ |
| `decision_log` | phase9 persist; resolved by preflight_reflect | frontend (1×), scorecard | ✅ (resolves in-graph) |
| `position_events` | **`execute_at_open.py`** (price cron 14:35) — sole recurring writer (not materialize) | frontend (3×) | ✅ |
| **`portfolio_metrics`** | `refresh_performance_metrics.py` | frontend (1×) | ⚠️ **EMPTY — no cron** |
| **`position_attribution`** | `refresh_attribution.py` | frontend (1×) | ⚠️ **EMPTY — no cron** (migration 040) |
| `atlas_run_diagnostics` | diagnostics.write_row (every run) | `atlas_run_health` view | ✅ writes; view = migration 041 (held human gate) |
| `atlas_run_health` (view) | migration 041 | frontend (1×) | ⚠️ only if 041 applied |
| `macro_series_observations` | `ingest_fred` + fed-prob fetchers | tools, frontend (1×) | ✅ (fed-prob rows only if `fedprob` source ingested) |
| `price_history` / `price_technicals` | `digiquant prices` cron | tools, frontend (4×) | ✅ |
| `trading_calendar` | `sync-calendar` | frontend (1×) | ✅ |
| `fx_economic_calendar` | — (Twelve-X port not built) | — | ⚠️ empty mirror (migration 031) |

---

## 6. Wiring-status summary

**Fully wired & working:** the entire Atlas research graph; the Hermes 4-axis analyst → bull/bear
debate → risk debate → PM chain; deterministic risk-sizing (phase7e) + drawdown breaker;
book materialization (nav/positions/theses); publish; diagnostics; the in-graph learning loop
(persist + resolve); OpenRouter cost controls + empty-response self-heal.

**Partial / not deployed:**
1. **`portfolio_metrics` + `position_attribution` have no scheduler.** `refresh_performance_metrics.py`
   and `refresh_attribution.py` are referenced by **zero** workflows → both dashboard surfaces are
   empty in prod. (Matches the held draft-cron PR #771.) **Highest-impact gap.**
2. **`OLYMPUS_POSITION_RISK_FIELDS` is OFF by default** → per-position stop/target/horizon/
   conviction/entry_price are not written (migration 039), so the Allocations risk fields are empty.
3. **`atlas_run_health` view (041) is a held human gate** → Run-Health tab has no source until applied.
4. **`fed_odds` is structurally unlit** — `phase6` hardcodes `None`; `get_fed_rate_probabilities`
   exists as an analyst *tool* but never reaches the deterministic digest/bias row (Fed PR2 deferred).
5. **Correlation is hard-stubbed** in phase7e (`corr=None`) → vol-targeting uses ρ=1.0
   (full-correlation) and systematically over-raises cash.
6. **~~Two positions writers~~ — RESOLVED (deep-dive):** in the automated pipeline **only `materialize`
   writes `positions`**. `execute_at_open.py` writes `position_events` (a different table) — no conflict.
   The other `positions` writers (`sync_positions_from_rebalance`, `update_tearsheet`,
   `refresh_performance_metrics`) are operator/recovery tools, not the scheduled pipeline.
7. **The `digest` skill was a dead pointer — RESOLVED (WS3).** `phase7_synthesis` was loading `skills/digest/SKILL.md`,
   whose body was *"This skill has been superseded… Immediately load and follow: `skills/orchestrator/SKILL.md`"*
   (a path that no longer exists). The digest skill body has been replaced with a real synthesis instruction.

**Orphaned-from-scheduling but NOT dead:** `atlas/attribution.py`, `atlas/backtest.py`,
`atlas/dashboard_digest.py` (0 src importers) are imported by `scripts/atlas/{refresh_attribution,
backtest_decisions,update_tearsheet}.py` — library code whose runners aren't cronned.

---

## 7. Dead-code / simplification candidates (need confirm before removal)

- **`AnalystPayload.risks` is always `""`** (`phase7c_analyst.py` join) — a declared-but-unfilled
  field; either wire it (from specialist risk text / bear case) or drop it.
- **`build_phase1` docstring says "4 parallel nodes"** but builds **5** (`_SPECS` has 5) — stale comment.
- **`PROTECTED-SCRIPTS.md` is stale** — references a `daily-price-update.yml` workflow that no longer
  exists and `scripts/*` paths that are now `scripts/atlas/*`. Misleads any future pruning.
- **60 scripts in `scripts/atlas/`** — many are one-shot backfills (`backfill_*`, `retrofit_*`,
  `legacy_delta_to_ops`, `convert_snapshot_v1`, `migrate_md_outputs_to_json`). Candidate for an
  `scripts/atlas/archive/` move once confirmed run-once. **(verify each before removal.)**
- **`pipeline_builder.py` is a one-line shim** over `digigraph.graph.pipeline_builder` (decoupling
  tracked in #579) — fine to keep, noted for the #579 cleanup.
- **`phase_monthly` import in `chain.py`** is a `# noqa: F401` "keep for doc linkage" — smells like a
  workaround; confirm it's load-bearing.

---

## 8. Recommended next steps (for discussion — not yet actioned)

1. **Schedule the refresh scripts** (resolve the #771 gate): cron `refresh_performance_metrics.py`
   + `refresh_attribution.py` daily after EOD prices → lights up the Performance & Attribution tabs.
2. **Flip `OLYMPUS_POSITION_RISK_FIELDS`** (after migration 039 is applied) → per-position risk fields.
3. **Apply migration 041** (owner sign-off) → Run-Health tab.
4. **Wire correlation** into phase7e (the stubbed `corr`) → correct vol-targeting.
5. **Reconcile the two positions writers** (materialize vs execute_at_open).
6. Then **Step 2: the dashboard frontend audit.**

---

## 9. Deep-dive addendum (verified by a 10-agent Sonnet pass, 2026-06-16)

A second multi-agent pass read the SKILL.md prompt bodies, state reducers, all migrations, and the
fetcher/reader shapes, seeded with the map above. It confirmed the structure and resolved the open
items. Net corrections + new findings:

### Verified / corrected
- **Triage is fully deterministic (no LLM).** A static rule table (`triage.py`, `@lru_cache`) with four
  evaluators: mandatory (macro/equity/crypto always regen), price-move (bonds/commodities/forex; regen if
  |move| > 0.5% or directional prior bias or non-supabase fallback), bias-or-price (11 sectors; regen if
  directional bias or a tracked name moved > 1.5%), bias-only (alt-data/inst/international). Conservative
  default = regen when evidence is thin. Signals: `price_history` deltas (look-back-guarded) + prior bias.
- **`positions` has one automated writer (`materialize`).** `execute_at_open.py` writes `position_events`,
  not `positions` — the earlier "two writers" concern is a non-issue for the scheduled pipeline.
- **State reducers (`atlas/state.py`; `HermesState` is an alias of `AtlasResearchState`):** `phase1/2/4/5_outputs`
  use a **collision-loud** merge (`SegmentSlotCollisionError` if two nodes write the same slug); `phase7c_specialists`
  merges by axis (inner collision = error); `phase7c_analysts` + `phase7cd_debates` are right-wins; **`errors`
  uses an append reducer** (parallel fan-out never drops a `PhaseError`). Good — the fan-out error-collection is correct.
- **`fed_odds` is doubly-unlit:** `phase6` sets `None`, and `phase7` only passes the bias row through as *input*
  (it can't populate an input field). The FEDPROB data IS ingested + served via the `get_fed_rate_probabilities`
  *tool*, so analysts can reach it — but the deterministic digest/bias row never carries it.
- **`portfolio_metrics` / `position_attribution`:** confirmed **no GitHub Actions cron**. They're not strictly
  always-empty — operator scripts (`run_db_first.py`, `update_tearsheet.py`, `ensure_position_activity_through_today.py`)
  populate them on manual runs — but the *scheduled* pipeline never fills them. Dashboard surfaces are empty
  unless an operator runs those by hand.
- **Monthly cron** = `14:00 UTC` on days 28–31 + a guard job gating to the last weekday (not 12:00).
- **`alt-options-derivatives` grounds on FRED data tools** (`get_macro_series` for VIXCLS/VXVCLS/VXNCLS/GVZCLS/OVXCLS),
  not web_search; the skill explicitly tells the LLM GEX / put-call / max-pain are unavailable (no free source).

### New high-value finding
- **The `digest` skill was a dead pointer** (see §6.7 — now resolved in WS3). Also, the `pm-rebalance-decision` skill is the live PM
  prompt; `portfolio-manager` and `pm-allocation-memo` are human-session fallbacks incompatible with automated use
  (bash commands, file writes) — they only "work" because the waterfall reaches them rarely.

### Confirmed dead code / deslop inventory (high confidence; verify before deleting)
**FROZEN scripts superseded by the `digiquant prices` CLI** (zero importers, no cron, explicit FROZEN headers):
`scripts/atlas/{compute-technicals,fetch-quotes,fetch-macro,ingest_fred,ingest_fx_frankfurter,ingest_crypto_fng,preload-history}.py`.
`ingest_treasury_curve.py` is the same pattern (no FROZEN header but absorbed by the eod-macro job).

**One-shot backfills already executed** (true orphans — 0 importers / 0 cron / 0 test):
`scripts/atlas/{backfill_simulated_runs,regen_research_deltas,retrofit_delta_requests,legacy_delta_to_ops,convert_snapshot_v1,migrate_md_outputs_to_json}.py`
→ candidate for an `scripts/atlas/archive/` move.

**Dead module paths in shared data:** `data/m2.py` (`M2DataFetcher`/`build_m2_composite` — not wired to any cron or
the pipeline); `data/prices/macro_ingest.py` Frankfurter + crypto-FNG fetchers (dropped as default sources since #328,
opt-in only). `migrations/007` defines a **`bb_middle` column that is never written** (`TECHNICAL_COLUMNS` omits it → always NULL).

**Dead skills (now deleted — WS4a):** These 21 graph-unused human-session wrapper skills have been removed:
Atlas: `asset-analyst, daily-delta, data-fetch, deep-dive, earnings, github-workflow, market-thesis-exploration,
mcp-data-fetch, orchestrator, premarket-pulse, profile-setup, research-daily, research-library, sector-heatmap,
sector-rotation, weekly-baseline`. Hermes: `deliberation, opportunity-screener, thesis, thesis-tracker, thesis-vehicle-map`.
Plus the `digest` skill body (dead pointer — addressed in WS3).

**Stale docs (mislead future pruning/onboarding):** `PROTECTED-SCRIPTS.md` cites a non-existent `daily-price-update.yml`
and old `scripts/*` paths; `migrations/026` SQL comment references the removed `apps/digiquant-atlas/` paths; `SCHEMA.md`
lists `position_events` PK as BIGSERIAL (actually `uuid`) and still ERDs the dropped `benchmark_history` table.

### Still-true gaps (unchanged by the deep-dive)
`OLYMPUS_POSITION_RISK_FIELDS` off by default; `atlas_run_health` view (041) held; correlation stubbed in phase7e;
`fed_odds` unlit; `portfolio_metrics`/`position_attribution` unscheduled. `AnalystPayload.risks` always `""` (no
specialist emits a risks field; the join hard-sets it empty; materialize reads it as an invalidation fallback but it's empty).
