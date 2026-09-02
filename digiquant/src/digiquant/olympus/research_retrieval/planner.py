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

WP13.1 (#2918) adds versioned :class:`ResearchAttentionPolicy`, five attention
modes, and :func:`plan_research_attention` for pre-provider routing. Runtime
Atlas/Hermes wiring is WP13.3/13.4 — this module exposes the policy + planner API only.

WP13.2 (#2922) adds persistence contracts consumed by
:class:`~digiquant.olympus.research_retrieval.store.AttentionStore` — storage
only; no Atlas/Hermes activation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Annotated,
    Any,
    Literal,
    Mapping,
    Sequence,
    TypeAlias,
)
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.olympus.envcompat import (
    H6_BOUNDARY_PRICE_DELTA,
    H6_MATERIAL_WEIGHT_PCT,
    H6_SELECTION_MODE,
    RESEARCH_POLICY_PATH,
    env_lookup,
)
from digiquant.olympus.temporal import require_utc_datetime

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
    raw = env_lookup(H6_SELECTION_MODE, default="shadow").strip().lower()
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
    raw = env_lookup(H6_MATERIAL_WEIGHT_PCT).strip()
    if not raw:
        return _DEFAULT_MATERIAL_WEIGHT_PCT
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_MATERIAL_WEIGHT_PCT


def _boundary_price_delta() -> float:
    raw = env_lookup(H6_BOUNDARY_PRICE_DELTA).strip()
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


# ---------------------------------------------------------------------------
# WP13.1 — versioned research attention policy (#2918)
# ---------------------------------------------------------------------------

OLYMPUS_RESEARCH_POLICY_ENV = "OLYMPUS_RESEARCH_POLICY_PATH"
_ATTENTION_PLAN_NS = uuid5(NAMESPACE_URL, "digithings.olympus.research_attention_plan")
_ATTENTION_DECISION_NS = uuid5(NAMESPACE_URL, "digithings.olympus.research_attention_decision")
_ATTENTION_EVALUATION_NS = uuid5(NAMESPACE_URL, "digithings.olympus.research_attention_evaluation")
_TriageMode: TypeAlias = Literal["quiet", "stale", "active"]


class AttentionMode(StrEnum):
    """Five pre-provider attention modes (Phase 3 planner contract)."""

    CARRY = "carry"
    METRIC_PATCH = "metric_patch"
    SECTION_PATCH = "section_patch"
    CHALLENGE = "challenge"
    DEEP_REFRESH = "deep_refresh"


class AttentionRolloutMode(StrEnum):
    """Rollout knob for research attention planner (off|shadow|enforce)."""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class AttentionReason(StrEnum):
    """Stable attention reason codes — one primary per decision (metric gate)."""

    INVALIDATION_RISK = "invalidation_risk"
    CONFLICT = "conflict"
    DECISION_BOUNDARY = "decision_boundary"
    UNCERTAINTY = "uncertainty"
    MATERIAL = "material"
    EXPLORATION = "exploration"
    FORCE_FULL = "force_full"
    STALE_CONTENT = "stale_content"
    STRUCTURED_DELTA = "structured_delta"
    TRIAGE_STALE = "triage_stale"
    TRIAGE_QUIET = "triage_quiet"
    NO_PRIOR = "no_prior"
    LOW_VALUE_CARRY = "low_value_carry"


class AttentionTargetKind(StrEnum):
    ARTIFACT = "artifact"
    TICKER = "ticker"


class AttentionBudgetEstimate(H6PlannerModel):
    """Estimated provider/search/token budget for one attention decision."""

    provider_calls: int = Field(ge=0)
    searches: int = Field(ge=0)
    uncached_tokens: int = Field(ge=0)
    min_h6_rounds: int = Field(default=0, ge=0)


class PolicyThresholds(H6PlannerModel):
    material_weight_pct: float = Field(ge=0.0, allow_inf_nan=False)
    boundary_price_delta: float = Field(ge=0.0, allow_inf_nan=False)
    boundary_conviction: int = Field(ge=0)
    stale_days_full: int = Field(ge=0)


class PolicyExploration(H6PlannerModel):
    min_reserved_slots: int = Field(ge=0)


class PolicySessionBudget(H6PlannerModel):
    max_provider_calls: int = Field(ge=0)
    max_searches: int = Field(ge=0)
    max_uncached_tokens: int = Field(ge=0)


class ResearchAttentionPolicy(H6PlannerModel):
    """Versioned YAML policy with content-addressed hash."""

    schema_version: int = Field(ge=1)
    policy_version: NonEmptyStr
    content_hash: NonEmptyStr
    reason_priority: tuple[AttentionReason, ...]
    thresholds: PolicyThresholds
    exploration: PolicyExploration
    session_budget: PolicySessionBudget
    mode_budgets: dict[AttentionMode, AttentionBudgetEstimate]

    @field_validator("reason_priority", mode="before")
    @classmethod
    def _coerce_reason_priority(cls, value: object) -> tuple[AttentionReason, ...]:
        if not isinstance(value, (list, tuple)):
            return value  # type: ignore[return-value]
        return tuple(AttentionReason(str(item)) for item in value)

    @field_validator("mode_budgets", mode="before")
    @classmethod
    def _coerce_mode_budgets(cls, value: object) -> dict[AttentionMode, AttentionBudgetEstimate]:
        if not isinstance(value, Mapping):
            return value  # type: ignore[return-value]
        out: dict[AttentionMode, AttentionBudgetEstimate] = {}
        for key, raw in value.items():
            mode = AttentionMode(str(key))
            if isinstance(raw, AttentionBudgetEstimate):
                out[mode] = raw
            elif isinstance(raw, Mapping):
                out[mode] = AttentionBudgetEstimate.model_validate(raw)
            else:
                raise TypeError(f"mode_budgets[{key!r}] must be a mapping")
        return out


class AttentionFeatures(H6PlannerModel):
    """Structured inputs for deterministic attention routing."""

    target_kind: AttentionTargetKind
    target_key: NonEmptyStr
    state_version_id: str | None = None
    h6: H6DecisionFeatures | None = None
    has_prior: bool = False
    force_full_rewrite: bool = False
    triage_mode: _TriageMode | None = None
    has_structured_delta: bool = False
    staleness_days: int | None = Field(default=None, ge=0)
    exploration_slot: bool = False

    @field_validator("target_key")
    @classmethod
    def _normalize_target_key(cls, value: str) -> str:
        cleaned = value.strip()
        if ":" in cleaned:
            kind, ident = cleaned.split(":", 1)
            return f"{kind.strip().lower()}:{ident.strip()}"
        return cleaned.upper()

    @model_validator(mode="after")
    def _ticker_requires_h6(self) -> AttentionFeatures:
        if self.target_kind is AttentionTargetKind.TICKER and self.h6 is None:
            raise ValueError("ticker AttentionFeatures must include h6 decision features")
        if self.target_kind is AttentionTargetKind.TICKER and self.h6 is not None:
            if self.h6.ticker != self.target_key:
                raise ValueError("h6.ticker must match target_key for ticker targets")
        return self


class AttentionDecision(H6PlannerModel):
    """One pre-provider attention routing outcome."""

    target_key: NonEmptyStr
    mode: AttentionMode
    reason: AttentionReason
    reasons: tuple[AttentionReason, ...] = Field(..., min_length=1)
    features: AttentionFeatures
    budget: AttentionBudgetEstimate
    exploration_reserved: bool = False
    actuated: bool = False

    @model_validator(mode="after")
    def _primary_reason_first(self) -> AttentionDecision:
        if self.reasons[0] is not self.reason:
            raise ValueError("reasons[0] must equal primary reason")
        return self


class AttentionPlan(H6PlannerModel):
    """Immutable research attention plan for one run under a pinned policy."""

    plan_id: UUID
    run_id: NonEmptyStr
    state_version_id: UUID | None = None
    policy_content_hash: NonEmptyStr
    rollout_mode: AttentionRolloutMode
    actuated: bool = False
    decisions: tuple[AttentionDecision, ...] = Field(default_factory=tuple)
    total_budget: AttentionBudgetEstimate
    exploration_slots_reserved: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_plan(self) -> AttentionPlan:
        if self.rollout_mode is AttentionRolloutMode.OFF and self.decisions:
            raise ValueError("rollout_mode=off must not produce decisions")
        if self.rollout_mode is AttentionRolloutMode.ENFORCE and not self.actuated:
            raise ValueError("enforce plans must set actuated=True")
        if self.rollout_mode is not AttentionRolloutMode.ENFORCE and self.actuated:
            raise ValueError("off/shadow plans must not actuate")
        expected_id = attention_plan_id(
            run_id=self.run_id,
            state_version_id=self.state_version_id,
            policy_content_hash=self.policy_content_hash,
            target_keys=tuple(d.target_key for d in self.decisions),
        )
        if self.plan_id != expected_id:
            raise ValueError("plan_id must match run/state/policy/targets")
        return self


def _canonical_policy_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def policy_content_hash(raw: Mapping[str, object]) -> str:
    """SHA-256 over canonical policy body (ordering-independent)."""
    return hashlib.sha256(_canonical_policy_json(dict(raw)).encode("utf-8")).hexdigest()


def default_research_policy_path() -> Path:
    """Default bundled policy path relative to digiquant package root."""
    return Path(__file__).resolve().parents[4] / "config" / "olympus_research_policy.yaml"


def resolve_research_policy_path() -> Path:
    override = env_lookup(RESEARCH_POLICY_PATH).strip()
    if override:
        return Path(override)
    return default_research_policy_path()


@lru_cache(maxsize=4)
def load_research_attention_policy(path: Path | None = None) -> ResearchAttentionPolicy:
    """Load and validate the versioned research attention policy YAML."""
    resolved = path if path is not None else resolve_research_policy_path()
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"policy YAML must be a mapping: {resolved}")
    digest = policy_content_hash(raw)
    body = dict(raw)
    body["content_hash"] = digest
    return ResearchAttentionPolicy.model_validate(body)


