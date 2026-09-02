"""Deterministic helpers for Integration Task 2.1 Phase 2 lock tests (#2820).

Composes WP8 allocation bundle → WP9 PreTradeRiskReport → WP10 shadow artifact /
challenger / paired comparison without wiring challenger into production H8/H9.
"""

from __future__ import annotations

import ast
import importlib.util
from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

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
    ShadowAllocationArtifact,
    ShadowCommitMetadata,
    build_shadow_allocation_artifact,
)
from digiquant.portfolio.shadow_optimizer import (
    ShadowCostSchedule,
    ShadowFeasibilityConstraints,
    ShadowObjectiveParams,
    ShadowOptimizerRequest,
    evaluate_shadow_challenger,
)
from digiquant.dashboard.replay.allocation_comparison import (
    ComparisonArm,
    ComparisonArmInput,
    ComparisonStatus,
    build_shared_manifest,
    compare_allocation_arms,
    load_shadow_criteria,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    HoldingSnapshot,
    InstrumentBarSeries,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    TargetWeight,
    portfolio_replay_result_content_hash,
)

PHASE2_RUN_ID = "run-phase2-2820"
PHASE2_SESSION = date(2026, 8, 26)
PHASE2_CUTOFF = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)

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

_REPO = Path(__file__).resolve().parents[3]
_UTC = timezone.utc

FORBIDDEN_PHASE2_NODES = frozenset(
    {
        "shadow-optimizer",
        "shadow-challenger",
        "allocation-comparison",
        "portfolio-replay",
        "challenger-selector",
        "online-learning",
    }
)

HERMES_COMPILED_NODES = frozenset(
    {
        "hermes/thesis/market-review",
        "hermes/thesis/market-exploration",
        "hermes/thesis/vehicle-map",
        "hermes/thesis/opportunity-screener",
        "hermes/portfolio/asset-analyst-worker",
        "hermes/portfolio/deliberation-worker",
        "hermes/portfolio/pm-direction",
        "hermes/portfolio/risk-sizing",
        "hermes/portfolio/commit-run",
    }
)

PRODUCTION_GUARD_PATHS = (
    _REPO / "digiquant/src/digiquant/olympus/hermes/chain.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/phase7e_risk_sizing.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/h9_commit_run.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/shadow_artifact.py",
)

