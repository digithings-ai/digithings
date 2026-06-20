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


def _merge_right_wins_dict[T](
    left: dict[str, T] | None,
    right: dict[str, T] | None,
) -> dict[str, T]:
    """Reducer for parallel per-key writes where right wins on collision.

    Used for Phase 7C analyst rows and Phase 7C-D debate summaries — each
    node keys on ticker; collisions should not happen unless the watchlist
    duplicates an entry. Named (not inline lambda) so reducers stay importable
    and testable like ``_merge_segment_dict``.
    """
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    return merged


def _merge_specialist_dict(
    left: dict[str, dict[str, dict[str, Any]]] | None,
    right: dict[str, dict[str, dict[str, Any]]] | None,
) -> dict[str, dict[str, dict[str, Any]]]:
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
    merged: dict[str, dict[str, dict[str, Any]]] = {
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


def _merge_append_list[T](left: list[T] | None, right: list[T] | None) -> list[T]:
    """Reducer for append-only ledgers written concurrently (e.g. ``state.errors``).

    Parallel fan-out nodes (11 sectors, 5 alt-data) each return ``{"errors": [...]}``
    for their own recoverable failure; without an append reducer LangGraph's default
    last-writer-wins would drop all but one. Concatenate so every node's
    ``PhaseError`` survives the fan-in into the diagnostics audit row.
    """
    return [*(left or []), *(right or [])]


RunType = Literal["baseline", "delta", "monthly"]
"""Legacy storage label for ``daily_snapshots.run_type``; derived from ``refresh_scope``."""

Cadence = Literal["daily"]
"""Olympus v1 operator cadence — single daily graph topology."""

RefreshScope = Literal["none", "all", "segments", "hermes", "digest", "beliefs"]
"""Operator override forcing full rewrites for matching artifact classes."""


def refresh_scope_forces_full(
    refresh_scope: RefreshScope,
    *,
    artifact: Literal["segment", "digest"],
) -> bool:
    """Whether ``refresh_scope`` forces ``resolve_edit_mode → full`` for *artifact*."""
    if refresh_scope == "all":
        return True
    if refresh_scope == "segments" and artifact == "segment":
        return True
    if refresh_scope == "digest" and artifact == "digest":
        return True
    return False


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
    active_theses: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Non-terminal ``theses`` rows from the latest booked date before ``run_date``. "
            "Hermes phase-0 entry (thesis review) consumes these until Wave-2 h1–h4 land."
        ),
    )
    decision_lessons: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Resolved Atlas Phase 9 decisions with their LLM reflections. Loaded by the "
            "preflight node from ``decision_log`` — last 5 same-ticker per watchlist member "
            "plus 3 cross-ticker rows ordered by run_date desc. Phase 7D PM reads these to "
            "anchor the next decision against past calls. Empty list on first run."
        ),
    )
    prior_book: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Materialized ``positions`` rows for the most recent date strictly before "
            "``run_date``. Empty on the first ever run. Hydrated in preflight for prompt "
            "continuity and mirrored into ``config.preferences.current_weights``."
        ),
    )
    prior_analyst_by_ticker: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Slim prior ``analyst/{ticker}`` summaries for held names — date, document_key, "
            "stance, conviction_score, thesis_excerpt. Full payloads stay in Supabase; phases "
            "fetch via ``query_data`` when the excerpt is insufficient (#859)."
        ),
    )
    portfolio_performance: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Latest ``nav_history`` point strictly before ``run_date`` plus same-day "
            "``portfolio_metrics`` when present. PM / risk phases use this as a pointer; "
            "full history is tool-fetchable (#859)."
        ),
    )


class DataLayerSnapshot(BaseModel):
    """Freshness probe + compact market values for price/macro data. Populated in pre-flight."""

    price_technicals_latest: date | None = None
    price_technicals_ticker_count: int = 0
    macro_series_latest: date | None = None
    fallback_used: Literal["supabase", "scripts", "mcp", "none"] = "none"
    # Deterministic quantitative context injected into every phase's shared
    # context (#694): latest technicals for the core/sector ETF set plus the
    # latest macro series values. Agents were expected to pull these via the
    # data tools but never call them (tool_choice=auto) — inject instead.
    market_context: dict[str, Any] = Field(default_factory=dict)
    # Phase 2 institutional circuit-breaker signals (#928). ``institutional_data_available``
    # is the freshness flag: True when the most recent prior run published an ``inst-*``
    # document (ingest present). ``institutional_absence_streak`` counts how many consecutive
    # recent runs published none — when this reaches the delta breaker threshold the paid
    # Phase 2 institutional LLM/search nodes are skipped in favor of a deterministic "absent"
    # stub. Derived in pre-flight via ``query_institutional_absence_streak``.
    institutional_data_available: bool = True
    institutional_absence_streak: int = 0


