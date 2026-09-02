"""WP5.4 (#2684): attach + persist shadow forecast calibration at H6/H7 boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.research import forecast_registry as fr
from digiquant.research.state import ResearchState, PhasePortfolioState, PriorContext
from digiquant.portfolio import forecast_calibration as fc
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    EffectiveSource,
    ForecastTerms,
    RawUncertainty,
    forecast_terms_content_hash,
)
from digiquant.portfolio.models.forecast_calibration import (
    CalibrationArtifactStatus,
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from digiquant.portfolio.phases.h7_pm_direction import build_h7_pm_direction

from tests.dq.research.test_forecast_registry import RegistryFake, _assessment

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 25)
_TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
_AS_OF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
_REF = date(2026, 7, 15)
_MAT = date(2026, 8, 13)
_BASE_ID = UUID("11111111-1111-5111-8111-111111111111")
_EFF_ID = UUID("33333333-3333-5333-8333-333333333333")


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


def _effective(*, ticker: str = "AAPL") -> EffectiveForecast:
    terms = _terms()
    return EffectiveForecast(
        effective_id=_EFF_ID,
        ticker=ticker,
        base_forecast_id=_BASE_ID,
        amendment_id=None,
        source=EffectiveSource.BASE,
        terms=terms,
        content_hash=forecast_terms_content_hash(terms),
        amendment_outcome=AmendmentOutcome.NONE,
        degradation_reason=None,
        effective_at=_TS,
        known_at=_TS,
    )


def _snapshot(*, session: date, price: str = "100") -> SessionPriceSnapshot:
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=_TS - timedelta(hours=6),
        known_at=_TS - timedelta(hours=5),
    )


def _resolved_outcome(
    *, salt: int = 0, known_at: datetime = _TS, horizon_sessions: int = 21
) -> ForecastOutcome:
    mean = Decimal("0.04")
    real = Decimal("0.06")
    residual = real - mean
    ticker = f"T{salt:02d}"
    draft: dict[str, object] = dict(
        base_forecast_id=_BASE_ID,
        effective_forecast_id=UUID(f"22222222-2222-5222-8222-{salt:012d}"),
        ticker=ticker,
        horizon_sessions=horizon_sessions,
        reference_session=_REF,
        maturity_session=_MAT,
        reference_snapshot=_snapshot(session=_REF),
        maturity_snapshot=_snapshot(session=_MAT, price="106"),
        forecast_mean_return=mean,
        realized_return=real,
        signed_residual=residual,
        positive_label=True,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=known_at,
        known_at=known_at,
    )
    payload = {
        **{k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in draft.items()},
        "base_forecast_id": str(draft["base_forecast_id"]),
        "effective_forecast_id": str(draft["effective_forecast_id"]),
        "horizon_sessions": horizon_sessions,
        "reference_snapshot": draft["reference_snapshot"].model_dump(mode="json"),  # type: ignore[union-attr]
        "maturity_snapshot": draft["maturity_snapshot"].model_dump(mode="json"),  # type: ignore[union-attr]
        "forecast_mean_return": str(mean),
        "realized_return": str(real),
        "signed_residual": str(residual),
        "status": OutcomeStatus.RESOLVED.value,
        "event_time": known_at.isoformat(),
        "known_at": known_at.isoformat(),
        "reference_session": _REF.isoformat(),
        "maturity_session": _MAT.isoformat(),
    }
    content_hash = forecast_outcome_content_hash(payload=payload)
    outcome_id = forecast_outcome_id(
        effective_forecast_id=draft["effective_forecast_id"],  # type: ignore[arg-type]
        maturity_session=_MAT,
        content_hash=content_hash,
    )
    return ForecastOutcome(outcome_id=outcome_id, content_hash=content_hash, **draft)  # type: ignore[arg-type]


def _state_with_effective(*, ticker: str = "AAPL") -> ResearchState:
    eff = _effective(ticker=ticker)
    return ResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 8, 24),
        knowledge_cutoff_at=_AS_OF,
        prior_context=PriorContext(),
        phase_portfolio=PhasePortfolioState(
            deliberation_summaries={
                ticker: {
                    "ticker": ticker,
                    "net_stance": "buy",
                    "effective_forecast_id": str(eff.effective_id),
                    "base_forecast_id": str(eff.base_forecast_id),
                    "effective_forecast": eff.model_dump(mode="json"),
                }
            }
        ),
    )


class TestAttachShadowCalibrations:
    def test_empty_subjects_yield_empty_attachment(self) -> None:
        attachment = fc.attach_shadow_calibrations(
            subjects=[],
            outcomes=[_resolved_outcome()],
            as_of=_AS_OF,
        )
        assert attachment.calibrations == ()
        assert attachment.calibrated_forecasts == ()

    def test_empty_cohort_emits_typed_unavailable_subject(self) -> None:
        attachment = fc.attach_shadow_calibrations(
            subjects=[_effective()],
            outcomes=[],
            as_of=_AS_OF,
        )
        assert len(attachment.calibrations) == 1
        assert attachment.calibrations[0].status is CalibrationArtifactStatus.UNAVAILABLE
        assert attachment.calibrations[0].unavailable_reason == "empty_cohort"
        assert len(attachment.calibrated_forecasts) == 1
        subject = attachment.calibrated_forecasts[0]
        assert subject.status is CalibrationArtifactStatus.UNAVAILABLE
        assert subject.ticker == "AAPL"
        assert subject.calibration_id is None

    def test_late_known_outcomes_excluded(self) -> None:
        late = _resolved_outcome(salt=1, known_at=_AS_OF + timedelta(hours=2))
        attachment = fc.attach_shadow_calibrations(
            subjects=[_effective()],
            outcomes=[late],
            as_of=_AS_OF,
        )
        assert attachment.calibrations[0].status is CalibrationArtifactStatus.UNAVAILABLE

    def test_resolved_cohort_emits_available_shadow(self) -> None:
        outcomes = [_resolved_outcome(salt=i) for i in range(3)]
        attachment = fc.attach_shadow_calibrations(
            subjects=[_effective()],
            outcomes=outcomes,
            as_of=_AS_OF,
        )
        assert attachment.calibrations[0].status is CalibrationArtifactStatus.AVAILABLE
        subject = attachment.calibrated_forecasts[0]
        assert subject.status is CalibrationArtifactStatus.AVAILABLE
        assert subject.calibration_id == attachment.calibrations[0].calibration_id
        assert subject.forecast_error_std is not None and subject.forecast_error_std > 0

    def test_from_state_collects_effective_forecasts(self) -> None:
        state = _state_with_effective()
        attachment = fc.attach_shadow_calibrations_from_state(
            state,
            outcomes=[_resolved_outcome(salt=0)],
        )
        assert len(attachment.calibrated_forecasts) == 1
        assert "AAPL" in attachment.calibrated_forecast_dumps()

    def test_from_state_without_cutoff_returns_empty(self) -> None:
        """#2797: never stamp identities with datetime.now when cutoff is missing."""
        state = ResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            baseline_date=date(2026, 8, 24),
            knowledge_cutoff_at=None,
            prior_context=PriorContext(),
            phase_portfolio=PhasePortfolioState(
                deliberation_summaries={
                    "AAPL": {
                        "effective_forecast": _effective().model_dump(mode="json"),
                    }
                }
            ),
        )
        attachment = fc.attach_shadow_calibrations_from_state(
            state,
            outcomes=[_resolved_outcome(salt=0)],
        )
        assert attachment.calibrations == ()
        assert attachment.calibrated_forecasts == ()

    def test_attach_filters_outcomes_by_subject_horizon(self) -> None:
        outcomes = [
            *[_resolved_outcome(salt=i, horizon_sessions=21) for i in range(3)],
            *[_resolved_outcome(salt=10 + i, horizon_sessions=5) for i in range(4)],
        ]
        attachment = fc.attach_shadow_calibrations(
            subjects=[_effective()],
            outcomes=outcomes,
            as_of=_AS_OF,
        )
        assert attachment.calibrations[0].cohort_key == "horizon:21|regime:default"
        assert attachment.calibrations[0].sample_count == 3


