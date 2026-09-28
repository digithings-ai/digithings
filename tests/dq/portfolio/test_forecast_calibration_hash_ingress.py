"""G4: calibration hashes survive a numeric -> float PostgREST round-trip.

PR #4298 canonicalized ``ForecastOutcome`` return spellings. ``Postgres numeric``
does not preserve trailing zeros, PostgREST returns the column as a JSON number,
and ``Decimal(str(float))`` re-spells ``0.50000000`` as ``0.5``. This file pins
the same invariant for ``ForecastCalibration`` / ``CalibratedForecast``: a stored
row read back as JSON numbers must re-hydrate to the digest recorded at write
time. The guard test proves the pre-#4298 raw-``str()`` payload would not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from digiquant.portfolio.models import forecast_calibration as fc
from digiquant.portfolio.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    ForecastCalibration,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
    canonical_return_fraction,
    forecast_calibration_content_hash,
    forecast_calibration_id,
)
from pydantic import ValidationError

_TS = datetime(2026, 1, 2, 15, 30, tzinfo=UTC)
_BASE_ID = UUID("11111111-1111-4111-8111-111111111111")
_EFF_ID = UUID("22222222-2222-4222-8222-222222222222")
_OUTCOME_ID = UUID("33333333-3333-4333-8333-333333333333")

# Deliberately 8-decimal spellings with trailing zeros: the exact shape Postgres
# stores and PostgREST flattens to a JSON number on read-back.
_CAL_DECIMALS: dict[str, str] = {
    "equivalent_sample_size": "0.50000000",
    "bias": "0.02000000",
    "dispersion": "0.08000000",
    "brier_score": "0.18000000",
    "log_score": "-0.45000000",
    "reliability": "0.25000000",
}
_SUBJECT_DECIMALS: dict[str, str] = {
    "expected_gross_return": "0.03000000",
    "forecast_error_std": "0.09000000",
    "calibrated_positive_probability": "0.55000000",
    "reliability_weight": "0.25000000",
}
_SUBJECT_QUANTILES = ("-0.20000000", "-0.10000000", "-0.05000000")


def _calibration() -> ForecastCalibration:
    payload = forecast_calibration_payload_with_raw_decimals()
    content_hash = forecast_calibration_content_hash(payload=payload)
    return ForecastCalibration(
        calibration_id=forecast_calibration_id(
            cohort_key="horizon:21|regime:default",
            method_version="shadow-calibrator@1",
            content_hash=content_hash,
        ),
        cohort_key="horizon:21|regime:default",
        prior_definition="zero_mean_shrinkage@v1",
        method_version="shadow-calibrator@1",
        sample_count=1,
        equivalent_sample_size=Decimal(_CAL_DECIMALS["equivalent_sample_size"]),
        bias=Decimal(_CAL_DECIMALS["bias"]),
        dispersion=Decimal(_CAL_DECIMALS["dispersion"]),
        brier_score=Decimal(_CAL_DECIMALS["brier_score"]),
        log_score=Decimal(_CAL_DECIMALS["log_score"]),
        reliability=Decimal(_CAL_DECIMALS["reliability"]),
        status=CalibrationArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        outcome_ids=(_OUTCOME_ID,),
        content_hash=content_hash,
        effective_at=_TS,
        known_at=_TS,
    )


def forecast_calibration_payload_with_raw_decimals() -> dict[str, object]:
    """Write-time payload exactly as the calibrator spelled it (raw ``str()``)."""
    return {
        "cohort_key": "horizon:21|regime:default",
        "prior_definition": "zero_mean_shrinkage@v1",
        "method_version": "shadow-calibrator@1",
        "sample_count": 1,
        "equivalent_sample_size": _CAL_DECIMALS["equivalent_sample_size"],
        "bias": _CAL_DECIMALS["bias"],
        "dispersion": _CAL_DECIMALS["dispersion"],
        "brier_score": _CAL_DECIMALS["brier_score"],
        "log_score": _CAL_DECIMALS["log_score"],
        "reliability": _CAL_DECIMALS["reliability"],
        "status": "available",
        "unavailable_reason": None,
        "outcome_ids": [str(_OUTCOME_ID)],
        "effective_at": _TS.isoformat(),
        "known_at": _TS.isoformat(),
    }


def _calibrated(calibration: ForecastCalibration) -> CalibratedForecast:
    payload = calibrated_forecast_payload_with_raw_decimals(str(calibration.calibration_id))
    content_hash = calibrated_forecast_content_hash(payload=payload)
    return CalibratedForecast(
        calibrated_forecast_id=calibrated_forecast_id(
            effective_forecast_id=_EFF_ID,
            calibration_id=calibration.calibration_id,
            content_hash=content_hash,
        ),
        base_forecast_id=_BASE_ID,
        effective_forecast_id=_EFF_ID,
        calibration_id=calibration.calibration_id,
        ticker="AAPL",
        expected_gross_return=Decimal(_SUBJECT_DECIMALS["expected_gross_return"]),
        forecast_error_std=Decimal(_SUBJECT_DECIMALS["forecast_error_std"]),
        downside_quantiles=tuple(Decimal(value) for value in _SUBJECT_QUANTILES),
        calibrated_positive_probability=Decimal(
            _SUBJECT_DECIMALS["calibrated_positive_probability"]
        ),
        reliability_weight=Decimal(_SUBJECT_DECIMALS["reliability_weight"]),
        effective_until=_TS + timedelta(days=21),
        status=CalibrationArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        content_hash=content_hash,
        effective_at=_TS,
        known_at=_TS,
    )


def calibrated_forecast_payload_with_raw_decimals(calibration_id: str) -> dict[str, object]:
    """Write-time payload exactly as the calibrator spelled it (raw ``str()``)."""
    return {
        "base_forecast_id": str(_BASE_ID),
        "effective_forecast_id": str(_EFF_ID),
        "calibration_id": calibration_id,
        "ticker": "AAPL",
        "expected_gross_return": _SUBJECT_DECIMALS["expected_gross_return"],
        "forecast_error_std": _SUBJECT_DECIMALS["forecast_error_std"],
        "downside_quantiles": list(_SUBJECT_QUANTILES),
        "calibrated_positive_probability": _SUBJECT_DECIMALS["calibrated_positive_probability"],
        "reliability_weight": _SUBJECT_DECIMALS["reliability_weight"],
        "effective_until": (_TS + timedelta(days=21)).isoformat(),
        "status": "available",
        "unavailable_reason": None,
        "effective_at": _TS.isoformat(),
        "known_at": _TS.isoformat(),
    }


def _postgrest_row(subject: ForecastCalibration | CalibratedForecast) -> dict[str, Any]:
    """Dump like PostgREST returns: 8dp numerics become JSON numbers (floats)."""
    row: dict[str, Any] = subject.model_dump(mode="json")
    scalar_keys = (
        tuple(_CAL_DECIMALS)
        if isinstance(subject, ForecastCalibration)
        else tuple(_SUBJECT_DECIMALS)
    )
    for key in scalar_keys:
        if row.get(key) is not None:
            row[key] = float(row[key])
    if isinstance(subject, CalibratedForecast):
        row["downside_quantiles"] = [float(value) for value in row["downside_quantiles"]]
    return row


def _raw_legacy_digest(payload: dict[str, object]) -> str:
    """Pre-fix digest over the raw payload, exactly as #4298 describes the bug."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_canonical_return_fraction_fixes_trailing_zero_spelling() -> None:
    assert canonical_return_fraction(Decimal("0.50000000")) == "0.50000000"
    assert str(Decimal(str(float(Decimal("0.50000000"))))) == "0.5"


