"""WP10.3 — solver-free robust shadow challenger (#2770)."""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.portfolio.allocation_contracts import (
    AllocationCadence,
    AllocationInputBundle,
    AllocationRunContext,
    AssetInputStatus,
    BookWeightsView,
    CalibratedReturnSlice,
    ConcentrationBlock,
    ControlOutcomesBlock,
    ControlSettingsFingerprint,
    CostLiquidityBinding,
    CostLiquidityReportBlock,
    CovarianceBinding,
    ExposureBlock,
    ForecastQualityBlock,
    MandateReference,
    MetricProvenance,
    NameSectorFactorScenarioBlock,
    PerAssetRiskContribution,
    PortfolioRiskBlock,
    PreTradeRiskReport,
    PriorBookSnapshot,
    PriorWeightEntry,
    ReportMetricStatus,
    ReportWeightEntry,
    ScalarMetric,
    TradeDeltaEntry,
    build_source_hashes,
)
from digiquant.portfolio.allocation_hashes import (
    allocation_bundle_content_hash,
    pretrade_risk_report_content_hash,
    weights_fingerprint,
)
from digiquant.portfolio.shadow_artifact import (
    ShadowCommitMetadata,
    build_shadow_allocation_artifact,
)
from digiquant.portfolio.shadow_optimizer import (
    CASH_TOKEN,
    FORBIDDEN_IMPORT_PREFIXES,
    OBJECTIVE_TOLERANCE,
    ShadowCostSchedule,
    ShadowFeasibilityConstraints,
    ShadowObjectiveParams,
    ShadowOptimizerRequest,
    ShadowOptimizerStatus,
    book_to_weight_map,
    build_book_weights,
    check_feasibility,
    evaluate_shadow_challenger,
    robust_objective,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)
_SESSION = date(2026, 8, 26)
_POLICY_ID = UUID("11111111-1111-4111-8111-111111111111")
_SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
_FORECAST_ID = UUID("33333333-3333-4333-8333-333333333333")
_POLICY_HASH = "a" * 64
_CAL_HASH_A = "b" * 64
_CAL_HASH_B = "c" * 64
_COST_HASH_A = "d" * 64
_COST_HASH_B = "e" * 64
_H7_HASH = "f" * 64
_COV_HASH = "1" * 64

_OPTIMIZER = (
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "shadow_optimizer.py"
)
_PRODUCTION_GUARD_PATHS = (
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "chain.py",
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "phases"
    / "phase7e_risk_sizing.py",
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "phases"
    / "h9_commit_run.py",
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "shadow_artifact.py",
)


def _available(
    value: float, provenance: MetricProvenance = MetricProvenance.DERIVED
) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.AVAILABLE,
        value=value,
        provenance=provenance,
    )


def _unavailable(reason: str) -> ScalarMetric:
    return ScalarMetric(status=ReportMetricStatus.UNAVAILABLE, unavailable_reason=reason)


def _weights(entries: tuple[tuple[str, float], ...], cash: float) -> BookWeightsView:
    weight_map = {ticker: weight for ticker, weight in entries}
    return BookWeightsView(
        entries=tuple(ReportWeightEntry(ticker=t, weight_pct=w) for t, w in entries),
        cash_weight_pct=cash,
        weights_fingerprint=weights_fingerprint(weight_map),
    )


