"""Forecast outcome / calibration contract models (#2672 / WP5.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.portfolio.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    ForecastCalibration,
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
    forecast_calibration_content_hash,
    forecast_calibration_id,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_REF = date(2026, 7, 15)
_MAT = date(2026, 8, 13)
_BASE_ID = UUID("11111111-1111-5111-8111-111111111111")
_EFF_ID = UUID("22222222-2222-5222-8222-222222222222")


def _snapshot(*, session: date, price: str = "190.50") -> SessionPriceSnapshot:
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=_TS - timedelta(hours=6),
        known_at=_TS - timedelta(hours=5),
    )


def _resolved_outcome(**overrides: object) -> ForecastOutcome:
    forecast_mean = Decimal("0.04")
    realized = Decimal("0.06")
    residual = realized - forecast_mean
    draft = dict(
        base_forecast_id=_BASE_ID,
        effective_forecast_id=_EFF_ID,
        ticker="AAPL",
        horizon_sessions=21,
        reference_session=_REF,
        maturity_session=_MAT,
        reference_snapshot=_snapshot(session=_REF),
        maturity_snapshot=_snapshot(session=_MAT, price="201.93"),
        forecast_mean_return=forecast_mean,
        realized_return=realized,
        signed_residual=residual,
        positive_label=True,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=_TS,
        known_at=_TS,
    )
    draft.update(overrides)
    if "content_hash" not in draft or "outcome_id" not in draft:
        # Build a temporary model-shaped payload for hash helpers without recursion.
        tmp = {**draft}
        payload = {
            "base_forecast_id": str(tmp["base_forecast_id"]),
            "effective_forecast_id": str(tmp["effective_forecast_id"]),
            "ticker": tmp["ticker"],
            "horizon_sessions": tmp["horizon_sessions"],
            "reference_session": tmp["reference_session"].isoformat(),
            "maturity_session": tmp["maturity_session"].isoformat(),
            "reference_snapshot": (
                None
                if tmp.get("reference_snapshot") is None
                else tmp["reference_snapshot"].model_dump(mode="json")
            ),
            "maturity_snapshot": (
                None
                if tmp.get("maturity_snapshot") is None
                else tmp["maturity_snapshot"].model_dump(mode="json")
            ),
            "forecast_mean_return": (
                None
                if tmp.get("forecast_mean_return") is None
                else str(tmp["forecast_mean_return"])
            ),
            "realized_return": (
                None if tmp.get("realized_return") is None else str(tmp["realized_return"])
            ),
            "signed_residual": (
                None if tmp.get("signed_residual") is None else str(tmp["signed_residual"])
            ),
            "positive_label": tmp.get("positive_label"),
            "status": tmp["status"].value
            if isinstance(tmp["status"], OutcomeStatus)
            else tmp["status"],
            "unavailable_reason": tmp.get("unavailable_reason"),
            "event_time": tmp["event_time"].isoformat(),
            "known_at": tmp["known_at"].isoformat(),
        }
        content_hash = forecast_outcome_content_hash(payload=payload)
        draft.setdefault("content_hash", content_hash)
        draft.setdefault(
            "outcome_id",
            forecast_outcome_id(
                effective_forecast_id=draft["effective_forecast_id"],  # type: ignore[arg-type]
                maturity_session=draft["maturity_session"],  # type: ignore[arg-type]
                content_hash=content_hash,
            ),
        )
    return ForecastOutcome(**draft)


def _calibration(**overrides: object) -> ForecastCalibration:
    outcome = _resolved_outcome()
    draft: dict[str, object] = dict(
        cohort_key="horizon:21|regime:default",
        prior_definition="zero_mean_shrinkage@v1",
        method_version="shadow-calibrator@1",
        sample_count=1,
        equivalent_sample_size=Decimal("0.5"),
        bias=Decimal("0.02"),
        dispersion=Decimal("0.08"),
        brier_score=Decimal("0.18"),
        log_score=Decimal("-0.45"),
        reliability=Decimal("0.25"),
        status=CalibrationArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        outcome_ids=(outcome.outcome_id,),
        effective_at=_TS,
        known_at=_TS,
    )
    draft.update(overrides)
    if "content_hash" not in draft or "calibration_id" not in draft:
        payload = {
            "cohort_key": draft["cohort_key"],
            "prior_definition": draft["prior_definition"],
            "method_version": draft["method_version"],
            "sample_count": draft["sample_count"],
            "equivalent_sample_size": str(draft["equivalent_sample_size"]),
            "bias": None if draft.get("bias") is None else str(draft["bias"]),
            "dispersion": None if draft.get("dispersion") is None else str(draft["dispersion"]),
            "brier_score": None if draft.get("brier_score") is None else str(draft["brier_score"]),
            "log_score": None if draft.get("log_score") is None else str(draft["log_score"]),
            "reliability": str(draft["reliability"]),
            "status": draft["status"].value
            if isinstance(draft["status"], CalibrationArtifactStatus)
            else draft["status"],
            "unavailable_reason": draft.get("unavailable_reason"),
            "outcome_ids": [str(item) for item in draft["outcome_ids"]],  # type: ignore[index]
            "effective_at": draft["effective_at"].isoformat(),  # type: ignore[union-attr]
            "known_at": draft["known_at"].isoformat(),  # type: ignore[union-attr]
        }
        content_hash = forecast_calibration_content_hash(payload=payload)
        draft.setdefault("content_hash", content_hash)
        draft.setdefault(
            "calibration_id",
            forecast_calibration_id(
                cohort_key=str(draft["cohort_key"]),
                method_version=str(draft["method_version"]),
                content_hash=content_hash,
            ),
        )
    return ForecastCalibration(**draft)


def _calibrated(**overrides: object) -> CalibratedForecast:
    calibration = _calibration()
    draft: dict[str, object] = dict(
        base_forecast_id=_BASE_ID,
        effective_forecast_id=_EFF_ID,
        calibration_id=calibration.calibration_id,
        ticker="AAPL",
        expected_gross_return=Decimal("0.03"),
        forecast_error_std=Decimal("0.09"),
        downside_quantiles=(Decimal("-0.20"), Decimal("-0.10"), Decimal("-0.05")),
        calibrated_positive_probability=Decimal("0.55"),
        reliability_weight=Decimal("0.25"),
        effective_until=_TS + timedelta(days=21),
        status=CalibrationArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        effective_at=_TS,
        known_at=_TS,
    )
    draft.update(overrides)
    if "content_hash" not in draft or "calibrated_forecast_id" not in draft:
        payload = {
            "base_forecast_id": str(draft["base_forecast_id"]),
            "effective_forecast_id": str(draft["effective_forecast_id"]),
            "calibration_id": (
                None if draft.get("calibration_id") is None else str(draft["calibration_id"])
            ),
            "ticker": draft["ticker"],
            "expected_gross_return": (
                None
                if draft.get("expected_gross_return") is None
                else str(draft["expected_gross_return"])
            ),
            "forecast_error_std": (
                None
                if draft.get("forecast_error_std") is None
                else str(draft["forecast_error_std"])
            ),
            "downside_quantiles": (
                None
                if draft.get("downside_quantiles") is None
                else [str(item) for item in draft["downside_quantiles"]]  # type: ignore[union-attr]
            ),
            "calibrated_positive_probability": (
                None
                if draft.get("calibrated_positive_probability") is None
                else str(draft["calibrated_positive_probability"])
            ),
            "reliability_weight": str(draft["reliability_weight"]),
            "effective_until": (
                None
                if draft.get("effective_until") is None
                else draft["effective_until"].isoformat()  # type: ignore[union-attr]
            ),
            "status": draft["status"].value
            if isinstance(draft["status"], CalibrationArtifactStatus)
            else draft["status"],
            "unavailable_reason": draft.get("unavailable_reason"),
            "effective_at": draft["effective_at"].isoformat(),  # type: ignore[union-attr]
            "known_at": draft["known_at"].isoformat(),  # type: ignore[union-attr]
        }
        content_hash = calibrated_forecast_content_hash(payload=payload)
        draft.setdefault("content_hash", content_hash)
        draft.setdefault(
            "calibrated_forecast_id",
            calibrated_forecast_id(
                effective_forecast_id=draft["effective_forecast_id"],  # type: ignore[arg-type]
                calibration_id=draft.get("calibration_id"),  # type: ignore[arg-type]
                content_hash=content_hash,
            ),
        )
    return CalibratedForecast(**draft)


class TestForecastOutcome:
    def test_resolved_outcome_is_immutable_and_idempotent(self) -> None:
        a = _resolved_outcome()
        b = _resolved_outcome()
        assert a.outcome_id == b.outcome_id
        assert a.signed_residual == Decimal("0.02")
        assert a.positive_label is True
        assert isinstance(a.outcome_id, UUID)
        assert a.outcome_id.version == 5
        with pytest.raises((TypeError, ValidationError)):
            a.realized_return = Decimal("0.10")  # type: ignore[misc]

    def test_signed_residual_must_match_realized_minus_mean(self) -> None:
        with pytest.raises(ValidationError, match="signed_residual"):
            _resolved_outcome(signed_residual=Decimal("0.99"))

    def test_positive_label_false_for_zero_or_negative(self) -> None:
        mean = Decimal("0.04")
        realized = Decimal("0")
        outcome = _resolved_outcome(
            realized_return=realized,
            signed_residual=realized - mean,
            positive_label=False,
        )
        assert outcome.positive_label is False
        with pytest.raises(ValidationError, match="positive_label"):
            _resolved_outcome(
                realized_return=Decimal("-0.01"),
                signed_residual=Decimal("-0.05"),
                positive_label=True,
            )

    def test_pending_forbids_realized_labels(self) -> None:
        with pytest.raises(ValidationError, match="pending"):
            _resolved_outcome(
                status=OutcomeStatus.PENDING,
                maturity_snapshot=None,
                # realized_return left set — pending must not carry labels
            )

    def test_pending_outcome_accepts_typed_gap(self) -> None:
        draft = dict(
            base_forecast_id=_BASE_ID,
            effective_forecast_id=_EFF_ID,
            ticker="AAPL",
            horizon_sessions=21,
            reference_session=_REF,
            maturity_session=_MAT,
            reference_snapshot=_snapshot(session=_REF),
            maturity_snapshot=None,
            forecast_mean_return=Decimal("0.04"),
            realized_return=None,
            signed_residual=None,
            positive_label=None,
            status=OutcomeStatus.PENDING,
            unavailable_reason=None,
            event_time=_TS,
            known_at=_TS,
        )
        payload = {
            "base_forecast_id": str(draft["base_forecast_id"]),
            "effective_forecast_id": str(draft["effective_forecast_id"]),
            "ticker": draft["ticker"],
            "horizon_sessions": draft["horizon_sessions"],
            "reference_session": draft["reference_session"].isoformat(),
            "maturity_session": draft["maturity_session"].isoformat(),
            "reference_snapshot": draft["reference_snapshot"].model_dump(mode="json"),
            "maturity_snapshot": None,
            "forecast_mean_return": str(draft["forecast_mean_return"]),
            "realized_return": None,
            "signed_residual": None,
            "positive_label": None,
            "status": "pending",
            "unavailable_reason": None,
            "event_time": draft["event_time"].isoformat(),
            "known_at": draft["known_at"].isoformat(),
        }
        content_hash = forecast_outcome_content_hash(payload=payload)
        pending = ForecastOutcome(
            **draft,
            content_hash=content_hash,
            outcome_id=forecast_outcome_id(
                effective_forecast_id=_EFF_ID,
                maturity_session=_MAT,
                content_hash=content_hash,
            ),
        )
        assert pending.status is OutcomeStatus.PENDING

    def test_unavailable_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="unavailable_reason"):
            _resolved_outcome(
                status=OutcomeStatus.UNAVAILABLE,
                reference_snapshot=None,
                maturity_snapshot=None,
                forecast_mean_return=None,
                realized_return=None,
                signed_residual=None,
                positive_label=None,
                unavailable_reason=None,
            )

    def test_same_id_different_hash_is_rejected(self) -> None:
        a = _resolved_outcome()
        with pytest.raises(ValidationError, match="content_hash|outcome_id"):
            ForecastOutcome(
                outcome_id=a.outcome_id,
                base_forecast_id=_BASE_ID,
                effective_forecast_id=_EFF_ID,
                ticker="AAPL",
                horizon_sessions=21,
                reference_session=_REF,
                maturity_session=_MAT,
                reference_snapshot=_snapshot(session=_REF),
                maturity_snapshot=_snapshot(session=_MAT, price="210.00"),
                forecast_mean_return=Decimal("0.04"),
                realized_return=Decimal("0.10"),
                signed_residual=Decimal("0.06"),
                positive_label=True,
                status=OutcomeStatus.RESOLVED,
                event_time=_TS,
                known_at=_TS,
                content_hash="0" * 64,
            )

    def test_rejects_non_utc_and_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            _resolved_outcome(known_at=_TS.replace(tzinfo=None))
        outcome = _resolved_outcome()
        with pytest.raises(ValidationError):
            ForecastOutcome.model_validate({**outcome.model_dump(), "portfolio_pnl": "1"})


class TestForecastCalibration:
    def test_available_calibration_reports_cohort_metrics(self) -> None:
        cal = _calibration()
        assert cal.sample_count == 1
        assert cal.brier_score == Decimal("0.18")
        assert cal.reliability == Decimal("0.25")
        assert cal.calibration_id.version == 5

    def test_sample_count_must_match_outcome_ids(self) -> None:
        with pytest.raises(ValidationError, match="sample_count"):
            _calibration(sample_count=2)

    def test_unavailable_calibration_is_typed(self) -> None:
        draft = dict(
            cohort_key="horizon:21|regime:default",
            prior_definition="zero_mean_shrinkage@v1",
            method_version="shadow-calibrator@1",
            sample_count=0,
            equivalent_sample_size=Decimal("0"),
            bias=None,
            dispersion=None,
            brier_score=None,
            log_score=None,
            reliability=Decimal("0"),
            status=CalibrationArtifactStatus.UNAVAILABLE,
            unavailable_reason="sparse_cohort",
            outcome_ids=(),
            effective_at=_TS,
            known_at=_TS,
        )
        payload = {
            "cohort_key": draft["cohort_key"],
            "prior_definition": draft["prior_definition"],
            "method_version": draft["method_version"],
            "sample_count": 0,
            "equivalent_sample_size": "0",
            "bias": None,
            "dispersion": None,
            "brier_score": None,
            "log_score": None,
            "reliability": "0",
            "status": "unavailable",
            "unavailable_reason": "sparse_cohort",
            "outcome_ids": [],
            "effective_at": draft["effective_at"].isoformat(),
            "known_at": draft["known_at"].isoformat(),
        }
        content_hash = forecast_calibration_content_hash(payload=payload)
        cal = ForecastCalibration(
            **draft,
            content_hash=content_hash,
            calibration_id=forecast_calibration_id(
                cohort_key=str(draft["cohort_key"]),
                method_version=str(draft["method_version"]),
                content_hash=content_hash,
            ),
        )
        assert cal.status is CalibrationArtifactStatus.UNAVAILABLE


class TestCalibratedForecast:
    def test_shadow_calibrated_forecast_identity(self) -> None:
        subject = _calibrated()
        again = _calibrated()
        assert subject.calibrated_forecast_id == again.calibrated_forecast_id
        assert subject.forecast_error_std == Decimal("0.09")
        assert subject.reliability_weight == Decimal("0.25")

    def test_zero_error_std_rejected(self) -> None:
        with pytest.raises(ValidationError, match="forecast_error_std"):
            _calibrated(forecast_error_std=Decimal("0"))

    def test_downside_quantiles_must_be_ordered(self) -> None:
        with pytest.raises(ValidationError, match="downside_quantiles"):
            _calibrated(downside_quantiles=(Decimal("-0.05"), Decimal("-0.20"), Decimal("-0.10")))

    def test_unavailable_subject_keeps_typed_reason(self) -> None:
        draft = dict(
            base_forecast_id=_BASE_ID,
            effective_forecast_id=_EFF_ID,
            calibration_id=None,
            ticker="AAPL",
            expected_gross_return=None,
            forecast_error_std=None,
            downside_quantiles=None,
            calibrated_positive_probability=None,
            reliability_weight=Decimal("0"),
            effective_until=None,
            status=CalibrationArtifactStatus.UNAVAILABLE,
            unavailable_reason="calibration_unavailable",
            effective_at=_TS,
            known_at=_TS,
        )
        payload = {
            "base_forecast_id": str(_BASE_ID),
            "effective_forecast_id": str(_EFF_ID),
            "calibration_id": None,
            "ticker": "AAPL",
            "expected_gross_return": None,
            "forecast_error_std": None,
            "downside_quantiles": None,
            "calibrated_positive_probability": None,
            "reliability_weight": "0",
            "effective_until": None,
            "status": "unavailable",
            "unavailable_reason": "calibration_unavailable",
            "effective_at": draft["effective_at"].isoformat(),
            "known_at": draft["known_at"].isoformat(),
        }
        content_hash = calibrated_forecast_content_hash(payload=payload)
        subject = CalibratedForecast(
            **draft,
            content_hash=content_hash,
            calibrated_forecast_id=calibrated_forecast_id(
                effective_forecast_id=_EFF_ID,
                calibration_id=None,
                content_hash=content_hash,
            ),
        )
        assert subject.status is CalibrationArtifactStatus.UNAVAILABLE
        assert subject.calibration_id is None

    def test_rejects_foreign_calibration_id_mismatch_on_hash(self) -> None:
        subject = _calibrated()
        with pytest.raises(ValidationError, match="calibrated_forecast_id|content_hash"):
            CalibratedForecast(
                calibrated_forecast_id=subject.calibrated_forecast_id,
                base_forecast_id=_BASE_ID,
                effective_forecast_id=_EFF_ID,
                calibration_id=uuid4(),
                ticker="AAPL",
                expected_gross_return=Decimal("0.03"),
                forecast_error_std=Decimal("0.09"),
                downside_quantiles=(Decimal("-0.20"), Decimal("-0.10")),
                calibrated_positive_probability=Decimal("0.55"),
                reliability_weight=Decimal("0.25"),
                effective_until=_TS + timedelta(days=21),
                status=CalibrationArtifactStatus.AVAILABLE,
                effective_at=_TS,
                known_at=_TS,
                content_hash=subject.content_hash,
            )