CHALLENGER_MODULE_FRAGMENTS = frozenset(
    {
        "shadow_optimizer",
        "allocation_comparison",
        "olympus.replay",
        "olympus.replay.worker",
        "olympus.replay.nautilus_portfolio",
    }
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


def book_weights(entries: tuple[tuple[str, float], ...], cash: float) -> BookWeightsView:
    weight_map = {ticker: weight for ticker, weight in entries}
    return BookWeightsView(
        entries=tuple(ReportWeightEntry(ticker=t, weight_pct=w) for t, w in entries),
        cash_weight_pct=cash,
        weights_fingerprint=weights_fingerprint(weight_map),
    )


def phase2_allocation_bundle(
    *,
    ranks: dict[str, int] | None = None,
    mu: dict[str, float] | None = None,
    err: dict[str, float] | None = None,
) -> AllocationInputBundle:
    """Canonical calibrated AllocationInputBundle for Phase 2 composition."""
    tickers = ("AAPL", "MSFT")
    rank_map = ranks or {"AAPL": 1, "MSFT": 2}
    mu = mu or {"AAPL": 0.08, "MSFT": 0.04}
    err = err or {"AAPL": 0.02, "MSFT": 0.02}
    mandates = tuple(
        MandateReference(
            ticker=ticker,
            direction="long",
            conviction_rank=rank_map[ticker],
            effective_forecast_id=_FORECAST_ID,
        )
        for ticker in tickers
    )
    calibrated = tuple(
        CalibratedReturnSlice(
            ticker=ticker,
            horizon_sessions=21,
            expected_gross_return=Decimal(str(mu[ticker])),
            forecast_error_std=Decimal(str(err[ticker])),
            reliability_weight=Decimal("1.0"),
            calibrated_forecast_content_hash=_CAL_HASH_A if ticker == "AAPL" else _CAL_HASH_B,
            status=AssetInputStatus.AVAILABLE,
        )
        for ticker in tickers
    )
    prior = PriorBookSnapshot(
        entries=(
            PriorWeightEntry(ticker="AAPL", weight_pct=30.0),
            PriorWeightEntry(ticker="MSFT", weight_pct=20.0),
        ),
        cash_weight_pct=50.0,
    )
    control = ControlSettingsFingerprint(
        risk_policy_content_hash=_POLICY_HASH,
        risk_policy_id=_POLICY_ID,
    )
    covariance = CovarianceBinding(
        snapshot_id=_SNAPSHOT_ID,
        content_hash=_COV_HASH,
        tickers=tickers,
    )
    cost = CostLiquidityBinding(entries=(("AAPL", _COST_HASH_A), ("MSFT", _COST_HASH_B)))
    source = build_source_hashes(
        h7_memo_hash=_H7_HASH,
        risk_policy_hash=_POLICY_HASH,
        prior_entries=tuple((entry.ticker, entry.weight_pct) for entry in prior.entries),
        calibrated_hashes=(("AAPL", _CAL_HASH_A), ("MSFT", _CAL_HASH_B)),
        covariance_hash=_COV_HASH,
        cost_hashes=cost.entries,
    )
    run = AllocationRunContext(
        run_id=PHASE2_RUN_ID,
        session_date=PHASE2_SESSION,
        cutoff_at=PHASE2_CUTOFF,
        cadence=AllocationCadence.DAILY,
    )
    payload = {
        "schema_version": "1.0",
        "run": run,
        "canonical_asset_order": tickers,
        "mandates": mandates,
        "calibrated_returns": calibrated,
        "prior_book": prior,
        "control_settings": control,
        "covariance": covariance,
        "cost_liquidity": cost,
        "source_hashes": source,
    }
    draft = AllocationInputBundle.model_construct(**payload, bundle_content_hash="")
    digest = allocation_bundle_content_hash(payload=draft._hash_payload())
    return AllocationInputBundle.model_validate({**payload, "bundle_content_hash": digest})


def phase2_pretrade_report(
    *,
    bundle: AllocationInputBundle,
    final: BookWeightsView,
) -> PreTradeRiskReport:
    """PreTradeRiskReport bound to the final book + bundle hashes."""
    prior = book_weights(
        tuple((e.ticker, e.weight_pct) for e in bundle.prior_book.entries),
        cash=bundle.prior_book.cash_weight_pct,
    )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": PHASE2_RUN_ID,
        "session_date": PHASE2_SESSION,
        "status": ReportMetricStatus.AVAILABLE,
        "allocation_input_bundle_hash": bundle.bundle_content_hash,
        "final_book_weights_fingerprint": final.weights_fingerprint,
        "prior_weights": prior,
        "final_weights": final,
        "trade_deltas": (
            TradeDeltaEntry(ticker="AAPL", delta_weight_pct=-5.0),
            TradeDeltaEntry(ticker="MSFT", delta_weight_pct=5.0),
        ),
        "exposures": ExposureBlock(
            gross_exposure_pct=_available(50.0, MetricProvenance.FINAL_BOOK),
            net_exposure_pct=_available(50.0, MetricProvenance.FINAL_BOOK),
            cash_weight_pct=_available(50.0, MetricProvenance.FINAL_BOOK),
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
            herfindahl=_available(0.25, MetricProvenance.FINAL_BOOK),
            effective_bets=_available(4.0, MetricProvenance.FINAL_BOOK),
            max_name_weight_pct=_available(25.0, MetricProvenance.FINAL_BOOK),
        ),
        "name_sector_factor_scenario": NameSectorFactorScenarioBlock(
            name_max_weight_pct=_available(25.0, MetricProvenance.FINAL_BOOK),
            sector_max_weight_pct=_unavailable("sector map not bound"),
            factor_exposure=_unavailable("factor model not configured"),
            scenario_stress_pct=_unavailable("scenario library not configured"),
        ),
        "cost_liquidity": CostLiquidityReportBlock(
            expected_cost=_available(8.0, MetricProvenance.COST_LIQUIDITY),
            turnover_pct=_available(10.0, MetricProvenance.DERIVED),
            adv_participation_pct=_available(1.5, MetricProvenance.COST_LIQUIDITY),
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
    draft = PreTradeRiskReport.model_construct(**payload, report_content_hash="")
    digest = pretrade_risk_report_content_hash(payload=draft._hash_payload())
    return PreTradeRiskReport.model_validate({**payload, "report_content_hash": digest})


def phase2_shadow_artifact(
    *,
    final: BookWeightsView | None = None,
    ranks: dict[str, int] | None = None,
) -> ShadowAllocationArtifact:
    """Full WP8→WP9→WP10.1 composition fixture with byte-stable artifact hash."""
    bundle = phase2_allocation_bundle(ranks=ranks)
    final_book = final or book_weights((("AAPL", 25.0), ("MSFT", 25.0)), cash=50.0)
    report = phase2_pretrade_report(bundle=bundle, final=final_book)
    return build_shadow_allocation_artifact(
        run_id=PHASE2_RUN_ID,
        session_date=PHASE2_SESSION,
        allocation_input_bundle=bundle,
        pre_trade_risk_report=report,
        incumbent_final_weights=final_book,
        commit=ShadowCommitMetadata(
            commit_id="ledger-phase2-2820",
            commit_status="committed",
            weights_fingerprint=final_book.weights_fingerprint,
            source_run_id=PHASE2_RUN_ID,
        ),
    )


def phase2_challenger_request(
    artifact: ShadowAllocationArtifact | None = None,
) -> ShadowOptimizerRequest:
    art = artifact or phase2_shadow_artifact()
    return ShadowOptimizerRequest(
        artifact=art,
        covariance_matrix=((0.04, 0.0), (0.0, 0.04)),
        cost_schedule=ShadowCostSchedule(rates=(("AAPL", 0.0), ("MSFT", 0.0))),
        constraints=ShadowFeasibilityConstraints(weight_increment_pct=5.0),
        objective=ShadowObjectiveParams(kappa=0.0, lambda_risk=0.0, gamma=0.0),
    )


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=_UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str, closes: list[str]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 2, c) for i, c in enumerate(closes)),
    )


