"""WP16.2 — append-only policy replay governance store (#2983)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

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
from digiquant.dashboard.replay.governance_models import (
    GateCriteriaVersion,
    GateEvaluation,
    GovernanceDecisionKind,
    PolicyComparisonReport,
    PolicyGovernanceDecision,
    ReplayRunEvent,
    ReplayRunEventKind,
    governance_content_hash,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    InstrumentBarSeries,
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
from digiquant.dashboard.replay.store import (
    LoadedGateEvidence,
    PolicyReplayStore,
    PolicyReplayStoreConflict,
    PolicyReplayStoreError,
    PolicyReplayStoreMissingError,
)
from digiquant.portfolio.allocation_hashes import sha256_hex

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
_RUN = "replay-run-wp162"
_PAIR_ID = "pair-wp162"


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=(_bar(2, "100"), _bar(3, "101"), _bar(4, "102")),
    )


def _request() -> PortfolioReplayRequest:
    return PortfolioReplayRequest(
        request_id="req-wp162",
        starting_cash=Decimal("100000"),
        series=(_series("AAPL"), _series("MSFT")),
        target_weights=(
            TargetWeight(ticker="AAPL", weight=Decimal("0.4")),
            TargetWeight(ticker="MSFT", weight=Decimal("0.4")),
        ),
        execution=ExecutionPolicy(random_seed=42),
    )


def _manifest() -> ReplayInputManifest:
    request = _request()
    execution = request.execution
    shared = SharedInputIdentity(
        data_hash=data_hash_from_request(request),
        cost_hash=cost_hash_from_execution(execution),
        execution_hash=execution_policy_hash(execution),
        random_seed_hash=random_seed_hash(execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(execution.fill_fraction),
        starting_cash=request.starting_cash,
    )
    dataset_hash = data_hash_from_request(request)
    sources = tuple(
        sorted(
            (
                PolicyVersionRef(
                    family=PolicyFamily.DATA_SOURCE,
                    version_id="bars-v1",
                    content_hash=dataset_hash,
                ),
                PolicyVersionRef(
                    family=PolicyFamily.COST_SCHEDULE,
                    version_id="cost-v1",
                    content_hash=shared.cost_hash,
                ),
            ),
            key=lambda ref: (ref.family.value, ref.version_id),
        )
    )
    manifest_hash = replay_input_manifest_content_hash(
        manifest_id="manifest-wp162",
        replay_as_of=_TS,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    return ReplayInputManifest(
        manifest_id="manifest-wp162",
        replay_as_of=_TS,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=manifest_hash,
    )


def _arm(
    arm: ReplayArmLabel, manifest: ReplayInputManifest, *, arm_id: str, weights_fp: str
) -> ReplayArmSpec:
    bundle = PolicyBundle(
        portfolio_target=PolicyVersionRef(
            family=PolicyFamily.PORTFOLIO_TARGET,
            version_id=f"portfolio-{arm_id}",
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


def _pair(manifest: ReplayInputManifest | None = None):
    manifest = manifest or _manifest()
    incumbent = _arm(ReplayArmLabel.INCUMBENT, manifest, arm_id="inc-1", weights_fp="w-inc")
    challenger = _arm(ReplayArmLabel.CHALLENGER, manifest, arm_id="chl-1", weights_fp="w-chl")
    return build_replay_pair(
        pair_id=_PAIR_ID,
        shared_manifest=manifest,
        incumbent=incumbent,
        challenger=challenger,
    )


def _ok_result(*, arm_id: str, request_hash: str) -> PortfolioReplayResult:
    draft = PortfolioReplayResult.model_construct(
        request_id=f"req-{arm_id}",
        request_content_hash=request_hash,
        status=PortfolioReplayStatus.OK,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("50000"),
        ending_nav=Decimal("100500"),
        total_commission=Decimal("12"),
        rebalance_commission=Decimal("12"),
        result_content_hash="a" * 64,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(), "result_content_hash": digest}
    )


def _criteria(
    *, criteria_key: str = "shadow-allocation-v1", **overrides: object
) -> GateCriteriaVersion:
    fields: dict[str, object] = dict(
        criteria_version_id=uuid4(),
        criteria_key=criteria_key,
        content_hash="",
        effective_at=_TS - timedelta(days=1),
        recorded_at=_TS,
        author="dashboard-governance",
        rationale="shadow evidence gate",
        supersedes_version_id=None,
    )
    fields.update(overrides)
    base = GateCriteriaVersion(
        criteria_version_id=fields["criteria_version_id"],  # type: ignore[arg-type]
        criteria_key=str(fields["criteria_key"]),
        content_hash="b" * 64,
        effective_at=fields["effective_at"],  # type: ignore[arg-type]
        recorded_at=fields["recorded_at"],  # type: ignore[arg-type]
        author=str(fields["author"]),
        rationale=str(fields["rationale"]),
        supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
    )
    digest = governance_content_hash(base)
    return base.model_copy(update={"content_hash": digest})


class TestPolicyReplayStoreManifestAndPair:
    def test_manifest_content_hash_dedupe(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        first = store.append_manifest(manifest, recorded_at=_TS)
        second = store.append_manifest(manifest, recorded_at=_TS + timedelta(seconds=1))
        assert second.record_id == first.record_id
        assert store.manifest_count() == 1

    def test_pair_requires_identical_shared_manifest_hash(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        stored = store.append_pair(pair, recorded_at=_TS)
        assert stored.pair.pair_content_hash == pair.pair_content_hash

        bad_manifest = manifest.model_copy(
            update={
                "manifest_id": "other-manifest",
                "manifest_content_hash": "c" * 64,
            }
        )
        bad_incumbent = pair.incumbent.model_copy(
            update={"manifest_content_hash": bad_manifest.manifest_content_hash}
        )
        with pytest.raises(PolicyReplayStoreError, match="identical shared manifest"):
            store.append_pair(
                pair.model_copy(
                    update={"incumbent": bad_incumbent, "shared_manifest": bad_manifest}
                ),
                recorded_at=_TS,
            )

    def test_pair_dedupe_by_content_hash(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        first = store.append_pair(pair, recorded_at=_TS)
        second = store.append_pair(pair, recorded_at=_TS + timedelta(minutes=1))
        assert second.record_id == first.record_id


class TestPolicyReplayStoreRunLifecycle:
    def test_run_events_append_only_no_mutable_status_row(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        store.append_pair(pair, recorded_at=_TS)

        started = store.append_run_event(
            ReplayRunEvent(
                event_id=uuid4(),
                run_id=_RUN,
                pair_id=pair.pair_id,
                event_kind=ReplayRunEventKind.RUN_STARTED,
                sequence=0,
                recorded_at=_TS,
            )
        )
        dispatched = store.append_run_event(
            ReplayRunEvent(
                event_id=uuid4(),
                run_id=_RUN,
                pair_id=pair.pair_id,
                event_kind=ReplayRunEventKind.ARM_DISPATCHED,
                sequence=1,
                recorded_at=_TS + timedelta(seconds=1),
                detail="incumbent",
            )
        )
        assert started.sequence == 0
        assert dispatched.sequence == 1
        events = store.list_run_events(_RUN)
        assert len(events) == 2
        assert events[0].event_kind == ReplayRunEventKind.RUN_STARTED
        assert store.run_status_from_events(_RUN) == "in_progress"

        store.append_run_event(
            ReplayRunEvent(
                event_id=uuid4(),
                run_id=_RUN,
                pair_id=pair.pair_id,
                event_kind=ReplayRunEventKind.RUN_COMPLETED,
                sequence=2,
                recorded_at=_TS + timedelta(seconds=2),
            )
        )
        assert store.run_status_from_events(_RUN) == "completed"

    def test_duplicate_event_id_is_idempotent(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        store.append_pair(_pair(manifest), recorded_at=_TS)
        event = ReplayRunEvent(
            event_id=uuid4(),
            run_id=_RUN,
            pair_id=_PAIR_ID,
            event_kind=ReplayRunEventKind.RUN_STARTED,
            sequence=0,
            recorded_at=_TS,
        )
        first = store.append_run_event(event)
        second = store.append_run_event(event)
        assert second == first

    def test_changed_event_content_raises_conflict(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        store.append_pair(_pair(manifest), recorded_at=_TS)
        event_id = uuid4()
        store.append_run_event(
            ReplayRunEvent(
                event_id=event_id,
                run_id=_RUN,
                pair_id=_PAIR_ID,
                event_kind=ReplayRunEventKind.RUN_STARTED,
                sequence=0,
                recorded_at=_TS,
            )
        )
        mutated = ReplayRunEvent(
            event_id=event_id,
            run_id=_RUN,
            pair_id=_PAIR_ID,
            event_kind=ReplayRunEventKind.RUN_FAILED,
            sequence=0,
            recorded_at=_TS,
        )
        with pytest.raises(PolicyReplayStoreConflict):
            store.append_run_event(mutated)

    def test_duplicate_run_sequence_raises_conflict(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        store.append_pair(_pair(manifest), recorded_at=_TS)
        store.append_run_event(
            ReplayRunEvent(
                event_id=uuid4(),
                run_id=_RUN,
                pair_id=_PAIR_ID,
                event_kind=ReplayRunEventKind.RUN_STARTED,
                sequence=0,
                recorded_at=_TS,
            )
        )
        with pytest.raises(PolicyReplayStoreConflict, match="sequence already exists"):
            store.append_run_event(
                ReplayRunEvent(
                    event_id=uuid4(),
                    run_id=_RUN,
                    pair_id=_PAIR_ID,
                    event_kind=ReplayRunEventKind.ARM_DISPATCHED,
                    sequence=0,
                    recorded_at=_TS + timedelta(seconds=1),
                )
            )

    def test_arm_result_immutable_final(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        store.append_pair(pair, recorded_at=_TS)
        result = _ok_result(arm_id="inc-1", request_hash=pair.incumbent.arm_content_hash)
        stored = store.append_arm_result(
            run_id=_RUN, arm_id="inc-1", result=result, recorded_at=_TS
        )
        assert stored.result.result_content_hash == result.result_content_hash
        again = store.append_arm_result(run_id=_RUN, arm_id="inc-1", result=result, recorded_at=_TS)
        assert again.record_id == stored.record_id

        other = result.model_copy(update={"ending_nav": Decimal("999999")})
        with pytest.raises(PolicyReplayStoreConflict):
            store.append_arm_result(run_id=_RUN, arm_id="inc-1", result=other, recorded_at=_TS)


class TestPolicyReplayStoreGovernance:
    def test_criteria_superseding_and_as_of(self) -> None:
        store = PolicyReplayStore()
        v1 = _criteria(effective_at=_TS - timedelta(days=2))
        store.append_criteria(v1)
        v2 = _criteria(
            criteria_version_id=uuid4(),
            effective_at=_TS - timedelta(hours=1),
            supersedes_version_id=v1.criteria_version_id,
        )
        store.append_criteria(v2)

        as_early = store.select_criteria_as_of(
            criteria_key="shadow-allocation-v1", as_of=_TS - timedelta(days=1)
        )
        assert as_early is not None
        assert as_early.criteria_version_id == v1.criteria_version_id

        as_late = store.select_criteria_as_of(criteria_key="shadow-allocation-v1", as_of=_TS)
        assert as_late is not None
        assert as_late.criteria_version_id == v2.criteria_version_id

    def test_evaluation_and_decision_immutable(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        store.append_pair(pair, recorded_at=_TS)

        comparison = PolicyComparisonReport(
            comparison_id=uuid4(),
            pair_content_hash=pair.pair_content_hash,
            shared_manifest_content_hash=manifest.manifest_content_hash,
            report_content_hash=sha256_hex({"status": "ok"}),
            recorded_at=_TS,
            status="ok",
            metric_groups_present=("portfolio", "research"),
        )
        store.append_comparison(comparison)

        criteria = _criteria()
        store.append_criteria(criteria)

        evaluation = GateEvaluation(
            evaluation_id=uuid4(),
            comparison_id=comparison.comparison_id,
            criteria_version_id=criteria.criteria_version_id,
            evaluation_content_hash=sha256_hex(
                {"eligible": True, "comparison": str(comparison.comparison_id)}
            ),
            recorded_at=_TS,
            eligible_for_human_review=True,
        )
        store.append_evaluation(evaluation)

        decision = PolicyGovernanceDecision(
            decision_id=uuid4(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.DEFER,
            actor_principal="human-reviewer@digithings.ai",
            rationale="needs more folds",
            decision_content_hash=sha256_hex(
                {"kind": "defer", "evaluation": str(evaluation.evaluation_id)}
            ),
            recorded_at=_TS,
        )
        store.append_decision(decision)

        mutated_eval = evaluation.model_copy(update={"eligible_for_human_review": False})
        with pytest.raises(PolicyReplayStoreConflict):
            store.append_evaluation(mutated_eval)

        mutated_decision = decision.model_copy(
            update={
                "rationale": "changed",
                "decision_content_hash": sha256_hex({"kind": "defer", "rationale": "changed"}),
            }
        )
        with pytest.raises(PolicyReplayStoreConflict):
            store.append_decision(mutated_decision)

    def test_reconstruct_gate_evidence_from_immutable_ids(self) -> None:
        store = PolicyReplayStore()
        manifest = _manifest()
        store.append_manifest(manifest, recorded_at=_TS)
        pair = _pair(manifest)
        store.append_pair(pair, recorded_at=_TS)

        comparison = PolicyComparisonReport(
            comparison_id=uuid4(),
            pair_content_hash=pair.pair_content_hash,
            shared_manifest_content_hash=manifest.manifest_content_hash,
            report_content_hash=sha256_hex({"status": "ok"}),
            recorded_at=_TS,
            status="ok",
        )
        store.append_comparison(comparison)
        criteria = _criteria()
        store.append_criteria(criteria)
        evaluation = GateEvaluation(
            evaluation_id=uuid4(),
            comparison_id=comparison.comparison_id,
            criteria_version_id=criteria.criteria_version_id,
            evaluation_content_hash=sha256_hex({"eligible": True}),
            recorded_at=_TS,
            eligible_for_human_review=True,
        )
        store.append_evaluation(evaluation)
        decision = PolicyGovernanceDecision(
            decision_id=uuid4(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.APPROVE,
            actor_principal="human-reviewer@digithings.ai",
            rationale="eligible after review",
            decision_content_hash=sha256_hex({"kind": "approve"}),
            recorded_at=_TS,
        )
        store.append_decision(decision)

        evidence = store.load_gate_evidence(evaluation.evaluation_id)
        assert isinstance(evidence, LoadedGateEvidence)
        assert evidence.evaluation.evaluation_id == evaluation.evaluation_id
        assert evidence.comparison.comparison_id == comparison.comparison_id
        assert evidence.criteria.criteria_version_id == criteria.criteria_version_id
        assert evidence.decisions == (decision,)
        assert evidence.pair.pair_content_hash == pair.pair_content_hash
        assert evidence.manifest.manifest_content_hash == manifest.manifest_content_hash

    def test_missing_evaluation_raises(self) -> None:
        store = PolicyReplayStore()
        with pytest.raises(PolicyReplayStoreMissingError):
            store.load_gate_evidence(uuid4())
