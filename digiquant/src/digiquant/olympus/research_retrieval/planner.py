"""WP11.3 — deterministic H6 deliberation selection (#2902).

Select H6 only for structured decision-value cases (decision boundary, conflict,
uncertainty, invalidation risk, material portfolio weight, or exploration).
Low-value names carry with a recorded reason and zero provider budget.

Modes (``OLYMPUS_H6_SELECTION_MODE``):

* ``shadow`` (default) — record :class:`H6Selection`; run full incumbent H6
* ``enforce`` — actuate carry/select from the typed selection
* ``off`` — skip selection; full incumbent H6

Planner failure falls back to **full incumbent H6**, never an unrecorded skip.
Materiality (``weight_pct``) is a selection feature only — callers must not
inject it into provider prompts.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

OLYMPUS_H6_SELECTION_MODE_ENV = "OLYMPUS_H6_SELECTION_MODE"

# Portfolio weight at/above this selects ``material`` (percent of book).
_DEFAULT_MATERIAL_WEIGHT_PCT = 5.0
# Absolute price move that marks an entry/exit/sizing boundary for held names.
_DEFAULT_BOUNDARY_PRICE_DELTA = 0.02
# |conviction| at/above this with directional stance marks a sizing boundary.
_DEFAULT_BOUNDARY_CONVICTION = 3

_EXPLORATORY_ROSTER_REASONS = frozenset({"technical", "momentum", "other"})

NonEmptyStr: TypeAlias = Annotated[str, Field(min_length=1, max_length=500)]
RosterReason: TypeAlias = Literal["thesis_mapped", "technical", "held", "momentum", "other"]
RawUncertaintyLabel: TypeAlias = Literal["low", "medium", "high"]


class H6SelectionMode(StrEnum):
    """Rollout knob for deterministic H6 selection."""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class H6Action(StrEnum):
    """Whether H6 deliberation should run or carry."""

    SELECT = "select"
    CARRY = "carry"


class H6SelectionReason(StrEnum):
    """Exactly one primary reason per run/carry (metric gate)."""

    DECISION_BOUNDARY = "decision_boundary"
    CONFLICT = "conflict"
    UNCERTAINTY = "uncertainty"
    INVALIDATION_RISK = "invalidation_risk"
    MATERIAL = "material"
    EXPLORATION = "exploration"
    LOW_VALUE_CARRY = "low_value_carry"
    INCUMBENT_FALLBACK = "incumbent_fallback"


class H6PlannerModel(BaseModel):
    """Strict immutable base for H6 selection contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class H6DecisionFeatures(H6PlannerModel):
    """Structured inputs for deterministic selection (not prompt material)."""

    ticker: NonEmptyStr
    roster_reason: RosterReason
    held: bool = False
    weight_pct: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    stance: NonEmptyStr = "hold"
    prior_stance: str | None = None
    conviction_score: int = Field(default=0, ge=-5, le=5)
    raw_uncertainty: RawUncertaintyLabel | None = None
    has_evidence_conflict: bool = False
    counter_evidence_count: int = Field(default=0, ge=0)
    invalidation_risk: bool = False
    evidence_bundle_id: str | None = None
    price_delta_abs: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    stance_changed: bool = False

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("stance")
    @classmethod
    def _normalize_stance(cls, value: str) -> str:
        return value.strip().lower() or "hold"


class H6Budget(H6PlannerModel):
    """Provider/round budget implied by the selection decision."""

    max_provider_calls: int = Field(ge=0)
    min_rounds: int = Field(ge=0)
    estimated_rounds: int = Field(ge=0)


class H6Selection(H6PlannerModel):
    """Typed H6 selection outcome — reasons / features / budget."""

    ticker: NonEmptyStr
    action: H6Action
    reason: H6SelectionReason
    features: H6DecisionFeatures
    budget: H6Budget
    mode: H6SelectionMode = H6SelectionMode.SHADOW
    actuated: bool = False

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


def resolve_h6_selection_mode() -> H6SelectionMode:
    """Read ``OLYMPUS_H6_SELECTION_MODE``; unknown values → shadow."""
    raw = os.environ.get(OLYMPUS_H6_SELECTION_MODE_ENV, "shadow").strip().lower()
    try:
        return H6SelectionMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            OLYMPUS_H6_SELECTION_MODE_ENV,
            raw,
        )
        return H6SelectionMode.SHADOW