def _reason_rank(policy: ResearchAttentionPolicy, reason: AttentionReason) -> int:
    try:
        return policy.reason_priority.index(reason)
    except ValueError:
        return len(policy.reason_priority)


def _pick_primary_reason(
    candidates: Sequence[AttentionReason],
    policy: ResearchAttentionPolicy,
) -> AttentionReason:
    if not candidates:
        return AttentionReason.LOW_VALUE_CARRY
    return min(candidates, key=lambda item: _reason_rank(policy, item))


def _stable_reasons(
    candidates: Sequence[AttentionReason],
    primary: AttentionReason,
) -> tuple[AttentionReason, ...]:
    ordered = sorted(set(candidates), key=lambda item: item.value)
    if primary in ordered:
        ordered.remove(primary)
    return (primary, *ordered)


def _h6_reason_to_attention(reason: H6SelectionReason) -> AttentionReason:
    return AttentionReason(reason.value)


def _thresholds_from_policy(policy: ResearchAttentionPolicy) -> PolicyThresholds:
    return policy.thresholds


def _evaluate_ticker_reasons(
    features: AttentionFeatures,
    policy: ResearchAttentionPolicy,
) -> list[AttentionReason]:
    assert features.h6 is not None
    h6 = features.h6
    thresholds = _thresholds_from_policy(policy)
    reasons: list[AttentionReason] = []

    if features.force_full_rewrite:
        reasons.append(AttentionReason.FORCE_FULL)
    if not features.has_prior:
        reasons.append(AttentionReason.NO_PRIOR)
    if features.triage_mode == "quiet":
        reasons.append(AttentionReason.TRIAGE_QUIET)
    if features.triage_mode == "stale":
        reasons.append(AttentionReason.TRIAGE_STALE)
    if features.has_structured_delta:
        reasons.append(AttentionReason.STRUCTURED_DELTA)
    if (
        features.staleness_days is not None
        and features.staleness_days >= thresholds.stale_days_full
    ):
        reasons.append(AttentionReason.STALE_CONTENT)

    if h6.invalidation_risk:
        reasons.append(AttentionReason.INVALIDATION_RISK)
    if h6.has_evidence_conflict or h6.counter_evidence_count > 0:
        reasons.append(AttentionReason.CONFLICT)
    if h6.stance_changed:
        reasons.append(AttentionReason.DECISION_BOUNDARY)
    elif (
        h6.stance in {"buy", "sell"} and abs(h6.conviction_score) >= thresholds.boundary_conviction
    ):
        reasons.append(AttentionReason.DECISION_BOUNDARY)
    elif (
        h6.held
        and h6.price_delta_abs is not None
        and h6.price_delta_abs >= thresholds.boundary_price_delta
    ):
        reasons.append(AttentionReason.DECISION_BOUNDARY)
    if h6.raw_uncertainty == "high":
        reasons.append(AttentionReason.UNCERTAINTY)
    if h6.held and h6.weight_pct >= thresholds.material_weight_pct:
        reasons.append(AttentionReason.MATERIAL)
    if h6.roster_reason in _EXPLORATORY_ROSTER_REASONS or features.exploration_slot:
        reasons.append(AttentionReason.EXPLORATION)

    if not reasons:
        reasons.append(AttentionReason.LOW_VALUE_CARRY)
    return reasons


