"""Atlas sub-graph state model.

Why Pydantic (not TypedDict): sub-graph-internal state benefits from validation
and discriminated unions — see ADR-0008. Supervisor-level state in DigiGraph
stays a TypedDict (``digigraph.graph.state.WorkflowState``) for different
reasons (reducer composition). The conventions are documented; don't mix them.

Shared sub-models used across phases are defined here. Per-phase segment
output models live in their phase modules (commits 4–7) and are slotted
into ``AtlasResearchState`` via ``SegmentPayload | Carried``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal  # noqa: F401 — used for dict shape typing below
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SegmentSlotCollisionError(RuntimeError):
    """Two nodes wrote the same segment slug in one run — a wiring bug."""


def _merge_segment_dict(
    left: dict[str, "SegmentSlot"] | None,
    right: dict[str, "SegmentSlot"] | None,
) -> dict[str, "SegmentSlot"]:
    """Reducer for parallel phase-output writes.

    Each phase-1/2/4/5 node returns ``{phase_N_outputs: {segment_slug: slot}}``
    for its own segment only. LangGraph combines concurrent writes to the
    same field via this reducer — without it, LangGraph raises
    ``InvalidConcurrentGraphUpdate``.

    Collision (two writes for the same segment slug) is a copy-paste-style
    wiring bug and fails loud here. Silent right-wins would mask a
    mis-wired graph and produce nondeterministic output.
    """
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    collisions = set(left) & set(right)
    if collisions:
        raise SegmentSlotCollisionError(
            f"two nodes wrote the same segment slug(s): {sorted(collisions)}"
        )
    merged = dict(left)
    merged.update(right)
    return merged


def _merge_analyst_dict(
    left: dict[str, dict[str, Any]] | None,
    right: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Reducer for parallel Phase 7C per-ticker analyst writes.

    Each analyst node keys on ticker — collisions shouldn't happen unless
    the caller duplicates a watchlist entry. We merge and let right-wins
    on collision (the watchlist dedupes upstream); keeping the reducer a
    named function rather than an inline lambda so it is importable and
    testable like ``_merge_segment_dict``.
    """
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    return merged


RunType = Literal["baseline", "delta", "monthly"]
"""Three-tier cadence: Sunday full, weekday delta, month-end rollup."""


class Carried(BaseModel):
    """Marker that a segment was not regenerated on this run.

    Downstream consumers (synthesis, dashboard) treat ``Carried`` as
    'read the baseline payload from Supabase for this segment'. Explicit
    carry-forward is safer than a silently missing segment.
    """

    baseline_date: date
    reason: str = Field(description="Why this segment was carried, e.g. 'below_triage_threshold'")
    source: Literal["carried"] = "carried"


class SegmentPayload(BaseModel):
    """A freshly generated segment output.

    The ``body`` field holds the validated per-segment Pydantic model's
    ``.model_dump()`` — typed on the way in (at the phase node), untyped at
    this state-container level so state.py doesn't have to import every
    phase's segment model.
    """

    segment: str = Field(description="Stable segment slug, e.g. 'macro', 'sector-technology'")
    body: dict[str, Any] = Field(
        description="Validated segment payload — matches templates/schemas/<segment>.json"
    )
    source: Literal["today"] = "today"
    as_of: date


class SegmentSlot(BaseModel):
    """Discriminated slot: either a fresh payload or an explicit carry marker.

    Downstream code reads ``slot.source`` before accessing fields; this
    discriminator is what keeps fresh-vs-carried decisions auditable.
    """

    model_config = ConfigDict(frozen=True)

    payload: SegmentPayload | Carried = Field(discriminator="source")


class AtlasConfigBundle(BaseModel):
    """Static per-run config. Frozen so the LLM cache key stays stable across phases."""

    model_config = ConfigDict(frozen=True)

    watchlist: list[str] = Field(default_factory=list)
    investment_profile: dict[str, Any] = Field(default_factory=dict)
    hedge_funds: list[str] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    macro_series: list[str] = Field(default_factory=list)