def _material_weight_threshold() -> float:
    raw = os.environ.get("OLYMPUS_H6_MATERIAL_WEIGHT_PCT", "").strip()
    if not raw:
        return _DEFAULT_MATERIAL_WEIGHT_PCT
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_MATERIAL_WEIGHT_PCT


def _boundary_price_delta() -> float:
    raw = os.environ.get("OLYMPUS_H6_BOUNDARY_PRICE_DELTA", "").strip()
    if not raw:
        return _DEFAULT_BOUNDARY_PRICE_DELTA
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_BOUNDARY_PRICE_DELTA


def _is_decision_boundary(features: H6DecisionFeatures) -> bool:
    if features.stance_changed:
        return True
    directional = features.stance in {"buy", "sell"}
    if directional and abs(features.conviction_score) >= _DEFAULT_BOUNDARY_CONVICTION:
        return True
    if features.held and features.price_delta_abs is not None:
        if features.price_delta_abs >= _boundary_price_delta():
            return True
    return False


def _is_conflict(features: H6DecisionFeatures) -> bool:
    return features.has_evidence_conflict or features.counter_evidence_count > 0


def _is_uncertainty(features: H6DecisionFeatures) -> bool:
    return features.raw_uncertainty == "high"


def _is_material(features: H6DecisionFeatures) -> bool:
    return features.held and features.weight_pct >= _material_weight_threshold()


def _is_exploration(features: H6DecisionFeatures) -> bool:
    return features.roster_reason in _EXPLORATORY_ROSTER_REASONS


def _primary_reason(features: H6DecisionFeatures) -> H6SelectionReason:
    """Stable priority: invalidation → conflict → boundary → uncertainty → material → exploration."""
    if features.invalidation_risk:
        return H6SelectionReason.INVALIDATION_RISK
    if _is_conflict(features):
        return H6SelectionReason.CONFLICT
    if _is_decision_boundary(features):
        return H6SelectionReason.DECISION_BOUNDARY
    if _is_uncertainty(features):
        return H6SelectionReason.UNCERTAINTY
    if _is_material(features):
        return H6SelectionReason.MATERIAL
    if _is_exploration(features):
        return H6SelectionReason.EXPLORATION
    return H6SelectionReason.LOW_VALUE_CARRY


def _budget_for(reason: H6SelectionReason) -> H6Budget:
    if reason is H6SelectionReason.LOW_VALUE_CARRY:
        return H6Budget(max_provider_calls=0, min_rounds=0, estimated_rounds=0)
    # Selected success always meets the two-round adversarial floor (#945 / WP11.3).
    return H6Budget(max_provider_calls=4, min_rounds=2, estimated_rounds=2)


def select_h6(
    features: H6DecisionFeatures,
    *,
    mode: H6SelectionMode | None = None,
    actuated: bool | None = None,
) -> H6Selection:
    """Deterministic H6 selection — no LLM, no H4 roster mutation."""
    resolved_mode = mode if mode is not None else resolve_h6_selection_mode()
    reason = _primary_reason(features)
    action = H6Action.CARRY if reason is H6SelectionReason.LOW_VALUE_CARRY else H6Action.SELECT
    if actuated is None:
        # Actuation only when enforce will honor the decision.
        actuated = resolved_mode is H6SelectionMode.ENFORCE
    return H6Selection(
        ticker=features.ticker,
        action=action,
        reason=reason,
        features=features,
        budget=_budget_for(reason),
        mode=resolved_mode,
        actuated=actuated,
    )


def incumbent_fallback_selection(
    features: H6DecisionFeatures,
    *,
    mode: H6SelectionMode | None = None,
) -> H6Selection:
    """Typed provenance when selection fails — still run full incumbent H6."""
    resolved_mode = mode if mode is not None else resolve_h6_selection_mode()
    return H6Selection(
        ticker=features.ticker,
        action=H6Action.SELECT,
        reason=H6SelectionReason.INCUMBENT_FALLBACK,
        features=features,
        budget=H6Budget(max_provider_calls=4, min_rounds=2, estimated_rounds=2),
        mode=resolved_mode,
        actuated=False,
    )