class Phase6BiasRow(TypedDict, total=False):
    """Deterministic daily_snapshots bias row assembled in phase6_consolidate."""

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
    # On-chain smart-money vs rekt cohort divergence from Hyperdash (#801). Compact dict
    # (overall_divergence + top divergent markets) populated by preflight; None on outage.
    onchain_positioning: Any | None
    notes: str


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
    data_quality: str | None
    confidence: float | None
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
    regime_label: str
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


class FocusRosterEntry(BaseModel):
    """One ticker on the Hermes H4 focus roster."""

    ticker: str
    roster_reason: Literal["thesis_mapped", "technical", "held", "momentum", "other"]
    linked_market_thesis_id: str | None = None


class PhaseHermesState(BaseModel):
    """Thesis-first Hermes slots (H1–H9)."""

    thesis_review: dict[str, Any] | None = None
    market_thesis_exploration: dict[str, Any] | None = None
    thesis_vehicle_map: dict[str, Any] | None = None
    focus_roster: list[FocusRosterEntry] = Field(default_factory=list)
    asset_analysts: Annotated[dict[str, dict[str, Any]], _merge_right_wins_dict] = Field(
        default_factory=dict
    )
    deliberation_summaries: Annotated[dict[str, dict[str, Any]], _merge_right_wins_dict] = Field(
        default_factory=dict
    )
    pm_direction_memo: Any | None = (
        None  # PMDirectionMemo JSON; typed in hermes.models.pm_direction
    )
    sized_book: RebalancePayload | None = None
    commit_manifest: dict[str, Any] | None = None


def _merge_phase_hermes(
    left: PhaseHermesState | None,
    right: PhaseHermesState | None,
) -> PhaseHermesState:
    """Reducer for parallel H5/H6 writes into nested ``phase_hermes`` slots."""
    if not left:
        return right or PhaseHermesState()
    if not right:
        return left
    merged = left.model_copy(deep=True)
    if right.asset_analysts:
        merged.asset_analysts = {**merged.asset_analysts, **right.asset_analysts}
    if right.deliberation_summaries:
        merged.deliberation_summaries = {
            **merged.deliberation_summaries,
            **right.deliberation_summaries,
        }
    for field in (
        "thesis_review",
        "market_thesis_exploration",
        "thesis_vehicle_map",
        "focus_roster",
        "pm_direction_memo",
        "sized_book",
        "commit_manifest",
    ):
        val = getattr(right, field)
        if val:
            object.__setattr__(merged, field, val)
    return merged


class AtlasResearchState(BaseModel):
    """Sub-graph state. See ``docs/plans/atlas-digigraph-migration.md`` for field rationale.

    Field grouping:
    - Run metadata (run_id, run_type, dates).
    - Frozen context (config, prior_context, data_layer) — shared-context cache key.
    - Per-phase outputs as ``dict[str, SegmentSlot]`` keyed by segment slug.
    - Triage result (delta runs only).
    - Side-effect ledgers (``published``, ``errors``). ``errors`` uses an
      append reducer (``_merge_append_list``) so concurrent per-node writes
      concatenate; ``published`` stays append-by-convention (single-node writer).
    """

    run_id: UUID = Field(default_factory=uuid4)
    run_type: RunType
    cadence: Cadence = "daily"
    refresh_scope: RefreshScope = "none"
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
    phase7d_risk_debate: RiskDebatePayload | None = None
    phase7d_rebalance: RebalancePayload | None = None
    phase9_evolution: Phase9EvolutionPayload | None = None
    phase_hermes: Annotated[PhaseHermesState, _merge_phase_hermes] = Field(
        default_factory=PhaseHermesState
    )

    # Transient per-Send fan-out cursor: a ``FanOutPhase`` dispatch (the H5/H6 per-ticker map)
    # sets this on the state copy it hands each parallel worker, so the worker knows which
    # ticker it owns. Workers never write it back, so the merged graph state keeps it None.
    hermes_fanout_ticker: str | None = None

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
    document_deltas: Annotated[dict[str, dict[str, Any]], _merge_right_wins_dict] = Field(
        default_factory=dict,
        description=(
            "Audit ``DocumentPatch`` payloads keyed by target materialized "
            "document_key (§5.4). Populated by edit-mode nodes; consumed by publish."
        ),
    )
    published: list[PublishedArtifact] = Field(default_factory=list)
    # Append reducer (not last-writer-wins): parallel fan-out nodes each record
    # their own recoverable failure via ``{"errors": [PhaseError(...)]}``; the
    # reducer concatenates them so none are lost before the diagnostics row.
    errors: Annotated[list[PhaseError], _merge_append_list] = Field(default_factory=list)
