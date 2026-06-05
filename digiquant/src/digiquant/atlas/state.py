"""Atlas sub-graph state model (Pydantic — see ADR-0008).

Per-phase segment outputs live in phase modules and slot into
``AtlasResearchState`` via ``SegmentPayload | Carried``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, TypedDict  # noqa: F401 — dict shape typing below
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
    left: dict[str, AnalystRowPayload] | None,
    right: dict[str, AnalystRowPayload] | None,
) -> dict[str, AnalystRowPayload]:
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


def _merge_debate_dict(
    left: dict[str, DebateTickerState] | None,
    right: dict[str, DebateTickerState] | None,
) -> dict[str, DebateTickerState]:
    """Reducer for Phase 7C-D per-ticker debate summaries (same merge as analysts)."""
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    return merged


def _merge_specialist_dict(
    left: dict[str, dict[str, SpecialistAxisPayload]] | None,
    right: dict[str, dict[str, SpecialistAxisPayload]] | None,
) -> dict[str, dict[str, SpecialistAxisPayload]]:
    """Reducer for Phase 7C 4-axis specialist writes (#430).

    Outer key is ticker, inner key is axis ("technical" / "sentiment" /
    "news" / "fundamental"). Specialists run in parallel and each writes
    a single inner key for one ticker — collision on the outer key is
    expected, collision on the *inner* key would be a wiring bug. Merge
    inner dicts when the outer key is shared; raise on inner collision
    so two specialists writing the same axis fail loud.
    """
    if not left:
        return {ticker: dict(axes) for ticker, axes in (right or {}).items()}
    if not right:
        return {ticker: dict(axes) for ticker, axes in left.items()}
    merged: dict[str, dict[str, SpecialistAxisPayload]] = {
        ticker: dict(axes) for ticker, axes in left.items()
    }
    for ticker, axes in right.items():
        if ticker not in merged:
            merged[ticker] = dict(axes)
            continue
        for axis, payload in axes.items():
            if axis in merged[ticker]:
                raise SegmentSlotCollisionError(
                    f"two specialists wrote axis {axis!r} for ticker {ticker!r}"
                )
            merged[ticker][axis] = payload
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
    decision_lessons: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Resolved Atlas Phase 9 decisions with their LLM reflections. Loaded by the "
            "preflight node from ``decision_log`` — last 5 same-ticker per watchlist member "
            "plus 3 cross-ticker rows ordered by run_date desc. Phase 7D PM reads these to "
            "anchor the next decision against past calls. Empty list on first run."
        ),
    )


class DataLayerSnapshot(BaseModel):
    """Freshness probe for price/macro data. Populated in pre-flight."""

    price_technicals_latest: date | None = None
    price_technicals_ticker_count: int = 0
    macro_series_latest: date | None = None
    fallback_used: Literal["supabase", "scripts", "mcp", "none"] = "none"


class Phase6BiasRow(TypedDict, total=False):
    """14-column daily_snapshots bias row assembled in phase6_consolidate."""

    date: str
    run_type: str
    macro_regime: str
    equity_bias: str
    crypto_bias: str
    bond_bias: str
    commodity_bias: str
    forex_bias: str
    vix_level: float | None
    inst_flow: str
    options_sentiment: str
    cta_direction: str
    hf_consensus: str
    fed_odds: Any | None
    notes: str


class SpecialistAxisPayload(TypedDict, total=False):
    """One Phase 7C specialist axis — mirrors ``SpecialistPayload`` JSON."""

    axis: str
    ticker: str
    conviction_axis: float
    stance_axis: str
    rationale: str
    sources: list[str]


class AnalystRowPayload(TypedDict, total=False):
    """Per-ticker Phase 7C join output — mirrors ``AnalystPayload`` JSON."""

    ticker: str
    conviction_score: int
    stance: str
    thesis: str
    risks: str
    sources: list[str]


class DebateRoundPayload(TypedDict, total=False):
    """One Bull/Bear exchange round inside :class:`DebateTickerState`."""

    round_number: int
    bull_argument: str
    bear_argument: str


class DebateTickerState(TypedDict, total=False):
    """Phase 7C-D per-ticker slot — in-progress ``pending`` or final summary."""

    pending: dict[str, Any]
    rounds: list[DebateRoundPayload]
    ticker: str
    bull_thesis: str
    bear_thesis: str
    net_stance: str
    conviction_delta: int


class RiskDebatePayload(TypedDict, total=False):
    """Phase 7D risk temperament debate synthesis."""

    aggressive_case: str
    conservative_case: str
    key_tension: str


class TargetWeightRow(TypedDict):
    """One row in ``RebalancePayload.recommended_portfolio``."""

    ticker: str
    target_pct: float


class RebalanceActionRow(TypedDict, total=False):
    """One row in ``RebalancePayload.actions``."""

    ticker: str
    action: str
    current_pct: float | None
    target_pct: float
    rationale: str


class RebalancePayload(TypedDict, total=False):
    """Phase 7D PM rebalance decision JSON."""

    recommended_portfolio: list[TargetWeightRow]
    actions: list[RebalanceActionRow]
    notes: str


class Phase9EvolutionPayload(TypedDict, total=False):
    """Phase 9 LLM artifacts — mirrors ``Phase9Artifacts.model_dump``."""

    sources: dict[str, Any]
    quality: dict[str, Any]
    proposals: dict[str, Any]


class Phase7DigestPayload(TypedDict, total=False):
    """Phase 7 master digest — mirrors ``DigestSnapshot`` / ``MonthlyDigest`` dumps."""

    # SegmentReport core (present on daily + monthly digests).
    segment: str
    date: str
    bias: str
    headline: str
    material_findings: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    notes: str
    # DigestSnapshot extensions.
    market_regime_snapshot: str
    alt_data_dashboard: str
    institutional_summary: str
    asset_classes_summary: str
    us_equities_summary: str
    thesis_tracker: str
    portfolio_recommendations: str
    actionable_summary: list[dict[str, Any]]
    risk_radar: list[dict[str, Any]]
    segment_freshness: dict[str, dict[str, Any]]
    # MonthlyDigest-only.
    month_over_month_regime_delta: str


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
    phase6_bias_row: Phase6BiasRow | None = None
    phase7_digest: Phase7DigestPayload | None = None
    # Per-ticker per-axis specialist outputs (#430). Outer key = ticker,
    # inner key = axis. Populated by the 4 parallel specialists in the
    # Phase 7C fan-out; consumed by the join phase that synthesizes the
    # final ``AnalystPayload`` written into ``phase7c_analysts``.
    phase7c_specialists: Annotated[
        dict[str, dict[str, SpecialistAxisPayload]], _merge_specialist_dict
    ] = Field(default_factory=dict)
    phase7c_analysts: Annotated[dict[str, AnalystRowPayload], _merge_analyst_dict] = Field(
        default_factory=dict
    )
    # Per-ticker Bull/Bear debate summaries (#429). Populated by the
    # Phase 7C-D research-manager node; consumed by Phase 7D PM as
    # ``phase_inputs["debate_summaries"]``. Empty dict on routine runs
    # where debate is skipped (legacy graphs that don't wire the phase).
    phase7cd_debates: Annotated[dict[str, DebateTickerState], _merge_debate_dict] = Field(
        default_factory=dict
    )
    phase7d_risk_debate: RiskDebatePayload | None = None
    phase7d_rebalance: RebalancePayload | None = None
    phase9_evolution: Phase9EvolutionPayload | None = None

    # Optional user-supplied prompt for a one-off custom research run (#313).
    # When set, Phase 7 synthesis includes the prompt as additional context
    # and the publish phase routes the digest to
    # ``doc_type='Custom Research'`` / ``document_key='custom-research/<run_id>'``
    # instead of the standard ``Daily Digest`` / ``digest`` keys. Empty
    # string is treated as None at the CLI boundary.
    custom_prompt: str | None = None

    triage: DeltaTriageResult | None = None
    # Per-ticker fractional pct_change between the two most-recent trading
    # days strictly before run_date. Populated by the triage phase on delta
    # runs (empty dict on baseline / monthly). Frozen-by-convention: the
    # triage phase writes once; downstream nodes read only.
    price_deltas: dict[str, float] = Field(
        default_factory=dict,
        description="Per-ticker fractional pct_change from triage.",
    )
    published: list[PublishedArtifact] = Field(default_factory=list)
    errors: list[PhaseError] = Field(default_factory=list)