class PriorContext(BaseModel):
    """Pre-flight load from Supabase. Frozen — same caching rationale as AtlasConfigBundle."""

    model_config = ConfigDict(frozen=True)

    last_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    latest_segments: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Segment slug → latest published payload (from Supabase documents)",
    )
    active_theses: list[dict[str, Any]] = Field(default_factory=list)


class DataLayerSnapshot(BaseModel):
    """Freshness probe for price/macro data. Populated in pre-flight."""

    price_technicals_latest: date | None = None
    price_technicals_ticker_count: int = 0
    macro_series_latest: date | None = None
    fallback_used: Literal["supabase", "scripts", "mcp", "none"] = "none"


class DeltaTriageDecision(BaseModel):
    """Per-segment triage outcome on a delta run."""

    segment: str
    decision: Literal["regenerate", "carry"]
    reason: str
    tier: Literal["mandatory", "high", "standard", "low"]


class DeltaTriageResult(BaseModel):
    """Output of the triage preamble on delta runs."""

    evaluated_at: date
    baseline_date: date
    decisions: list[DeltaTriageDecision] = Field(default_factory=list)


class PublishedArtifact(BaseModel):
    """One row published to Supabase. Appended to state.published by the Supabase adapter."""

    table: str
    document_key: str | None = None
    row_id: str
    published_at: date


class PhaseError(BaseModel):
    """Recoverable per-phase error; collected into state.errors for the audit row."""

    phase: str
    node: str
    message: str
    retryable: bool = True


class AtlasResearchState(BaseModel):
    """Sub-graph state. See ``docs/plans/atlas-digigraph-migration.md`` for field rationale.

    Field grouping:
    - Run metadata (run_id, run_type, dates).
    - Frozen context (config, prior_context, data_layer) — shared-context cache key.
    - Per-phase outputs as ``dict[str, SegmentSlot]`` keyed by segment slug.
    - Triage result (delta runs only).
    - Side-effect ledgers (``published``, ``errors``) — append-only by
      convention. Phase nodes should use ``list.append`` (never reassign).
      A future commit may replace with an ``Annotated[list, add]`` reducer.
    """

    run_id: UUID = Field(default_factory=uuid4)
    run_type: RunType
    run_date: date
    baseline_date: date | None = None

    config: AtlasConfigBundle = Field(default_factory=AtlasConfigBundle)
    prior_context: PriorContext = Field(default_factory=PriorContext)
    data_layer: DataLayerSnapshot = Field(default_factory=DataLayerSnapshot)

    # Parallel fan-out fields: Annotated with the segment-dict reducer so
    # LangGraph merges concurrent writes from per-segment phase nodes instead
    # of raising InvalidConcurrentGraphUpdate.
    phase1_outputs: Annotated[dict[str, SegmentSlot], _merge_segment_dict] = Field(
        default_factory=dict
    )
    phase2_outputs: Annotated[dict[str, SegmentSlot], _merge_segment_dict] = Field(
        default_factory=dict
    )
    phase3_output: SegmentSlot | None = None
    phase4_outputs: Annotated[dict[str, SegmentSlot], _merge_segment_dict] = Field(
        default_factory=dict
    )
    phase5_outputs: Annotated[dict[str, SegmentSlot], _merge_segment_dict] = Field(
        default_factory=dict
    )
    phase6_bias_row: dict[str, Any] | None = None
    phase7_digest: dict[str, Any] | None = None
    phase7c_analysts: Annotated[dict[str, dict[str, Any]], _merge_analyst_dict] = Field(
        default_factory=dict
    )
    phase7d_rebalance: dict[str, Any] | None = None
    phase9_evolution: dict[str, Any] | None = None

    triage: DeltaTriageResult | None = None
    # Per-ticker fractional pct_change between the two most-recent trading
    # days strictly before run_date. Populated by the triage phase on delta
    # runs (empty dict on baseline / monthly). Frozen-by-convention: the
    # triage phase writes once; downstream nodes read only.
    price_deltas: dict[str, float] = Field(default_factory=dict)
    published: list[PublishedArtifact] = Field(default_factory=list)
    errors: list[PhaseError] = Field(default_factory=list)
