# Wave 2 Unit Specs — Hermes implementation

> **Historical note (WS4a):** This document describes the planned Wave 2 Hermes expansion. The Wave 2 skills (thesis, thesis-tracker, thesis-vehicle-map, opportunity-screener, deliberation, asset-analyst, market-thesis-exploration, deep-dive) were never wired to the live graph and have been deleted. This spec is preserved for reference.

> **Parent spec:** [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md).
> **Parent plan:** [`docs/plans/atlas-full-migration-wave1.md`](../../../../docs/plans/atlas-full-migration-wave1.md) §"Wave 2 preview".
> **Prereqs:** Wave 1 units W1-A-PLAN (this spec), W1-B (migration 024). W1-D and W1-E are independent.
> **Branch convention:** each unit branches `module/digiquant-atlas` → `task/w2X-<slug>`; PR back into `module/digiquant-atlas`.

Each unit below is ready to copy-paste into an agent prompt (set the branch, read the two parent docs, execute).

---

## Parallelism map

```
W2-A (adapters + migration 025) ──► W2-B, W2-C, W2-D, W2-E, W2-F, W2-G, W2-H
W2-B (state scaffold: PhaseHermesState, RecessRequest, _append_list) ──► W2-F
W2-E (h5) ───────────────────────► W2-F (h6 reads AssetRecommendation)
W2-F (h6) ───────────────────────► W2-G (h7 reads DeliberationSession)
W2-B, W2-C, W2-D — parallel (read h1/h2/h3 only)
W2-H — parallel after W2-A
```

- **Strictly sequential:** W2-A → (everything else). W2-E → W2-F → W2-G. W2-B → W2-F (the state scaffold containing `PhaseHermesState`, `RecessRequest`, and `_append_list` is authored in W2-B; W2-F consumes it instead of re-declaring).
- **Fully parallel after W2-A:** W2-B, W2-C, W2-D, W2-H.

---

## W2-A — Supabase adapters for migration 024

**Branch:** `task/w2a-adapters-024`
**Complexity:** M — blocking, run first.

**Files (create/modify):**

- Modify: `digiquant/src/digiquant/olympus/atlas/supabase_io.py` — add writer functions:
  - `write_thesis_vehicles(rows: list[ThesisVehicleRow]) -> list[PublishedArtifact]`
  - `write_deliberation_session(row: DeliberationSessionRow) -> PublishedArtifact`
  - `write_deliberation_rounds(rows: list[DeliberationRoundRow]) -> list[PublishedArtifact]`
  - `upsert_analyst_coverage(rows: list[AnalystCoverageRow]) -> list[PublishedArtifact]`
  - `write_deep_dive_triggers(rows: list[DeepDiveTriggerRow]) -> list[PublishedArtifact]`
  - `upsert_theses(rows: list[ThesisRow]) -> list[PublishedArtifact]` (may already exist). Writes **only** the canonical `theses` columns from migration 001: `date`, `thesis_id`, `name`, `vehicle`, `invalidation`, `status`, `notes`. There is **no** `evidence_log` column on `theses` — the per-day evidence trail lives in the `'Thesis Review'` document payload (`body.reviewed_theses[].evidence[]`), not in a relational column. Do NOT add an `evidence_log` column; if a future reader wants indexed evidence, propose it in a separate migration.
