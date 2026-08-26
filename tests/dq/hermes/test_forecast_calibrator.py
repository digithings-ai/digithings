"""Deterministic shadow forecast calibrator (#2680 / WP5.3)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.olympus.hermes import forecast_calibration as fc
from digiquant.olympus.hermes.models.forecast import (
    ForecastTerms,
    RawUncertainty,
)
from digiquant.olympus.hermes.models.forecast_calibration import (
    CalibrationArtifactStatus,
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_AS_OF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
_REF = date(2026, 7, 15)
_MAT = date(2026, 8, 13)
_BASE_ID = UUID("11111111-1111-5111-8111-111111111111")
_EFF_ID = UUID("22222222-2222-5222-8222-222222222222")


def _terms(**over: object) -> ForecastTerms:
    base: dict[str, object] = dict(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return=Decimal("-0.10"),
        base_return=Decimal("0.04"),
        bull_return=Decimal("0.15"),
        bear_probability=Decimal("0.25"),
        base_probability=Decimal("0.50"),
        bull_probability=Decimal("0.25"),
        thesis_valid_probability=Decimal("0.60"),
        raw_uncertainty=RawUncertainty.MEDIUM,
    )
    base.update(over)
    return ForecastTerms(**base)  # type: ignore[arg-type]


def _snapshot(*, session: date, price: str = "100") -> SessionPriceSnapshot:
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=_TS - timedelta(hours=6),
        known_at=_TS - timedelta(hours=5),
    )


def _resolved_outcome(
    *,
    forecast_mean: str = "0.04",
    realized: str = "0.06",
    known_at: datetime = _TS,
    outcome_salt: int = 0,
    horizon_sessions: int = 21,
) -> ForecastOutcome:
    mean = Decimal(forecast_mean)
    real = Decimal(realized)
    residual = real - mean
    # Distinct UUID paths via ticker salt so multiple outcomes don't collide.
    ticker = f"T{outcome_salt:02d}"
    draft: dict[str, object] = dict(
        base_forecast_id=_BASE_ID,
        effective_forecast_id=UUID(f"22222222-2222-5222-8222-{outcome_salt:012d}"),
        ticker=ticker,
        horizon_sessions=horizon_sessions,
        reference_session=_REF,
        maturity_session=_MAT,
        reference_snapshot=_snapshot(session=_REF),
        maturity_snapshot=_snapshot(
            session=_MAT,
            price=str((Decimal("100") * (Decimal("1") + real)).quantize(Decimal("0.00000001"))),
        ),
        forecast_mean_return=mean,
        realized_return=real,
        signed_residual=residual,
        positive_label=real > Decimal("0"),
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=known_at,
        known_at=known_at,
    )
    payload = {
        "base_forecast_id": str(draft["base_forecast_id"]),
        "effective_forecast_id": str(draft["effective_forecast_id"]),
        "ticker": draft["ticker"],
        "horizon_sessions": horizon_sessions,
        "reference_session": _REF.isoformat(),
        "maturity_session": _MAT.isoformat(),
        "reference_snapshot": draft["reference_snapshot"].model_dump(mode="json"),  # type: ignore[union-attr]
        "maturity_snapshot": draft["maturity_snapshot"].model_dump(mode="json"),  # type: ignore[union-attr]
        "forecast_mean_return": str(mean),
        "realized_return": str(real),
        "signed_residual": str(residual),
        "positive_label": draft["positive_label"],
        "status": OutcomeStatus.RESOLVED.value,
        "unavailable_reason": None,
        "event_time": known_at.isoformat(),
        "known_at": known_at.isoformat(),
    }
    content_hash = forecast_outcome_content_hash(payload=payload)
    outcome_id = forecast_outcome_id(
        effective_forecast_id=draft["effective_forecast_id"],  # type: ignore[arg-type]
        maturity_session=_MAT,
        content_hash=content_hash,
    )
    return ForecastOutcome(
        outcome_id=outcome_id,
        content_hash=content_hash,
        **draft,  # type: ignore[arg-type]
    )


class TestScenarioMeanAndPositiveMass:
    def test_scenario_mean_matches_terms(self) -> None:
        terms = _terms()
        assert terms.scenario_mean_return() == (
            Decimal("0.25") * Decimal("-0.10")
            + Decimal("0.50") * Decimal("0.04")
            + Decimal("0.25") * Decimal("0.15")
        )

    def test_scenario_positive_probability_strictly_positive_returns(self) -> None:
        terms = _terms()
        # base 0.04 and bull 0.15 are positive → 0.50 + 0.25
        assert fc.scenario_positive_probability(terms) == Decimal("0.75000000")


class TestCalibrateCohort:
    def test_empty_cohort_unavailable(self) -> None:
        cal = fc.calibrate_cohort([], cohort_key="horizon:21|regime:default", as_of=_AS_OF)
        assert cal.status is CalibrationArtifactStatus.UNAVAILABLE
        assert cal.unavailable_reason == "empty_cohort"
        assert cal.reliability == Decimal("0")
        assert cal.sample_count == 0
        assert cal.prior_definition == fc.PRIOR_DEFINITION
        assert cal.method_version == fc.METHOD_VERSION

    def test_late_known_exclusion(self) -> None:
        early = _resolved_outcome(realized="0.06", known_at=_TS, outcome_salt=1)
        late = _resolved_outcome(
            realized="0.10",
            known_at=_AS_OF + timedelta(hours=1),
            outcome_salt=2,
        )
        cal = fc.calibrate_cohort(
            [early, late],
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        assert cal.status is CalibrationArtifactStatus.AVAILABLE
        assert cal.sample_count == 1
        assert early.outcome_id in cal.outcome_ids
        assert late.outcome_id not in cal.outcome_ids

    def test_one_sample_low_reliability_nonzero_dispersion(self) -> None:
        o = _resolved_outcome(forecast_mean="0.04", realized="0.06", outcome_salt=3)
        cal = fc.calibrate_cohort(
            [o],
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        assert cal.status is CalibrationArtifactStatus.AVAILABLE
        assert cal.sample_count == 1
        # n/(n+n0) = 1/9
        assert cal.reliability == Decimal("0.11111111")
        assert cal.dispersion == fc.DISPERSION_FLOOR
        assert cal.dispersion > Decimal("0")
        assert cal.bias is not None
        # residual 0.02 shrunk: (1/9)*0.02
        assert cal.bias == Decimal("0.00222222")
        assert cal.brier_score is not None
        assert cal.log_score is not None
        assert Decimal("0") <= cal.reliability <= Decimal("1")

    def test_adequate_cohort_higher_reliability(self) -> None:
        outcomes = [
            _resolved_outcome(
                forecast_mean="0.04",
                realized=str(Decimal("0.02") + Decimal("0.01") * i),
                known_at=_TS + timedelta(minutes=i),
                outcome_salt=10 + i,
            )
            for i in range(8)
        ]
        cal = fc.calibrate_cohort(
            outcomes,
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        assert cal.status is CalibrationArtifactStatus.AVAILABLE
        assert cal.sample_count == 8
        # 8/(8+8) = 0.5
        assert cal.reliability == Decimal("0.50000000")
        assert cal.dispersion is not None
        assert cal.dispersion >= fc.DISPERSION_FLOOR
        assert cal.brier_score is not None
        assert Decimal("0") <= cal.brier_score <= Decimal("1")

    def test_input_order_deterministic(self) -> None:
        a = _resolved_outcome(realized="0.05", known_at=_TS, outcome_salt=20)
        b = _resolved_outcome(
            realized="0.08",
            known_at=_TS + timedelta(minutes=1),
            outcome_salt=21,
        )
        c = _resolved_outcome(
            realized="-0.02",
            known_at=_TS + timedelta(minutes=2),
            outcome_salt=22,
        )
        forward = fc.calibrate_cohort(
            [a, b, c],
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        reverse = fc.calibrate_cohort(
            [c, b, a],
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        assert forward.calibration_id == reverse.calibration_id
        assert forward.content_hash == reverse.content_hash
        assert forward.bias == reverse.bias
        assert forward.outcome_ids == reverse.outcome_ids

    def test_identical_cohorts_identical_ids(self) -> None:
        outcomes = [
            _resolved_outcome(realized="0.06", outcome_salt=30),
            _resolved_outcome(realized="0.01", outcome_salt=31),
        ]
        first = fc.calibrate_cohort(
            outcomes,
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        second = fc.calibrate_cohort(
            list(outcomes),
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        assert first.calibration_id == second.calibration_id
        assert first.model_dump() == second.model_dump()


class TestCalibrateSubject:
    def test_uses_scenario_mean_minus_bias(self) -> None:
        o = _resolved_outcome(forecast_mean="0.04", realized="0.06", outcome_salt=40)
        terms = _terms()
        bundle = fc.calibrate_forecast(
            outcomes=[o],
            terms=terms,
            base_forecast_id=_BASE_ID,
            effective_forecast_id=_EFF_ID,
            ticker="AAPL",
            as_of=_AS_OF,
        )
        assert bundle.calibration.status is CalibrationArtifactStatus.AVAILABLE
        subject = bundle.calibrated_forecast
        assert subject.status is CalibrationArtifactStatus.AVAILABLE
        raw = terms.scenario_mean_return()
        assert subject.expected_gross_return == (raw - bundle.calibration.bias).quantize(
            Decimal("0.00000001")
        )
        assert subject.forecast_error_std is not None
        assert subject.forecast_error_std > Decimal("0")
        assert subject.downside_quantiles is not None
        assert list(subject.downside_quantiles) == sorted(subject.downside_quantiles)
        assert subject.reliability_weight == bundle.calibration.reliability
        assert Decimal("0") <= subject.reliability_weight <= Decimal("1")

    def test_unavailable_calibration_yields_unavailable_subject(self) -> None:
        terms = _terms()
        bundle = fc.calibrate_forecast(
            outcomes=[],
            terms=terms,
            base_forecast_id=_BASE_ID,
            effective_forecast_id=_EFF_ID,
            ticker="AAPL",
            as_of=_AS_OF,
        )
        assert bundle.calibration.status is CalibrationArtifactStatus.UNAVAILABLE
        assert bundle.calibrated_forecast.status is CalibrationArtifactStatus.UNAVAILABLE
        assert bundle.calibrated_forecast.calibration_id is None
        assert bundle.calibrated_forecast.reliability_weight == Decimal("0")

    def test_sparse_remains_low_reliability(self) -> None:
        o = _resolved_outcome(outcome_salt=50)
        bundle = fc.calibrate_forecast(
            outcomes=[o],
            terms=_terms(),
            base_forecast_id=_BASE_ID,
            effective_forecast_id=_EFF_ID,
            ticker="MSFT",
            as_of=_AS_OF,
        )
        assert bundle.calibrated_forecast.reliability_weight < Decimal("0.2")


class TestDeclaredPriorMetadata:
    def test_prior_definition_declares_formula_and_methods(self) -> None:
        assert "zero_mean_shrinkage@v1" in fc.PRIOR_DEFINITION
        assert "n0=8" in fc.PRIOR_DEFINITION
        assert fc.SHRINKAGE_FORMULA in fc.PRIOR_DEFINITION
        assert fc.DOWNSIDE_METHOD in fc.PRIOR_DEFINITION
        assert "empirical_threshold=n>=3" in fc.PRIOR_DEFINITION
        assert fc.METHOD_VERSION == "shadow-calibrator@1"

    def test_cohort_key_helper(self) -> None:
        assert fc.cohort_key_for_horizon(21) == "horizon:21|regime:default"
        assert fc.horizon_sessions_from_cohort_key("horizon:21|regime:default") == 21
        assert fc.horizon_sessions_from_cohort_key("other") is None

    def test_mixed_horizon_union_does_not_contaminate_cohorts(self) -> None:
        """Gate 2 / #2797: horizon:N keys must not share residuals across horizons."""
        h21 = [
            _resolved_outcome(
                realized="0.50",
                known_at=_TS + timedelta(minutes=i),
                outcome_salt=100 + i,
                horizon_sessions=21,
            )
            for i in range(5)
        ]
        h5 = [
            _resolved_outcome(
                realized="-0.20",
                known_at=_TS + timedelta(minutes=10 + i),
                outcome_salt=200 + i,
                horizon_sessions=5,
            )
            for i in range(2)
        ]
        union = [*h21, *h5]
        cal21 = fc.calibrate_cohort(
            union,
            cohort_key="horizon:21|regime:default",
            as_of=_AS_OF,
        )
        cal5 = fc.calibrate_cohort(
            union,
            cohort_key="horizon:5|regime:default",
            as_of=_AS_OF,
        )
        assert cal21.status is CalibrationArtifactStatus.AVAILABLE
        assert cal5.status is CalibrationArtifactStatus.AVAILABLE
        assert cal21.sample_count == 5
        assert cal5.sample_count == 2
        assert cal21.bias != cal5.bias


class TestNoH8Coupling:
    def test_module_does_not_import_sizing(self) -> None:
        import digiquant.olympus.hermes.forecast_calibration as mod

        src = open(mod.__file__, encoding="utf-8").read()
        assert "sizing" not in src
        assert "phase7e" not in src
        assert "sized_book" not in src