def _bundle(
    *,
    mu: dict[str, float] | None = None,
    err: dict[str, float] | None = None,
    reliability: dict[str, float] | None = None,
    prior: tuple[tuple[str, float], ...] = (("AAPL", 30.0), ("MSFT", 20.0)),
    prior_cash: float = 50.0,
    include_covariance: bool = True,
    include_cost: bool = True,
    msft_status: AssetInputStatus = AssetInputStatus.AVAILABLE,
) -> AllocationInputBundle:
    tickers = ("AAPL", "MSFT")
    mu = mu or {"AAPL": 0.08, "MSFT": 0.04}
    err = err or {"AAPL": 0.02, "MSFT": 0.02}
    reliability = reliability or {"AAPL": 1.0, "MSFT": 1.0}
    mandates = tuple(
        MandateReference(
            ticker=ticker,
            direction="long",
            conviction_rank=idx,
            effective_forecast_id=_FORECAST_ID,
        )
        for idx, ticker in enumerate(tickers, start=1)
    )
    calibrated_list: list[CalibratedReturnSlice] = []
    for ticker in tickers:
        if ticker == "MSFT" and msft_status is not AssetInputStatus.AVAILABLE:
            calibrated_list.append(
                CalibratedReturnSlice(
                    ticker=ticker,
                    horizon_sessions=21,
                    reliability_weight=Decimal("0.5"),
                    status=msft_status,
                    unavailable_reason="degraded for test",
                )
            )
        else:
            calibrated_list.append(
                CalibratedReturnSlice(
                    ticker=ticker,
                    horizon_sessions=21,
                    expected_gross_return=Decimal(str(mu[ticker])),
                    forecast_error_std=Decimal(str(err[ticker])),
                    reliability_weight=Decimal(str(reliability[ticker])),
                    calibrated_forecast_content_hash=(
                        _CAL_HASH_A if ticker == "AAPL" else _CAL_HASH_B
                    ),
                    status=AssetInputStatus.AVAILABLE,
                )
            )
    calibrated = tuple(calibrated_list)
    prior_book = PriorBookSnapshot(
        entries=tuple(PriorWeightEntry(ticker=t, weight_pct=w) for t, w in prior),
        cash_weight_pct=prior_cash,
    )
    control = ControlSettingsFingerprint(
        risk_policy_content_hash=_POLICY_HASH,
        risk_policy_id=_POLICY_ID,
    )
    covariance = (
        CovarianceBinding(
            snapshot_id=_SNAPSHOT_ID,
            content_hash=_COV_HASH,
            tickers=tickers,
        )
        if include_covariance
        else None
    )
    cost = (
        CostLiquidityBinding(entries=(("AAPL", _COST_HASH_A), ("MSFT", _COST_HASH_B)))
        if include_cost
        else None
    )
    cal_hashes = tuple(
        (item.ticker, item.calibrated_forecast_content_hash or "")
        for item in calibrated
        if item.calibrated_forecast_content_hash is not None
    )
    source = build_source_hashes(
        h7_memo_hash=_H7_HASH,
        risk_policy_hash=_POLICY_HASH,
        prior_entries=tuple((entry.ticker, entry.weight_pct) for entry in prior_book.entries),
        calibrated_hashes=cal_hashes,
        covariance_hash=_COV_HASH if include_covariance else None,
        cost_hashes=cost.entries if cost is not None else (),
    )
    run = AllocationRunContext(
        run_id="run-2770",
        session_date=_SESSION,
        cutoff_at=_TS,
        cadence=AllocationCadence.DAILY,
    )
    payload = {
        "schema_version": "1.0",
        "run": run,
        "canonical_asset_order": tickers,
        "mandates": mandates,
        "calibrated_returns": calibrated,
        "prior_book": prior_book,
        "control_settings": control,
        "covariance": covariance,
        "cost_liquidity": cost,
        "source_hashes": source,
    }
    draft = AllocationInputBundle.model_construct(**payload, bundle_content_hash="")
    bundle_hash = allocation_bundle_content_hash(payload=draft._hash_payload())
    return AllocationInputBundle.model_validate({**payload, "bundle_content_hash": bundle_hash})