def phase2_replay_request(
    *,
    request_id: str,
    targets: tuple[tuple[str, str], ...] = (("AAPL", "0.25"), ("MSFT", "0.25")),
) -> PortfolioReplayRequest:
    closes = ["100", "101", "102", "103", "104"]
    msft = [str(Decimal(c) * 2) for c in closes]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal("100000"),
        series=(_series("AAPL", closes), _series("MSFT", msft)),
        target_weights=tuple(TargetWeight(ticker=t, weight=Decimal(w)) for t, w in targets),
        execution=ExecutionPolicy(commission_rate=Decimal("0.001")),
    )


def phase2_ok_result(
    request: PortfolioReplayRequest,
    *,
    ending_nav: str,
) -> PortfolioReplayResult:
    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=Decimal("20000"),
        ending_nav=Decimal(ending_nav),
        total_commission=Decimal("50"),
        rebalance_commission=Decimal("50"),
        holdings=(
            HoldingSnapshot(
                ticker="AAPL",
                quantity=Decimal("100"),
                last_price=Decimal("100"),
                market_value=Decimal("10000"),
            ),
        ),
        fills=(),
        message="",
        result_content_hash=None,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(mode="python"), "result_content_hash": digest}
    )


def phase2_comparison_report(
    *,
    challenger_breaches: tuple[str, ...] = (),
    challenger_nav: str = "110000",
):
    """Paired incumbent/challenger comparison under a shared observed manifest."""
    criteria = load_shadow_criteria(
        _REPO / "digiquant/src/digiquant/olympus/replay/shadow_criteria/v1.json"
    )
    inc_req = phase2_replay_request(request_id="inc-phase2")
    ch_req = phase2_replay_request(request_id="ch-phase2")
    # Prove shared-hash gate accepts identical data/cost/execution arms.
    assert build_shared_manifest(inc_req, ch_req) is not None
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=ComparisonArmInput(
            arm=ComparisonArm.INCUMBENT,
            weights_fingerprint="inc-fp",
            request=inc_req,
            result=phase2_ok_result(inc_req, ending_nav="105000"),
        ),
        challenger=ComparisonArmInput(
            arm=ComparisonArm.CHALLENGER,
            weights_fingerprint="ch-fp",
            request=ch_req,
            result=phase2_ok_result(ch_req, ending_nav=challenger_nav),
            hard_constraint_breaches=challenger_breaches,
        ),
    )
    return criteria, report


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    return imported


def production_imports_challenger(path: Path) -> list[str]:
    hits: list[str] = []
    for mod in imported_modules(path):
        for frag in CHALLENGER_MODULE_FRAGMENTS:
            if frag in mod:
                hits.append(mod)
                break
    return hits


def load_isolation_checker() -> Any:
    import sys

    script = _REPO / "digiquant/scripts/research/check_allocation_shadow_isolation.py"
    spec = importlib.util.spec_from_file_location("check_allocation_shadow_isolation", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_phase2_composition() -> dict[str, Any]:
    """End-to-end WP8→WP10 composition: bundle → report → artifact → challenger → comparison."""
    artifact = phase2_shadow_artifact()
    again = phase2_shadow_artifact()
    assert artifact.artifact_content_hash == again.artifact_content_hash

    challenger = evaluate_shadow_challenger(phase2_challenger_request(artifact))
    criteria, comparison = phase2_comparison_report()
    return {
        "artifact": artifact,
        "artifact_again": again,
        "challenger": challenger,
        "criteria": criteria,
        "comparison": comparison,
        "comparison_status": comparison.status,
    }


__all__ = [
    "CHALLENGER_MODULE_FRAGMENTS",
    "ComparisonStatus",
    "FORBIDDEN_PHASE2_NODES",
    "HERMES_COMPILED_NODES",
    "PHASE2_RUN_ID",
    "PHASE2_SESSION",
    "PRODUCTION_GUARD_PATHS",
    "book_weights",
    "imported_modules",
    "load_isolation_checker",
    "phase2_allocation_bundle",
    "phase2_challenger_request",
    "phase2_comparison_report",
    "phase2_pretrade_report",
    "phase2_shadow_artifact",
    "production_imports_challenger",
    "run_phase2_composition",
]
