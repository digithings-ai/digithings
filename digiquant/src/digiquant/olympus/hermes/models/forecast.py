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
    field_validator,
    model_validator,
)

# Stable namespace for ForecastAssessment UUID5 identity. Do not change — existing
# prospective IDs would diverge if this literal moves.
_FORECAST_ASSESSMENT_ID_NAMESPACE = UUID("a4c8e91b-2d7f-5e3a-9b06-1f8c4d7e2a90")

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


__all__ = [
    "ForecastAssessment",
    "ForecastModel",
    "ForecastTerms",
    "PriceAnchor",
    "PriceAnchorStatus",
    "RawUncertainty",
    "forecast_assessment_id",
    "forecast_terms_content_hash",
]