def _report(
    *, bundle_hash: str, final: BookWeightsView, prior: BookWeightsView
) -> PreTradeRiskReport:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "run-2770",
        "session_date": _SESSION,
        "status": ReportMetricStatus.AVAILABLE,
        "allocation_input_bundle_hash": bundle_hash,
        "final_book_weights_fingerprint": final.weights_fingerprint,
        "prior_weights": prior,
        "final_weights": final,
        "trade_deltas": tuple(
            TradeDeltaEntry(
                ticker=ticker,
                delta_weight_pct=book_to_weight_map(final).get(ticker, 0.0)
                - book_to_weight_map(prior).get(ticker, 0.0),
            )
            for ticker in sorted(set(book_to_weight_map(final)) | set(book_to_weight_map(prior)))
        ),
        "exposures": ExposureBlock(
            gross_exposure_pct=_available(
                100.0 - final.cash_weight_pct, MetricProvenance.FINAL_BOOK
            ),
            net_exposure_pct=_available(100.0 - final.cash_weight_pct, MetricProvenance.FINAL_BOOK),
            cash_weight_pct=_available(final.cash_weight_pct, MetricProvenance.FINAL_BOOK),
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
            binding_constraints=(),
            altered_targets=(),
            rejected_targets=(),
        ),
        "risk_policy_hash": _POLICY_HASH,
        "covariance_hash": _COV_HASH,
    }
    draft = PreTradeRiskReport.model_construct(
        schema_version="1.0",
        run_id="run-2770",
        session_date=_SESSION,
        status=ReportMetricStatus.AVAILABLE,
        unavailable_reason=None,
        allocation_input_bundle_hash=bundle_hash,
        final_book_weights_fingerprint=final.weights_fingerprint,
        prior_weights=prior,
        final_weights=final,
        trade_deltas=payload["trade_deltas"],  # type: ignore[arg-type]
        exposures=payload["exposures"],  # type: ignore[arg-type]
        portfolio_risk=payload["portfolio_risk"],  # type: ignore[arg-type]
        concentration=payload["concentration"],  # type: ignore[arg-type]
        name_sector_factor_scenario=payload["name_sector_factor_scenario"],  # type: ignore[arg-type]
        cost_liquidity=payload["cost_liquidity"],  # type: ignore[arg-type]
        forecast_quality=payload["forecast_quality"],  # type: ignore[arg-type]
        controls=payload["controls"],  # type: ignore[arg-type]
        risk_policy_hash=_POLICY_HASH,
        covariance_hash=_COV_HASH,
        report_content_hash="",
    )
    report_hash = pretrade_risk_report_content_hash(payload=draft._hash_payload())
    return PreTradeRiskReport.model_validate({**payload, "report_content_hash": report_hash})


def _artifact(
    *,
    bundle: AllocationInputBundle | None = None,
    final: BookWeightsView | None = None,
) -> object:
    bundle = bundle or _bundle()
    prior = _weights(
        tuple((e.ticker, e.weight_pct) for e in bundle.prior_book.entries),
        cash=bundle.prior_book.cash_weight_pct,
    )
    final = final or _weights((("AAPL", 25.0), ("MSFT", 25.0)), cash=50.0)
    report = _report(bundle_hash=bundle.bundle_content_hash, final=final, prior=prior)
    return build_shadow_allocation_artifact(
        run_id="run-2770",
        session_date=_SESSION,
        allocation_input_bundle=bundle,
        pre_trade_risk_report=report,
        incumbent_final_weights=final,
        commit=ShadowCommitMetadata(
            commit_id="ledger-2770",
            commit_status="committed",
            weights_fingerprint=final.weights_fingerprint,
            source_run_id="run-2770",
        ),
    )


def _request(
    *,
    artifact: object | None = None,
    covariance: tuple[tuple[float, ...], ...] | None = None,
    cost_rates: tuple[tuple[str, float], ...] = (("AAPL", 0.0), ("MSFT", 0.0)),
    constraints: ShadowFeasibilityConstraints | None = None,
    objective: ShadowObjectiveParams | None = None,
) -> ShadowOptimizerRequest:
    art = artifact or _artifact()
    cov = covariance or ((0.04, 0.0), (0.0, 0.04))
    return ShadowOptimizerRequest(
        artifact=art,  # type: ignore[arg-type]
        covariance_matrix=cov,
        cost_schedule=ShadowCostSchedule(rates=cost_rates),
        constraints=constraints or ShadowFeasibilityConstraints(weight_increment_pct=5.0),
        objective=objective or ShadowObjectiveParams(),
    )