class TestPersistShadowCalibrations:
    def test_exact_retry_skips(self) -> None:
        client = RegistryFake()
        assessment = _assessment()
        fr.persist_forecast_lineage(client=client, assessments=[assessment])
        outcomes = [_resolved_outcome(salt=0)]
        attachment = fc.attach_shadow_calibrations(
            subjects=[
                EffectiveForecast(
                    effective_id=assessment.forecast_id,
                    ticker=assessment.ticker,
                    base_forecast_id=assessment.forecast_id,
                    amendment_id=None,
                    source=EffectiveSource.BASE,
                    terms=assessment.terms,
                    content_hash=assessment.content_hash,
                    amendment_outcome=AmendmentOutcome.NONE,
                    degradation_reason=None,
                    effective_at=_TS,
                    known_at=_TS,
                )
            ],
            outcomes=outcomes,
            as_of=_AS_OF,
        )
        # Force base id match for FK
        subject = attachment.calibrated_forecasts[0]
        # Rebuild subject against the persisted assessment id
        rebuilt = fc.calibrate_subject(
            base_forecast_id=assessment.forecast_id,
            effective_forecast_id=assessment.forecast_id,
            ticker=assessment.ticker,
            terms=assessment.terms,
            calibration=attachment.calibrations[0],
            as_of=_AS_OF,
        )
        first = fr.persist_shadow_calibrations(
            client=client,
            calibrations=attachment.calibrations,
            calibrated_forecasts=[rebuilt],
        )
        second = fr.persist_shadow_calibrations(
            client=client,
            calibrations=attachment.calibrations,
            calibrated_forecasts=[rebuilt],
        )
        assert first.calibrations_written == 1
        assert first.calibrated_forecasts_written == 1
        assert second.calibrations_skipped == 1
        assert second.calibrated_forecasts_skipped == 1
        assert len(client.store.get(fr.CALIBRATIONS, [])) == 1
        assert len(client.store.get(fr.CALIBRATED_FORECASTS, [])) == 1
        assert subject.ticker == "AAPL" or rebuilt.ticker == assessment.ticker.upper()

    def test_from_state_persists_shadow_slots(self) -> None:
        client = RegistryFake()
        assessment = _assessment()
        fr.persist_forecast_lineage(client=client, assessments=[assessment])
        attachment = fc.attach_shadow_calibrations(
            subjects=[
                EffectiveForecast(
                    effective_id=assessment.forecast_id,
                    ticker=assessment.ticker,
                    base_forecast_id=assessment.forecast_id,
                    amendment_id=None,
                    source=EffectiveSource.BASE,
                    terms=assessment.terms,
                    content_hash=assessment.content_hash,
                    amendment_outcome=AmendmentOutcome.NONE,
                    degradation_reason=None,
                    effective_at=_TS,
                    known_at=_TS,
                )
            ],
            outcomes=[],
            as_of=_AS_OF,
        )
        state = ResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            baseline_date=date(2026, 8, 24),
            prior_context=PriorContext(),
            phase_portfolio=PhasePortfolioState(
                asset_analysts={"SPY": {"forecast_assessment": assessment.model_dump(mode="json")}},
                forecast_calibrations=attachment.calibration_dumps(),
                calibrated_forecasts=attachment.calibrated_forecast_dumps(),
            ),
        )
        result = fr.persist_forecast_lineage_from_state(client=client, state=state)
        assert result.assessments_skipped == 1  # already written
        assert result.calibrations_written == 1
        # unavailable subject has no calibration FK — still inserts
        assert result.calibrated_forecasts_written == 1


class TestH7BoundaryAttach:
    def test_h7_attaches_shadow_without_feeding_memo_economics(self) -> None:
        from unittest.mock import patch

        from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection

        state = _state_with_effective()
        phase = build_h7_pm_direction(client=None)
        node = phase.nodes[0].run
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
        )
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            return_value=memo,
        ):
            out = node(state)
        portfolio = out["phase_portfolio"]
        assert portfolio.pm_direction_memo is not None
        assert portfolio.forecast_calibrations
        assert portfolio.calibrated_forecasts
        # H7 memo still direction-only — no calibrated economics on the memo.
        assert not hasattr(portfolio.pm_direction_memo.roster[0], "expected_gross_return")
        assert "AAPL" in portfolio.calibrated_forecasts
        assert (
            portfolio.calibrated_forecasts["AAPL"]["status"]
            == CalibrationArtifactStatus.UNAVAILABLE.value
        )
