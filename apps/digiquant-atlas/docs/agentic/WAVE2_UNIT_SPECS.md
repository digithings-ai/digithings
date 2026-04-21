# Wave 2 Unit Specs — Hermes implementation

> **Parent spec:** [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md).
> **Parent plan:** [`docs/plans/atlas-full-migration-wave1.md`](../../../../docs/plans/atlas-full-migration-wave1.md) §"Wave 2 preview".
> **Prereqs:** Wave 1 units W1-A-PLAN (this spec), W1-B (migration 024). W1-D and W1-E are independent.
> **Branch convention:** each unit branches `module/digiquant-atlas` → `task/w2X-<slug>`; PR back into `module/digiquant-atlas`.

Each unit below is ready to copy-paste into an agent prompt (set the branch, read the two parent docs, execute).

---

## Parallelism map

```
W2-A (adapters) ──► W2-B, W2-C, W2-D, W2-E, W2-F, W2-G, W2-H
W2-E (h5) ─────────► W2-F (h6 reads AssetRecommendation)
W2-F (h6) ─────────► W2-G (h7 reads DeliberationSession)
W2-B, W2-C, W2-D — parallel (read h1/h2/h3 only)
W2-H — parallel after W2-A
```

- **Strictly sequential:** W2-A → (everything else). W2-E → W2-F → W2-G.
- **Fully parallel after W2-A:** W2-B, W2-C, W2-D, W2-H.

---

## W2-A — Supabase adapters for migration 024

**Branch:** `task/w2a-adapters-024`
**Complexity:** M — blocking, run first.

**Files (create/modify):**

- Modify: `apps/digiquant-atlas/src/digiquant_atlas/supabase_io.py` — add writer functions:
  - `write_thesis_vehicles(rows: list[ThesisVehicleRow]) -> list[PublishedArtifact]`
  - `write_deliberation_session(row: DeliberationSessionRow) -> PublishedArtifact`
  - `write_deliberation_rounds(rows: list[DeliberationRoundRow]) -> list[PublishedArtifact]`
  - `upsert_analyst_coverage(rows: list[AnalystCoverageRow]) -> list[PublishedArtifact]`
  - `write_deep_dive_triggers(rows: list[DeepDiveTriggerRow]) -> list[PublishedArtifact]`
  - `upsert_theses(rows: list[ThesisRow]) -> list[PublishedArtifact]` (may already exist; extend with `evidence_log` append semantics).
- Create: `apps/digiquant-atlas/src/digiquant_atlas/supabase_rows.py` — typed dataclasses/Pydantic for the five row types above.
- Modify: tests FakeSupabaseClient in `apps/digiquant-atlas/tests/conftest.py` — record writes per-table for assertion.

**Tests:**

- `tests/test_supabase_io_024.py` — one happy-path test per writer (insert, assert FakeSupabase recorded the row).
- `tests/test_supabase_io_idempotency.py` — re-running with the same `(session_id, ticker, round_number)` updates in place (deliberation_rounds unique constraint).

**Acceptance:** all writers callable against FakeSupabase; rows land under the expected table name; `PublishedArtifact` records returned with table + row_id + key.

**Depends on:** W1-B (migration 024 applied in dev DB).

---

## W2-B — phase_h1_thesis_review + theses CRUD

**Branch:** `task/w2b-phase-h1-thesis-review`
**Complexity:** M.

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h1_thesis_review.py` — single-node phase; loads `thesis` + `thesis-tracker` skills; outputs `ThesisReviewOutput`.
- Create: `apps/digiquant-atlas/templates/schemas/thesis-review.schema.json` — envelope `{schema_version, doc_type="thesis_review", date, meta, body}`; body per [HERMES_SUBGRAPH §4.1](HERMES_SUBGRAPH.md#41-thesisreviewoutput-phase_h1).
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/state.py` — add `PhaseHermesState` scaffold + `RecessRequest` + new reducers `_merge_session_dict`, `_append_list`. Add `phase_hermes: PhaseHermesState` field to `AtlasResearchState`.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — wire `phase_h1_thesis_review` after `phase6_consolidate`.

**Tests:**

- `tests/phases/test_phase_h1_thesis_review.py` — skill-load + node-run with a stub `run_research_agent` returning a `ThesisReviewOutput`; asserts `state.phase_hermes.thesis_review` is set and `upsert_theses` writer is called.
- State round-trip test for `PhaseHermesState`.

