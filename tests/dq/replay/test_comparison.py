"""WP16.6 — complete paired policy comparison reports (#2999).

Red coverage: shared hash required; metric direction; absolute/delta;
count/missing/provenance/evidence mode; modeled/observed not pooled;
undersampled cannot promote; accounting/hard breach visible; folds retained;
deterministic report hash; every required group has values or unavailable reasons.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
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
    REQUIRED_METRIC_GROUPS,
    ArmFoldEvidence,
    ComparisonReportStatus,
    EvidenceMode,
    MetricDirection,
    MetricGroupId,
    OptionalArmTelemetry,
    PolicyComparisonReport,
    ResearchTelemetry,
    SignalQualityTelemetry,
    compare_policy_pair,
    policy_comparison_report_content_hash,
)
from digiquant.dashboard.replay.governance_models import (
    PolicyComparisonReport as GovernanceComparisonEnvelope,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    FillRecord,
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
    WalkForwardFold,
    build_replay_pair,
    portfolio_replay_result_content_hash,
)
from digiquant.dashboard.replay.store import PolicyReplayStore
from digiquant.portfolio.allocation_hashes import sha256_hex
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


def _manifest(
    request: PortfolioReplayRequest, *, fold: WalkForwardFold | None = None
) -> ReplayInputManifest:
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
        fold=fold,
    )
    return ReplayInputManifest(
        manifest_id="manifest-1",
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=content_hash,
        fold=fold,
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
    fills: tuple[FillRecord, ...] = (),
    nav_path: tuple[tuple[int, str], ...] | None = None,
) -> PortfolioReplayResult:
    holdings = (
        HoldingSnapshot(
            ticker="AAPL",
            quantity=Decimal("100"),
            last_price=Decimal("100"),
            market_value=Decimal("10000"),
        ),
    )
    path = ()
    if nav_path is not None:
        path = tuple(
            NavPoint(ts=datetime(2024, 1, day, tzinfo=_UTC), nav=Decimal(nav))
            for day, nav in nav_path
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
        fills=fills,
        nav_path=path,
        message="",
        result_content_hash=None,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(mode="python"), "result_content_hash": digest}
    )


def _pair_and_arms():
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
    return request, manifest, pair


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


def _arm_fold(
    *,
    arm: ReplayArmLabel,
    fold_id: str,
    request: PortfolioReplayRequest,
    result: PortfolioReplayResult,
    telemetry: OptionalArmTelemetry | None = None,
    manifest_content_hash: str,
    hard_constraint_breaches: tuple[str, ...] = (),
    accounting_breach: bool = False,
) -> ArmFoldEvidence:
    tel = telemetry or _full_telemetry()
    if hard_constraint_breaches or accounting_breach:
        tel = tel.model_copy(
            update={
                "hard_constraint_breaches": hard_constraint_breaches,
                "accounting_breach": accounting_breach,
            }
        )
    return ArmFoldEvidence(
        arm=arm,
        fold_id=fold_id,
        manifest_content_hash=manifest_content_hash,
        request_content_hash=request.content_hash(),
        result=result,
        telemetry=tel,
    )


def test_required_metric_groups_are_complete() -> None:
    assert REQUIRED_METRIC_GROUPS == frozenset(
        {
            MetricGroupId.RESEARCH,
            MetricGroupId.SIGNAL_QUALITY,
            MetricGroupId.FORECAST,
            MetricGroupId.ACTIONS,
            MetricGroupId.PORTFOLIO,
            MetricGroupId.RISK,
            MetricGroupId.ENGINE,
        }
    )


def test_shared_manifest_hash_required() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "102000"), (4, "105000")),
    )
    ch_req = _request(request_id="req-ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "103000"), (4, "106000")),
    )
    wrong_hash = "b" * 64
    with pytest.raises(ValueError, match="shared manifest"):
        compare_policy_pair(
            pair=pair,
            incumbent_folds=(
                _arm_fold(
                    arm=ReplayArmLabel.INCUMBENT,
                    fold_id="fold-1",
                    request=request,
                    result=inc_result,
                    manifest_content_hash=wrong_hash,
                ),
            ),
            challenger_folds=(
                _arm_fold(
                    arm=ReplayArmLabel.CHALLENGER,
                    fold_id="fold-1",
                    request=ch_req,
                    result=ch_result,
                    manifest_content_hash=manifest.manifest_content_hash,
                ),
            ),
            recorded_at=_TS,
            min_eval_folds=1,
        )


def test_every_required_group_present_with_direction_absolute_delta() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "102000"), (4, "105000")),
        fills=(
            FillRecord(
                ts=datetime(2024, 1, 3, tzinfo=_UTC),
                ticker="AAPL",
                side="buy",
                quantity=Decimal("10"),
                price=Decimal("100"),
                commission=Decimal("1"),
            ),
        ),
    )
    ch_req = _request(request_id="req-ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "103000"), (4, "106000")),
        fills=(
            FillRecord(
                ts=datetime(2024, 1, 3, tzinfo=_UTC),
                ticker="AAPL",
                side="buy",
                quantity=Decimal("12"),
                price=Decimal("100"),
                commission=Decimal("1.2"),
            ),
        ),
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=1,
    )
    assert isinstance(report, PolicyComparisonReport)
    assert report.status is ComparisonReportStatus.COMPLETE
    present = {g.group_id for g in report.metric_groups}
    assert present == REQUIRED_METRIC_GROUPS
    for group in report.metric_groups:
        assert group.metrics, f"{group.group_id} must expose metrics or unavailable leaves"
        for metric in group.metrics:
            assert isinstance(metric.direction, MetricDirection)
            assert metric.provenance.strip()
            assert metric.evidence_mode in EvidenceMode
            if metric.availability.value == "available":
                assert metric.absolute_incumbent is not None
                assert metric.absolute_challenger is not None
                assert metric.delta is not None
                assert metric.delta == metric.absolute_challenger - metric.absolute_incumbent
            else:
                assert metric.unavailable_reason
            assert metric.sample_count >= 0
            assert metric.missing_count >= 0


def test_modeled_and_observed_not_pooled() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    ch_req = _request(request_id="req-ch")
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "106000")),
    )
    # Incumbent observed research; challenger modeled — must remain distinct leaves.
    inc_tel = _full_telemetry()
    ch_tel = _full_telemetry().model_copy(
        update={
            "research": ResearchTelemetry(
                calls=12,
                searches=5,
                tokens=1500,
                cost_usd=Decimal("0.55"),
                latency_ms=Decimal("900"),
                budget_usd=Decimal("1.00"),
                evidence_mode=EvidenceMode.MODELED,
                provenance="wp13.modeled_counterfactual",
                sample_count=5,
                missing_count=0,
            )
        }
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                telemetry=inc_tel,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                telemetry=ch_tel,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=1,
    )
    research = next(g for g in report.metric_groups if g.group_id is MetricGroupId.RESEARCH)
    # Heterogeneous evidence modes → research leaves are unavailable (not pooled).
    for metric in research.metrics:
        assert metric.availability.value != "available" or (
            metric.evidence_mode is not EvidenceMode.OBSERVED
            or all(
                m.evidence_mode is EvidenceMode.OBSERVED
                for m in research.metrics
                if m.availability.value == "available"
            )
        )
    available_modes = {
        m.evidence_mode for m in research.metrics if m.availability.value == "available"
    }
    assert not (
        EvidenceMode.OBSERVED in available_modes and EvidenceMode.MODELED in available_modes
    ), "observed and modeled must not be pooled into available metrics"


def test_missing_telemetry_is_explicit_unavailable_not_zero() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    ch_req = _request(request_id="req-ch")
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "106000")),
    )
    empty = OptionalArmTelemetry()
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                telemetry=empty,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                telemetry=empty,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=1,
    )
    research = next(g for g in report.metric_groups if g.group_id is MetricGroupId.RESEARCH)
    for metric in research.metrics:
        assert metric.availability.value != "available"
        assert metric.unavailable_reason
        assert metric.absolute_incumbent is None
        assert metric.delta is None


def test_undersampled_cannot_promote() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    ch_req = _request(request_id="req-ch")
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "106000")),
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=3,
    )
    assert report.status is ComparisonReportStatus.UNDERSAMPLED
    assert report.undersampled is True
    assert report.eligible_for_governance is False
    assert report.promotion_blocked is True
    assert any("undersampled" in b or "min_eval_folds" in b for b in report.promotion_blockers)


def test_accounting_and_hard_breach_visible() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    ch_req = _request(request_id="req-ch")
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "106000")),
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                manifest_content_hash=manifest.manifest_content_hash,
                hard_constraint_breaches=("max_weight",),
                accounting_breach=True,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=1,
    )
    assert report.hard_constraint_breach_visible is True
    assert report.accounting_breach_visible is True
    assert report.eligible_for_governance is False
    assert report.promotion_blocked is True
    risk = next(g for g in report.metric_groups if g.group_id is MetricGroupId.RISK)
    assert any("hard_constraint" in m.name or "breach" in m.name for m in risk.metrics)


def test_folds_retained_and_hash_deterministic() -> None:
    request, manifest, pair = _pair_and_arms()
    fold_ids = ("fold-1", "fold-2")
    inc_folds = []
    ch_folds = []
    for fold_id in fold_ids:
        inc_req = _request(request_id=f"inc-{fold_id}")
        ch_req = _request(
            request_id=f"ch-{fold_id}",
            targets=(("AAPL", "0.5"), ("MSFT", "0.3")),
        )
        inc_folds.append(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id=fold_id,
                request=inc_req,
                result=_ok_result(
                    inc_req,
                    ending_nav="105000",
                    nav_path=((2, "100000"), (3, "105000")),
                ),
                manifest_content_hash=manifest.manifest_content_hash,
            )
        )
        ch_folds.append(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id=fold_id,
                request=ch_req,
                result=_ok_result(
                    ch_req,
                    ending_nav="106000",
                    nav_path=((2, "100000"), (3, "106000")),
                ),
                manifest_content_hash=manifest.manifest_content_hash,
            )
        )
    comparison_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    report_a = compare_policy_pair(
        pair=pair,
        incumbent_folds=tuple(inc_folds),
        challenger_folds=tuple(ch_folds),
        recorded_at=_TS,
        comparison_id=comparison_id,
        min_eval_folds=2,
    )
    report_b = compare_policy_pair(
        pair=pair,
        incumbent_folds=tuple(inc_folds),
        challenger_folds=tuple(ch_folds),
        recorded_at=_TS,
        comparison_id=comparison_id,
        min_eval_folds=2,
    )
    assert [f.fold_id for f in report_a.folds] == list(fold_ids)
    assert report_a.report_content_hash == report_b.report_content_hash
    assert report_a.report_content_hash == policy_comparison_report_content_hash(report_a)


def test_incomplete_report_not_governance_ready() -> None:
    request, manifest, pair = _pair_and_arms()
    # Challenger fold missing → incomplete pairing.
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    with pytest.raises(ValueError, match="paired fold"):
        compare_policy_pair(
            pair=pair,
            incumbent_folds=(
                _arm_fold(
                    arm=ReplayArmLabel.INCUMBENT,
                    fold_id="fold-1",
                    request=request,
                    result=inc_result,
                    manifest_content_hash=manifest.manifest_content_hash,
                ),
            ),
            challenger_folds=(),
            recorded_at=_TS,
            min_eval_folds=1,
        )


def test_governance_envelope_persists_via_store() -> None:
    request, manifest, pair = _pair_and_arms()
    inc_result = _ok_result(
        request,
        ending_nav="105000",
        nav_path=((2, "100000"), (3, "105000")),
    )
    ch_req = _request(request_id="req-ch")
    ch_result = _ok_result(
        ch_req,
        ending_nav="106000",
        nav_path=((2, "100000"), (3, "106000")),
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=(
            _arm_fold(
                arm=ReplayArmLabel.INCUMBENT,
                fold_id="fold-1",
                request=request,
                result=inc_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        challenger_folds=(
            _arm_fold(
                arm=ReplayArmLabel.CHALLENGER,
                fold_id="fold-1",
                request=ch_req,
                result=ch_result,
                manifest_content_hash=manifest.manifest_content_hash,
            ),
        ),
        recorded_at=_TS,
        min_eval_folds=1,
    )
    envelope = report.to_governance_envelope()
    assert isinstance(envelope, GovernanceComparisonEnvelope)
    assert set(envelope.metric_groups_present) == {g.value for g in REQUIRED_METRIC_GROUPS}

    store = PolicyReplayStore()
    store.append_manifest(manifest, recorded_at=_TS)
    store.append_pair(pair, recorded_at=_TS)
    stored = store.append_comparison(envelope)
    assert stored.comparison_id == report.comparison_id
    assert stored.report_content_hash == report.report_content_hash


def test_metric_leaf_rejects_available_without_values() -> None:
    from digiquant.dashboard.replay.comparison import ComparisonMetric, MetricAvailability

    with pytest.raises(ValidationError):
        ComparisonMetric(
            name="calls",
            direction=MetricDirection.LOWER_IS_BETTER,
            evidence_mode=EvidenceMode.OBSERVED,
            availability=MetricAvailability.AVAILABLE,
            provenance="t",
            sample_count=1,
            missing_count=0,
        )
