"""Strict typed forecast contracts for Hermes H5+ (#2637 / WP4.2).

Separates LLM-proposed economics (:class:`ForecastTerms`) from deterministic
identity and audit metadata (:class:`ForecastAssessment`). Legacy
``conviction_score`` / ``price_targets`` on :class:`~.analyst.AnalystPayload`
remain for compatibility and **must never** be used to synthesize these terms.

Style mirrors :mod:`digiquant.olympus.hermes.models.portfolio_ledger`: frozen,
``extra="forbid"``, UTC-only aware datetimes, Decimal economics, UUID5
idempotent identity.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import (  # score:allow untyped any — nested LLM wrapper payloads
    Annotated,
    Any,
    TypeAlias,
)
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Stable namespace for ForecastAssessment UUID5 identity. Do not change — existing
# prospective IDs would diverge if this literal moves.
_FORECAST_ASSESSMENT_ID_NAMESPACE = UUID("a4c8e91b-2d7f-5e3a-9b06-1f8c4d7e2a90")
# Stable namespace for ForecastAmendment UUID5 identity (WP4.4).
_FORECAST_AMENDMENT_ID_NAMESPACE = UUID("b5d9f02c-3e80-6f4b-ac17-2a9d5e8f3b01")

Probability: TypeAlias = Annotated[
    Decimal, Field(ge=0, le=1, allow_inf_nan=False, max_digits=16, decimal_places=8)
]
ReturnFraction: TypeAlias = Annotated[
    Decimal, Field(allow_inf_nan=False, max_digits=16, decimal_places=8)
]
PositiveSessions: TypeAlias = Annotated[int, Field(gt=0)]
NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
PositivePrice: TypeAlias = Annotated[
    Decimal, Field(gt=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]


class RawUncertainty(StrEnum):
    """Coarse pre-calibration uncertainty label on raw scenario terms."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriceAnchorStatus(StrEnum):
    """Whether an assessment carries an observed price or a typed gap."""

    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"