- Create: `digiquant/supabase/migrations/025_hermes_doc_types.sql` — extends `chk_documents_doc_type` to include `'Thesis Review'` and `'Opportunity Screen'` (see [HERMES_SUBGRAPH §5.1](HERMES_SUBGRAPH.md#51-migration-025--hermes-doc_type-additions-stub-implemented-in-w2-a)). Keep every existing token from migration 023 in the new CHECK. Apply to dev DB before W2-B / W2-D start.
- Create: `digiquant/src/digiquant/olympus/atlas/supabase_rows.py` — typed dataclasses/Pydantic for the five row types above.
- Modify: tests FakeSupabaseClient in `tests/dq/atlas/conftest.py` — record writes per-table for assertion.

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

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h1_thesis_review.py` — single-node phase; loads `thesis` + `thesis-tracker` skills; outputs `ThesisReviewOutput`.
- Create: `digiquant/src/digiquant/olympus/atlas/templates/schemas/thesis-review.schema.json` — envelope `{schema_version, doc_type="Thesis Review", date, meta, body}` (Title-Case token matching migration 025's extension to `chk_documents_doc_type`; see [HERMES_SUBGRAPH §5.1](HERMES_SUBGRAPH.md#51-migration-025--hermes-doc_type-additions-stub-implemented-in-w2-a)); body per [HERMES_SUBGRAPH §4.1](HERMES_SUBGRAPH.md#41-thesisreviewoutput-phase_h1). `body.reviewed_theses[].new_status` is constrained to the seven tokens allowed by `chk_theses_status` (`ACTIVE` / `MONITORING` / `CHALLENGED` / `CLOSED` / `INVALIDATED` / `PAUSED` / `NEW`); `body.reviewed_theses[].resolution` (optional) is `"win" | "loss"`, required iff `new_status == "CLOSED"`. Persistence writes the status to the `theses` row and the evidence list to the document payload — there is no relational `evidence_log` field.
- Modify: `digiquant/src/digiquant/olympus/atlas/state.py` — add `PhaseHermesState` scaffold + `RecessRequest` + new reducers `_merge_session_dict`, `_append_list`. Add `phase_hermes: PhaseHermesState` field to `AtlasResearchState`.
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — wire `phase_h1_thesis_review` after `phase6_consolidate`.

**Inline Pydantic contract (authoritative for W2-B):**

```python
class ThesisStatusUpdate(BaseModel):
    thesis_id: str
    prior_status: Literal["ACTIVE", "MONITORING", "CHALLENGED", "CLOSED", "INVALIDATED", "PAUSED", "NEW"] | None
    new_status:   Literal["ACTIVE", "MONITORING", "CHALLENGED", "CLOSED", "INVALIDATED", "PAUSED", "NEW"]
    evidence: list[str]
    challenged_by: list[str] | None = None
    resolution: Literal["win", "loss"] | None = None   # required iff new_status=="CLOSED"
    reason: str | None = None                           # required iff new_status=="INVALIDATED"

class ThesisReviewOutput(BaseModel):
    reviewed_theses: list[ThesisStatusUpdate]
    new_candidate_theses: list[str] = Field(default_factory=list)
    notes: str = ""
```

**Tests:**

- `tests/phases/test_phase_h1_thesis_review.py` — skill-load + node-run with a stub `run_research_agent` returning a `ThesisReviewOutput`; asserts `state.phase_hermes.thesis_review` is set and `upsert_theses` writer is called.
- State round-trip test for `PhaseHermesState`.
- Validation test: `new_status="CLOSED"` without `resolution` raises; `new_status="INVALIDATED"` without `reason` raises.

**Acceptance:** phase runs standalone; `theses` table upsert invoked with correct status transitions; schema validates a golden fixture.

**Depends on:** W2-A.

---

## W2-C — phase_h2_market_thesis_exploration

**Branch:** `task/w2c-phase-h2-market-thesis`
**Complexity:** S.

**Files:**

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h2_market_thesis_exploration.py`.
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — wire after h1.
- Pydantic model `MarketThesisExploration` in the phase module, validated against existing [`market-thesis-exploration.schema.json`](../../hermes/templates/schemas/market-thesis-exploration.schema.json).

**Inline Pydantic contract:**

```python
class ThesisProposal(BaseModel):
    thesis_id: constr(max_length=32)
    title: constr(max_length=200)
    direction: Literal["long", "short", "pair", "hedge", "avoid"]
    statement: constr(max_length=4000)
    validation_criteria: list[str] = Field(min_length=1)
    invalidation_criteria: list[str] = Field(min_length=1)
    headwinds: list[str] = Field(default_factory=list)
    tailwinds: list[str] = Field(default_factory=list)
    bull_case: str | None = None
    bear_case: str | None = None

class MarketThesisExploration(BaseModel):
    executive_digest_pointer: str
    deeper_dives: list[str] = Field(default_factory=list)
    theses: list[ThesisProposal]
```

**Tests:**

- `tests/phases/test_phase_h2_market_thesis.py` — stub `run_research_agent`; assert new thesis rows are inserted into `theses` via W2-A.

**Acceptance:** new `ThesisProposal`s create `theses` rows with `status='ACTIVE'`; `thesis_id` uniqueness enforced within the run.

**Depends on:** W2-A. Parallel with W2-B and W2-D.

---

## W2-D — phase_h3_thesis_vehicle_map + phase_h4_opportunity_screener

**Branch:** `task/w2d-phase-h3-h4-vehicle-screener`
**Complexity:** M — two phases but tightly coupled (h4 reads h3).

**Files:**

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h3_thesis_vehicle_map.py`.
- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h4_opportunity_screener.py`.
- Create: `digiquant/src/digiquant/olympus/atlas/templates/schemas/opportunity-screen.schema.json` — envelope `{schema_version, doc_type="Opportunity Screen", date, meta, body}` (Title-Case token; added to `chk_documents_doc_type` by migration 025).
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — wire h3→h4.

**Inline Pydantic contracts:**

```python
class ThesisVehicleMapping(BaseModel):
    thesis_id: str
    candidate_tickers: list[constr(max_length=12)] = Field(min_length=1)
    rationale: constr(max_length=4000)
    exclusion_reasons: list[str] = Field(default_factory=list)
    user_mandate_notes: list[str] = Field(default_factory=list)

class ThesisVehicleMap(BaseModel):
    mappings: list[ThesisVehicleMapping]

class RosterPick(BaseModel):
    ticker: str
    rank: int  # 1 = highest; unique + dense across roster
    score: float = Field(ge=0, le=1)
    source_thesis_ids: list[str] = Field(min_length=1)
    rationale: constr(max_length=800)

class OpportunityScreen(BaseModel):
    roster: list[RosterPick]
    excluded: list[dict] = Field(default_factory=list)  # ExcludedTicker — ticker + reason
    notes: str = ""
```

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

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h5_asset_analyst.py` — per-ticker fan-out over `state.phase_hermes.opportunity_screen.roster`; Pydantic `AssetRecommendation` validated against [`asset-recommendation.schema.json`](../../hermes/templates/schemas/asset-recommendation.schema.json).

**Inline Pydantic contract:**

```python
class PriceContext(BaseModel):
    price: float
    day_pct: float
    segment_bias: str

class Verdict(BaseModel):
    bias: Literal["overweight", "neutral", "underweight", "avoid"]
    thesis_status: str  # same 7-token vocabulary as chk_theses_status
    recommended_weight_pct: float = Field(ge=0, le=100)  # ignored iff bias=="avoid"
    rationale: constr(max_length=2000)

class AssetRecommendation(BaseModel):
    context: PriceContext
    bull_case: list[str]
    bear_case: list[str]
    verdict: Verdict
    catalysts: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    # Blinded rule: MUST NOT read config/portfolio.json current_weights.
```
- **Delete:** `digiquant/src/digiquant/olympus/atlas/phases/phase7c_analyst.py`.
- Modify: `digiquant/src/digiquant/olympus/atlas/state.py` — remove `phase7c_analysts` field and `AnalystPayload`. **Decision (pre-made — do not re-litigate):** `_merge_analyst_dict` is kept AND renamed to `_merge_ticker_dict`; both h5 (`asset_recommendations`) and h6 (`deliberation_sessions`) reuse it — there is only one ticker-keyed merge policy in Hermes so the neutral name is clearer. Update [`HERMES_SUBGRAPH §3`](HERMES_SUBGRAPH.md#3-state-additions-to-atlasresearchstate) to reference `_merge_ticker_dict` in the same PR (replace the two `_merge_analyst_dict` / `_merge_session_dict` annotations with one shared reducer).
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — swap `build_phase7c` call for `build_phase_h5`.
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

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h6_deliberation.py` — per-ticker fan-out; each ticker node is a nested `StateGraph` (analyst_present → pm_challenge → converge_check → loop/exit) compiled once at phase-build time.
- Create: `digiquant/src/digiquant/olympus/atlas/phases/_deliberation_loop.py` — nested graph builder; isolated for unit-testing the loop independently.
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — wire h6 after h5.
- Modify: `digiquant/src/digiquant/olympus/atlas/state.py` — confirm `RecessRequest` + `_append_list` from W2-B are used.
- Persistence: writes `documents` (`doc_type='Deliberation Transcript'` per ticker + one `doc_type='Deliberation Session Index'`; Title-Case tokens already in migration-023 allowlist) + `deliberation_sessions` (run-level; `kind` ∈ `{'baseline', 'delta_scoped', 'monthly'}`) + `deliberation_rounds` (per round per ticker) + `deep_dive_triggers` (per `RecessRequest`; `triggered_by='pm_recess'` — see W2-F phase_h6). Adapters from W2-A.
- Env var reader: `ATLAS_DELIBERATION_MAX_ROUNDS` with default 6 (canonical definition: [HERMES_SUBGRAPH §2.2](HERMES_SUBGRAPH.md#22-safety-cap)).

**Inline Pydantic contracts:**

```python
class RecessRequest(BaseModel):       # state-only marker
    ticker: str
    reason: str
    trigger_round_number: int

class DeliberationRound(BaseModel):
    label: str
    round_number: int
    sections: list[dict]  # each {"heading": one of {"analyst","pm_challenge","analyst_defense","pm_decision","recess_reason"}, "markdown": str}
    converged: bool
    recess_triggered: bool
    deep_dive_document_key: str | None = None

class FinalDecision(BaseModel):
    ticker: str
    analyst_recommendation: str
    pm_decision: str
    invalidation_condition: str

class DeliberationSession(BaseModel):
    trigger_summary: list[str]
    rounds: list[DeliberationRound]
    final_decisions: list[FinalDecision]
    converged: bool
    escalated: bool = False           # True iff cap hit
    rounds_completed: int             # == len(rounds)
```

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

- Create: `digiquant/src/digiquant/olympus/atlas/phases/phase_h7_pm_allocation_memo.py` — single node; loads `pm-allocation-memo` skill; Pydantic `PMAllocationMemo` validated against [`pm-allocation-memo.schema.json`](../../hermes/templates/schemas/pm-allocation-memo.schema.json). Conditional router: skip when no deliberation session ran this run (see HERMES_SUBGRAPH §6).

**Inline Pydantic contract:**

```python
class TargetWeightRationale(BaseModel):
    ticker: str
    target_weight_pct: float = Field(ge=0, le=100)
    prior_weight_pct: float | None = None
    rationale: constr(max_length=2000)
    deliberation_document_key: str | None = None  # must resolve to a deliberation_sessions row when non-null

class PMAllocationMemo(BaseModel):
    narrative: constr(max_length=12000)
    turnover_discipline: constr(max_length=4000)
    target_weights_rationale: list[TargetWeightRationale]
    open_questions: list[str] = Field(default_factory=list)
    # Validation: sum(target_weight_pct) <= 100 + cash tolerance (default 101).
```
- Modify: `digiquant/src/digiquant/olympus/atlas/phases/phase7d_pm.py` — replace LLM call with deterministic transform that reads `state.phase_hermes.pm_allocation_memo` and current weights, emits `RebalanceDecision`. Remove skill loading.
- Modify: `digiquant/src/digiquant/olympus/atlas/graph.py` — wire h7 after h6 (or after `deep_dive_batch` when present); phase7d consumes h7.

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

- Modify: `digiquant/src/digiquant/olympus/atlas/triage.py` — add rule kinds `hermes_thesis_drift`, `hermes_ticker_filter`, `hermes_memo_gate`. Extend gate signature to support ticker-keyed Carried markers; document the split (per-segment vs per-ticker).
- Modify: `digiquant/src/digiquant/olympus/atlas/phases/_node_factory.py` — accept per-ticker triage gate for h5/h6 builders.
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
4. Tests pass: `pytest tests/dq/atlas -m unit -v`.
5. `make doc-check` passes (no link regressions).
6. `make score` passes the 4-dim gate.
7. Commit message: `feat(atlas): <unit title>` + `Refs #178`.
8. End with `PR: <url>` on its own line.