def _evaluate_artifact_reasons(
    features: AttentionFeatures,
    policy: ResearchAttentionPolicy,
) -> list[AttentionReason]:
    thresholds = _thresholds_from_policy(policy)
    reasons: list[AttentionReason] = []

    if features.force_full_rewrite:
        reasons.append(AttentionReason.FORCE_FULL)
    if not features.has_prior:
        reasons.append(AttentionReason.NO_PRIOR)
    if features.triage_mode == "quiet":
        reasons.append(AttentionReason.TRIAGE_QUIET)
    if features.triage_mode == "stale":
        reasons.append(AttentionReason.TRIAGE_STALE)
    if features.has_structured_delta:
        reasons.append(AttentionReason.STRUCTURED_DELTA)
    if (
        features.staleness_days is not None
        and features.staleness_days >= thresholds.stale_days_full
    ):
        reasons.append(AttentionReason.STALE_CONTENT)

    if not reasons:
        reasons.append(AttentionReason.LOW_VALUE_CARRY)
    return reasons


def _mode_for_reason(reason: AttentionReason) -> AttentionMode:
    if reason in {AttentionReason.LOW_VALUE_CARRY, AttentionReason.TRIAGE_QUIET}:
        return AttentionMode.CARRY
    if reason is AttentionReason.STRUCTURED_DELTA:
        return AttentionMode.METRIC_PATCH
    if reason in {AttentionReason.TRIAGE_STALE, AttentionReason.STALE_CONTENT}:
        return AttentionMode.SECTION_PATCH
    if reason in {
        AttentionReason.CONFLICT,
        AttentionReason.DECISION_BOUNDARY,
        AttentionReason.UNCERTAINTY,
        AttentionReason.INVALIDATION_RISK,
        AttentionReason.MATERIAL,
        AttentionReason.EXPLORATION,
    }:
        return AttentionMode.CHALLENGE
    return AttentionMode.DEEP_REFRESH


