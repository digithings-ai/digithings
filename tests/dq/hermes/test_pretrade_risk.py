"""WP9.1 — PreTradeRiskReport contracts and stable hashes (#2742)."""

from __future__ import annotations

from datetime import date

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