def test_identity_when_no_improving_move() -> None:
    # Seed equals prior at a balanced book; huge linear costs make every quantum move lose.
    seed = _weights((("AAPL", 25.0), ("MSFT", 25.0)), cash=50.0)
    artifact = _artifact(
        bundle=_bundle(
            mu={"AAPL": 0.05, "MSFT": 0.05},
            prior=(("AAPL", 25.0), ("MSFT", 25.0)),
            prior_cash=50.0,
        ),
        final=seed,
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            cost_rates=(("AAPL", 10.0), ("MSFT", 10.0)),
            objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=0.0, gamma=0.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.IDENTITY
    assert result.move_trace == ()
    assert result.challenger_weights is not None
    assert book_to_weight_map(result.challenger_weights) == {"AAPL": 25.0, "MSFT": 25.0}
    assert result.challenger_objective is not None
    assert result.seed_objective is not None
    assert result.challenger_objective + OBJECTIVE_TOLERANCE >= result.seed_objective


def test_uncertainty_penalty_prefers_lower_error_asset() -> None:
    artifact = _artifact(
        bundle=_bundle(
            mu={"AAPL": 0.06, "MSFT": 0.06},
            err={"AAPL": 0.01, "MSFT": 0.20},
        ),
        final=_weights((("AAPL", 20.0), ("MSFT", 20.0)), cash=60.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            objective=ShadowObjectiveParams(kappa=5.0, lambda_risk=0.0, gamma=0.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.IMPROVED
    assert result.challenger_weights is not None
    weights = book_to_weight_map(result.challenger_weights)
    assert weights.get("AAPL", 0.0) > weights.get("MSFT", 0.0)


def test_diversification_avoids_concentrated_correlated_book() -> None:
    # High correlation + risk aversion: prefer diversifying away from AAPL-heavy seed.
    artifact = _artifact(
        bundle=_bundle(mu={"AAPL": 0.05, "MSFT": 0.05}),
        final=_weights((("AAPL", 30.0), ("MSFT", 5.0)), cash=65.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            covariance=((0.04, 0.035), (0.035, 0.04)),
            constraints=ShadowFeasibilityConstraints(
                max_position_pct=40.0,
                weight_increment_pct=5.0,
            ),
            objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=20.0, gamma=0.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.IMPROVED
    assert result.challenger_weights is not None
    weights = book_to_weight_map(result.challenger_weights)
    assert abs(weights.get("AAPL", 0.0) - weights.get("MSFT", 0.0)) < 30.0 - 5.0


def test_cost_dominated_no_trade() -> None:
    # Seed already at prior — any quantum move pays full linear cost and loses.
    seed = _weights((("AAPL", 20.0), ("MSFT", 20.0)), cash=60.0)
    artifact = _artifact(
        bundle=_bundle(
            mu={"AAPL": 0.10, "MSFT": 0.01},
            prior=(("AAPL", 20.0), ("MSFT", 20.0)),
            prior_cash=60.0,
        ),
        final=seed,
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            cost_rates=(("AAPL", 50.0), ("MSFT", 50.0)),
            objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=0.0, gamma=0.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.IDENTITY
    assert result.move_trace == ()


def test_cash_moves_accepted_when_objective_improves() -> None:
    # High-mu AAPL vs cash: move quantum from cash into AAPL.
    artifact = _artifact(
        bundle=_bundle(mu={"AAPL": 0.20, "MSFT": 0.01}, err={"AAPL": 0.01, "MSFT": 0.01}),
        final=_weights((("AAPL", 20.0), ("MSFT", 5.0)), cash=75.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=0.0, gamma=0.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.IMPROVED
    assert any(
        move.donor == CASH_TOKEN or move.receiver == CASH_TOKEN for move in result.move_trace
    )
    assert result.challenger_weights is not None
    assert book_to_weight_map(result.challenger_weights).get("AAPL", 0.0) > 20.0


def test_caps_and_grid_block_illegal_moves() -> None:
    artifact = _artifact(
        bundle=_bundle(mu={"AAPL": 1.0, "MSFT": 0.0}),
        final=_weights((("AAPL", 30.0),), cash=70.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            constraints=ShadowFeasibilityConstraints(
                max_position_pct=30.0,
                weight_increment_pct=5.0,
                min_cash_pct=0.0,
            ),
            objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=0.0, gamma=0.0),
        )
    )
    # Cannot raise AAPL above 30%; may still move into MSFT or stay.
    if result.challenger_weights is not None:
        assert book_to_weight_map(result.challenger_weights).get("AAPL", 0.0) <= 30.0 + 1e-9
        for entry in result.challenger_weights.entries:
            assert entry.weight_pct % 5.0 < 1e-9 or abs(entry.weight_pct % 5.0 - 5.0) < 1e-9


def test_infeasible_seed_abstains() -> None:
    artifact = _artifact(final=_weights((("AAPL", 33.0), ("MSFT", 20.0)), cash=47.0))
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            constraints=ShadowFeasibilityConstraints(weight_increment_pct=5.0),
        )
    )
    assert result.status is ShadowOptimizerStatus.ABSTAINED
    assert result.abstain_reason is not None
    assert "infeasible seed" in result.abstain_reason


def test_missing_covariance_abstains() -> None:
    artifact = _artifact(bundle=_bundle(include_covariance=False))
    result = evaluate_shadow_challenger(_request(artifact=artifact))
    assert result.status is ShadowOptimizerStatus.ABSTAINED
    assert result.abstain_reason == "missing covariance binding"


def test_missing_cost_binding_abstains() -> None:
    artifact = _artifact(bundle=_bundle(include_cost=False))
    result = evaluate_shadow_challenger(_request(artifact=artifact))
    assert result.status is ShadowOptimizerStatus.ABSTAINED
    assert result.abstain_reason == "missing cost/liquidity binding"


def test_degraded_calibrated_input_abstains() -> None:
    artifact = _artifact(bundle=_bundle(msft_status=AssetInputStatus.DEGRADED))
    result = evaluate_shadow_challenger(_request(artifact=artifact))
    assert result.status is ShadowOptimizerStatus.ABSTAINED
    assert result.abstain_reason is not None
    assert "not available" in result.abstain_reason


def test_deterministic_ties_pick_lexicographic_donor_receiver() -> None:
    # Symmetric assets: first improving move must be lex-smallest (donor, receiver).
    artifact = _artifact(
        bundle=_bundle(mu={"AAPL": 0.10, "MSFT": 0.10}, err={"AAPL": 0.01, "MSFT": 0.01}),
        final=_weights((), cash=100.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            covariance=((0.01, 0.0), (0.0, 0.01)),
            objective=ShadowObjectiveParams(
                kappa=0.0,
                lambda_risk=0.0,
                gamma=0.0,
                max_iterations=1,
            ),
        )
    )
    assert result.status is ShadowOptimizerStatus.IMPROVED
    assert len(result.move_trace) == 1
    assert result.move_trace[0].donor == CASH_TOKEN
    assert result.move_trace[0].receiver == "AAPL"


def test_repeated_evaluation_byte_identical() -> None:
    req = _request(
        artifact=_artifact(
            bundle=_bundle(mu={"AAPL": 0.12, "MSFT": 0.03}),
            final=_weights((("AAPL", 15.0), ("MSFT", 15.0)), cash=70.0),
        ),
        objective=ShadowObjectiveParams(kappa=0.1, lambda_risk=0.5, gamma=0.0),
    )
    first = evaluate_shadow_challenger(req)
    second = evaluate_shadow_challenger(req)
    assert first.result_content_hash == second.result_content_hash
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_never_worse_than_seed_and_zero_hard_violations() -> None:
    result = evaluate_shadow_challenger(
        _request(
            artifact=_artifact(
                bundle=_bundle(mu={"AAPL": 0.15, "MSFT": 0.02}),
                final=_weights((("AAPL", 10.0), ("MSFT", 20.0)), cash=70.0),
            ),
            objective=ShadowObjectiveParams(kappa=0.2, lambda_risk=1.0, gamma=0.01),
        )
    )
    assert result.status in {
        ShadowOptimizerStatus.IMPROVED,
        ShadowOptimizerStatus.IDENTITY,
    }
    assert result.seed_objective is not None
    assert result.challenger_objective is not None
    assert result.challenger_objective + OBJECTIVE_TOLERANCE >= result.seed_objective
    assert result.challenger_weights is not None
    reason = check_feasibility(
        risky_pct=book_to_weight_map(result.challenger_weights),
        cash_pct=result.challenger_weights.cash_weight_pct,
        constraints=ShadowFeasibilityConstraints(weight_increment_pct=5.0),
        authorized_longs=frozenset({"AAPL", "MSFT"}),
    )
    assert reason is None


def test_bounded_iterations_respected() -> None:
    artifact = _artifact(
        bundle=_bundle(mu={"AAPL": 0.50, "MSFT": 0.01}),
        final=_weights((), cash=100.0),
    )
    result = evaluate_shadow_challenger(
        _request(
            artifact=artifact,
            objective=ShadowObjectiveParams(
                kappa=0.0,
                lambda_risk=0.0,
                gamma=0.0,
                max_iterations=3,
            ),
        )
    )
    assert result.status is ShadowOptimizerStatus.IMPROVED
    assert len(result.move_trace) <= 3


def test_objective_helper_matches_manual_terms() -> None:
    params = ShadowObjectiveParams(kappa=1.0, lambda_risk=2.0, gamma=0.5)
    value = robust_objective(
        risky_frac={"AAPL": 0.2, "MSFT": 0.1},
        asset_order=("AAPL", "MSFT"),
        mu={"AAPL": 0.1, "MSFT": 0.05},
        d_mu={"AAPL": 0.02, "MSFT": 0.03},
        covariance=((0.04, 0.0), (0.0, 0.09)),
        prior_frac={"AAPL": 0.1, "MSFT": 0.1},
        cost_rates={"AAPL": 0.01, "MSFT": 0.01},
        params=params,
    )
    # μ·w = 0.1*0.2 + 0.05*0.1 = 0.025
    # κ||Dw|| = 1 * sqrt((0.004)^2 + (0.003)^2)
    # (λ/2)wΣw = 1.0 * (0.2^2*0.04 + 0.1^2*0.09) = 0.0025
    # C = 0.01*|0.1| + 0.01*|0| = 0.001
    # γ||Δ||1 = 0.5 * 0.1 = 0.05
    unc = ((0.004) ** 2 + (0.003) ** 2) ** 0.5
    expected = 0.025 - unc - 0.0025 - 0.001 - 0.05
    assert abs(value - expected) < 1e-12


def test_build_book_weights_sorted_fingerprint() -> None:
    book = build_book_weights({"MSFT": 10.0, "AAPL": 15.0}, cash_pct=75.0)
    assert [e.ticker for e in book.entries] == ["AAPL", "MSFT"]
    assert book.weights_fingerprint == weights_fingerprint({"AAPL": 15.0, "MSFT": 10.0})


def test_optimizer_forbidden_imports_absent() -> None:
    source = _OPTIMIZER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    for module in imported:
        assert not any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        ), module


def test_production_surfaces_do_not_import_shadow_optimizer() -> None:
    for path in _PRODUCTION_GUARD_PATHS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "shadow_optimizer" not in node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "shadow_optimizer" not in alias.name
