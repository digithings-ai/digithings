"""WP16.7 — evaluate immutable human-authored gate criteria (#3003).

Red coverage: no criteria fails closed; evaluator cannot author; missing metrics
insufficient; manifest/accounting/hard breach ineligible; per-criterion result;
``eligible_for_human_review``; rollback separate; no config write; every
evaluation explained by immutable criteria/result IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.dashboard.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_request,
    execution_policy_hash,
    fill_fraction_hash,
    policy_bundle_content_hash,
    random_seed_hash,
    replay_input_manifest_content_hash,
)
from digiquant.dashboard.replay.comparison import (
    ArmFoldEvidence,
    EvidenceMode,
    MetricDirection,
    OptionalArmTelemetry,
    PolicyComparisonReport,
    ResearchTelemetry,
    SignalQualityTelemetry,
    compare_policy_pair,
)
from digiquant.dashboard.replay.governance import (
    ConfidenceBoundRule,
    CriterionOutcome,
    GateCriterion,
    GateKind,
    HumanAuthoredGateCriteria,
    MetricComparisonKind,
    MissingDataRule,
    evaluate_gate_criteria,
    gate_criteria_content_hash,
    persist_gate_evaluation,
    to_store_criteria_version,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    HoldingSnapshot,
    InstrumentBarSeries,
    NavPoint,
    OhlcvBar,
    PolicyBundle,
    PolicyFamily,
    PolicyVersionRef,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    ReplayArmLabel,
    ReplayArmSpec,
    ReplayInputManifest,
    SharedInputIdentity,
    TargetWeight,
    build_replay_pair,
    portfolio_replay_result_content_hash,
)
from digiquant.dashboard.replay.store import PolicyReplayStore
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_UTC = UTC
_TS = datetime(2024, 2, 1, tzinfo=_UTC)


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


def _request(
    *,
    request_id: str = "req-1",
    targets: tuple[tuple[str, str], ...] = (("AAPL", "0.4"), ("MSFT", "0.4")),
    starting_cash: str = "100000",
) -> PortfolioReplayRequest:
    closes = ["100", "101", "102", "103", "104"]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal(starting_cash),
        series=(_series("AAPL", closes), _series("MSFT", closes)),
        target_weights=tuple(TargetWeight(ticker=t, weight=Decimal(w)) for t, w in targets),
        execution=ExecutionPolicy(commission_rate=Decimal("0"), random_seed=42),
    )


def _policy_ref(
    family: PolicyFamily, version_id: str, content_hash: str = "a" * 64
) -> PolicyVersionRef:
    return PolicyVersionRef(family=family, version_id=version_id, content_hash=content_hash)


def _manifest(request: PortfolioReplayRequest) -> ReplayInputManifest:
    shared = SharedInputIdentity(
        data_hash=data_hash_from_request(request),
        cost_hash=cost_hash_from_execution(request.execution),
        execution_hash=execution_policy_hash(request.execution),
        random_seed_hash=random_seed_hash(request.execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(request.execution.fill_fraction),
        starting_cash=request.starting_cash,
    )
    dataset_hash = data_hash_from_request(request)
    sources = tuple(
        sorted(
            (
                _policy_ref(PolicyFamily.DATA_SOURCE, "bars-v1", dataset_hash),
                _policy_ref(PolicyFamily.COST_SCHEDULE, "cost-v1", shared.cost_hash),
            ),
            key=lambda ref: (ref.family.value, ref.version_id),
        )
    )
    replay_as_of = datetime(2024, 1, 10, tzinfo=_UTC)
    content_hash = replay_input_manifest_content_hash(
        manifest_id="manifest-1",
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    return ReplayInputManifest(
        manifest_id="manifest-1",
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=content_hash,
        fold=None,
    )


def _arm(
    arm: ReplayArmLabel,
    manifest: ReplayInputManifest,
    *,
    arm_id: str,
    weights_fp: str,
    portfolio_version: str,
) -> ReplayArmSpec:
    bundle = PolicyBundle(
        portfolio_target=_policy_ref(
            PolicyFamily.PORTFOLIO_TARGET,
            portfolio_version,
            content_hash=sha256_hex({"weights_fingerprint": weights_fp}),
        ),
    )
    return ReplayArmSpec(
        arm=arm,
        arm_id=arm_id,
        manifest_content_hash=manifest.manifest_content_hash,
        policy_bundle=bundle,
        weights_fingerprint=weights_fp,
        arm_content_hash=policy_bundle_content_hash(bundle, weights_fingerprint=weights_fp),
    )


def _ok_result(
    request: PortfolioReplayRequest,
    *,
    ending_nav: str,
    ending_cash: str = "20000",
    commission: str = "50",
) -> PortfolioReplayResult:
    holdings = (
        HoldingSnapshot(
            ticker="AAPL",
            quantity=Decimal("100"),
            last_price=Decimal("100"),
            market_value=Decimal("10000"),
        ),
    )
    path = (
        NavPoint(ts=datetime(2024, 1, 2, tzinfo=_UTC), nav=Decimal("100000")),
        NavPoint(ts=datetime(2024, 1, 3, tzinfo=_UTC), nav=Decimal(ending_nav)),
    )
    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=Decimal(ending_cash),
        ending_nav=Decimal(ending_nav),
        total_commission=Decimal(commission),
        rebalance_commission=Decimal(commission),
        holdings=holdings,
        fills=(),
        nav_path=path,
        message="",
        result_content_hash=None,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(mode="python"), "result_content_hash": digest}
    )


def _full_telemetry() -> OptionalArmTelemetry:
    return OptionalArmTelemetry(
        research=ResearchTelemetry(
            calls=10,
            searches=4,
            tokens=1200,
            cost_usd=Decimal("0.42"),
            latency_ms=Decimal("850"),
            budget_usd=Decimal("1.00"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="wp13.telemetry",
            sample_count=5,
            missing_count=0,
        ),
        signal_quality=SignalQualityTelemetry(
            novelty=Decimal("0.3"),
            conflict=Decimal("0.1"),
            coverage=Decimal("0.8"),
            exploration=Decimal("0.2"),
            staleness_days=Decimal("2"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="wp13.signal_quality",
            sample_count=5,
            missing_count=0,
        ),
        forecast_brier=Decimal("0.18"),
        forecast_log_score=Decimal("-0.55"),
        forecast_uncertainty=Decimal("0.22"),
        forecast_evidence_mode=EvidenceMode.OBSERVED,
        forecast_provenance="wp5.calibration",
        forecast_sample_count=12,
        forecast_missing_count=0,
        active_return=Decimal("0.01"),
        benchmark_return=Decimal("0.005"),
        tail_loss=Decimal("-0.04"),
        scenario_pnl=Decimal("-0.02"),
        hard_constraint_breaches=(),
        accounting_breach=False,
        engine_status="ok",
        data_status="ok",
        failure_codes=(),
    )


def _pair_and_report(
    *,
    accounting_breach: bool = False,
    hard_constraint_breaches: tuple[str, ...] = (),
    challenger_nav: str = "106000",
) -> tuple[ReplayInputManifest, object, PolicyComparisonReport]:
    request = _request()
    manifest = _manifest(request)
    incumbent = _arm(
        ReplayArmLabel.INCUMBENT,
        manifest,
        arm_id="inc",
        weights_fp="w-inc",
        portfolio_version="incumbent@v1",
    )
    challenger = _arm(
        ReplayArmLabel.CHALLENGER,
        manifest,
        arm_id="ch",
        weights_fp="w-ch",
        portfolio_version="challenger@v1",
    )
    pair = build_replay_pair(
        pair_id="pair-1",
        shared_manifest=manifest,
        incumbent=incumbent,
        challenger=challenger,
    )
    ch_req = _request(request_id="req-ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    tel = _full_telemetry()
    if accounting_breach or hard_constraint_breaches:
        tel = tel.model_copy(
            update={
                "accounting_breach": accounting_breach,
                "hard_constraint_breaches": hard_constraint_breaches,
            }
        )
    inc_fold = ArmFoldEvidence(
        arm=ReplayArmLabel.INCUMBENT,
        fold_id="fold-1",
        manifest_content_hash=manifest.manifest_content_hash,
        request_content_hash=request.content_hash(),
        result=_ok_result(request, ending_nav="105000"),
        telemetry=_full_telemetry(),
    )
    ch_fold = ArmFoldEvidence(
        arm=ReplayArmLabel.CHALLENGER,
        fold_id="fold-1",
        manifest_content_hash=manifest.manifest_content_hash,
        request_content_hash=ch_req.content_hash(),
        result=_ok_result(ch_req, ending_nav=challenger_nav),
        telemetry=tel,
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(inc_fold,),
        challenger_folds=(ch_fold,),
        recorded_at=_TS,
        comparison_id=uuid4(),
        min_eval_folds=1,
    )
    return manifest, pair, report


def _criterion(
    *,
    criterion_id: str = "promo-nav-delta",
    gate_kind: GateKind = GateKind.PROMOTION,
    metric_name: str = "ending_nav",
    comparison_kind: MetricComparisonKind = MetricComparisonKind.PAIRED_DELTA,
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER,
    threshold: str = "0",
    evidence_mode: EvidenceMode = EvidenceMode.OBSERVED,
    min_sample_count: int = 1,
    min_folds: int = 1,
    min_duration_days: int = 0,
) -> GateCriterion:
    return GateCriterion(
        criterion_id=criterion_id,
        gate_kind=gate_kind,
        metric_name=metric_name,
        cohort="all",
        comparison_kind=comparison_kind,
        direction=direction,
        threshold=Decimal(threshold),
        evidence_mode=evidence_mode,
        min_sample_count=min_sample_count,
        min_folds=min_folds,
        min_duration_days=min_duration_days,
        missing_data_rule=MissingDataRule.FAIL_CLOSED,
        confidence_bound_rule=ConfidenceBoundRule.REQUIRE_AVAILABLE,
    )


def _criteria(
    *criteria: GateCriterion,
    author: str = "human-governance@dashboard",
    rationale: str = "pre-versioned promotion gate",
    criteria_version_id: UUID | None = None,
) -> HumanAuthoredGateCriteria:
    version_id = criteria_version_id or uuid4()
    draft = HumanAuthoredGateCriteria.model_construct(
        schema_version="1.0",
        criteria_key="policy-promotion-v1",
        criteria_version_id=version_id,
        author=author,
        rationale=rationale,
        effective_at=_TS,
        recorded_at=_TS,
        content_hash="0" * 64,
        criteria=tuple(criteria),
        require_identical_manifest=True,
        require_eligible_comparison=True,
        reject_accounting_breach=True,
        reject_hard_constraint_breach=True,
        supersedes_version_id=None,
    )
    digest = gate_criteria_content_hash(draft)
    return HumanAuthoredGateCriteria.model_validate(
        {**draft.model_dump(mode="python"), "content_hash": digest}
    )


def test_empty_criteria_fails_closed() -> None:
    _, _, report = _pair_and_report()
    criteria = _criteria()
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert "no_criteria" in detail.blockers
    assert detail.criterion_results == ()


def test_evaluator_cannot_author_criteria() -> None:
    assert not hasattr(evaluate_gate_criteria, "author_criteria")
    from digiquant.dashboard.replay import governance as gov

    assert not hasattr(gov, "author_gate_criteria")
    assert not hasattr(gov, "mint_criteria_from_report")
    with pytest.raises((TypeError, ValidationError)):
        HumanAuthoredGateCriteria()  # type: ignore[call-arg]


def test_missing_metric_is_insufficient() -> None:
    _, _, report = _pair_and_report()
    criteria = _criteria(
        _criterion(
            criterion_id="missing-metric",
            metric_name="does_not_exist",
            threshold="0",
        )
    )
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert len(detail.criterion_results) == 1
    row = detail.criterion_results[0]
    assert row.outcome is CriterionOutcome.INSUFFICIENT
    assert "missing" in row.reason


def test_accounting_breach_ineligible() -> None:
    _, _, report = _pair_and_report(accounting_breach=True)
    assert report.accounting_breach_visible is True
    criteria = _criteria(_criterion(threshold="-1000000"))
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert "accounting_breach_visible" in detail.blockers


def test_hard_constraint_breach_ineligible() -> None:
    _, _, report = _pair_and_report(hard_constraint_breaches=("max_weight",))
    assert report.hard_constraint_breach_visible is True
    criteria = _criteria(_criterion(threshold="-1000000"))
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert "hard_constraint_breach_visible" in detail.blockers


def test_promotion_blocked_report_ineligible() -> None:
    _, _, report = _pair_and_report(accounting_breach=True)
    assert report.eligible_for_governance is False
    criteria = _criteria(_criterion(threshold="-1000000"))
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert any("eligible_for_governance" in b or "accounting" in b for b in detail.blockers)


def test_per_criterion_results_and_eligible_name() -> None:
    _, _, report = _pair_and_report(challenger_nav="110000")
    assert report.eligible_for_governance is True
    criteria = _criteria(
        _criterion(
            criterion_id="nav-delta-positive",
            metric_name="ending_nav",
            comparison_kind=MetricComparisonKind.PAIRED_DELTA,
            direction=MetricDirection.HIGHER_IS_BETTER,
            threshold="0",
        ),
        _criterion(
            criterion_id="cost-not-worse",
            metric_name="cost_usd",
            comparison_kind=MetricComparisonKind.PAIRED_DELTA,
            direction=MetricDirection.LOWER_IS_BETTER,
            threshold="1",
        ),
    )
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert hasattr(detail, "eligible_for_human_review")
    assert detail.eligible_for_human_review is True
    assert {r.criterion_id for r in detail.criterion_results} == {
        "nav-delta-positive",
        "cost-not-worse",
    }
    assert all(r.outcome is CriterionOutcome.PASSED for r in detail.criterion_results)


def test_rollback_criteria_separate_from_promotion() -> None:
    _, _, report = _pair_and_report(challenger_nav="90000")
    # Challenger worse on NAV — promotion should fail; rollback can still pass.
    criteria = _criteria(
        _criterion(
            criterion_id="promo-nav",
            gate_kind=GateKind.PROMOTION,
            metric_name="ending_nav",
            comparison_kind=MetricComparisonKind.PAIRED_DELTA,
            direction=MetricDirection.HIGHER_IS_BETTER,
            threshold="0",
        ),
        _criterion(
            criterion_id="rollback-nav",
            gate_kind=GateKind.ROLLBACK,
            metric_name="ending_nav",
            comparison_kind=MetricComparisonKind.PAIRED_DELTA,
            direction=MetricDirection.LOWER_IS_BETTER,
            threshold="0",
        ),
    )
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.eligible_for_human_review is False
    assert detail.rollback_eligible_for_human_review is True
    promo = next(r for r in detail.criterion_results if r.criterion_id == "promo-nav")
    rollback = next(r for r in detail.criterion_results if r.criterion_id == "rollback-nav")
    assert promo.outcome is CriterionOutcome.FAILED
    assert rollback.outcome is CriterionOutcome.PASSED


def test_no_config_write(tmp_path: Path) -> None:
    _, _, report = _pair_and_report()
    criteria = _criteria(_criterion(threshold="-1000000"))
    before = {p.name for p in tmp_path.iterdir()} if tmp_path.exists() else set()
    detail = evaluate_gate_criteria(
        criteria=criteria,
        report=report,
        recorded_at=_TS,
        config_root=tmp_path,
    )
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after
    assert detail.evaluation_content_hash


def test_evaluation_explained_by_immutable_ids() -> None:
    manifest, pair, report = _pair_and_report(challenger_nav="110000")
    criteria = _criteria(_criterion(threshold="-1000000"))
    detail = evaluate_gate_criteria(criteria=criteria, report=report, recorded_at=_TS)
    assert detail.comparison_id == report.comparison_id
    assert detail.criteria_version_id == criteria.criteria_version_id
    assert detail.criteria_content_hash == criteria.content_hash
    assert detail.report_content_hash == report.report_content_hash
    assert len(detail.evaluation_content_hash) == 64
    assert detail.evaluation_id

    store = PolicyReplayStore()
    store.append_manifest(manifest, recorded_at=_TS)
    store.append_pair(pair, recorded_at=_TS)
    stored = persist_gate_evaluation(
        store,
        criteria=criteria,
        report=report,
        detail=detail,
    )
    evidence = store.load_gate_evidence(stored.evaluation_id)
    assert evidence.evaluation.evaluation_id == detail.evaluation_id
    assert evidence.evaluation.eligible_for_human_review == detail.eligible_for_human_review
    assert evidence.criteria.criteria_version_id == criteria.criteria_version_id
    assert evidence.comparison.comparison_id == report.comparison_id


def test_tampered_criteria_hash_rejected() -> None:
    _, _, report = _pair_and_report()
    criteria = _criteria(_criterion())
    bad = criteria.model_copy(update={"content_hash": "f" * 64})
    with pytest.raises(ValueError, match="content_hash"):
        evaluate_gate_criteria(criteria=bad, report=report, recorded_at=_TS)


def test_to_store_criteria_preserves_author_not_evaluator() -> None:
    criteria = _criteria(_criterion(), author="alice@dashboard")
    row = to_store_criteria_version(criteria)
    assert row.author == "alice@dashboard"
    assert row.author != "evaluator"
    assert row.content_hash == criteria.content_hash
