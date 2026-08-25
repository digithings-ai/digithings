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
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# Stable namespaces for forecast UUID5 identity. Do not change — existing
# prospective IDs would diverge if these literals move.
_FORECAST_ASSESSMENT_ID_NAMESPACE = UUID("a4c8e91b-2d7f-5e3a-9b06-1f8c4d7e2a90")
_FORECAST_AMENDMENT_ID_NAMESPACE = UUID("b5d9f02c-3e80-6f4b-ac17-209d5e8f3b01")
_EFFECTIVE_FORECAST_ID_NAMESPACE = UUID("c6e0a13d-4f91-705c-bd28-31ae6f904c12")

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


class ForecastLineageDegradation(StrEnum):
    """Typed degradation on an effective forecast (never invent zeros)."""

    NONE = "none"
    AMENDMENT_REJECTED = "amendment_rejected"
    LLM_FAILURE = "llm_failure"
    FORECAST_UNAVAILABLE = "forecast_unavailable"


class EffectiveForecastSource(StrEnum):
    """Whether the effective terms come from the immutable base or an amendment."""

    BASE = "base"
    AMENDMENT = "amendment"


def forecast_amendment_id(
    *,
    base_forecast_id: UUID,
    source_run_id: str,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for an H6 amendment (complete term replacement)."""
    if not source_run_id.strip() or not content_hash.strip():
        raise ValueError("source_run_id and content_hash are required for amendment_id")
    return uuid5(
        _FORECAST_AMENDMENT_ID_NAMESPACE,
        f"{base_forecast_id}:{source_run_id.strip()}:{content_hash.strip()}",
    )


def effective_forecast_id(
    *,
    base_forecast_id: UUID,
    amendment_id: UUID | None,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for the selected effective forecast."""
    if not content_hash.strip():
        raise ValueError("content_hash is required for effective_forecast_id")
    amendment_key = str(amendment_id) if amendment_id is not None else "base"
    return uuid5(
        _EFFECTIVE_FORECAST_ID_NAMESPACE,
        f"{base_forecast_id}:{amendment_key}:{content_hash.strip()}",
    )


class ForecastAmendment(ForecastModel):
    """Immutable H6 amendment: complete term replacement with base lineage.

    Never a partial patch and never inferred from conviction prose.
    """

    amendment_id: UUID
    base_forecast_id: UUID
    supersedes_amendment_id: UUID | None = None
    ticker: NonEmptyId
    terms: ForecastTerms
    reason: NonEmptyId
    evidence_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    counter_evidence_ids: tuple[NonEmptyId, ...] = Field(default_factory=tuple)
    source_run_id: NonEmptyId
    provider_invocation_id: NonEmptyId
    effective_at: AwareDatetime
    known_at: AwareDatetime
    content_hash: NonEmptyId

    @field_validator("evidence_ids", "counter_evidence_ids", mode="before")
    @classmethod
    def _coerce_id_sequence(cls, value: object) -> object:
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
    def _validate_identity_and_time(self) -> ForecastAmendment:
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
        return self


class EffectiveForecast(ForecastModel):
    """Selected forecast for downstream consumers: base or one valid amendment."""

    effective_forecast_id: UUID
    base_forecast_id: UUID
    amendment_id: UUID | None = None
    ticker: NonEmptyId
    terms: ForecastTerms
    content_hash: NonEmptyId
    effective_at: AwareDatetime
    known_at: AwareDatetime
    source: EffectiveForecastSource
    degradation: ForecastLineageDegradation = ForecastLineageDegradation.NONE

    @model_validator(mode="after")
    def _validate_selection(self) -> EffectiveForecast:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")

        expected_hash = forecast_terms_content_hash(self.terms)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ForecastTerms digest")

        if self.source is EffectiveForecastSource.AMENDMENT:
            if self.amendment_id is None:
                raise ValueError("amendment source requires amendment_id")
            if self.degradation is not ForecastLineageDegradation.NONE:
                raise ValueError("accepted amendment cannot carry degradation")
        elif self.amendment_id is not None:
            raise ValueError("base source cannot carry amendment_id")

        expected_id = effective_forecast_id(
            base_forecast_id=self.base_forecast_id,
            amendment_id=self.amendment_id,
            content_hash=self.content_hash,
        )
        if self.effective_forecast_id != expected_id:
            raise ValueError(
                "effective_forecast_id must be the UUID5 of "
                "base_forecast_id+amendment_key+content_hash"
            )
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
    evidence_ids: tuple[str, ...] | list[str] = (),
    counter_evidence_ids: tuple[str, ...] | list[str] = (),
    supersedes_amendment_id: UUID | None = None,
) -> ForecastAmendment:
    """Build an immutable amendment from a complete term set (not a partial patch)."""
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
        evidence_ids=tuple(evidence_ids),
        counter_evidence_ids=tuple(counter_evidence_ids),
        source_run_id=source_run_id,
        provider_invocation_id=provider_invocation_id,
        effective_at=effective_at,
        known_at=known_at,
        content_hash=content_hash,
    )


