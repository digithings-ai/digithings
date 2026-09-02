"""WP13.3 — route Atlas research attention before provider work (#2926).

Invokes :func:`plan_research_attention` after triage and branches early in
provider-owning nodes. ``off`` / ``shadow`` / ``enforce`` via
``OLYMPUS_RESEARCH_ATTENTION_MODE``. Not a graph node; no provider call to decide.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
)
from uuid import UUID

from digiquant.research.state import (
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    SegmentPayload,
    SegmentSlot,
)
from digiquant.research.triage import triage_decision_to_signal
from digiquant.research.triage_signals import max_abs_move_for_segment, segment_tickers
from digiquant.dashboard.edit_mode.content_identity import prior_content_date
from digiquant.dashboard.edit_mode.models import PriorPublished, TriageSignal
from digiquant.dashboard.edit_mode.prior import artifact_document_key
from digiquant.dashboard.edit_mode.resolve import resolve_edit_mode
from digiquant.dashboard.envcompat import RESEARCH_ATTENTION_MODE, env_lookup
from digiquant.dashboard.research_retrieval.planner import (
    AttentionDecision,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionRolloutMode,
    AttentionTargetKind,
    plan_research_attention,
)
from digiquant.dashboard.research_retrieval.store import AttentionStore

logger = logging.getLogger(__name__)

OLYMPUS_RESEARCH_ATTENTION_MODE_ENV = "OLYMPUS_RESEARCH_ATTENTION_MODE"

EnforcePath = Literal["carry", "metric_patch", "full"] | None

_RUN_STORES: dict[str, AttentionStore] = {}


def reset_attention_stores() -> None:
    """Clear in-memory attention stores (unit tests only)."""
    _RUN_STORES.clear()


def attention_store_for_run(run_id: str) -> AttentionStore:
    """Return the append-only store for one run (in-memory until Supabase writer lands)."""
    if run_id not in _RUN_STORES:
        _RUN_STORES[run_id] = AttentionStore()
    return _RUN_STORES[run_id]


def resolve_research_attention_rollout_mode() -> AttentionRolloutMode:
    """Read ``OLYMPUS_RESEARCH_ATTENTION_MODE``; unknown values → shadow."""
    raw = env_lookup(RESEARCH_ATTENTION_MODE, default="shadow").strip().lower()
    try:
        return AttentionRolloutMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            OLYMPUS_RESEARCH_ATTENTION_MODE_ENV,
            raw,
        )
        return AttentionRolloutMode.SHADOW


class _StatePriorLoader:
    """Resolve segment/digest priors from ``state.prior_context.latest_segments``."""

    def __init__(self, state: AtlasResearchState) -> None:
        self._state = state

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        doc_key = artifact_document_key(artifact_key)
        row = self._state.prior_context.latest_segments.get(doc_key)
        if not isinstance(row, dict):
            return None
        row_date = row.get("date")
        payload = row.get("payload")
        if not isinstance(row_date, str) or not isinstance(payload, dict):
            return None
        published = date.fromisoformat(row_date)
        if published >= run_date:
            return None
        return PriorPublished(
            date=published,
            document_key=doc_key,
            payload=dict(payload),
            content_date=prior_content_date(payload, published),
        )


def artifact_target_key(artifact_kind: str, artifact_id: str) -> str:
    """Canonical attention target key (``segment:macro``, ``digest:digest``)."""
    return f"{artifact_kind.strip().lower()}:{artifact_id.strip()}"


def _state_version_id(state: AtlasResearchState) -> UUID | None:
    pin = state.research_state_pin
    if not isinstance(pin, dict):
        return None
    raw = pin.get("state_version_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _triage_mode_from_signal(
    signal: TriageSignal | None,
) -> Literal["quiet", "stale", "active"] | None:
    if signal is None:
        return None
    return signal.mode


def _segment_has_structured_delta(state: AtlasResearchState, segment: str) -> bool:
    tickers = segment_tickers().get(segment, ())
    if not tickers or not state.price_deltas:
        return False
    return any(ticker in state.price_deltas for ticker in tickers)


def _staleness_days(prior: PriorPublished | None, run_date: date) -> int | None:
    if prior is None:
        return None
    content_date = prior.content_date or prior.date
    return max(0, (run_date - content_date).days)


def build_segment_attention_features(
    state: AtlasResearchState,
    segment: str,
    decision: DeltaTriageDecision | None = None,
) -> AttentionFeatures:
    """Structured features for one Atlas segment artifact."""
    loader = _StatePriorLoader(state)
    prior = loader.load(("segment", segment), state.run_date)
    triage_signal = triage_decision_to_signal(decision) if decision is not None else None
    pin_raw = _state_version_id(state)
    return AttentionFeatures(
        target_kind=AttentionTargetKind.ARTIFACT,
        target_key=artifact_target_key("segment", segment),
        state_version_id=str(pin_raw) if pin_raw is not None else None,
        has_prior=prior is not None,
        force_full_rewrite=state.refresh_scope in ("all", "segments"),
        triage_mode=_triage_mode_from_signal(triage_signal),
        has_structured_delta=_segment_has_structured_delta(state, segment),
        staleness_days=_staleness_days(prior, state.run_date),
    )


def build_digest_attention_features(
    state: AtlasResearchState,
    *,
    document_key: str,
    triage_signal: TriageSignal | None,
) -> AttentionFeatures:
    """Structured features for the master-digest artifact."""
    loader = _StatePriorLoader(state)
    prior = loader.load(("digest", document_key), state.run_date)
    pin_raw = _state_version_id(state)
    return AttentionFeatures(
        target_kind=AttentionTargetKind.ARTIFACT,
        target_key=artifact_target_key("digest", document_key),
        state_version_id=str(pin_raw) if pin_raw is not None else None,
        has_prior=prior is not None,
        force_full_rewrite=state.refresh_scope in ("all", "digest"),
        triage_mode=_triage_mode_from_signal(triage_signal),
        has_structured_delta=bool(state.price_deltas),
        staleness_days=_staleness_days(prior, state.run_date),
    )


def collect_atlas_attention_features(state: AtlasResearchState) -> tuple[AttentionFeatures, ...]:
    """All Atlas artifact targets for one run (segments + master digest)."""
    if state.custom_prompt:
        return ()
    features: list[AttentionFeatures] = []
    if state.triage is not None:
        for decision in state.triage.decisions:
            features.append(build_segment_attention_features(state, decision.segment, decision))
    from digiquant.research.phases.phase7_synthesis import (
        _digest_document_key,
        _digest_triage_signal,
    )

    doc_key = _digest_document_key(state)
    features.append(
        build_digest_attention_features(
            state,
            document_key=doc_key,
            triage_signal=_digest_triage_signal(state),
        )
    )
    return tuple(features)


def plan_atlas_research_attention(state: AtlasResearchState) -> AttentionPlan | None:
    """Build the research attention plan for this run; ``None`` when mode is off."""
    rollout = resolve_research_attention_rollout_mode()
    if rollout is AttentionRolloutMode.OFF:
        return None
    features = collect_atlas_attention_features(state)
    if not features:
        return None
    return plan_research_attention(
        run_id=str(state.run_id),
        state_version_id=_state_version_id(state),
        features=features,
        rollout_mode=rollout,
    )


def persist_research_attention_plan(
    *,
    state: AtlasResearchState,
    plan: AttentionPlan,
    attempt_id: str | None = None,
    recorded_at: datetime | None = None,
) -> None:
    """Append plan + decisions to the run-scoped :class:`AttentionStore`."""
    stamp = recorded_at or datetime.now(tz=UTC)
    resolved_attempt = attempt_id or str(state.run_id)
    store = attention_store_for_run(str(state.run_id))
    store.append_plan(plan, attempt_id=resolved_attempt, recorded_at=stamp)


def plan_and_persist_research_attention(state: AtlasResearchState) -> AttentionPlan | None:
    """Plan after triage and persist reasons to :class:`AttentionStore`."""
    plan = plan_atlas_research_attention(state)
    if plan is not None:
        persist_research_attention_plan(state=state, plan=plan)
    return plan


def _load_attention_plan(state: AtlasResearchState) -> AttentionPlan | None:
    raw = state.research_attention_plan
    if raw is None:
        return None
    if isinstance(raw, AttentionPlan):
        return raw
    return AttentionPlan.model_validate(raw)


def resolve_attention_plan_for_node(state: AtlasResearchState) -> AttentionPlan | None:
    """Return the plan for provider gating — lazy-build when triage ran without persist."""
    rollout = resolve_research_attention_rollout_mode()
    if rollout is AttentionRolloutMode.OFF or state.custom_prompt:
        return None
    plan = _load_attention_plan(state)
    if plan is not None:
        return plan
    if state.triage is not None:
        return plan_atlas_research_attention(state)
    if rollout is AttentionRolloutMode.ENFORCE:
        raise RuntimeError(
            "research attention plan missing before provider work "
            f"(run_id={state.run_id}); triage must plan first"
        )
    return None


def require_research_attention_plan(state: AtlasResearchState) -> AttentionPlan:
    """Fail closed when provider work starts without a plan (shadow/enforce)."""
    plan = resolve_attention_plan_for_node(state)
    if plan is None:
        raise RuntimeError(
            "research attention plan missing before provider work "
            f"(run_id={state.run_id}); triage must plan first"
        )
    return plan


def lookup_attention_decision(
    plan: AttentionPlan | None,
    target_key: str,
) -> AttentionDecision | None:
    if plan is None:
        return None
    for decision in plan.decisions:
        if decision.target_key == target_key:
            return decision
    return None


def enforce_path_for_decision(decision: AttentionDecision | None) -> EnforcePath:
    """Map an enforced decision to an early-exit path (``None`` → incumbent)."""
    if decision is None or not decision.actuated:
        return None
    if decision.mode is AttentionMode.CARRY:
        return "carry"
    if decision.mode is AttentionMode.METRIC_PATCH:
        return "metric_patch"
    if decision.mode is AttentionMode.DEEP_REFRESH:
        return "full"
    return None


def research_attention_enforce_path(
    state: AtlasResearchState,
    *,
    target_key: str,
) -> EnforcePath:
    """Return early-exit path under enforce mode; ``None`` for off/shadow/incumbent."""
    if resolve_research_attention_rollout_mode() is not AttentionRolloutMode.ENFORCE:
        return None
    plan = resolve_attention_plan_for_node(state)
    if plan is None:
        return None
    decision = lookup_attention_decision(plan, target_key)
    return enforce_path_for_decision(decision)


def apply_segment_metric_patch(
    state: AtlasResearchState,
    segment: str,
    prior: PriorPublished,
) -> SegmentSlot:
    """Deterministic structured update — zero provider calls (#2926)."""
    body = dict(prior.payload)
    tickers = segment_tickers().get(segment, ())
    deltas = {
        ticker: state.price_deltas[ticker] for ticker in tickers if ticker in state.price_deltas
    }
    if not deltas and tickers:
        move = max_abs_move_for_segment(state.price_deltas, segment)
        if move is not None:
            deltas = {"_segment_max_abs_move": move}
    body["structured_price_deltas"] = deltas
    body["metric_patch"] = True
    body["segment"] = segment
    body["date"] = state.run_date.isoformat()
    return SegmentSlot(
        payload=SegmentPayload(segment=segment, body=body, as_of=state.run_date),
    )


def apply_digest_metric_patch(
    state: AtlasResearchState,
    prior: PriorPublished,
) -> dict[str, Any]:
    """Deterministic digest structured update — zero provider calls."""
    body = dict(prior.payload)
    body["structured_price_deltas"] = dict(state.price_deltas)
    body["metric_patch"] = True
    body["date"] = state.run_date.isoformat()
    return body


def carry_segment_slot(
    state: AtlasResearchState,
    segment: str,
    *,
    reason: str,
    prior: PriorPublished | None = None,
) -> SegmentSlot:
    if prior is not None:
        baseline = prior.date
    elif state.baseline_date is not None:
        baseline = state.baseline_date
    else:
        loader = _StatePriorLoader(state)
        loaded = loader.load(("segment", segment), state.run_date)
        baseline = loaded.date if loaded is not None else state.run_date
    return SegmentSlot(payload=Carried(baseline_date=baseline, reason=reason))


def incumbent_segment_edit_mode(state: AtlasResearchState, segment: str) -> str:
    loader = _StatePriorLoader(state)
    triage_signal = None
    if state.triage is not None:
        decision = next((d for d in state.triage.decisions if d.segment == segment), None)
        if decision is not None:
            triage_signal = triage_decision_to_signal(decision)
    from digiquant.research.state import refresh_scope_forces_full

    return resolve_edit_mode(
        artifact_key=("segment", segment),
        run_date=state.run_date,
        prior_loader=loader,
        triage=triage_signal,
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="segment"),
    )


def triage_phase_attention_update(state: AtlasResearchState) -> dict[str, Any]:
    """State update dict after triage evaluation — plan before provider nodes."""
    plan = plan_and_persist_research_attention(state)
    if plan is None:
        return {}
    return {"research_attention_plan": plan.model_dump(mode="json")}


__all__ = [
    "OLYMPUS_RESEARCH_ATTENTION_MODE_ENV",
    "apply_digest_metric_patch",
    "apply_segment_metric_patch",
    "artifact_target_key",
    "attention_store_for_run",
    "build_digest_attention_features",
    "build_segment_attention_features",
    "carry_segment_slot",
    "collect_atlas_attention_features",
    "enforce_path_for_decision",
    "incumbent_segment_edit_mode",
    "lookup_attention_decision",
    "persist_research_attention_plan",
    "plan_and_persist_research_attention",
    "plan_atlas_research_attention",
    "require_research_attention_plan",
    "research_attention_enforce_path",
    "reset_attention_stores",
    "resolve_attention_plan_for_node",
    "resolve_research_attention_rollout_mode",
    "triage_phase_attention_update",
]