_MODE_RANK: dict[AttentionMode, int] = {
    AttentionMode.CARRY: 0,
    AttentionMode.METRIC_PATCH: 1,
    AttentionMode.SECTION_PATCH: 2,
    AttentionMode.CHALLENGE: 3,
    AttentionMode.DEEP_REFRESH: 4,
}


def _budget_for_mode(
    mode: AttentionMode, policy: ResearchAttentionPolicy
) -> AttentionBudgetEstimate:
    return policy.mode_budgets[mode]


def route_attention(
    features: AttentionFeatures,
    policy: ResearchAttentionPolicy,
    *,
    actuated: bool = False,
) -> AttentionDecision:
    """Deterministic single-target attention routing — no LLM, no graph node."""
    if features.target_kind is AttentionTargetKind.TICKER:
        candidates = _evaluate_ticker_reasons(features, policy)
    else:
        candidates = _evaluate_artifact_reasons(features, policy)
    primary = _pick_primary_reason(candidates, policy)
    mode = _mode_for_reason(primary)
    return AttentionDecision(
        target_key=features.target_key,
        mode=mode,
        reason=primary,
        reasons=_stable_reasons(candidates, primary),
        features=features,
        budget=_budget_for_mode(mode, policy),
        exploration_reserved=False,
        actuated=actuated,
    )


