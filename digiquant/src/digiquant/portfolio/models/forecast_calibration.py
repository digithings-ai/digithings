"""Forecast outcome and calibration contracts (#2672 / WP5.1).

Defines immutable prospective labels and versioned calibration artifacts for
dashboard Phase 1. Schema + strict Pydantic only — the deterministic calibrator
and H6→H7 attach helpers live in
:mod:`digiquant.portfolio.forecast_calibration` (WP5.3/5.4); table writers
in :mod:`digiquant.research.forecast_registry` (WP5.4). No H8 consumption.

Style mirrors :mod:`digiquant.portfolio.models.forecast`: frozen,
``extra="forbid"``, UTC-only aware datetimes, Decimal economics, UUID5
idempotent identity, content hashes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
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

# Stable namespaces — do not change; existing prospective IDs would diverge.
_FORECAST_OUTCOME_ID_NAMESPACE = UUID("c6e0a13d-4f91-705c-bd28-3bae6f9c4c12")
_FORECAST_CALIBRATION_ID_NAMESPACE = UUID("d7f1b24e-5a02-816d-ce39-4cbf7a0d5d23")
_CALIBRATED_FORECAST_ID_NAMESPACE = UUID("e8a2c35f-6b13-927e-df4a-5dc08b1e6e34")

Probability: TypeAlias = Annotated[
    Decimal, Field(ge=0, le=1, allow_inf_nan=False, max_digits=16, decimal_places=8)
]
ReturnFraction: TypeAlias = Annotated[
    Decimal, Field(allow_inf_nan=False, max_digits=16, decimal_places=8)
]
NonNegativeDecimal: TypeAlias = Annotated[
    Decimal, Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]
PositivePrice: TypeAlias = Annotated[
    Decimal, Field(gt=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]
NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
NonNegativeInt: TypeAlias = Annotated[int, Field(ge=0)]
PositiveSessions: TypeAlias = Annotated[int, Field(gt=0)]


class OutcomeStatus(StrEnum):
    """Lifecycle of a prospective forecast market label."""

    RESOLVED = "resolved"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"


class CalibrationArtifactStatus(StrEnum):
    """Whether a calibration or calibrated-forecast artifact carries metrics."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ForecastCalibrationModel(BaseModel):
    """Strict immutable base for every forecast-calibration contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionPriceSnapshot(ForecastCalibrationModel):
    """Observed close used as a prospective reference or maturity mark."""

    session_date: date
    price: PositivePrice
    observed_at: AwareDatetime
    known_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_utc(self) -> SessionPriceSnapshot:
        for field_name, value in (
            ("observed_at", self.observed_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")
        return self


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def forecast_outcome_content_hash(*, payload: dict[str, object]) -> str:
    """SHA-256 over canonical JSON of outcome economic identity fields."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def forecast_outcome_id(
    *,
    effective_forecast_id: UUID,
    maturity_session: date,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for a matured (or typed-pending) forecast outcome."""
    if not content_hash.strip():
        raise ValueError("content_hash is required for outcome_id")
    return uuid5(
        _FORECAST_OUTCOME_ID_NAMESPACE,
        f"{effective_forecast_id}:{maturity_session.isoformat()}:{content_hash.strip()}",
    )


def forecast_calibration_content_hash(*, payload: dict[str, object]) -> str:
    """SHA-256 over canonical JSON of calibration cohort/metrics identity."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def forecast_calibration_id(
    *,
    cohort_key: str,
    method_version: str,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for a versioned calibration artifact."""
    if not cohort_key.strip() or not method_version.strip() or not content_hash.strip():
        raise ValueError("cohort_key, method_version, and content_hash are required")
    return uuid5(
        _FORECAST_CALIBRATION_ID_NAMESPACE,
        f"{cohort_key.strip()}:{method_version.strip()}:{content_hash.strip()}",
    )


def calibrated_forecast_content_hash(*, payload: dict[str, object]) -> str:
    """SHA-256 over canonical JSON of calibrated-forecast shadow fields."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def calibrated_forecast_id(
    *,
    effective_forecast_id: UUID,
    calibration_id: UUID | None,
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for a shadow calibrated forecast subject."""
    if not content_hash.strip():
        raise ValueError("content_hash is required for calibrated_forecast_id")
    cal_key = str(calibration_id) if calibration_id is not None else "unavailable"
    return uuid5(
        _CALIBRATED_FORECAST_ID_NAMESPACE,
        f"{effective_forecast_id}:{cal_key}:{content_hash.strip()}",
    )


class ForecastOutcome(ForecastCalibrationModel):
    """Immutable prospective market label for one base/effective forecast.

    Measures forecast quality only — never portfolio contribution or sizing P&L.
    Horizons use trading-session dates, not calendar-day approximations.
    """

    outcome_id: UUID
    base_forecast_id: UUID
    effective_forecast_id: UUID
    ticker: NonEmptyId
    horizon_sessions: PositiveSessions
    reference_session: date
    maturity_session: date
    reference_snapshot: SessionPriceSnapshot | None = None
    maturity_snapshot: SessionPriceSnapshot | None = None
    forecast_mean_return: ReturnFraction | None = None
    realized_return: ReturnFraction | None = None
    signed_residual: ReturnFraction | None = None
    positive_label: bool | None = None
    status: OutcomeStatus
    unavailable_reason: NonEmptyId | None = None
    event_time: AwareDatetime
    known_at: AwareDatetime
    content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_outcome(self) -> ForecastOutcome:
        for field_name, value in (
            ("event_time", self.event_time),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")
        if self.maturity_session < self.reference_session:
            raise ValueError("maturity_session must be on or after reference_session")

        if self.status is OutcomeStatus.RESOLVED:
            if self.unavailable_reason is not None:
                raise ValueError("resolved outcome cannot carry unavailable_reason")
            required = (
                self.reference_snapshot,
                self.maturity_snapshot,
                self.forecast_mean_return,
                self.realized_return,
                self.signed_residual,
                self.positive_label,
            )
            if any(item is None for item in required):
                raise ValueError(
                    "resolved outcome requires reference/maturity snapshots, "
                    "forecast_mean_return, realized_return, signed_residual, positive_label"
                )
            assert self.reference_snapshot is not None
            assert self.maturity_snapshot is not None
            assert self.forecast_mean_return is not None
            assert self.realized_return is not None
            assert self.signed_residual is not None
            if self.reference_snapshot.session_date != self.reference_session:
                raise ValueError("reference_snapshot.session_date must match reference_session")
            if self.maturity_snapshot.session_date != self.maturity_session:
                raise ValueError("maturity_snapshot.session_date must match maturity_session")
            expected_residual = self.realized_return - self.forecast_mean_return
            if self.signed_residual != expected_residual:
                raise ValueError(
                    "signed_residual must equal realized_return - forecast_mean_return"
                )
            expected_positive = self.realized_return > Decimal("0")
            if self.positive_label is not expected_positive:
                raise ValueError(
                    "positive_label must be True iff realized_return > 0 "
                    "(zero and negative are False)"
                )
        elif self.status is OutcomeStatus.PENDING:
            if self.unavailable_reason is not None:
                raise ValueError("pending outcome cannot carry unavailable_reason")
            if any(
                value is not None
                for value in (
                    self.maturity_snapshot,
                    self.realized_return,
                    self.signed_residual,
                    self.positive_label,
                )
            ):
                raise ValueError(
                    "pending outcome cannot carry maturity snapshot or realized labels"
                )
        else:
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("unavailable outcome requires unavailable_reason")
            if any(
                value is not None
                for value in (
                    self.realized_return,
                    self.signed_residual,
                    self.positive_label,
                )
            ):
                raise ValueError("unavailable outcome cannot carry realized labels")

        payload = self._hash_payload()
        expected_hash = forecast_outcome_content_hash(payload=payload)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ForecastOutcome digest")
        expected_id = forecast_outcome_id(
            effective_forecast_id=self.effective_forecast_id,
            maturity_session=self.maturity_session,
            content_hash=self.content_hash,
        )
        if self.outcome_id != expected_id:
            raise ValueError(
                "outcome_id must be the UUID5 of "
                "effective_forecast_id+maturity_session+content_hash"
            )
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "base_forecast_id": str(self.base_forecast_id),
            "effective_forecast_id": str(self.effective_forecast_id),
            "ticker": self.ticker,
            "horizon_sessions": self.horizon_sessions,
            "reference_session": self.reference_session.isoformat(),
            "maturity_session": self.maturity_session.isoformat(),
            "reference_snapshot": (
                None
                if self.reference_snapshot is None
                else self.reference_snapshot.model_dump(mode="json")
            ),
            "maturity_snapshot": (
                None
                if self.maturity_snapshot is None
                else self.maturity_snapshot.model_dump(mode="json")
            ),
            "forecast_mean_return": (
                None if self.forecast_mean_return is None else str(self.forecast_mean_return)
            ),
            "realized_return": (
                None if self.realized_return is None else str(self.realized_return)
            ),
            "signed_residual": (
                None if self.signed_residual is None else str(self.signed_residual)
            ),
            "positive_label": self.positive_label,
            "status": self.status.value,
            "unavailable_reason": self.unavailable_reason,
            "event_time": self.event_time.isoformat(),
            "known_at": self.known_at.isoformat(),
        }


class ForecastCalibration(ForecastCalibrationModel):
    """Versioned cohort calibration metrics against a declared prior.

    Sparse cohorts shrink toward the prior and must report low reliability —
    never invent high precision from a handful of correct calls.
    """

    calibration_id: UUID
    cohort_key: NonEmptyId
    prior_definition: NonEmptyId
    method_version: NonEmptyId
    sample_count: NonNegativeInt
    equivalent_sample_size: NonNegativeDecimal
    bias: ReturnFraction | None = None
    dispersion: NonNegativeDecimal | None = None
    brier_score: Probability | None = None
    log_score: Decimal | None = None
    reliability: Probability
    status: CalibrationArtifactStatus
    unavailable_reason: NonEmptyId | None = None
    outcome_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    content_hash: NonEmptyId
    effective_at: AwareDatetime
    known_at: AwareDatetime

    @field_validator("outcome_ids", mode="before")
    @classmethod
    def _coerce_outcome_ids(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_calibration(self) -> ForecastCalibration:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")

        if self.status is CalibrationArtifactStatus.AVAILABLE:
            if self.unavailable_reason is not None:
                raise ValueError("available calibration cannot carry unavailable_reason")
            if self.sample_count != len(self.outcome_ids):
                raise ValueError("sample_count must equal len(outcome_ids)")
            if self.bias is None or self.dispersion is None:
                raise ValueError("available calibration requires bias and dispersion")
            if self.log_score is not None and self.log_score.is_nan():
                raise ValueError("log_score must be finite when present")
        else:
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("unavailable calibration requires unavailable_reason")
            if any(
                value is not None
                for value in (self.bias, self.dispersion, self.brier_score, self.log_score)
            ):
                raise ValueError("unavailable calibration cannot carry metric fields")
            if self.outcome_ids:
                raise ValueError("unavailable calibration cannot list outcome_ids")
            if self.sample_count != 0:
                raise ValueError("unavailable calibration requires sample_count=0")

        payload = self._hash_payload()
        expected_hash = forecast_calibration_content_hash(payload=payload)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ForecastCalibration digest")
        expected_id = forecast_calibration_id(
            cohort_key=self.cohort_key,
            method_version=self.method_version,
            content_hash=self.content_hash,
        )
        if self.calibration_id != expected_id:
            raise ValueError(
                "calibration_id must be the UUID5 of cohort_key+method_version+content_hash"
            )
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "cohort_key": self.cohort_key,
            "prior_definition": self.prior_definition,
            "method_version": self.method_version,
            "sample_count": self.sample_count,
            "equivalent_sample_size": str(self.equivalent_sample_size),
            "bias": None if self.bias is None else str(self.bias),
            "dispersion": None if self.dispersion is None else str(self.dispersion),
            "brier_score": None if self.brier_score is None else str(self.brier_score),
            "log_score": None if self.log_score is None else str(self.log_score),
            "reliability": str(self.reliability),
            "status": self.status.value,
            "unavailable_reason": self.unavailable_reason,
            "outcome_ids": [str(item) for item in self.outcome_ids],
            "effective_at": self.effective_at.isoformat(),
            "known_at": self.known_at.isoformat(),
        }


class CalibratedForecast(ForecastCalibrationModel):
    """Versioned calibrated subject forecast for the H8 allocation bundle (WP8.4).

    Unavailable subjects retain typed reasons and low reliability rather than
    inventing zeros. H8 consumes AVAILABLE slices via ``AllocationInputBundle``;
    degraded/unavailable slices receive no new risk.
    """

    calibrated_forecast_id: UUID
    base_forecast_id: UUID
    effective_forecast_id: UUID
    calibration_id: UUID | None = None
    ticker: NonEmptyId
    expected_gross_return: ReturnFraction | None = None
    forecast_error_std: NonNegativeDecimal | None = None
    downside_quantiles: tuple[Decimal, ...] | None = None
    calibrated_positive_probability: Probability | None = None
    reliability_weight: Probability
    effective_until: AwareDatetime | None = None
    status: CalibrationArtifactStatus
    unavailable_reason: NonEmptyId | None = None
    content_hash: NonEmptyId
    effective_at: AwareDatetime
    known_at: AwareDatetime

    @field_validator("downside_quantiles", mode="before")
    @classmethod
    def _coerce_quantiles(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_calibrated(self) -> CalibratedForecast:
        for field_name, value in (
            ("effective_at", self.effective_at),
            ("known_at", self.known_at),
        ):
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{field_name} must be timezone-aware UTC")
        if self.effective_until is not None and self.effective_until.utcoffset() != timedelta(0):
            raise ValueError("effective_until must be timezone-aware UTC")

        if self.status is CalibrationArtifactStatus.AVAILABLE:
            if self.unavailable_reason is not None:
                raise ValueError("available calibrated forecast cannot carry unavailable_reason")
            if self.calibration_id is None:
                raise ValueError("available calibrated forecast requires calibration_id")
            required = (
                self.expected_gross_return,
                self.forecast_error_std,
                self.downside_quantiles,
                self.calibrated_positive_probability,
                self.effective_until,
            )
            if any(item is None for item in required):
                raise ValueError(
                    "available calibrated forecast requires expected_gross_return, "
                    "forecast_error_std, downside_quantiles, "
                    "calibrated_positive_probability, effective_until"
                )
            assert self.downside_quantiles is not None
            if len(self.downside_quantiles) == 0:
                raise ValueError("downside_quantiles must be non-empty when available")
            if list(self.downside_quantiles) != sorted(self.downside_quantiles):
                raise ValueError("downside_quantiles must be non-decreasing")
            if self.forecast_error_std == Decimal("0"):
                raise ValueError("forecast_error_std must be positive when available")
        else:
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("unavailable calibrated forecast requires unavailable_reason")
            if self.calibration_id is not None:
                raise ValueError("unavailable calibrated forecast cannot carry calibration_id")
            if any(
                value is not None
                for value in (
                    self.expected_gross_return,
                    self.forecast_error_std,
                    self.downside_quantiles,
                    self.calibrated_positive_probability,
                    self.effective_until,
                )
            ):
                raise ValueError("unavailable calibrated forecast cannot carry metric fields")

        payload = self._hash_payload()
        expected_hash = calibrated_forecast_content_hash(payload=payload)
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical CalibratedForecast digest")
        expected_id = calibrated_forecast_id(
            effective_forecast_id=self.effective_forecast_id,
            calibration_id=self.calibration_id,
            content_hash=self.content_hash,
        )
        if self.calibrated_forecast_id != expected_id:
            raise ValueError(
                "calibrated_forecast_id must be the UUID5 of "
                "effective_forecast_id+calibration_id+content_hash"
            )
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "base_forecast_id": str(self.base_forecast_id),
            "effective_forecast_id": str(self.effective_forecast_id),
            "calibration_id": (None if self.calibration_id is None else str(self.calibration_id)),
            "ticker": self.ticker,
            "expected_gross_return": (
                None if self.expected_gross_return is None else str(self.expected_gross_return)
            ),
            "forecast_error_std": (
                None if self.forecast_error_std is None else str(self.forecast_error_std)
            ),
            "downside_quantiles": (
                None
                if self.downside_quantiles is None
                else [str(item) for item in self.downside_quantiles]
            ),
            "calibrated_positive_probability": (
                None
                if self.calibrated_positive_probability is None
                else str(self.calibrated_positive_probability)
            ),
            "reliability_weight": str(self.reliability_weight),
            "effective_until": (
                None if self.effective_until is None else self.effective_until.isoformat()
            ),
            "status": self.status.value,
            "unavailable_reason": self.unavailable_reason,
            "effective_at": self.effective_at.isoformat(),
            "known_at": self.known_at.isoformat(),
        }


__all__ = [
    "CalibratedForecast",
    "CalibrationArtifactStatus",
    "ForecastCalibration",
    "ForecastCalibrationModel",
    "ForecastOutcome",
    "OutcomeStatus",
    "SessionPriceSnapshot",
    "calibrated_forecast_content_hash",
    "calibrated_forecast_id",
    "forecast_calibration_content_hash",
    "forecast_calibration_id",
    "forecast_outcome_content_hash",
    "forecast_outcome_id",
]