**Acceptance:** phase runs standalone; `theses` table upsert invoked with correct status transitions; schema validates a golden fixture.

**Depends on:** W2-A.

---

## W2-C — phase_h2_market_thesis_exploration

**Branch:** `task/w2c-phase-h2-market-thesis`
**Complexity:** S.

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h2_market_thesis_exploration.py`.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — wire after h1.
- Pydantic model `MarketThesisExploration` in the phase module, validated against existing [`market-thesis-exploration.schema.json`](../../templates/schemas/market-thesis-exploration.schema.json).

**Tests:**

- `tests/phases/test_phase_h2_market_thesis.py` — stub `run_research_agent`; assert new thesis rows are inserted into `theses` via W2-A.

**Acceptance:** new `ThesisProposal`s create `theses` rows with `status='ACTIVE'`; `thesis_id` uniqueness enforced within the run.

**Depends on:** W2-A. Parallel with W2-B and W2-D.

---

## W2-D — phase_h3_thesis_vehicle_map + phase_h4_opportunity_screener

**Branch:** `task/w2d-phase-h3-h4-vehicle-screener`
**Complexity:** M — two phases but tightly coupled (h4 reads h3).

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h3_thesis_vehicle_map.py`.
- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h4_opportunity_screener.py`.
- Create: `apps/digiquant-atlas/templates/schemas/opportunity-screen.schema.json`.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — wire h3→h4.

**Tests:**

- `tests/phases/test_phase_h3_vehicle_map.py` — asserts `thesis_vehicles` writer called with `candidate_rank` derived from list position.
- `tests/phases/test_phase_h4_opportunity_screener.py` — asserts `analyst_coverage` upsert called for each `RosterPick`.
- Cross-phase: `roster` members must all have a `thesis_vehicles` row covering them.

**Acceptance:** h3 produces mappings; h4 produces non-empty roster when any thesis is ACTIVE/CHALLENGED.

**Depends on:** W2-A. Parallel with W2-B, W2-C.

---

## W2-E — phase_h5_asset_analyst (replaces phase7c)

**Branch:** `task/w2e-phase-h5-asset-analyst`
**Complexity:** M — includes deletion of old phase7c.

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h5_asset_analyst.py` — per-ticker fan-out over `state.phase_hermes.opportunity_screen.roster`; Pydantic `AssetRecommendation` validated against [`asset-recommendation.schema.json`](../../templates/schemas/asset-recommendation.schema.json).
- **Delete:** `apps/digiquant-atlas/src/digiquant_atlas/phases/phase7c_analyst.py`.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/state.py` — remove `phase7c_analysts` field and `AnalystPayload`; remove `_merge_analyst_dict` if no other caller (keep if h5 + h6 reuse it — rename to `_merge_ticker_dict` for clarity).
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — swap `build_phase7c` call for `build_phase_h5`.
- Modify: any tests referencing `phase7c_analysts` or `AnalystPayload`.

**Tests:**

- `tests/phases/test_phase_h5_asset_analyst.py` — parallel fan-out produces one `AssetRecommendation` per roster ticker; blinded-rule assertion (no `current_weights` key leaks into `phase_inputs`).
- `tests/test_migration_phase7c_removed.py` — imports fail fast (regression guard).

**Acceptance:** no references to `phase7c_analysts` remain in repo; `state.phase_hermes.asset_recommendations` populated; `analyst_coverage` gets `current_recommendation_key` update.

**Depends on:** W2-A. **Blocks:** W2-F.

---

## W2-F — phase_h6_deliberation (cyclic round loop)

**Branch:** `task/w2f-phase-h6-deliberation`
**Complexity:** L — the centerpiece.

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h6_deliberation.py` — per-ticker fan-out; each ticker node is a nested `StateGraph` (analyst_present → pm_challenge → converge_check → loop/exit) compiled once at phase-build time.
- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/_deliberation_loop.py` — nested graph builder; isolated for unit-testing the loop independently.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — wire h6 after h5.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/state.py` — confirm `RecessRequest` + `_append_list` from W2-B are used.
- Persistence: writes `documents` (`deliberation_transcript` per ticker + one `deliberation_session_index`) + `deliberation_sessions` (run-level) + `deliberation_rounds` (per round per ticker) + `deep_dive_triggers` (per `RecessRequest`). Adapters from W2-A.
- Env var reader: `ATLAS_DELIBERATION_MAX_ROUNDS` with default 6.

**Tests:**