def sum_budget_estimates(decisions: Sequence[AttentionDecision]) -> AttentionBudgetEstimate:
    """Aggregate call/search/token estimates across decisions."""
    return AttentionBudgetEstimate(
        provider_calls=sum(item.budget.provider_calls for item in decisions),
        searches=sum(item.budget.searches for item in decisions),
        uncached_tokens=sum(item.budget.uncached_tokens for item in decisions),
        min_h6_rounds=max((item.budget.min_h6_rounds for item in decisions), default=0),
    )


def _downgrade_mode(mode: AttentionMode) -> AttentionMode:
    order = (
        AttentionMode.DEEP_REFRESH,
        AttentionMode.CHALLENGE,
        AttentionMode.SECTION_PATCH,
        AttentionMode.METRIC_PATCH,
        AttentionMode.CARRY,
    )
    idx = order.index(mode)
    if idx + 1 >= len(order):
        return AttentionMode.CARRY
    return order[idx + 1]


def apply_session_budget(
    decisions: Sequence[AttentionDecision],
    policy: ResearchAttentionPolicy,
) -> tuple[tuple[AttentionDecision, ...], AttentionBudgetEstimate]:
    """Trim decisions to session budget while preserving exploration reservations."""
    working = list(decisions)
    total = sum_budget_estimates(working)

    def _within_budget(budget: AttentionBudgetEstimate) -> bool:
        return (
            budget.provider_calls <= policy.session_budget.max_provider_calls
            and budget.searches <= policy.session_budget.max_searches
            and budget.uncached_tokens <= policy.session_budget.max_uncached_tokens
        )

    # Ensure minimum exploration slots survive before trimming others.
    exploration_candidates = [
        d
        for d in working
        if d.features.exploration_slot
        and d.mode in {AttentionMode.CHALLENGE, AttentionMode.DEEP_REFRESH}
    ]
    must_keep = set(
        d.target_key
        for d in sorted(
            exploration_candidates,
            key=lambda item: (-_MODE_RANK[item.mode], item.target_key),
        )[: policy.exploration.min_reserved_slots]
    )
    for idx, decision in enumerate(working):
        if decision.target_key in must_keep:
            working[idx] = decision.model_copy(update={"exploration_reserved": True})
    protected = must_keep

    while working and not _within_budget(total):
        trimmable = [
            d
            for d in working
            if d.target_key not in protected or d.mode is AttentionMode.DEEP_REFRESH
        ]
        if not trimmable:
            break
        victim = max(trimmable, key=lambda item: (_MODE_RANK[item.mode], item.target_key))
        if victim.mode is AttentionMode.CARRY:
            working.remove(victim)
        else:
            new_mode = _downgrade_mode(victim.mode)
            idx = working.index(victim)
            working[idx] = victim.model_copy(
                update={
                    "mode": new_mode,
                    "budget": _budget_for_mode(new_mode, policy),
                    "exploration_reserved": victim.exploration_reserved
                    and new_mode in {AttentionMode.CHALLENGE, AttentionMode.DEEP_REFRESH},
                }
            )
        total = sum_budget_estimates(working)

    return tuple(working), total


def attention_plan_id(
    *,
    run_id: str,
    state_version_id: UUID | None,
    policy_content_hash: str,
    target_keys: Sequence[str],
) -> UUID:
    """Deterministic plan id for identical run/state/policy/target set."""
    state_part = "" if state_version_id is None else state_version_id.hex
    targets = ",".join(sorted(target_keys))
    return uuid5(
        _ATTENTION_PLAN_NS,
        f"{run_id}:{state_part}:{policy_content_hash}:{targets}",
    )