def _forecast_terms_blob(analyst: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = analyst.get("forecast_assessment")
    if isinstance(raw, Mapping):
        terms = raw.get("terms") if "terms" in raw else raw
        if isinstance(terms, Mapping):
            return terms
        return raw
    forecast_terms = analyst.get("forecast_terms")
    if isinstance(forecast_terms, Mapping):
        return forecast_terms
    return None


def build_h6_decision_features(
    *,
    ticker: str,
    roster_reason: str,
    held: bool,
    weight_pct: float,
    analyst: Mapping[str, Any],
    prior_analyst: Mapping[str, Any] | None = None,
    price_delta: float | None = None,
    evidence_bundle_id: str | None = None,
    has_evidence_conflict: bool = False,
    invalidation_risk: bool = False,
) -> H6DecisionFeatures:
    """Assemble features from H5/H4/book state (selection path only)."""
    stance = str(analyst.get("stance") or "hold").strip().lower() or "hold"
    prior_stance: str | None = None
    if isinstance(prior_analyst, Mapping) and prior_analyst:
        prior_stance = str(prior_analyst.get("stance") or "").strip().lower() or None
    stance_changed = bool(prior_stance and prior_stance != stance)

    conviction = 0
    raw_conv = analyst.get("conviction_score")
    if raw_conv is not None:
        try:
            conviction = int(raw_conv)
        except (TypeError, ValueError):
            conviction = 0
    conviction = max(-5, min(5, conviction))

    terms = _forecast_terms_blob(analyst)
    uncertainty: RawUncertaintyLabel | None = None
    counter_count = 0
    if terms is not None:
        raw_u = str(terms.get("raw_uncertainty") or "").strip().lower()
        if raw_u in {"low", "medium", "high"}:
            uncertainty = raw_u  # type: ignore[assignment]
        counters = terms.get("counter_evidence_ids")
        if isinstance(counters, (list, tuple)):
            counter_count = len(counters)
        # Invalidation rules present + directional move ≈ risk signal when flagged.
        rules = terms.get("invalidation_rules")
        if not invalidation_risk and isinstance(rules, (list, tuple)) and rules:
            # Do not auto-fire on rules alone — caller may set invalidation_risk.
            pass

    reason = str(roster_reason or "other").strip().lower()
    if reason not in {"thesis_mapped", "technical", "held", "momentum", "other"}:
        reason = "other"

    delta_abs: float | None = None
    if price_delta is not None:
        try:
            delta_abs = abs(float(price_delta))
        except (TypeError, ValueError):
            delta_abs = None

    return H6DecisionFeatures(
        ticker=ticker,
        roster_reason=reason,  # type: ignore[arg-type]
        held=held,
        weight_pct=max(0.0, float(weight_pct or 0.0)),
        stance=stance,
        prior_stance=prior_stance,
        conviction_score=conviction,
        raw_uncertainty=uncertainty,
        has_evidence_conflict=has_evidence_conflict,
        counter_evidence_count=counter_count,
        invalidation_risk=invalidation_risk,
        evidence_bundle_id=evidence_bundle_id,
        price_delta_abs=delta_abs,
        stance_changed=stance_changed,
    )


# Keys that must never appear in H6 provider phase_inputs (blinding / anti-leak).
H6_SELECTION_PROMPT_FORBIDDEN_KEYS = frozenset(
    {
        "weight_pct",
        "materiality",
        "material_weight",
        "h6_selection",
        "selection_features",
        "decision_features",
        "portfolio_materiality",
    }
)


def assert_no_materiality_in_prompt(phase_inputs: Mapping[str, Any]) -> None:
    """Hard guard: selection materiality features never enter provider prompts."""
    leaked = H6_SELECTION_PROMPT_FORBIDDEN_KEYS.intersection(phase_inputs)
    if leaked:
        raise ValueError(f"H6 prompt must not include selection materiality keys: {sorted(leaked)}")


__all__ = [
    "H6_SELECTION_PROMPT_FORBIDDEN_KEYS",
    "OLYMPUS_H6_SELECTION_MODE_ENV",
    "H6Action",
    "H6Budget",
    "H6DecisionFeatures",
    "H6Selection",
    "H6SelectionMode",
    "H6SelectionReason",
    "assert_no_materiality_in_prompt",
    "build_h6_decision_features",
    "incumbent_fallback_selection",
    "resolve_h6_selection_mode",
    "select_h6",
]
