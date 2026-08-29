"""Append-only outcome-learning store (#2959 / WP15.2).

Covers content idempotency, changed-content append, supersession lineage,
as-of-visible version selection, exact load after newer rows, report/lesson
membership checks, and no historical fabrication. Migration privacy contracts
live in ``tests/dq/atlas/test_migration_093.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
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
    OutcomeLessonVersion,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    episode_content_hash,
    episode_version_id,
    lesson_content_hash,
    lesson_version_id,
)
from digiquant.olympus.learning.outcome_store import (
    OutcomeLearningConflict,
    OutcomeLearningError,
    OutcomeLearningMissingError,
    OutcomeLearningStore,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_HORIZON_END = _TS + timedelta(days=21)
_AVAILABLE = _TS + timedelta(days=22)
_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_OUTCOME_ID = UUID("22222222-2222-4222-8222-222222222222")
_EPISODE_KEY = f"forecast:{_FORECAST_ID}:horizon:21"


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
        episode_key=_EPISODE_KEY,
        forecast_id=_FORECAST_ID,
        outcome_id=_OUTCOME_ID,
        mandate_id="mandate-daily",
        instrument_id="AAPL",
        horizon_id="h-21s",
        source_run_id="run-2026-08-26",
        evidence_bundle_id=UUID("33333333-3333-4333-8333-333333333333"),
        research_state_version_id=UUID("44444444-4444-4444-8444-444444444444"),
        context_manifest_id=UUID("55555555-5555-4555-8555-555555555555"),
        policy_version_id="policy-v1",
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
    episode: OutcomeEpisode, *, report_id: UUID | None = None
) -> ComponentAttributionReport:
    rid = report_id or UUID("dddddddd-eeee-4fff-8000-111111111111")
    return ComponentAttributionReport(
        report_id=rid,
        episode_version_id=episode.episode_version_id,
        observations=(
            ComponentObservation(
                component=AttributionComponent.FORECAST,
                metric="forecast_error_bps",
                value=Decimal("-12.5"),
                unit="bps",
                uncertainty=Decimal("3.0"),
                baseline="point_forecast",
                interval_start=_TS - timedelta(days=21),
                interval_end=_HORIZON_END,
                artifact_ids=(_FORECAST_ID,),
                evidence_quality=EvidenceQuality.OBSERVED,
                method=AttributionMethod.OBSERVED,
            ),
        ),
    )


def _lesson(
    episode: OutcomeEpisode,
    report: ComponentAttributionReport,
    **overrides: object,
) -> OutcomeLessonVersion:
    fields: dict[str, object] = dict(
        compilation_policy_id="lesson-policy-v1",
        compilation_cutoff=_AVAILABLE,
        episode_version_ids=(episode.episode_version_id,),
        report_ids=(report.report_id,),
        cohort="large_cap_us",
        regime="risk_on",
        horizon_id="h-21s",
        component=AttributionComponent.FORECAST,
        sample_count=42,
        effective_sample_count=38,
        estimate=Decimal("-8.5"),
        uncertainty=Decimal("2.1"),
        prior=Decimal("-10.0"),
        shrinkage=Decimal("0.15"),
        quality_state=LessonQualityState.ADEQUATE,
        recommendation_code="forecast_bias_negative",
        warning_codes=(),
        available_at=_AVAILABLE + timedelta(hours=1),
        supersedes_version_id=None,
    )
    fields.update(overrides)
    content_hash = lesson_content_hash(
        compilation_policy_id=str(fields["compilation_policy_id"]),
        compilation_cutoff=fields["compilation_cutoff"],  # type: ignore[arg-type]
        episode_version_ids=tuple(fields["episode_version_ids"]),  # type: ignore[arg-type]
        report_ids=tuple(fields["report_ids"]),  # type: ignore[arg-type]
        component=fields["component"],  # type: ignore[arg-type]
        estimate=fields["estimate"],  # type: ignore[arg-type]
        uncertainty=fields["uncertainty"],  # type: ignore[arg-type]
        sample_count=int(fields["sample_count"]),  # type: ignore[arg-type]
        effective_sample_count=int(fields["effective_sample_count"]),  # type: ignore[arg-type]
        quality_state=fields["quality_state"],  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "lesson_version_id",
        lesson_version_id(
            compilation_policy_id=str(fields["compilation_policy_id"]),
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return OutcomeLessonVersion(**fields)


def test_exact_retry_of_episode_is_idempotent() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    assert store.append_episode(episode) is store.append_episode(episode)
    assert len(store._episodes) == 1


def test_changed_content_appends_new_episode_version() -> None:
    store = OutcomeLearningStore()
    first = _episode(realized=_realized(instrument_return=Decimal("0.040")))
    second = _episode(realized=_realized(instrument_return=Decimal("0.045")))
    store.append_episode(first)
    store.append_episode(second)
    assert first.episode_version_id != second.episode_version_id
    assert len(store._episodes) == 2


def test_episode_supersession_requires_parent() -> None:
    store = OutcomeLearningStore()
    orphan = _episode(supersedes_version_id=uuid4())
    with pytest.raises(OutcomeLearningError, match="missing parent"):
        store.append_episode(orphan)


def test_episode_supersession_appends_child() -> None:
    store = OutcomeLearningStore()
    parent = _episode()
    store.append_episode(parent)
    child = _episode(
        realized=_realized(instrument_return=Decimal("0.050")),
        supersedes_version_id=parent.episode_version_id,
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(days=1),
            known_at=_AVAILABLE,
            recorded_at=_AVAILABLE + timedelta(hours=1),
        ),
    )
    store.append_episode(child)
    assert parent.episode_version_id in store._episodes
    assert child.episode_version_id in store._episodes


def test_report_requires_existing_episode() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    with pytest.raises(OutcomeLearningError, match="missing episode"):
        store.append_report(_report(episode))


def test_report_exact_retry_is_idempotent() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    store.append_episode(episode)
    report = _report(episode)
    assert store.append_report(report) is store.append_report(report)


def test_lesson_requires_episode_and_report_membership() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    report = _report(episode)
    store.append_episode(episode)
    store.append_report(report)
    lesson = _lesson(episode, report)
    assert store.append_lesson(lesson) is store.append_lesson(lesson)


def test_lesson_rejects_missing_episode_ref() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    report = _report(episode)
    store.append_episode(episode)
    store.append_report(report)
    with pytest.raises(OutcomeLearningError, match="missing episode"):
        store.append_lesson(_lesson(episode, report, episode_version_ids=(uuid4(),)))


def test_select_episode_as_of_returns_version_visible_at_cutoff() -> None:
    """Metric: exact cutoff returns the version then visible after correction."""
    store = OutcomeLearningStore()
    parent = _episode(
        temporal=_temporal(
            available_at=_AVAILABLE,
            known_at=_TS - timedelta(days=20),
        )
    )
    store.append_episode(parent)
    correction = _episode(
        realized=_realized(instrument_return=Decimal("0.055")),
        supersedes_version_id=parent.episode_version_id,
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(days=3),
            known_at=_AVAILABLE + timedelta(days=2),
            recorded_at=_AVAILABLE + timedelta(days=2, hours=1),
        ),
    )
    store.append_episode(correction)

    cutoff_between = _AVAILABLE + timedelta(days=1)
    selected = store.select_episode_as_of(
        episode_key=_EPISODE_KEY,
        as_of=cutoff_between,
        knowledge_cutoff_at=cutoff_between,
    )
    assert selected is not None
    assert selected.episode_version_id == parent.episode_version_id

    after_correction = _AVAILABLE + timedelta(days=4)
    selected_later = store.select_episode_as_of(
        episode_key=_EPISODE_KEY,
        as_of=after_correction,
        knowledge_cutoff_at=after_correction,
    )
    assert selected_later is not None
    assert selected_later.episode_version_id == correction.episode_version_id


def test_select_episode_as_of_excludes_future_known() -> None:
    store = OutcomeLearningStore()
    early = _episode(
        temporal=_temporal(
            available_at=_AVAILABLE,
            known_at=_TS - timedelta(days=20),
        )
    )
    store.append_episode(early)
    late = _episode(
        realized=_realized(instrument_return=Decimal("0.060")),
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(hours=6),
            known_at=_AVAILABLE + timedelta(hours=4),
            recorded_at=_AVAILABLE + timedelta(hours=6),
        ),
    )
    store.append_episode(late)

    selected = store.select_episode_as_of(
        episode_key=_EPISODE_KEY,
        as_of=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(hours=3),
    )
    assert selected is not None
    assert selected.episode_version_id == early.episode_version_id


def test_select_episode_as_of_returns_none_without_fabrication() -> None:
    store = OutcomeLearningStore()
    assert (
        store.select_episode_as_of(
            episode_key=_EPISODE_KEY,
            as_of=_AVAILABLE,
            knowledge_cutoff_at=_AVAILABLE,
        )
        is None
    )


def test_exact_episode_round_trip_after_newer_rows() -> None:
    store = OutcomeLearningStore()
    parent = _episode()
    store.append_episode(parent)
    original_bytes = store.exact_episode_bytes(parent.episode_version_id)

    correction = _episode(
        realized=_realized(instrument_return=Decimal("0.070")),
        supersedes_version_id=parent.episode_version_id,
        temporal=_temporal(
            available_at=_AVAILABLE + timedelta(days=5),
            known_at=_AVAILABLE + timedelta(days=4),
            recorded_at=_AVAILABLE + timedelta(days=4, hours=2),
        ),
    )
    store.append_episode(correction)

    loaded = store.load_episode(parent.episode_version_id)
    assert loaded == parent
    assert store.exact_episode_bytes(parent.episode_version_id) == original_bytes
    assert loaded.model_dump_json().encode("utf-8") == original_bytes


def test_load_episode_with_reports_never_fabricates() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    report = _report(episode)
    store.append_episode(episode)
    store.append_report(report)

    loaded = store.load_episode_with_reports(episode.episode_version_id)
    assert loaded.episode == episode
    assert loaded.reports == (report,)


def test_conflict_on_seeded_hash_mismatch() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    store.append_episode(episode)
    tainted = OutcomeEpisode.model_construct(**episode.model_dump())
    object.__setattr__(tainted, "content_hash", "0" * 64)
    store._episodes[episode.episode_version_id] = tainted
    with pytest.raises(OutcomeLearningConflict):
        store.append_episode(episode)


def test_load_missing_raises() -> None:
    store = OutcomeLearningStore()
    with pytest.raises(OutcomeLearningMissingError):
        store.load_episode(uuid4())


def test_store_has_no_update_or_delete_surface() -> None:
    store = OutcomeLearningStore()
    for name in ("update", "delete", "upsert", "replace", "load_latest"):
        assert not hasattr(store, name)


def test_lesson_rejects_report_for_unlisted_episode() -> None:
    store = OutcomeLearningStore()
    episode_a = _episode()
    episode_b = _episode(realized=_realized(instrument_return=Decimal("0.048")))
    report_b = _report(episode_b)
    store.append_episode(episode_a)
    store.append_episode(episode_b)
    store.append_report(report_b)
    with pytest.raises(OutcomeLearningError, match="not in episode_version_ids"):
        store.append_lesson(_lesson(episode_a, report_b))


def test_load_episode_with_reports_fails_on_broken_index() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    report = _report(episode)
    store.append_episode(episode)
    store.append_report(report)
    store._reports_by_episode[episode.episode_version_id] = (uuid4(),)
    with pytest.raises(OutcomeLearningError, match="missing report"):
        store.load_episode_with_reports(episode.episode_version_id)


def test_lesson_supersession_and_as_of_selection() -> None:
    store = OutcomeLearningStore()
    episode = _episode()
    report = _report(episode)
    store.append_episode(episode)
    store.append_report(report)

    parent_lesson = _lesson(episode, report)
    store.append_lesson(parent_lesson)
    child_lesson = _lesson(
        episode,
        report,
        estimate=Decimal("-7.0"),
        supersedes_version_id=parent_lesson.lesson_version_id,
        available_at=_AVAILABLE + timedelta(days=2),
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
    )
    store.append_lesson(child_lesson)

    mid = _AVAILABLE + timedelta(hours=12)
    selected = store.select_lesson_as_of(
        compilation_policy_id="lesson-policy-v1",
        cohort="large_cap_us",
        component=AttributionComponent.FORECAST,
        horizon_id="h-21s",
        regime="risk_on",
        as_of=mid,
    )
    assert selected is not None
    assert selected.lesson_version_id == parent_lesson.lesson_version_id

    later = _AVAILABLE + timedelta(days=3)
    selected_later = store.select_lesson_as_of(
        compilation_policy_id="lesson-policy-v1",
        cohort="large_cap_us",
        component=AttributionComponent.FORECAST,
        horizon_id="h-21s",
        regime="risk_on",
        as_of=later,
    )
    assert selected_later is not None
    assert selected_later.lesson_version_id == child_lesson.lesson_version_id
