"""WP9.1/WP9.2 — PreTradeRiskReport contracts and deterministic builders (#2742/#2746)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from digiquant.olympus.hermes.allocation_contracts import (
    AlteredTarget,
    BindingConstraint,
    BookWeightsView,
    ConcentrationBlock,
    ControlOutcomesBlock,
    CostLiquidityReportBlock,
    ExposureBlock,
    ForecastQualityBlock,
    MetricProvenance,
    NameSectorFactorScenarioBlock,
    PerAssetRiskContribution,
    PortfolioRiskBlock,
    PreTradeRiskReport,
    RejectedTarget,
    ReportMetricStatus,
    ReportWeightEntry,
    ScalarMetric,
    TradeDeltaEntry,
)
from digiquant.olympus.hermes.allocation_hashes import (
    pretrade_risk_report_content_hash,
    weights_fingerprint,
)
from digiquant.olympus.hermes.models.risk_policy import (
    CovarianceSnapshot,
    PolicyArtifactStatus,
    covariance_snapshot_content_hash,
    covariance_snapshot_id,
    snapshot_hash_payload,
)
from digiquant.olympus.hermes.pretrade_risk import (
    CostLiquidityScalars,
    ForecastQualityScalars,
    PreTradeRiskBuildRequest,
    build_pretrade_risk_report,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_SESSION = date(2026, 8, 26)
_BUNDLE_HASH = "a" * 64
_POLICY_HASH = "b" * 64
_COV_HASH = "c" * 64


def _available(
    value: float, provenance: MetricProvenance = MetricProvenance.DERIVED
) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.AVAILABLE,
        value=value,
        provenance=provenance,
    )


def _unavailable(reason: str) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.UNAVAILABLE,
        unavailable_reason=reason,
    )


def _degraded(
    value: float,
    reason: str,
    provenance: MetricProvenance = MetricProvenance.DERIVED,
) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.DEGRADED,
        value=value,
        provenance=provenance,
        unavailable_reason=reason,
    )


def _weights(
    entries: tuple[tuple[str, float], ...],
    cash: float,
) -> BookWeightsView:
    weight_map = {ticker: weight for ticker, weight in entries}
    return BookWeightsView(
        entries=tuple(ReportWeightEntry(ticker=t, weight_pct=w) for t, w in entries),
        cash_weight_pct=cash,
        weights_fingerprint=weights_fingerprint(weight_map),
    )


def _complete_report(**overrides: object) -> PreTradeRiskReport:
    prior = _weights((("AAPL", 30.0), ("MSFT", 20.0)), cash=50.0)
    final = _weights((("AAPL", 40.0), ("MSFT", 25.0)), cash=35.0)
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "run-2742",
        "session_date": _SESSION,
        "status": ReportMetricStatus.AVAILABLE,
        "allocation_input_bundle_hash": _BUNDLE_HASH,
        "final_book_weights_fingerprint": final.weights_fingerprint,
        "prior_weights": prior,
        "final_weights": final,
        "trade_deltas": (
            TradeDeltaEntry(ticker="AAPL", delta_weight_pct=10.0),
            TradeDeltaEntry(ticker="MSFT", delta_weight_pct=5.0),
        ),
        "exposures": ExposureBlock(
            gross_exposure_pct=_available(65.0, MetricProvenance.FINAL_BOOK),
            net_exposure_pct=_available(65.0, MetricProvenance.FINAL_BOOK),
            cash_weight_pct=_available(35.0, MetricProvenance.FINAL_BOOK),
        ),
        "portfolio_risk": PortfolioRiskBlock(
            variance=_available(0.04, MetricProvenance.COVARIANCE_SNAPSHOT),
            volatility_annualized_pct=_available(20.0, MetricProvenance.COVARIANCE_SNAPSHOT),
            contributions=(
                PerAssetRiskContribution(
                    ticker="AAPL",
                    marginal_risk=_available(0.12, MetricProvenance.COVARIANCE_SNAPSHOT),
                    component_risk=_available(0.08, MetricProvenance.COVARIANCE_SNAPSHOT),
                ),
                PerAssetRiskContribution(
                    ticker="MSFT",
                    marginal_risk=_available(0.09, MetricProvenance.COVARIANCE_SNAPSHOT),
                    component_risk=_available(0.05, MetricProvenance.COVARIANCE_SNAPSHOT),
                ),
            ),
        ),
        "concentration": ConcentrationBlock(
            herfindahl=_available(0.3, MetricProvenance.FINAL_BOOK),
            effective_bets=_available(3.3, MetricProvenance.FINAL_BOOK),
            max_name_weight_pct=_available(40.0, MetricProvenance.FINAL_BOOK),
        ),
        "name_sector_factor_scenario": NameSectorFactorScenarioBlock(
            name_max_weight_pct=_available(40.0, MetricProvenance.FINAL_BOOK),
            sector_max_weight_pct=_unavailable("sector map not bound"),
            factor_exposure=_unavailable("factor model not configured"),
            scenario_stress_pct=_unavailable("scenario library not configured"),
        ),
        "cost_liquidity": CostLiquidityReportBlock(
            expected_cost=_available(12.5, MetricProvenance.COST_LIQUIDITY),
            turnover_pct=_available(15.0, MetricProvenance.DERIVED),
            adv_participation_pct=_available(2.0, MetricProvenance.COST_LIQUIDITY),
            days_to_liquidate=_available(1.0, MetricProvenance.COST_LIQUIDITY),
        ),
        "forecast_quality": ForecastQualityBlock(
            staleness_sessions=_available(0.0, MetricProvenance.ALLOCATION_BUNDLE),
            forecast_uncertainty=_available(0.02, MetricProvenance.ALLOCATION_BUNDLE),
            degraded_input_count=_available(0.0, MetricProvenance.ALLOCATION_BUNDLE),
        ),
        "controls": ControlOutcomesBlock(
            binding_constraints=(
                BindingConstraint(
                    constraint_id="single_name_cap",
                    constraint_kind="single_name_cap",
                    ticker="AAPL",
                    bound_value=40.0,
                    observed_value=40.0,
                    reason="position cap binding",
                ),
            ),
            altered_targets=(
                AlteredTarget(
                    ticker="AAPL",
                    requested_weight_pct=48.0,
                    final_weight_pct=40.0,
                    adjustment_type="single_name_cap",
                    reason="single-name cap applied",
                ),
            ),
            rejected_targets=(),
        ),
        "risk_policy_hash": _POLICY_HASH,
        "covariance_hash": _COV_HASH,
    }
    payload.update(overrides)
    draft = PreTradeRiskReport.model_construct(
        schema_version="1.0",
        run_id=str(payload["run_id"]),
        session_date=payload["session_date"],  # type: ignore[arg-type]
        status=payload["status"],  # type: ignore[arg-type]
        unavailable_reason=payload.get("unavailable_reason"),  # type: ignore[arg-type]
        allocation_input_bundle_hash=str(payload["allocation_input_bundle_hash"]),
        final_book_weights_fingerprint=str(payload["final_book_weights_fingerprint"]),
        prior_weights=payload["prior_weights"],  # type: ignore[arg-type]
        final_weights=payload["final_weights"],  # type: ignore[arg-type]
        trade_deltas=payload["trade_deltas"],  # type: ignore[arg-type]
        exposures=payload["exposures"],  # type: ignore[arg-type]
        portfolio_risk=payload["portfolio_risk"],  # type: ignore[arg-type]
        concentration=payload["concentration"],  # type: ignore[arg-type]
        name_sector_factor_scenario=payload["name_sector_factor_scenario"],  # type: ignore[arg-type]
        cost_liquidity=payload["cost_liquidity"],  # type: ignore[arg-type]
        forecast_quality=payload["forecast_quality"],  # type: ignore[arg-type]
        controls=payload["controls"],  # type: ignore[arg-type]
        risk_policy_hash=str(payload["risk_policy_hash"]),
        covariance_hash=payload.get("covariance_hash"),  # type: ignore[arg-type]
        report_content_hash="",
    )
    report_hash = pretrade_risk_report_content_hash(payload=draft._hash_payload())
    return PreTradeRiskReport.model_validate({**payload, "report_content_hash": report_hash})


def test_complete_report_constructs_and_hashes_stably() -> None:
    report = _complete_report()
    again = _complete_report()
    assert report.status is ReportMetricStatus.AVAILABLE
    assert report.report_content_hash == again.report_content_hash
    assert len(report.report_content_hash) == 64
    assert report.final_book_weights_fingerprint == report.final_weights.weights_fingerprint
    assert report.controls.binding_constraints[0].constraint_kind == "single_name_cap"
    assert report.controls.altered_targets[0].adjustment_type == "single_name_cap"


def test_degraded_report_allows_mix_of_metric_states() -> None:
    report = _complete_report(
        status=ReportMetricStatus.DEGRADED,
        unavailable_reason="covariance degraded; sector exposures unavailable",
        portfolio_risk=PortfolioRiskBlock(
            variance=_degraded(
                0.05, "shrinkage fallback used", MetricProvenance.COVARIANCE_SNAPSHOT
            ),
            volatility_annualized_pct=_degraded(
                22.0, "shrinkage fallback used", MetricProvenance.COVARIANCE_SNAPSHOT
            ),
            contributions=(
                PerAssetRiskContribution(
                    ticker="AAPL",
                    marginal_risk=_unavailable("ticker missing from covariance"),
                    component_risk=_unavailable("ticker missing from covariance"),
                ),
                PerAssetRiskContribution(
                    ticker="MSFT",
                    marginal_risk=_available(0.09, MetricProvenance.COVARIANCE_SNAPSHOT),
                    component_risk=_available(0.05, MetricProvenance.COVARIANCE_SNAPSHOT),
                ),
            ),
        ),
    )
    assert report.status is ReportMetricStatus.DEGRADED
    assert report.unavailable_reason is not None
    assert report.portfolio_risk.variance.status is ReportMetricStatus.DEGRADED
    assert (
        report.portfolio_risk.contributions[0].marginal_risk.status
        is ReportMetricStatus.UNAVAILABLE
    )


def test_unavailable_report_requires_reason_and_forbids_values() -> None:
    with pytest.raises(ValidationError, match="unavailable"):
        ScalarMetric(
            status=ReportMetricStatus.UNAVAILABLE, value=1.0, provenance=MetricProvenance.DERIVED
        )

    with pytest.raises(ValidationError, match="unavailable_reason"):
        ScalarMetric(status=ReportMetricStatus.UNAVAILABLE)

    metric = _unavailable("covariance snapshot missing")
    assert metric.value is None
    assert metric.provenance is None


def test_available_metric_requires_value_and_provenance() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        ScalarMetric(status=ReportMetricStatus.AVAILABLE, value=1.0)
    with pytest.raises(ValidationError, match="value"):
        ScalarMetric(status=ReportMetricStatus.AVAILABLE, provenance=MetricProvenance.DERIVED)
    with pytest.raises(ValidationError, match="unavailable_reason"):
        ScalarMetric(
            status=ReportMetricStatus.AVAILABLE,
            value=1.0,
            provenance=MetricProvenance.DERIVED,
            unavailable_reason="nope",
        )


def test_rejects_nan_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ScalarMetric(
            status=ReportMetricStatus.AVAILABLE,
            value=float("nan"),
            provenance=MetricProvenance.DERIVED,
        )
    with pytest.raises(ValidationError, match="extra"):
        ScalarMetric(
            status=ReportMetricStatus.AVAILABLE,
            value=1.0,
            provenance=MetricProvenance.DERIVED,
            surprise=True,
        )


def test_rejects_unsorted_trade_deltas_and_contributions() -> None:
    report = _complete_report()
    with pytest.raises(ValidationError, match="sorted"):
        _complete_report(
            trade_deltas=(
                TradeDeltaEntry(ticker="MSFT", delta_weight_pct=5.0),
                TradeDeltaEntry(ticker="AAPL", delta_weight_pct=10.0),
            ),
        )
    with pytest.raises(ValidationError, match="sorted"):
        _complete_report(
            portfolio_risk=PortfolioRiskBlock(
                variance=report.portfolio_risk.variance,
                volatility_annualized_pct=report.portfolio_risk.volatility_annualized_pct,
                contributions=tuple(reversed(report.portfolio_risk.contributions)),
            ),
        )


def test_final_book_fingerprint_must_match_final_weights() -> None:
    with pytest.raises(ValidationError, match="final_book_weights_fingerprint"):
        _complete_report(final_book_weights_fingerprint="0" * 64)


def test_book_weights_fingerprint_must_match_entries() -> None:
    with pytest.raises(ValidationError, match="weights_fingerprint"):
        BookWeightsView(
            entries=(ReportWeightEntry(ticker="AAPL", weight_pct=10.0),),
            cash_weight_pct=90.0,
            weights_fingerprint="0" * 64,
        )


def test_binding_constraints_and_rejected_targets_represented() -> None:
    report = _complete_report(
        controls=ControlOutcomesBlock(
            binding_constraints=(
                BindingConstraint(
                    constraint_id="gross_cap",
                    constraint_kind="gross_cap",
                    ticker=None,
                    bound_value=80.0,
                    observed_value=80.0,
                    reason="gross exposure at policy cap",
                ),
            ),
            altered_targets=(),
            rejected_targets=(
                RejectedTarget(
                    ticker="TSLA",
                    requested_weight_pct=10.0,
                    reason="excluded from calibrated coverage",
                ),
            ),
        ),
    )
    assert report.controls.binding_constraints[0].constraint_kind == "gross_cap"
    assert report.controls.rejected_targets[0].ticker == "TSLA"


def test_source_change_changes_report_hash() -> None:
    base = _complete_report()
    mutated = _complete_report(
        exposures=ExposureBlock(
            gross_exposure_pct=_available(70.0, MetricProvenance.FINAL_BOOK),
            net_exposure_pct=_available(70.0, MetricProvenance.FINAL_BOOK),
            cash_weight_pct=_available(30.0, MetricProvenance.FINAL_BOOK),
        ),
    )
    assert base.report_content_hash != mutated.report_content_hash


# ── WP9.2 deterministic builders (#2746) ─────────────────────────────────────

_CUTOFF = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)


def _cov_snapshot(
    tickers: tuple[str, ...],
    matrix: tuple[tuple[float, ...], ...],
    *,
    status: PolicyArtifactStatus = PolicyArtifactStatus.AVAILABLE,
    unavailable_reason: str | None = None,
) -> CovarianceSnapshot:
    draft = CovarianceSnapshot.model_construct(
        snapshot_id=covariance_snapshot_id(
            as_of_session=_SESSION, tickers=tickers, content_hash="0" * 64
        ),
        method_version="incumbent-covariance@v1",
        as_of_session=_SESSION,
        lookback_days=63,
        estimator="pearson_daily_return",
        shrinkage="none",
        fallback_policy="asset_class_bucket@v1",
        tickers=tickers,
        matrix=matrix,
        observation_count=40,
        source_table=None,
        resolved_at=_CUTOFF,
        status=status,
        unavailable_reason=unavailable_reason,
        content_hash="0" * 64,
    )
    content_hash = covariance_snapshot_content_hash(payload=snapshot_hash_payload(draft))
    return CovarianceSnapshot.model_validate(
        {
            **draft.model_dump(mode="json"),
            "content_hash": content_hash,
            "snapshot_id": str(
                covariance_snapshot_id(
                    as_of_session=_SESSION, tickers=tickers, content_hash=content_hash
                )
            ),
        }
    )


def _base_request(**overrides: object) -> PreTradeRiskBuildRequest:
    payload: dict[str, object] = {
        "run_id": "run-2746",
        "session_date": _SESSION,
        "allocation_input_bundle_hash": _BUNDLE_HASH,
        "risk_policy_hash": _POLICY_HASH,
        "prior_risky_weights_pct": {},
        "prior_cash_weight_pct": 100.0,
        "final_risky_weights_pct": {},
        "final_cash_weight_pct": 100.0,
        "cost_liquidity": CostLiquidityScalars(
            expected_cost=0.0,
            adv_participation_pct=0.0,
            days_to_liquidate=1.0,
        ),
        "forecast_quality": ForecastQualityScalars(
            staleness_sessions=0.0,
            forecast_uncertainty=0.0,
            degraded_input_count=0.0,
        ),
    }
    payload.update(overrides)
    return PreTradeRiskBuildRequest(**payload)  # type: ignore[arg-type]


def test_one_asset_variance_mrc_crc_hand_calculated() -> None:
    # w=0.5, σ=0.20 → var=0.01, σ_p=0.10, MRC=0.20, CRC=0.10
    snapshot = _cov_snapshot(("AAPL",), ((1.0,),))
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAPL": 50.0},
            final_cash_weight_pct=50.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0},
        )
    )
    assert report.status is ReportMetricStatus.AVAILABLE
    assert report.portfolio_risk.variance.value == pytest.approx(0.01)
    assert report.portfolio_risk.volatility_annualized_pct.value == pytest.approx(10.0)
    contrib = report.portfolio_risk.contributions[0]
    assert contrib.ticker == "AAPL"
    assert contrib.marginal_risk.value == pytest.approx(0.2)
    assert contrib.component_risk.value == pytest.approx(0.1)
    assert report.covariance_hash == snapshot.content_hash
    assert report.allocation_input_bundle_hash == _BUNDLE_HASH
    assert report.risk_policy_hash == _POLICY_HASH
    assert report.concentration.herfindahl.value == pytest.approx(1.0)
    assert report.concentration.effective_bets.value == pytest.approx(1.0)


def test_two_asset_zero_corr_hand_calculated() -> None:
    # Equal 30/30, vols 20/20, ρ=0 → var=0.0072, σ_p=√0.0072
    snapshot = _cov_snapshot(
        ("AAPL", "MSFT"),
        ((1.0, 0.0), (0.0, 1.0)),
    )
    report = build_pretrade_risk_report(
        _base_request(
            prior_risky_weights_pct={"AAPL": 20.0, "MSFT": 20.0},
            prior_cash_weight_pct=60.0,
            final_risky_weights_pct={"AAPL": 30.0, "MSFT": 30.0},
            final_cash_weight_pct=40.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0, "MSFT": 20.0},
            cost_liquidity=CostLiquidityScalars(
                expected_cost=12.5,
                adv_participation_pct=2.0,
                days_to_liquidate=1.0,
            ),
        )
    )
    sigma_p = (0.0072) ** 0.5
    assert report.portfolio_risk.variance.value == pytest.approx(0.0072)
    assert report.portfolio_risk.volatility_annualized_pct.value == pytest.approx(sigma_p * 100.0)
    crc_sum = sum(c.component_risk.value or 0.0 for c in report.portfolio_risk.contributions)
    assert crc_sum == pytest.approx(sigma_p)
    for contrib in report.portfolio_risk.contributions:
        assert contrib.marginal_risk.value == pytest.approx(0.012 / sigma_p)
        assert contrib.component_risk.value == pytest.approx(0.3 * 0.012 / sigma_p)
    assert report.concentration.herfindahl.value == pytest.approx(0.5)
    assert report.concentration.effective_bets.value == pytest.approx(2.0)
    # Turnover: ½(|+10|+|+10|+|-20|) = 20
    assert report.cost_liquidity.turnover_pct.value == pytest.approx(20.0)
    assert report.cost_liquidity.expected_cost.value == pytest.approx(12.5)


def test_three_asset_correlated_hand_calculated() -> None:
    # A 40%, B 30%, C 20%; vols 20/15/25; corr as below → var=0.017475
    tickers = ("AAA", "BBB", "CCC")
    matrix = (
        (1.0, 0.5, 0.2),
        (0.5, 1.0, 0.3),
        (0.2, 0.3, 1.0),
    )
    snapshot = _cov_snapshot(tickers, matrix)
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAA": 40.0, "BBB": 30.0, "CCC": 20.0},
            final_cash_weight_pct=10.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAA": 20.0, "BBB": 15.0, "CCC": 25.0},
            sector_by_ticker={"AAA": "tech", "BBB": "tech", "CCC": "energy"},
            factor_exposure=0.35,
            scenario_stress_pct=-8.5,
        )
    )
    assert report.portfolio_risk.variance.value == pytest.approx(0.017475)
    sigma_p = (0.017475) ** 0.5
    assert report.portfolio_risk.volatility_annualized_pct.value == pytest.approx(sigma_p * 100.0)
    crc_sum = sum(c.component_risk.value or 0.0 for c in report.portfolio_risk.contributions)
    assert crc_sum == pytest.approx(sigma_p)
    by_ticker = {c.ticker: c for c in report.portfolio_risk.contributions}
    assert by_ticker["AAA"].marginal_risk.value == pytest.approx(0.0225 / sigma_p)
    assert by_ticker["BBB"].marginal_risk.value == pytest.approx(0.015 / sigma_p)
    assert by_ticker["CCC"].marginal_risk.value == pytest.approx(0.019875 / sigma_p)
    # Sector: tech=70, energy=20
    assert report.name_sector_factor_scenario.sector_max_weight_pct.value == pytest.approx(70.0)
    assert report.name_sector_factor_scenario.factor_exposure.value == pytest.approx(0.35)
    assert report.name_sector_factor_scenario.scenario_stress_pct.value == pytest.approx(-8.5)


def test_all_cash_zero_variance() -> None:
    report = build_pretrade_risk_report(_base_request())
    assert report.status is ReportMetricStatus.AVAILABLE
    assert report.portfolio_risk.variance.value == pytest.approx(0.0)
    assert report.portfolio_risk.volatility_annualized_pct.value == pytest.approx(0.0)
    assert report.portfolio_risk.contributions == ()
    assert report.concentration.herfindahl.value == pytest.approx(0.0)
    assert report.concentration.effective_bets.status is ReportMetricStatus.UNAVAILABLE
    assert report.exposures.cash_weight_pct.value == pytest.approx(100.0)
    assert report.covariance_hash is None


def test_zero_volatility_book() -> None:
    snapshot = _cov_snapshot(("CASHY",), ((1.0,),))
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"CASHY": 40.0},
            final_cash_weight_pct=60.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"CASHY": 0.0},
        )
    )
    assert report.portfolio_risk.variance.value == pytest.approx(0.0)
    assert report.portfolio_risk.volatility_annualized_pct.value == pytest.approx(0.0)
    assert report.portfolio_risk.contributions[0].marginal_risk.value == pytest.approx(0.0)
    assert report.portfolio_risk.contributions[0].component_risk.value == pytest.approx(0.0)


def test_missing_covariance_marks_risk_unavailable_and_degrades() -> None:
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAPL": 50.0},
            final_cash_weight_pct=50.0,
            covariance_snapshot=None,
            annualized_vol_pct={"AAPL": 20.0},
        )
    )
    assert report.status is ReportMetricStatus.DEGRADED
    assert report.portfolio_risk.variance.status is ReportMetricStatus.UNAVAILABLE
    assert (
        report.portfolio_risk.contributions[0].marginal_risk.status
        is ReportMetricStatus.UNAVAILABLE
    )
    assert report.final_weights.entries[0].weight_pct == 50.0  # book preserved


def test_missing_cost_and_forecast_degrade_without_substituting_book() -> None:
    snapshot = _cov_snapshot(("AAPL",), ((1.0,),))
    final = {"AAPL": 40.0}
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct=final,
            final_cash_weight_pct=60.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0},
            cost_liquidity=None,
            forecast_quality=None,
        )
    )
    assert report.status is ReportMetricStatus.DEGRADED
    assert report.cost_liquidity.expected_cost.status is ReportMetricStatus.UNAVAILABLE
    assert report.forecast_quality.staleness_sessions.status is ReportMetricStatus.UNAVAILABLE
    assert report.final_weights.weights_fingerprint == weights_fingerprint(final)


def test_unavailable_covariance_snapshot_does_not_fabricate_matrix() -> None:
    snapshot = _cov_snapshot(
        ("AAPL",),
        ((1.0,),),
        status=PolicyArtifactStatus.UNAVAILABLE,
        unavailable_reason="insufficient return history",
    )
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAPL": 50.0},
            final_cash_weight_pct=50.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0},
        )
    )
    assert report.status is ReportMetricStatus.DEGRADED
    assert report.portfolio_risk.variance.status is ReportMetricStatus.UNAVAILABLE
    assert "insufficient return history" in (report.unavailable_reason or "")
    assert report.covariance_hash == snapshot.content_hash


def test_factor_scenario_stay_unavailable_without_fabrication() -> None:
    snapshot = _cov_snapshot(("AAPL",), ((1.0,),))
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAPL": 50.0},
            final_cash_weight_pct=50.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0},
        )
    )
    assert (
        report.name_sector_factor_scenario.factor_exposure.status is ReportMetricStatus.UNAVAILABLE
    )
    assert (
        report.name_sector_factor_scenario.scenario_stress_pct.status
        is ReportMetricStatus.UNAVAILABLE
    )
    assert (
        report.name_sector_factor_scenario.sector_max_weight_pct.status
        is ReportMetricStatus.UNAVAILABLE
    )


def test_builder_does_not_mutate_input_weights() -> None:
    snapshot = _cov_snapshot(("AAPL", "MSFT"), ((1.0, 0.1), (0.1, 1.0)))
    prior = {"AAPL": 20.0, "MSFT": 10.0}
    final = {"AAPL": 30.0, "MSFT": 25.0}
    prior_before = dict(prior)
    final_before = dict(final)
    build_pretrade_risk_report(
        _base_request(
            prior_risky_weights_pct=prior,
            prior_cash_weight_pct=70.0,
            final_risky_weights_pct=final,
            final_cash_weight_pct=45.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0, "MSFT": 18.0},
            binding_constraints=(
                BindingConstraint(
                    constraint_id="single_name_cap",
                    constraint_kind="single_name_cap",
                    ticker="AAPL",
                    bound_value=40.0,
                    observed_value=30.0,
                    reason="cap not binding",
                ),
            ),
            altered_targets=(
                AlteredTarget(
                    ticker="MSFT",
                    requested_weight_pct=35.0,
                    final_weight_pct=25.0,
                    adjustment_type="single_name_cap",
                    reason="capped",
                ),
            ),
            rejected_targets=(
                RejectedTarget(ticker="TSLA", requested_weight_pct=5.0, reason="excluded"),
            ),
        )
    )
    assert prior == prior_before
    assert final == final_before


def test_force_unavailable_report() -> None:
    report = build_pretrade_risk_report(
        _base_request(force_unavailable_reason="allocation bundle missing")
    )
    assert report.status is ReportMetricStatus.UNAVAILABLE
    assert report.unavailable_reason == "allocation bundle missing"


def test_metric_source_hashes_equal_bundle_sources() -> None:
    snapshot = _cov_snapshot(("AAPL",), ((1.0,),))
    report = build_pretrade_risk_report(
        _base_request(
            final_risky_weights_pct={"AAPL": 50.0},
            final_cash_weight_pct=50.0,
            covariance_snapshot=snapshot,
            annualized_vol_pct={"AAPL": 20.0},
            allocation_input_bundle_hash=_BUNDLE_HASH,
            risk_policy_hash=_POLICY_HASH,
        )
    )
    assert report.allocation_input_bundle_hash == _BUNDLE_HASH
    assert report.risk_policy_hash == _POLICY_HASH
    assert report.covariance_hash == snapshot.content_hash
    assert report.final_book_weights_fingerprint == report.final_weights.weights_fingerprint