class ForecastModel(BaseModel):
    """Strict immutable base for every forecast contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastTerms(ForecastModel):
    """Economic scenario terms owned by H5 (immutable once materialized).

    Horizons are **trading sessions**, not calendar days. Scenario returns are
    ordered bear ≤ base ≤ bull; scenario probabilities are non-negative and
    sum exactly to one.
    """

    horizon_sessions: PositiveSessions
    half_life_sessions: PositiveSessions
    bear_return: ReturnFraction
    base_return: ReturnFraction
    bull_return: ReturnFraction
    bear_probability: Probability
    base_probability: Probability
    bull_probability: Probability
    thesis_valid_probability: Probability
    raw_uncertainty: RawUncertainty
    evidence_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    counter_evidence_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    invalidation_rules: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("evidence_ids", "counter_evidence_ids", mode="before")
    @classmethod
    def _coerce_id_sequence(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("assumptions", "invalidation_rules", mode="before")
    @classmethod
    def _coerce_str_sequence(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_ids", "counter_evidence_ids")
    @classmethod
    def _reject_blank_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not item.strip():
                raise ValueError("evidence IDs must be non-empty strings")
        return value

    @model_validator(mode="after")
    def _validate_economics(self) -> ForecastTerms:
        if not (self.bear_return <= self.base_return <= self.bull_return):
            raise ValueError("scenario returns must be ordered bear ≤ base ≤ bull")
        prob_sum = self.bear_probability + self.base_probability + self.bull_probability
        if prob_sum != Decimal("1"):
            raise ValueError(
                f"scenario probabilities must sum to 1 (got {prob_sum}); "
                "do not renormalize silently"
            )
        return self

    def scenario_mean_return(self) -> Decimal:
        """Raw probability-weighted expected return (pre-calibration)."""
        return (
            self.bear_probability * self.bear_return
            + self.base_probability * self.base_return
            + self.bull_probability * self.bull_return
        )


_FORECAST_WRAPPER_KEYS = frozenset({"terms", "amendment", "forecast_amendment"})
_ECONOMICS_KEYS = frozenset(
    {
        "bear_return",
        "base_return",
        "bull_return",
        "bear_probability",
        "base_probability",
        "bull_probability",
    }
)


def unwrap_nested_forecast_terms(
    raw: dict[str, Any],
    *,
    base: ForecastTerms | None = None,
) -> dict[str, Any]:
    """Unwrap one ``{terms|amendment|forecast_amendment: {...}}`` wrapper (#3299).

    Cheap models often emit a nested object instead of a flat ``ForecastTerms``.
    When the *only* keys are those wrappers, peel one level. If scenario
    economics are present but ``horizon_sessions`` / ``half_life_sessions`` are
    missing, copy those two fields from the H5 base (complete replacement of
    the rest). Objects with no scenario returns are left as-is so validation
    still rejects them (e.g. a ``catalyst_within_horizon`` blob).
    """
    data: dict[str, Any] = dict(raw)
    if data and set(data) <= _FORECAST_WRAPPER_KEYS:
        nested_key = next(
            (
                key
                for key in ("terms", "amendment", "forecast_amendment")
                if isinstance(data.get(key), dict)
            ),
            None,
        )
        if nested_key is not None:
            data = dict(data[nested_key])

    has_economics = bool(_ECONOMICS_KEYS & set(data))
    if has_economics and base is not None:
        if data.get("horizon_sessions") in (None, ""):
            data["horizon_sessions"] = base.horizon_sessions
        if data.get("half_life_sessions") in (None, ""):
            data["half_life_sessions"] = base.half_life_sessions
    return data


class PriceAnchor(ForecastModel):
    """Observed mark used as the forecast's economic anchor, or typed absence."""

    status: PriceAnchorStatus
    price: PositivePrice | None = None
    observed_at: AwareDatetime | None = None
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _xor_observed_vs_unavailable(self) -> PriceAnchor:
        if self.status is PriceAnchorStatus.OBSERVED:
            if self.price is None or self.observed_at is None:
                raise ValueError("observed price_anchor requires price and observed_at")
            if self.unavailable_reason is not None:
                raise ValueError("observed price_anchor cannot carry unavailable_reason")
            if self.observed_at.utcoffset() != timedelta(0):
                raise ValueError("price_anchor.observed_at must be UTC")
        else:
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("unavailable price_anchor requires unavailable_reason")
            if self.price is not None or self.observed_at is not None:
                raise ValueError("unavailable price_anchor cannot carry price/observed_at")
        return self


def forecast_terms_content_hash(terms: ForecastTerms) -> str:
    """SHA-256 over canonical JSON of economic terms (identity input)."""
    payload = terms.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def forecast_assessment_id(*, ticker: str, source_run_id: str, content_hash: str) -> UUID:
    """Deterministic UUID5 for a base forecast assessment.

    Identity keys on ticker + run + terms hash so retries with identical content
    collide idempotently; divergent content under a forced ID fails validation.
    """
    if not ticker.strip() or not source_run_id.strip() or not content_hash.strip():
        raise ValueError("ticker, source_run_id, and content_hash are required for forecast_id")
    return uuid5(
        _FORECAST_ASSESSMENT_ID_NAMESPACE,
        f"{ticker.strip().upper()}:{source_run_id.strip()}:{content_hash.strip()}",
    )


class ForecastAssessment(ForecastModel):
    """Immutable base forecast with provenance, anchor, and content identity."""

    forecast_id: UUID
    ticker: NonEmptyId
    terms: ForecastTerms
    source_run_id: NonEmptyId
    provider_invocation_id: NonEmptyId
    prompt_version: NonEmptyId
    artifact_version: NonEmptyId
    price_anchor: PriceAnchor
    effective_at: AwareDatetime
    known_at: AwareDatetime
    content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_identity_and_time(self) -> ForecastAssessment:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")

        expected_hash = forecast_terms_content_hash(self.terms)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ForecastTerms digest")

        expected_id = forecast_assessment_id(
            ticker=self.ticker,
            source_run_id=self.source_run_id,
            content_hash=self.content_hash,
        )
        if self.forecast_id != expected_id:
            raise ValueError(
                "forecast_id must be the UUID5 of ticker+source_run_id+content_hash "
                "(same-ID/different-hash conflicts are rejected)"
            )
        return self


class AmendmentOutcome(StrEnum):
    """How an H6 amendment attempt resolved relative to the immutable base."""

    ACCEPTED = "accepted"
    REJECTED = "amendment_rejected"
    LLM_FAILURE = "llm_failure"
    NONE = "none"


class EffectiveSource(StrEnum):
    """Which artifact supplies the effective numerical terms."""

    BASE = "base"
    AMENDMENT = "amendment"


def forecast_amendment_id(
    *,
    base_forecast_id: UUID,
    source_run_id: str,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for an H6 amendment of a base assessment."""
    if not source_run_id.strip() or not content_hash.strip():
        raise ValueError("source_run_id and content_hash are required for amendment_id")
    return uuid5(
        _FORECAST_AMENDMENT_ID_NAMESPACE,
        f"{base_forecast_id}:{source_run_id.strip()}:{content_hash.strip()}",
    )


class ForecastAmendment(ForecastModel):
    """Immutable H6 replacement terms that supersede a base without rewriting it.

    ``terms`` is a complete replacement set (never a partial patch). Lineage points
    at the immutable base ``forecast_id`` and optionally a prior amendment that this
    one supersedes.
    """

    amendment_id: UUID
    base_forecast_id: UUID
    supersedes_amendment_id: UUID | None = None
    ticker: NonEmptyId
    terms: ForecastTerms
    reason: NonEmptyId
    new_evidence_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    contradiction_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    source_run_id: NonEmptyId
    provider_invocation_id: NonEmptyId
    effective_at: AwareDatetime
    known_at: AwareDatetime
    content_hash: NonEmptyId

    @field_validator("new_evidence_ids", "contradiction_ids", mode="before")
    @classmethod
    def _coerce_amendment_id_sequence(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("new_evidence_ids", "contradiction_ids")
    @classmethod
    def _reject_blank_amendment_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not item.strip():
                raise ValueError("evidence IDs must be non-empty strings")
        return value

    @model_validator(mode="after")
    def _validate_amendment_identity(self) -> ForecastAmendment:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")

        expected_hash = forecast_terms_content_hash(self.terms)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ForecastTerms digest")

        expected_id = forecast_amendment_id(
            base_forecast_id=self.base_forecast_id,
            source_run_id=self.source_run_id,
            content_hash=self.content_hash,
        )
        if self.amendment_id != expected_id:
            raise ValueError(
                "amendment_id must be the UUID5 of base_forecast_id+source_run_id+content_hash"
            )
        if not self.reason.strip():
            raise ValueError("amendment reason is required")
        return self


class EffectiveForecast(ForecastModel):
    """Resolved forecast H7/H9 may reference: immutable base ± one accepted amendment."""

    effective_id: UUID
    ticker: NonEmptyId
    base_forecast_id: UUID
    amendment_id: UUID | None = None
    source: EffectiveSource
    terms: ForecastTerms
    content_hash: NonEmptyId
    amendment_outcome: AmendmentOutcome = AmendmentOutcome.NONE
    degradation_reason: NonEmptyId | None = None
    effective_at: AwareDatetime
    known_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_effective(self) -> EffectiveForecast:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")
        if self.source is EffectiveSource.AMENDMENT and self.amendment_id is None:
            raise ValueError("amendment source requires amendment_id")
        if self.source is EffectiveSource.BASE and self.amendment_id is not None:
            raise ValueError("base source cannot carry amendment_id")
        if self.content_hash != forecast_terms_content_hash(self.terms):
            raise ValueError("content_hash must match canonical ForecastTerms digest")
        return self


def materialize_forecast_amendment(
    *,
    base: ForecastAssessment,
    terms: ForecastTerms,
    reason: str,
    source_run_id: str,
    provider_invocation_id: str,
    effective_at: AwareDatetime,
    known_at: AwareDatetime,
    new_evidence_ids: tuple[str, ...] = (),
    contradiction_ids: tuple[str, ...] = (),
    supersedes_amendment_id: UUID | None = None,
) -> ForecastAmendment:
    """Build an immutable amendment of ``base`` with complete replacement terms."""
    content_hash = forecast_terms_content_hash(terms)
    return ForecastAmendment(
        amendment_id=forecast_amendment_id(
            base_forecast_id=base.forecast_id,
            source_run_id=source_run_id,
            content_hash=content_hash,
        ),
        base_forecast_id=base.forecast_id,
        supersedes_amendment_id=supersedes_amendment_id,
        ticker=base.ticker,
        terms=terms,
        reason=reason,
        new_evidence_ids=new_evidence_ids,
        contradiction_ids=contradiction_ids,
        source_run_id=source_run_id,
        provider_invocation_id=provider_invocation_id,
        effective_at=effective_at,
        known_at=known_at,
        content_hash=content_hash,
    )


def resolve_effective_forecast(
    *,
    base: ForecastAssessment,
    amendment: ForecastAmendment | None = None,
    amendment_outcome: AmendmentOutcome = AmendmentOutcome.NONE,
    degradation_reason: str | None = None,
    known_at: AwareDatetime | None = None,
) -> EffectiveForecast:
    """Select base or accepted amendment; never mutate the base assessment.

    Invalid/failed amendments keep the base as effective and record the outcome.
    """
    cutoff_known = known_at if known_at is not None else base.known_at
    if amendment is not None and amendment.base_forecast_id != base.forecast_id:
        return EffectiveForecast(
            effective_id=base.forecast_id,
            ticker=base.ticker,
            base_forecast_id=base.forecast_id,
            amendment_id=None,
            source=EffectiveSource.BASE,
            terms=base.terms,
            content_hash=base.content_hash,
            amendment_outcome=AmendmentOutcome.REJECTED,
            degradation_reason=degradation_reason or "amendment_base_mismatch",
            effective_at=base.effective_at,
            known_at=cutoff_known,
        )
    if (
        amendment is not None
        and amendment_outcome is AmendmentOutcome.ACCEPTED
        and amendment.known_at <= cutoff_known
    ):
        return EffectiveForecast(
            effective_id=amendment.amendment_id,
            ticker=base.ticker,
            base_forecast_id=base.forecast_id,
            amendment_id=amendment.amendment_id,
            source=EffectiveSource.AMENDMENT,
            terms=amendment.terms,
            content_hash=amendment.content_hash,
            amendment_outcome=AmendmentOutcome.ACCEPTED,
            degradation_reason=None,
            effective_at=amendment.effective_at,
            known_at=amendment.known_at,
        )
    outcome = amendment_outcome
    if amendment is not None and amendment.known_at > cutoff_known:
        outcome = AmendmentOutcome.REJECTED
        degradation_reason = degradation_reason or "amendment_after_knowledge_cutoff"
    elif amendment is not None and outcome is AmendmentOutcome.NONE:
        outcome = AmendmentOutcome.REJECTED
        degradation_reason = degradation_reason or "amendment_not_accepted"
    return EffectiveForecast(
        effective_id=base.forecast_id,
        ticker=base.ticker,
        base_forecast_id=base.forecast_id,
        amendment_id=None,
        source=EffectiveSource.BASE,
        terms=base.terms,
        content_hash=base.content_hash,
        amendment_outcome=outcome,
        degradation_reason=degradation_reason,
        effective_at=base.effective_at,
        known_at=cutoff_known,
    )


__all__ = [
    "AmendmentOutcome",
    "EffectiveForecast",
    "EffectiveSource",
    "ForecastAmendment",
    "ForecastAssessment",
    "ForecastModel",
    "ForecastTerms",
    "PriceAnchor",
    "PriceAnchorStatus",
    "RawUncertainty",
    "forecast_amendment_id",
    "forecast_assessment_id",
    "forecast_terms_content_hash",
    "materialize_forecast_amendment",
    "resolve_effective_forecast",
    "unwrap_nested_forecast_terms",
]
