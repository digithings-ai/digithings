"""WP16.9 — typed service exposure for policy replay evidence (#3011).

Red coverage: discovery helpers fail closed on invalid IDs; summaries/artifact
IDs only; run/evaluate cannot activate policy; decision write requires principal.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from digikey.models import DigiAuthContext
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
    ResearchTelemetry,
    SignalQualityTelemetry,
    compare_policy_pair,
)
from digiquant.dashboard.replay.governance import (
    AuthenticatedPrincipal,
    ConfidenceBoundRule,
    GateCriterion,
    GateKind,
    HumanAuthoredGateCriteria,
    MetricComparisonKind,
    MissingDataRule,
    gate_criteria_content_hash,
)
from digiquant.dashboard.replay.governance_models import GovernanceDecisionKind
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
from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.service import (
    service_evaluate_policy_gate,
    service_get_policy_comparison,
    service_get_policy_gate_evaluation,
    service_get_policy_replay,
    service_ingest_gate_criteria,
    service_ingest_policy_comparison,
    service_record_policy_governance_decision,
    service_run_policy_replay,
    set_policy_replay_store,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_UTC = UTC
_TS = datetime(2024, 2, 1, tzinfo=_UTC)


@pytest.fixture(autouse=True)
def _fresh_store() -> None:
    set_policy_replay_store(PolicyReplayStore())
    yield
    set_policy_replay_store(None)


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
) -> PortfolioReplayRequest:
    closes = ["100", "101", "102", "103", "104"]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal("100000"),
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
        manifest_id="manifest-svc",
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    return ReplayInputManifest(
        manifest_id="manifest-svc",
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


def _pair_and_report(*, challenger_nav: str = "105000"):
    req_inc = _request(request_id="req-inc")
    req_chl = _request(request_id="req-chl", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    manifest = _manifest(req_inc)
    pair = build_replay_pair(
        pair_id="pair-svc",
        shared_manifest=manifest,
        incumbent=_arm(
            ReplayArmLabel.INCUMBENT,
            manifest,
            arm_id="inc-1",
            weights_fp="w-inc",
            portfolio_version="p-inc",
        ),
        challenger=_arm(
            ReplayArmLabel.CHALLENGER,
            manifest,
            arm_id="chl-1",
            weights_fp="w-chl",
            portfolio_version="p-chl",
        ),
    )
    store = PolicyReplayStore()
    set_policy_replay_store(store)
    store.append_manifest(manifest, recorded_at=_TS)
    store.append_pair(pair, recorded_at=_TS)

    telemetry = OptionalArmTelemetry(
        research=ResearchTelemetry(
            calls=1,
            searches=1,
            tokens=100,
            cost_usd=Decimal("0.01"),
            latency_ms=Decimal("10"),
            budget_usd=Decimal("1"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="test.research",
        ),
        signal_quality=SignalQualityTelemetry(
            novelty=Decimal("0.1"),
            conflict=Decimal("0.0"),
            coverage=Decimal("1.0"),
            exploration=Decimal("0.2"),
            staleness_days=Decimal("1"),
            evidence_mode=EvidenceMode.OBSERVED,
            provenance="test.signal",
        ),
        accounting_breach=False,
        hard_constraint_breaches=(),
    )
    folds_inc = (
        ArmFoldEvidence(
            fold_id="fold-1",
            arm=ReplayArmLabel.INCUMBENT,
            manifest_content_hash=manifest.manifest_content_hash,
            request_content_hash=req_inc.content_hash(),
            result=_ok_result(req_inc, ending_nav="100000"),
            telemetry=telemetry,
        ),
    )
    folds_chl = (
        ArmFoldEvidence(
            fold_id="fold-1",
            arm=ReplayArmLabel.CHALLENGER,
            manifest_content_hash=manifest.manifest_content_hash,
            request_content_hash=req_chl.content_hash(),
            result=_ok_result(req_chl, ending_nav=challenger_nav),
            telemetry=telemetry,
        ),
    )
    report = compare_policy_pair(
        pair=pair,
        incumbent_folds=folds_inc,
        challenger_folds=folds_chl,
        recorded_at=_TS,
    )
    return pair, report


def _criteria() -> HumanAuthoredGateCriteria:
    criterion = GateCriterion(
        criterion_id="nav-delta",
        gate_kind=GateKind.PROMOTION,
        metric_name="ending_nav",
        cohort="all",
        comparison_kind=MetricComparisonKind.PAIRED_DELTA,
        direction=MetricDirection.HIGHER_IS_BETTER,
        threshold=Decimal("0"),
        evidence_mode=EvidenceMode.OBSERVED,
        min_sample_count=0,
        min_folds=0,
        min_duration_days=0,
        missing_data_rule=MissingDataRule.FAIL_CLOSED,
        confidence_bound_rule=ConfidenceBoundRule.REQUIRE_AVAILABLE,
    )
    draft = HumanAuthoredGateCriteria.model_construct(
        schema_version="1.0",
        criteria_key="promo-svc",
        criteria_version_id=uuid4(),
        author="human-author",
        rationale="pre-versioned promotion gate",
        effective_at=_TS,
        recorded_at=_TS,
        content_hash="0" * 64,
        criteria=(criterion,),
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


def test_run_policy_replay_fails_closed_on_unknown_pair() -> None:
    with pytest.raises(LookupError, match="pair"):
        service_run_policy_replay(pair_content_hash="f" * 64, recorded_at=_TS)


def test_run_and_get_policy_replay_summary_ids_only() -> None:
    pair, _report = _pair_and_report()
    summary = service_run_policy_replay(
        pair_content_hash=pair.pair_content_hash,
        run_id="run-svc-1",
        recorded_at=_TS,
    )
    assert summary.run_id == "run-svc-1"
    assert summary.pair_id == pair.pair_id
    assert summary.pair_content_hash == pair.pair_content_hash
    assert summary.status == "in_progress"
    assert "run_started" in summary.event_kinds
    dumped = summary.model_dump(mode="json")
    assert "fills" not in dumped
    assert "holdings" not in dumped
    assert "nav_path" not in dumped

    fetched = service_get_policy_replay("run-svc-1")
    assert fetched.run_id == summary.run_id
    assert fetched.status == "in_progress"


def test_get_policy_replay_fails_closed_on_unknown_run() -> None:
    with pytest.raises(LookupError, match="run"):
        service_get_policy_replay("missing-run")


def test_get_comparison_and_evaluate_gate_return_summaries() -> None:
    _pair, report = _pair_and_report(challenger_nav="110000")
    ingested = service_ingest_policy_comparison(report)
    assert ingested.comparison_id == report.comparison_id
    assert "metric_groups" not in ingested.model_dump(mode="json")
    assert "folds" not in ingested.model_dump(mode="json")

    fetched = service_get_policy_comparison(str(report.comparison_id))
    assert fetched.comparison_id == report.comparison_id
    assert fetched.report_content_hash == report.report_content_hash
    assert fetched.status == report.status.value

    criteria = _criteria()
    service_ingest_gate_criteria(criteria)
    evaluation = service_evaluate_policy_gate(
        comparison_id=str(report.comparison_id),
        criteria_version_id=str(criteria.criteria_version_id),
        recorded_at=_TS,
    )
    assert evaluation.eligible_for_human_review is True
    assert evaluation.comparison_id == report.comparison_id
    dumped = evaluation.model_dump(mode="json")
    assert "criterion_results" not in dumped or "observed_value" not in str(dumped)
    # summaries expose blockers / eligibility / IDs — not raw metric leaves
    assert "fills" not in dumped

    loaded = service_get_policy_gate_evaluation(str(evaluation.evaluation_id))
    assert loaded.evaluation_id == evaluation.evaluation_id


def test_invalid_comparison_and_evaluation_ids_fail_closed() -> None:
    with pytest.raises(LookupError):
        service_get_policy_comparison(str(uuid4()))
    with pytest.raises(LookupError):
        service_get_policy_gate_evaluation(str(uuid4()))
    with pytest.raises(LookupError):
        service_evaluate_policy_gate(
            comparison_id=str(uuid4()),
            criteria_version_id=str(uuid4()),
            recorded_at=_TS,
        )


def test_run_and_evaluate_have_no_activation_side_effects() -> None:
    pair, report = _pair_and_report(challenger_nav="110000")
    service_ingest_policy_comparison(report)
    criteria = _criteria()
    service_ingest_gate_criteria(criteria)
    service_run_policy_replay(
        pair_content_hash=pair.pair_content_hash,
        run_id="run-no-activate",
        recorded_at=_TS,
    )
    service_evaluate_policy_gate(
        comparison_id=str(report.comparison_id),
        criteria_version_id=str(criteria.criteria_version_id),
        recorded_at=_TS,
    )
    import digiquant.service as svc

    for name in (
        "service_run_policy_replay",
        "service_evaluate_policy_gate",
        "service_get_policy_replay",
        "service_get_policy_comparison",
        "service_get_policy_gate_evaluation",
    ):
        src = inspect.getsource(getattr(svc, name)).lower()
        for banned in ("set_live", "rollback_live", "broker.", "deploy_policy"):
            assert banned not in src
        # Must not call activation helpers (comments mentioning "never activate" are ok).
        assert "activate_policy" not in src
        assert "promote_policy" not in src


def test_decision_write_requires_authenticated_principal() -> None:
    _pair, report = _pair_and_report(challenger_nav="110000")
    service_ingest_policy_comparison(report)
    criteria = _criteria()
    service_ingest_gate_criteria(criteria)
    evaluation = service_evaluate_policy_gate(
        comparison_id=str(report.comparison_id),
        criteria_version_id=str(criteria.criteria_version_id),
        recorded_at=_TS,
    )
    sig = inspect.signature(service_record_policy_governance_decision)
    assert "actor" not in sig.parameters
    assert "actor_principal" not in sig.parameters
    assert "principal" in sig.parameters

    with pytest.raises((TypeError, ValidationError, ValueError)):
        service_record_policy_governance_decision(  # type: ignore[call-arg]
            evaluation_id=str(evaluation.evaluation_id),
            decision_kind=GovernanceDecisionKind.APPROVE,
            rationale="looks good",
            recorded_at=_TS,
            actor="spoofed",
        )

    auth = DigiAuthContext(
        subject="key:operator-1",
        scopes=["digiquant:backtest"],
        tenant_slug="default",
        principal_kind="api_key",
    )
    principal = AuthenticatedPrincipal.from_digi_auth(auth)
    decision = service_record_policy_governance_decision(
        principal=principal,
        evaluation_id=str(evaluation.evaluation_id),
        decision_kind=GovernanceDecisionKind.APPROVE,
        rationale="eligible challenger accepted for external review",
        recorded_at=_TS,
    )
    assert decision.actor_principal == "key:operator-1"
    assert decision.decision_kind is GovernanceDecisionKind.APPROVE