def resolve_effective_forecast(
    base: ForecastAssessment,
    amendment: ForecastAmendment | None = None,
    *,
    degradation: ForecastLineageDegradation = ForecastLineageDegradation.NONE,
) -> EffectiveForecast:
    """Select base or one valid amendment; invalid amendments never mutate the base."""
    if amendment is not None:
        if amendment.base_forecast_id != base.forecast_id:
            raise ValueError("amendment.base_forecast_id must match base.forecast_id")
        if amendment.ticker.strip().upper() != base.ticker.strip().upper():
            raise ValueError("amendment ticker must match base ticker")
        if degradation is not ForecastLineageDegradation.NONE:
            raise ValueError("accepted amendment requires degradation=none")
        return EffectiveForecast(
            effective_forecast_id=effective_forecast_id(
                base_forecast_id=base.forecast_id,
                amendment_id=amendment.amendment_id,
                content_hash=amendment.content_hash,
            ),
            base_forecast_id=base.forecast_id,
            amendment_id=amendment.amendment_id,
            ticker=base.ticker,
            terms=amendment.terms,
            content_hash=amendment.content_hash,
            effective_at=amendment.effective_at,
            known_at=amendment.known_at,
            source=EffectiveForecastSource.AMENDMENT,
            degradation=ForecastLineageDegradation.NONE,
        )

    return EffectiveForecast(
        effective_forecast_id=effective_forecast_id(
            base_forecast_id=base.forecast_id,
            amendment_id=None,
            content_hash=base.content_hash,
        ),
        base_forecast_id=base.forecast_id,
        amendment_id=None,
        ticker=base.ticker,
        terms=base.terms,
        content_hash=base.content_hash,
        effective_at=base.effective_at,
        known_at=base.known_at,
        source=EffectiveForecastSource.BASE,
        degradation=degradation,
    )


def try_resolve_effective_forecast(
    base: ForecastAssessment | None,
    amendment: ForecastAmendment | None = None,
    *,
    degradation: ForecastLineageDegradation = ForecastLineageDegradation.NONE,
) -> EffectiveForecast | None:
    """Resolve when a base exists; otherwise return ``None`` (typed unavailable upstream)."""
    if base is None:
        return None
    try:
        return resolve_effective_forecast(base, amendment, degradation=degradation)
    except (ValueError, ValidationError):
        # Invalid amendment proposal → preserve base with amendment_rejected.
        if amendment is not None:
            return resolve_effective_forecast(
                base,
                None,
                degradation=ForecastLineageDegradation.AMENDMENT_REJECTED,
            )
        raise


__all__ = [
    "EffectiveForecast",
    "EffectiveForecastSource",
    "ForecastAmendment",
    "ForecastAssessment",
    "ForecastLineageDegradation",
    "ForecastModel",
    "ForecastTerms",
    "PriceAnchor",
    "PriceAnchorStatus",
    "RawUncertainty",
    "effective_forecast_id",
    "forecast_amendment_id",
    "forecast_assessment_id",
    "forecast_terms_content_hash",
    "materialize_forecast_amendment",
    "resolve_effective_forecast",
    "try_resolve_effective_forecast",
]