def plan_research_attention(
    *,
    run_id: str,
    state_version_id: UUID | None,
    features: Sequence[AttentionFeatures],
    policy: ResearchAttentionPolicy | None = None,
    rollout_mode: AttentionRolloutMode | None = None,
) -> AttentionPlan:
    """Build a research attention plan — API only; no Atlas/Hermes wiring (WP13.3+)."""
    resolved_policy = policy if policy is not None else load_research_attention_policy()
    resolved_rollout = rollout_mode if rollout_mode is not None else AttentionRolloutMode.SHADOW

    if resolved_rollout is AttentionRolloutMode.OFF:
        zero = _budget_for_mode(AttentionMode.CARRY, resolved_policy)
        return AttentionPlan(
            plan_id=attention_plan_id(
                run_id=run_id,
                state_version_id=state_version_id,
                policy_content_hash=resolved_policy.content_hash,
                target_keys=tuple(),
            ),
            run_id=run_id,
            state_version_id=state_version_id,
            policy_content_hash=resolved_policy.content_hash,
            rollout_mode=AttentionRolloutMode.OFF,
            actuated=False,
            decisions=(),
            total_budget=zero,
            exploration_slots_reserved=0,
        )

    actuated = resolved_rollout is AttentionRolloutMode.ENFORCE
    raw_decisions = [route_attention(item, resolved_policy, actuated=actuated) for item in features]
    decisions, total = apply_session_budget(raw_decisions, resolved_policy)
    reserved = sum(
        1
        for d in decisions
        if d.exploration_reserved
        and d.mode in {AttentionMode.CHALLENGE, AttentionMode.DEEP_REFRESH}
    )
    return AttentionPlan(
        plan_id=attention_plan_id(
            run_id=run_id,
            state_version_id=state_version_id,
            policy_content_hash=resolved_policy.content_hash,
            target_keys=tuple(d.target_key for d in decisions),
        ),
        run_id=run_id,
        state_version_id=state_version_id,
        policy_content_hash=resolved_policy.content_hash,
        rollout_mode=resolved_rollout,
        actuated=actuated,
        decisions=decisions,
        total_budget=total,
        exploration_slots_reserved=reserved,
    )


def attention_decision_id(*, plan_id: UUID, target_key: str) -> UUID:
    """Deterministic decision row id for one plan target."""
    cleaned = target_key.strip()
    if not cleaned:
        raise ValueError("target_key is required")
    return uuid5(_ATTENTION_DECISION_NS, f"{plan_id.hex}:{cleaned}")


def attention_evaluation_id(*, plan_id: UUID, reconciliation_digest: str) -> UUID:
    """Deterministic evaluation id from plan + reconciliation body hash."""
    if not reconciliation_digest.strip():
        raise ValueError("reconciliation_digest is required")
    return uuid5(
        _ATTENTION_EVALUATION_NS,
        f"{plan_id.hex}:{reconciliation_digest.strip()}",
    )


class PersistedAttentionPlan(H6PlannerModel):
    """Stored attention plan envelope with run/attempt provenance."""

    plan: AttentionPlan
    attempt_id: NonEmptyStr
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_recorded_at(self) -> PersistedAttentionPlan:
        require_utc_datetime(self.recorded_at, field_name="recorded_at")
        return self


class PersistedAttentionDecision(H6PlannerModel):
    """One persisted attention decision linked to a plan and policy/state lineage."""

    decision_id: UUID
    plan_id: UUID
    decision: AttentionDecision
    run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    state_version_id: UUID | None = None
    policy_content_hash: NonEmptyStr
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_persisted_decision(self) -> PersistedAttentionDecision:
        require_utc_datetime(self.recorded_at, field_name="recorded_at")
        expected_id = attention_decision_id(
            plan_id=self.plan_id,
            target_key=self.decision.target_key,
        )
        if self.decision_id != expected_id:
            raise ValueError("decision_id must match plan_id+target_key")
        return self


class AttentionContextManifest(H6PlannerModel):
    """Append-only context manifest row (WP14 compiler will populate; storage only here)."""

    manifest_id: UUID
    plan_id: UUID
    decision_id: UUID | None = None
    run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    role: NonEmptyStr
    state_version_id: UUID | None = None
    content_hash: NonEmptyStr
    included_entity_ids: tuple[str, ...] = Field(default_factory=tuple)
    omission_reasons: tuple[str, ...] = Field(default_factory=tuple)
    recorded_at: AwareDatetime

    @field_validator("included_entity_ids", "omission_reasons", mode="before")
    @classmethod
    def _coerce_string_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("included_entity_ids")
    @classmethod
    def _canonicalize_included(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(item.strip() for item in value if item.strip()))

    @field_validator("omission_reasons")
    @classmethod
    def _canonicalize_omissions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def _validate_manifest(self) -> AttentionContextManifest:
        require_utc_datetime(self.recorded_at, field_name="recorded_at")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must be a 64-char SHA-256 hex digest")
        return self