def test_forecast_calibration_survives_numeric_float_roundtrip() -> None:
    calibration = _calibration()
    row = _postgrest_row(calibration)
    assert row["equivalent_sample_size"] == 0.5
    rehydrated = ForecastCalibration.model_validate(row)
    assert rehydrated.content_hash == calibration.content_hash
    assert rehydrated.calibration_id == calibration.calibration_id


def test_calibrated_forecast_survives_numeric_float_roundtrip() -> None:
    calibration = _calibration()
    subject = _calibrated(calibration)
    row = _postgrest_row(subject)
    assert row["expected_gross_return"] == 0.03
    assert row["downside_quantiles"] == [-0.2, -0.1, -0.05]
    rehydrated = CalibratedForecast.model_validate(row)
    assert rehydrated.content_hash == subject.content_hash
    assert rehydrated.calibrated_forecast_id == subject.calibrated_forecast_id


def _legacy_rehydrated_payload(subject: ForecastCalibration | CalibratedForecast) -> dict[str, Any]:
    """The payload the pre-fix validator would hash after a float read-back."""
    payload: dict[str, Any] = {}
    for key, value in _postgrest_row(subject).items():
        if isinstance(value, float):
            payload[key] = str(Decimal(str(value)))
        elif isinstance(value, list) and value and all(isinstance(item, float) for item in value):
            payload[key] = [str(Decimal(str(item))) for item in value]
        else:
            payload[key] = value
    return payload


def test_legacy_raw_spelling_digest_differs_from_canonical() -> None:
    """Non-tautological guard: the old rehydrated-``str()`` digest is not the fix's."""
    calibration = _calibration()
    canonical_digest = forecast_calibration_content_hash(payload=_postgrest_row(calibration))
    assert _raw_legacy_digest(_legacy_rehydrated_payload(calibration)) != canonical_digest


def test_legacy_raw_spelling_would_not_survive_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With canonicalization neutered, the float read-back no longer re-validates."""

    def _identity(
        payload: dict[str, object],
        *,
        scalar_keys: tuple[str, ...],
        sequence_keys: tuple[str, ...] = (),
    ) -> dict[str, object]:
        return dict(payload)

    monkeypatch.setattr(fc, "_canonicalize_payload_decimals", _identity)
    calibration = _calibration()
    row = _postgrest_row(calibration)
    with pytest.raises(ValidationError, match="content_hash"):
        ForecastCalibration.model_validate(row)


def test_legacy_raw_spelling_would_not_survive_roundtrip_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _identity(
        payload: dict[str, object],
        *,
        scalar_keys: tuple[str, ...],
        sequence_keys: tuple[str, ...] = (),
    ) -> dict[str, object]:
        return dict(payload)

    monkeypatch.setattr(fc, "_canonicalize_payload_decimals", _identity)
    subject = _calibrated(_calibration())
    row = _postgrest_row(subject)
    with pytest.raises(ValidationError, match="content_hash"):
        CalibratedForecast.model_validate(row)