- `tests/phases/test_phase_h6_round_loop.py` — stubbed LLM returns `converged=True` at round 1; assert single round recorded.
- `tests/phases/test_phase_h6_escalation.py` — stub returns `converged=False` every round; assert cap hit at 6, `meta.escalated=True`, warning in `state.errors`.
- `tests/phases/test_phase_h6_recess.py` — stub emits `recess_triggered=True` at round 2; assert `RecessRequest` appended to `state.phase_hermes.recess_requests`, `deep_dive_triggers` row written.
- `tests/phases/test_phase_h6_fanout.py` — 3 tickers run in parallel, results merged under correct ticker keys.

**Acceptance:** converged, escalated, and recess paths all write consistent `deliberation_sessions`/`deliberation_rounds`; `deep_dive_triggers` audit log populated.

**Depends on:** W2-A, W2-E. **Blocks:** W2-G.

---

## W2-G — phase_h7_pm_allocation_memo + phase7d integration

**Branch:** `task/w2g-phase-h7-pm-memo`
**Complexity:** M.

**Files:**

- Create: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase_h7_pm_allocation_memo.py` — single node; loads `pm-allocation-memo` skill; Pydantic `PMAllocationMemo` validated against [`pm-allocation-memo.schema.json`](../../templates/schemas/pm-allocation-memo.schema.json). Conditional router: skip when no deliberation session ran this run (see HERMES_SUBGRAPH §6).
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/phases/phase7d_pm.py` — replace LLM call with deterministic transform that reads `state.phase_hermes.pm_allocation_memo` and current weights, emits `RebalanceDecision`. Remove skill loading.
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/graph.py` — wire h7 after h6 (or after `deep_dive_batch` when present); phase7d consumes h7.

**Tests:**

- `tests/phases/test_phase_h7_pm_memo.py` — asserts memo references at least one `deliberation_document_key`; sum of `target_weight_pct` within tolerance.
- `tests/phases/test_phase7d_transform.py` — given fixture `PMAllocationMemo` + current weights, asserts `RebalanceDecision.actions` list is correctly diffed (hold/add/trim/exit/new).
- `tests/test_phase7d_no_llm.py` — regression guard: `run_research_agent` not called during phase7d.

**Acceptance:** phase7d produces the same `RebalanceDecision` shape as before, no schema break for downstream consumers; phase_h7 gated off when no deliberation ran.

**Depends on:** W2-A, W2-F.

---

## W2-H — delta-triage extensions for Hermes tier

**Branch:** `task/w2h-triage-hermes`
**Complexity:** S.

**Files:**

- Modify: `apps/digiquant-atlas/src/digiquant_atlas/triage.py` — add rule kinds `hermes_thesis_drift`, `hermes_ticker_filter`, `hermes_memo_gate`. Extend gate signature to support ticker-keyed Carried markers; document the split (per-segment vs per-ticker).
- Modify: `apps/digiquant-atlas/src/digiquant_atlas/phases/_node_factory.py` — accept per-ticker triage gate for h5/h6 builders.
- Add Hermes phases to the canonical rule table in `_default_rules()` per HERMES_SUBGRAPH §6.

**Tests:**

- `tests/test_triage_hermes.py` — delta run where h1 produces no status transitions → h2/h3 carry; h1 with a CHALLENGED transition → h2/h3 regenerate.
- `tests/test_triage_ticker_filter.py` — per-ticker gate carries tickers without bias flip and regenerates those with.
- `tests/test_triage_memo_gate.py` — h7 carries the prior memo when no h6 session ran.

**Acceptance:** on a delta day with quiet theses, token spend drops to h1 + (if triggered) h5/h6 for a single ticker; baseline day still regenerates all phases.

**Depends on:** W2-A (for row reads in evaluators). Parallel with W2-B/C/D/E/F/G once W2-A lands.

---

## Copy-paste checklist (per Wave 2 unit prompt)

Every Wave 2 unit prompt should include:

1. Read [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) and your unit's section in this file.
2. Read the skill file(s) your phase loads.
3. Follow the `task/<slug>` branch convention; PR target is `module/digiquant-atlas`.
4. Tests pass: `pytest apps/digiquant-atlas/tests -m unit -v`.
5. `make doc-check` passes (no link regressions).
6. `make score` passes the 4-dim gate.
7. Commit message: `feat(atlas): <unit title>` + `Refs #178`.
8. End with `PR: <url>` on its own line.