class AttentionDecisionReconciliation(H6PlannerModel):
    """Planned vs actual resource linkage for one decision (WP13.5/WP16 input)."""

    decision_id: UUID
    target_key: NonEmptyStr
    mode: AttentionMode
    reason: AttentionReason
    planned_budget: AttentionBudgetEstimate
    actual_budget: AttentionBudgetEstimate
    provider_attempt_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    complete: bool

    @field_validator("provider_attempt_ids", mode="before")
    @classmethod
    def _coerce_attempt_ids(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class AttentionPolicyEvaluation(H6PlannerModel):
    """Shadow/enforced policy evaluation with per-decision reconciliation."""

    evaluation_id: UUID
    plan_id: UUID
    run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    rollout_mode: AttentionRolloutMode
    complete: bool
    planned_total: AttentionBudgetEstimate
    actual_total: AttentionBudgetEstimate
    decision_reconciliations: tuple[AttentionDecisionReconciliation, ...] = Field(
        default_factory=tuple
    )
    recorded_at: AwareDatetime

    @field_validator("decision_reconciliations", mode="before")
    @classmethod
    def _coerce_reconciliations(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_evaluation(self) -> AttentionPolicyEvaluation:
        require_utc_datetime(self.recorded_at, field_name="recorded_at")
        return self


def h6_selection_to_attention_decision(
    selection: H6Selection,
    policy: ResearchAttentionPolicy,
    *,
    actuated: bool = False,
) -> AttentionDecision:
    """Bridge WP11.3 H6 selection into WP13.1 attention vocabulary."""
    features = AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=selection.ticker,
        h6=selection.features,
        has_prior=True,
        exploration_slot=selection.reason is H6SelectionReason.EXPLORATION,
    )
    if selection.action is H6Action.CARRY:
        primary = AttentionReason.LOW_VALUE_CARRY
        mode = AttentionMode.CARRY
        budget = _budget_for_mode(mode, policy)
    else:
        primary = _h6_reason_to_attention(selection.reason)
        mode = AttentionMode.CHALLENGE
        budget = _budget_for_mode(mode, policy)
    return AttentionDecision(
        target_key=features.target_key,
        mode=mode,
        reason=primary,
        reasons=(primary,),
        features=features,
        budget=budget,
        exploration_reserved=False,
        actuated=actuated,
    )


__all__ = [
    "AttentionBudgetEstimate",
    "AttentionContextManifest",
    "AttentionDecision",
    "AttentionDecisionReconciliation",
    "AttentionFeatures",
    "AttentionMode",
    "AttentionPlan",
    "AttentionPolicyEvaluation",
    "AttentionReason",
    "AttentionRolloutMode",
    "AttentionTargetKind",
    "PersistedAttentionDecision",
    "PersistedAttentionPlan",
    "H6_SELECTION_PROMPT_FORBIDDEN_KEYS",
    "OLYMPUS_H6_SELECTION_MODE_ENV",
    "OLYMPUS_RESEARCH_POLICY_ENV",
    "PolicyExploration",
    "PolicySessionBudget",
    "PolicyThresholds",
    "ResearchAttentionPolicy",
    "H6Action",
    "H6Budget",
    "H6DecisionFeatures",
    "H6Selection",
    "H6SelectionMode",
    "H6SelectionReason",
    "apply_session_budget",
    "assert_no_materiality_in_prompt",
    "attention_decision_id",
    "attention_evaluation_id",
    "attention_plan_id",
    "build_h6_decision_features",
    "default_research_policy_path",
    "h6_selection_to_attention_decision",
    "incumbent_fallback_selection",
    "load_research_attention_policy",
    "plan_research_attention",
    "policy_content_hash",
    "resolve_h6_selection_mode",
    "resolve_research_policy_path",
    "route_attention",
    "select_h6",
    "sum_budget_estimates",
]
