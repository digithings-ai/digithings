"""WP15.5 — compile immutable structured lesson versions (#2971).

Red coverage: cutoff/eligibility; Polars aggregation; low-sample prior/shrinkage;
deterministic hash; late episode new version; old queryable; prose cannot replace
payload; consuming run excluded; all source IDs exposed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.learning.lesson_registry import (
    LessonCompilationError,
    LessonCompilationPolicy,
    LessonCompiler,
    cohort_key,
)
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentAttributionReport,
    ComponentObservation,
    EpisodeDisposition,
    EvidenceQuality,
    H8TargetLineage,
    H9ExecutionLinks,
    LessonQualityState,
    OutcomeEpisode,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    episode_content_hash,
    episode_version_id,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_HORIZON_END = _TS + timedelta(days=21)
_AVAILABLE = _TS + timedelta(days=22)
_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_OUTCOME_ID = UUID("22222222-2222-4222-8222-222222222222")
_POLICY = LessonCompilationPolicy(
    policy_id="forecast-error-v1",
    component=AttributionComponent.FORECAST,
    metric="forecast_error_bps",
    min_sample=3,
    prior=Decimal("-10.0"),
)


def _temporal(**overrides: object) -> OutcomeTemporalContract:
    fields: dict[str, object] = dict(
        effective_at=_TS - timedelta(days=21),
        known_at=_TS - timedelta(days=20),
        recorded_at=_TS,
        horizon_end=_HORIZON_END,
        available_at=_AVAILABLE,
        replay_as_of=_AVAILABLE,
    )
    fields.update(overrides)
    return OutcomeTemporalContract(**fields)


def _realized(**overrides: object) -> RealizedReturnObservation:
    fields: dict[str, object] = dict(
        instrument_return=Decimal("0.042"),
        benchmark_return=Decimal("0.018"),
        active_return=Decimal("0.024"),
        accounting_period_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        contribution_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    fields.update(overrides)
    return RealizedReturnObservation(**fields)


def _episode(**overrides: object) -> OutcomeEpisode:
    fields: dict[str, object] = dict(
        episode_key=f"forecast:{_FORECAST_ID}:horizon:21s",
        forecast_id=_FORECAST_ID,
        outcome_id=_OUTCOME_ID,
        mandate_id="mandate-daily",
        instrument_id="AAPL",
        horizon_id="h-21s",
        source_run_id="run-2026-08-26",
        disposition=EpisodeDisposition.AUTHORIZED,
        temporal=_temporal(),
        h8_lineage=H8TargetLineage(
            requested_weight=Decimal("0.05"),
            approved_weight=Decimal("0.04"),
            adjustment_codes=("risk_cap",),
        ),
        h9_links=H9ExecutionLinks(
            action_id=UUID("66666666-6666-4666-8666-666666666666"),
            order_id=UUID("77777777-7777-4777-8777-777777777777"),
            fill_ids=(UUID("88888888-8888-4888-8888-888888888888"),),
            holding_id=UUID("99999999-9999-4999-8999-999999999999"),
        ),
        realized=_realized(),
        supersedes_version_id=None,
    )
    fields.update(overrides)
    content_hash = episode_content_hash(
        episode_key=str(fields["episode_key"]),
        forecast_id=fields["forecast_id"],  # type: ignore[arg-type]
        outcome_id=fields["outcome_id"],  # type: ignore[arg-type]
        mandate_id=str(fields["mandate_id"]),
        instrument_id=str(fields["instrument_id"]),
        horizon_id=str(fields["horizon_id"]),
        source_run_id=str(fields["source_run_id"]),
        disposition=fields["disposition"],  # type: ignore[arg-type]
        temporal=fields["temporal"],  # type: ignore[arg-type]
        realized=fields.get("realized"),  # type: ignore[arg-type]
        h8_lineage=fields.get("h8_lineage"),  # type: ignore[arg-type]
        h9_links=fields.get("h9_links"),  # type: ignore[arg-type]
        evidence_bundle_id=fields.get("evidence_bundle_id"),  # type: ignore[arg-type]
        research_state_version_id=fields.get("research_state_version_id"),  # type: ignore[arg-type]
        context_manifest_id=fields.get("context_manifest_id"),  # type: ignore[arg-type]
        policy_version_id=fields.get("policy_version_id"),  # type: ignore[arg-type]
        expected_cost_id=fields.get("expected_cost_id"),  # type: ignore[arg-type]
        realized_cost_id=fields.get("realized_cost_id"),  # type: ignore[arg-type]
        pre_trade_risk_report_id=fields.get("pre_trade_risk_report_id"),  # type: ignore[arg-type]
        component_eligibility=tuple(fields.get("component_eligibility", ())),  # type: ignore[arg-type]
        quality_issues=tuple(fields.get("quality_issues", ())),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "episode_version_id",
        episode_version_id(
            episode_key=str(fields["episode_key"]),
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return OutcomeEpisode(**fields)


def _report(
    episode: OutcomeEpisode,
    *,
    report_id: UUID | None = None,
    value: Decimal = Decimal("-100.0"),
) -> ComponentAttributionReport:
    rid = report_id or uuid4()
    return ComponentAttributionReport(
        report_id=rid,
        episode_version_id=episode.episode_version_id,
        observations=(
            ComponentObservation(
                component=AttributionComponent.FORECAST,
                metric="forecast_error_bps",
                value=value,
                unit="bps",
                uncertainty=Decimal("5.0"),
                baseline="point_forecast",
                interval_start=episode.temporal.effective_at,
                interval_end=episode.temporal.horizon_end,
                artifact_ids=(episode.forecast_id,),
                evidence_quality=EvidenceQuality.OBSERVED,
                method=AttributionMethod.OBSERVED,
            ),
        ),
    )


def _seed_episode_with_report(
    store: OutcomeLearningStore,
    *,
    value: Decimal = Decimal("-100.0"),
    report_id: UUID | None = None,
    **episode_overrides: object,
) -> tuple[OutcomeEpisode, ComponentAttributionReport]:
    episode = _episode(**episode_overrides)
    report = _report(episode, value=value, report_id=report_id)
    store.append_episode(episode)
    store.append_report(report)
    return episode, report


def _compiler(store: OutcomeLearningStore | None = None) -> LessonCompiler:
    return LessonCompiler(store=store or OutcomeLearningStore())


# ── Cutoff / eligibility ──────────────────────────────────────────────────────


def test_excludes_episodes_not_yet_available_at_cutoff() -> None:
    store = OutcomeLearningStore()
    future = _episode(
        temporal=_temporal(available_at=_AVAILABLE + timedelta(days=5)),
    )
    store.append_episode(future)
    store.append_report(_report(future))

    with pytest.raises(LessonCompilationError, match="no eligible episodes"):
        _compiler(store).compile_and_persist(
            policy=_POLICY,
            cohort=cohort_key(future),
            horizon_id="h-21s",
            compilation_cutoff=_AVAILABLE,
            knowledge_cutoff_at=_AVAILABLE,
        )


def test_excludes_episodes_known_after_knowledge_cutoff() -> None:
    store = OutcomeLearningStore()
    late_known = _episode(
        temporal=_temporal(
            known_at=_AVAILABLE + timedelta(days=2),
            recorded_at=_AVAILABLE + timedelta(days=2, hours=1),
            available_at=_AVAILABLE + timedelta(days=3),
        ),
    )
    store.append_episode(late_known)
    store.append_report(_report(late_known))

    with pytest.raises(LessonCompilationError, match="no eligible episodes"):
        _compiler(store).compile_and_persist(
            policy=_POLICY,
            cohort=cohort_key(late_known),
            horizon_id="h-21s",
            compilation_cutoff=_AVAILABLE + timedelta(days=4),
            knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
        )


def test_excludes_consuming_run_episodes() -> None:
    store = OutcomeLearningStore()
    ep1, _ = _seed_episode_with_report(store, source_run_id="run-prior")
    ep2, _ = _seed_episode_with_report(
        store,
        source_run_id="run-consuming",
        episode_key=f"forecast:{uuid4()}:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
    )

    lesson = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep1),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
        consuming_run_id="run-consuming",
    )
    assert ep2.episode_version_id not in lesson.episode_version_ids
    assert ep1.episode_version_id in lesson.episode_version_ids


# ── Polars aggregation ────────────────────────────────────────────────────────


def test_aggregates_forecast_error_mean_via_polars() -> None:
    store = OutcomeLearningStore()
    ep1, _ = _seed_episode_with_report(
        store,
        value=Decimal("-100.0"),
        episode_key="forecast:a:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
    )
    ep2, _ = _seed_episode_with_report(
        store,
        value=Decimal("-200.0"),
        episode_key="forecast:b:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
    )
    ep3, _ = _seed_episode_with_report(
        store,
        value=Decimal("-300.0"),
        episode_key="forecast:c:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
    )

    lesson = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep1),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert lesson.sample_count == 3
    assert lesson.effective_sample_count == 3
    assert lesson.estimate == Decimal("-200.0")
    assert lesson.uncertainty > Decimal("0")
    assert {ep1.episode_version_id, ep2.episode_version_id, ep3.episode_version_id} == set(
        lesson.episode_version_ids
    )


# ── Low-sample prior / shrinkage ──────────────────────────────────────────────


def test_applies_prior_shrinkage_when_below_min_sample() -> None:
    store = OutcomeLearningStore()
    ep, _ = _seed_episode_with_report(store, value=Decimal("-50.0"))
    low_sample_policy = LessonCompilationPolicy(
        policy_id="forecast-error-v1",
        component=AttributionComponent.FORECAST,
        metric="forecast_error_bps",
        min_sample=5,
        prior=Decimal("-10.0"),
    )

    lesson = _compiler(store).compile_and_persist(
        policy=low_sample_policy,
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert lesson.quality_state is LessonQualityState.LOW_SAMPLE
    assert lesson.prior == Decimal("-10.0")
    assert lesson.shrinkage is not None
    assert lesson.shrinkage > Decimal("0")
    assert lesson.estimate != Decimal("-50.0")
    assert lesson.estimate == Decimal("-18.0")


def test_adequate_quality_when_meeting_min_sample() -> None:
    store = OutcomeLearningStore()
    for idx in range(3):
        _seed_episode_with_report(
            store,
            value=Decimal("-100.0"),
            episode_key=f"forecast:{idx}:horizon:21s",
            forecast_id=uuid4(),
            outcome_id=uuid4(),
        )
    ep = _episode()
    lesson = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert lesson.quality_state is LessonQualityState.ADEQUATE
    assert lesson.prior is None
    assert lesson.shrinkage is None


# ── Deterministic hash / reproducibility ──────────────────────────────────────


def test_same_inputs_produce_identical_lesson_hash() -> None:
    store_a = OutcomeLearningStore()
    store_b = OutcomeLearningStore()
    report_ids = [
        UUID("a0000001-0001-4001-8001-000000000001"),
        UUID("a0000002-0002-4002-8002-000000000002"),
        UUID("a0000003-0003-4003-8003-000000000003"),
    ]
    for store in (store_a, store_b):
        for idx in range(3):
            _seed_episode_with_report(
                store,
                value=Decimal(str(-100 - idx * 10)),
                episode_key=f"forecast:{idx}:horizon:21s",
                forecast_id=UUID(f"{idx:08d}-1111-4111-8111-111111111111"),
                outcome_id=UUID(f"{idx:08d}-2222-4222-8222-222222222222"),
                report_id=report_ids[idx],
            )

    lesson_a = _compiler(store_a).compile_and_persist(
        policy=_POLICY,
        cohort="mandate-daily:AAPL",
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    lesson_b = _compiler(store_b).compile_and_persist(
        policy=_POLICY,
        cohort="mandate-daily:AAPL",
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert lesson_a.content_hash == lesson_b.content_hash
    assert lesson_a.lesson_version_id == lesson_b.lesson_version_id


# ── Versioning ────────────────────────────────────────────────────────────────


def test_late_episode_triggers_new_lesson_version_old_still_queryable() -> None:
    store = OutcomeLearningStore()
    ep1, rep1 = _seed_episode_with_report(store, value=Decimal("-100.0"))

    compiler = _compiler(store)
    first_cutoff = _AVAILABLE + timedelta(days=1)
    first = compiler.compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep1),
        horizon_id="h-21s",
        compilation_cutoff=first_cutoff,
        knowledge_cutoff_at=first_cutoff,
    )
    assert first.sample_count == 1
    assert first.episode_version_ids == (ep1.episode_version_id,)
    assert first.report_ids == (rep1.report_id,)

    ep2, _ = _seed_episode_with_report(
        store,
        value=Decimal("-200.0"),
        episode_key="forecast:mid:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
    )
    late_ep, _ = _seed_episode_with_report(
        store,
        value=Decimal("-300.0"),
        episode_key="forecast:very-late:horizon:21s",
        forecast_id=uuid4(),
        outcome_id=uuid4(),
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(days=10),
            known_at=_AVAILABLE + timedelta(days=9),
            recorded_at=_AVAILABLE + timedelta(days=9, hours=1),
        ),
    )

    second_cutoff = _AVAILABLE + timedelta(days=11)
    second = compiler.compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep1),
        horizon_id="h-21s",
        compilation_cutoff=second_cutoff,
        knowledge_cutoff_at=second_cutoff,
        supersedes_version_id=first.lesson_version_id,
    )
    assert second.lesson_version_id != first.lesson_version_id
    assert second.supersedes_version_id == first.lesson_version_id
    assert second.sample_count == 3
    assert late_ep.episode_version_id in second.episode_version_ids
    assert ep2.episode_version_id in second.episode_version_ids

    assert store.load_lesson(first.lesson_version_id) == first
    assert store.select_lesson_as_of(
        compilation_policy_id=_POLICY.policy_id,
        cohort=cohort_key(ep1),
        component=AttributionComponent.FORECAST,
        horizon_id="h-21s",
        as_of=first_cutoff,
    ) == first
    assert store.select_lesson_as_of(
        compilation_policy_id=_POLICY.policy_id,
        cohort=cohort_key(ep1),
        component=AttributionComponent.FORECAST,
        horizon_id="h-21s",
        as_of=second_cutoff,
    ) == second


# ── Prose cannot replace payload ──────────────────────────────────────────────


def test_rendered_prose_does_not_affect_structured_lesson() -> None:
    store = OutcomeLearningStore()
    ep, _ = _seed_episode_with_report(store, value=Decimal("-75.0"))
    prose = "The model was too optimistic on large-cap tech this month."

    lesson_without = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    lesson_with = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
        rendered_summary=prose,
    )
    assert lesson_with.content_hash == lesson_without.content_hash
    assert lesson_with.estimate == lesson_without.estimate


# ── Source IDs exposed ────────────────────────────────────────────────────────


def test_lesson_exposes_all_source_episode_and_report_ids() -> None:
    store = OutcomeLearningStore()
    episodes: list[OutcomeEpisode] = []
    reports: list[ComponentAttributionReport] = []
    for idx in range(2):
        ep, rep = _seed_episode_with_report(
            store,
            value=Decimal("-100.0"),
            episode_key=f"forecast:{idx}:horizon:21s",
            forecast_id=uuid4(),
            outcome_id=uuid4(),
        )
        episodes.append(ep)
        reports.append(rep)

    lesson = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(episodes[0]),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert set(lesson.episode_version_ids) == {ep.episode_version_id for ep in episodes}
    assert set(lesson.report_ids) == {rep.report_id for rep in reports}


def test_persists_via_append_lesson() -> None:
    store = OutcomeLearningStore()
    ep, _ = _seed_episode_with_report(store)
    lesson = _compiler(store).compile_and_persist(
        policy=_POLICY,
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    loaded = store.load_lesson(lesson.lesson_version_id)
    assert loaded == lesson


def test_superseded_episode_versions_deduped_via_as_of_selection() -> None:
    store = OutcomeLearningStore()
    parent = _episode()
    store.append_episode(parent)
    store.append_report(_report(parent, value=Decimal("-100.0")))
    child = _episode(
        realized=_realized(instrument_return=Decimal("0.055")),
        supersedes_version_id=parent.episode_version_id,
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(days=3),
            known_at=_AVAILABLE + timedelta(days=2),
            recorded_at=_AVAILABLE + timedelta(days=2, hours=1),
        ),
    )
    store.append_episode(child)
    store.append_report(_report(child, value=Decimal("-200.0")))

    lesson = _compiler(store).compile_and_persist(
        policy=LessonCompilationPolicy(
            policy_id="forecast-error-v1",
            component=AttributionComponent.FORECAST,
            metric="forecast_error_bps",
            min_sample=1,
            prior=Decimal("-10.0"),
        ),
        cohort=cohort_key(parent),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=4),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=4),
    )
    assert lesson.sample_count == 1
    assert lesson.episode_version_ids == (child.episode_version_id,)
    assert lesson.estimate == Decimal("-200.0")


def test_multiple_reports_uses_latest_per_episode() -> None:
    store = OutcomeLearningStore()
    ep = _episode()
    store.append_episode(ep)
    first = _report(ep, report_id=UUID("11111111-1111-4111-8111-111111111111"), value=Decimal("-50.0"))
    second = _report(ep, report_id=UUID("22222222-2222-4222-8222-222222222222"), value=Decimal("-150.0"))
    store.append_report(first)
    store.append_report(second)

    lesson = _compiler(store).compile_and_persist(
        policy=LessonCompilationPolicy(
            policy_id="forecast-error-v1",
            component=AttributionComponent.FORECAST,
            metric="forecast_error_bps",
            min_sample=1,
            prior=Decimal("-10.0"),
        ),
        cohort=cohort_key(ep),
        horizon_id="h-21s",
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
    )
    assert lesson.sample_count == 1
    assert lesson.report_ids == (second.report_id,)
    assert lesson.estimate == Decimal("-150.0")
