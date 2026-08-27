"""WP16.5 — purged and embargoed walk-forward folds (#2995).

Red coverage: strict ordering, crossing-horizon purge, late-known exclusion,
embargo boundary, shared folds, no train/eval overlap, empty/undersampled explicit,
timezone/inclusive boundaries, zero temporal/label overlap violations.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.olympus.learning.outcome_models import (
    EpisodeDisposition,
    H8TargetLineage,
    H9ExecutionLinks,
    OutcomeEpisode,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    episode_content_hash,
    episode_version_id,
)
from digiquant.olympus.replay.walk_forward import (
    WalkForwardBuildStatus,
    WalkForwardExclusionReason,
    WalkForwardScheduleParams,
    assign_episodes_to_fold,
    build_walk_forward_folds,
    episode_label_end,
    is_late_known_for_role,
    is_purged_for_eval,
    params_content_hash,
    verify_fold_assignments,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_OUTCOME_ID = UUID("22222222-2222-4222-8222-222222222222")


def _utc(y: int, m: int, d: int, *, hour: int = 0) -> datetime:
    return datetime(y, m, d, hour, tzinfo=UTC)


def _temporal(**overrides: object) -> OutcomeTemporalContract:
    fields: dict[str, object] = dict(
        effective_at=_utc(2024, 1, 15),
        known_at=_utc(2024, 1, 16),
        recorded_at=_utc(2024, 2, 10),
        horizon_end=_utc(2024, 2, 5),
        available_at=_utc(2024, 2, 6),
        replay_as_of=_utc(2024, 2, 6),
    )
    fields.update(overrides)
    known = fields["known_at"]
    available = fields["available_at"]
    assert isinstance(known, datetime)
    assert isinstance(available, datetime)
    if fields.get("recorded_at") == _utc(2024, 2, 10) and (
        known > _utc(2024, 2, 10) or available > _utc(2024, 2, 10)
    ):
        fields["recorded_at"] = max(known, available) + timedelta(days=1)
    if known > available:
        fields["available_at"] = known + timedelta(days=1)
        fields["recorded_at"] = fields["available_at"] + timedelta(days=1)
    return OutcomeTemporalContract(**fields)


def _realized() -> RealizedReturnObservation:
    return RealizedReturnObservation(
        instrument_return=Decimal("0.01"),
        benchmark_return=Decimal("0.005"),
        active_return=Decimal("0.005"),
        accounting_period_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        contribution_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )


def _episode(
    *,
    episode_key: str,
    effective_at: datetime,
    known_at: datetime | None = None,
    horizon_end: datetime | None = None,
    available_at: datetime | None = None,
) -> OutcomeEpisode:
    known = known_at or effective_at + timedelta(days=1)
    horizon = horizon_end or effective_at + timedelta(days=21)
    available = available_at or horizon + timedelta(days=1)
    temporal = _temporal(
        effective_at=effective_at,
        known_at=known,
        horizon_end=horizon,
        available_at=available,
        replay_as_of=min(available, _utc(2024, 12, 31)),
    )
    fields: dict[str, object] = dict(
        episode_key=episode_key,
        forecast_id=_FORECAST_ID,
        outcome_id=_OUTCOME_ID,
        mandate_id="mandate-daily",
        instrument_id="AAPL",
        horizon_id="h-21s",
        source_run_id="run-2024",
        disposition=EpisodeDisposition.AUTHORIZED,
        temporal=temporal,
        h8_lineage=H8TargetLineage(
            requested_weight=Decimal("0.05"), approved_weight=Decimal("0.04")
        ),
        h9_links=H9ExecutionLinks(action_id=UUID("66666666-6666-4666-8666-666666666666")),
        realized=_realized(),
    )
    content_hash = episode_content_hash(
        episode_key=str(fields["episode_key"]),
        forecast_id=fields["forecast_id"],  # type: ignore[arg-type]
        outcome_id=fields["outcome_id"],  # type: ignore[arg-type]
        mandate_id=str(fields["mandate_id"]),
        instrument_id=str(fields["instrument_id"]),
        horizon_id=str(fields["horizon_id"]),
        source_run_id=str(fields["source_run_id"]),
        disposition=fields["disposition"],  # type: ignore[arg-type]
        temporal=temporal,
        realized=fields["realized"],  # type: ignore[arg-type]
        h8_lineage=fields["h8_lineage"],  # type: ignore[arg-type]
        h9_links=fields["h9_links"],  # type: ignore[arg-type]
        evidence_bundle_id=None,
        research_state_version_id=None,
        context_manifest_id=None,
        policy_version_id=None,
        expected_cost_id=None,
        realized_cost_id=None,
        pre_trade_risk_report_id=None,
        component_eligibility=(),
        quality_issues=(),
    )
    version_id = episode_version_id(
        episode_key=str(fields["episode_key"]),
        content_hash=content_hash,
        supersedes_version_id=None,
    )
    return OutcomeEpisode(
        **fields,
        content_hash=content_hash,
        episode_version_id=version_id,
    )


def _params(**overrides: object) -> WalkForwardScheduleParams:
    fields: dict[str, object] = dict(
        params_id="wf-v1",
        train_days=60,
        eval_days=30,
        calibration_days=0,
        step_days=30,
        embargo_days=5,
        purge_horizon_days=21,
        min_train_episodes=1,
        min_eval_episodes=1,
    )
    fields.update(overrides)
    return WalkForwardScheduleParams(**fields)


def test_schedule_params_are_strict_frozen_and_versioned() -> None:
    params = _params()
    h1 = params_content_hash(params)
    h2 = params_content_hash(params)
    assert h1 == h2
    assert len(h1) == 64
    with pytest.raises(Exception):
        params.train_days = 90  # type: ignore[misc]
    with pytest.raises(ValidationError):
        WalkForwardScheduleParams(
            params_id="bad",
            train_days=0,
            eval_days=30,
            calibration_days=0,
            step_days=30,
            embargo_days=5,
            purge_horizon_days=21,
            min_train_episodes=1,
            min_eval_episodes=1,
        )


def test_build_folds_strict_window_ordering_and_embargo_gap() -> None:
    episodes = tuple(
        _episode(
            episode_key=f"ep-{i}",
            effective_at=_utc(2024, 1, 1) + timedelta(days=i * 5),
            horizon_end=_utc(2024, 1, 1) + timedelta(days=i * 5 + 14),
            available_at=_utc(2024, 1, 1) + timedelta(days=i * 5 + 15),
        )
        for i in range(40)
    )
    result = build_walk_forward_folds(
        episodes=episodes,
        replay_as_of=_utc(2024, 12, 31),
        params=_params(),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 8, 31),
    )
    assert result.status == WalkForwardBuildStatus.OK
    assert result.folds
    fold = result.folds[0].fold
    assert fold.train_end < fold.eval_start
    gap_days = (fold.eval_start.date() - fold.train_end.date()).days
    assert gap_days > fold.embargo_days
    if fold.calibration_start is not None and fold.calibration_end is not None:
        assert fold.train_end <= fold.calibration_start
        assert fold.calibration_end < fold.eval_start


def test_crossing_horizon_purged_from_train_not_eval() -> None:
    train_ep = _episode(
        episode_key="train-cross",
        effective_at=_utc(2024, 2, 1),
        horizon_end=_utc(2024, 4, 15),
        available_at=_utc(2024, 4, 16),
    )
    eval_ep = _episode(
        episode_key="eval-clean",
        effective_at=_utc(2024, 3, 15),
        horizon_end=_utc(2024, 4, 5),
        available_at=_utc(2024, 4, 6),
    )
    result_fold = build_walk_forward_folds(
        episodes=(train_ep, eval_ep),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(
            train_days=60, eval_days=30, step_days=120, min_train_episodes=0, min_eval_episodes=1
        ),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 5, 31),
    )
    assert result_fold.status == WalkForwardBuildStatus.OK
    plan = result_fold.folds[0]
    assert "train-cross" not in plan.train_episode_keys
    assert "eval-clean" in plan.eval_episode_keys
    purged = [
        ex
        for ex in plan.exclusions
        if ex.reason == WalkForwardExclusionReason.PURGED_HORIZON_CROSSING
    ]
    assert any(ex.episode_key == "train-cross" for ex in purged)
    assert is_purged_for_eval(
        train_ep,
        eval_start=plan.fold.eval_start,
        purge_horizon_days=plan.fold.purge_horizon_days,
    )


def test_late_known_excluded_from_train() -> None:
    ep = _episode(
        episode_key="late-known",
        effective_at=_utc(2024, 2, 1),
        known_at=_utc(2024, 5, 1),
        horizon_end=_utc(2024, 2, 25),
        available_at=_utc(2024, 5, 2),
    )
    result = build_walk_forward_folds(
        episodes=(ep,),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 7, 31),
    )
    plan = result.folds[0]
    assert "late-known" not in plan.train_episode_keys
    assert is_late_known_for_role(
        ep,
        role_cutoff=plan.fold.train_end,
        replay_as_of=_utc(2024, 12, 31),
    )
    late = [ex for ex in plan.exclusions if ex.reason == WalkForwardExclusionReason.LATE_KNOWN]
    assert any(ex.episode_key == "late-known" for ex in late)


def test_no_episode_in_both_train_and_eval() -> None:
    episodes = tuple(
        _episode(
            episode_key=f"ep-{i}",
            effective_at=_utc(2024, 1, 10) + timedelta(days=i * 3),
            horizon_end=_utc(2024, 1, 10) + timedelta(days=i * 3 + 10),
            available_at=_utc(2024, 1, 10) + timedelta(days=i * 3 + 11),
        )
        for i in range(50)
    )
    result = build_walk_forward_folds(
        episodes=episodes,
        replay_as_of=_utc(2024, 12, 31),
        params=_params(step_days=20),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 10, 31),
    )
    for plan in result.folds:
        train = set(plan.train_episode_keys)
        cal = set(plan.calibration_episode_keys)
        ev = set(plan.eval_episode_keys)
        assert train.isdisjoint(ev)
        assert cal.isdisjoint(ev)
        assert train.isdisjoint(cal)


def test_shared_folds_deterministic_for_identical_inputs() -> None:
    episodes = tuple(
        _episode(
            episode_key=f"ep-{i}",
            effective_at=_utc(2024, 3, 1) + timedelta(days=i * 4),
            horizon_end=_utc(2024, 3, 1) + timedelta(days=i * 4 + 12),
            available_at=_utc(2024, 3, 1) + timedelta(days=i * 4 + 13),
        )
        for i in range(30)
    )
    params = _params()
    kwargs = dict(
        episodes=episodes,
        replay_as_of=_utc(2024, 12, 31),
        params=params,
        history_start=date(2024, 1, 1),
        history_end=date(2024, 9, 30),
    )
    r1 = build_walk_forward_folds(**kwargs)
    r2 = build_walk_forward_folds(**kwargs)
    assert r1.folds == r2.folds
    assert r1.params_content_hash == r2.params_content_hash


def test_insufficient_history_when_undersampled() -> None:
    ep = _episode(
        episode_key="solo",
        effective_at=_utc(2024, 6, 1),
        horizon_end=_utc(2024, 6, 20),
        available_at=_utc(2024, 6, 21),
    )
    result = build_walk_forward_folds(
        episodes=(ep,),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(min_train_episodes=3, min_eval_episodes=2),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 7, 31),
    )
    assert result.status == WalkForwardBuildStatus.INSUFFICIENT_HISTORY
    assert "insufficient_history" in result.message


def test_empty_episodes_returns_insufficient_history() -> None:
    result = build_walk_forward_folds(
        episodes=(),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 6, 30),
    )
    assert result.status == WalkForwardBuildStatus.INSUFFICIENT_HISTORY
    assert result.folds == ()


def test_inclusive_day_boundaries_and_utc_required() -> None:
    boundary = _episode(
        episode_key="on-train-end",
        effective_at=_utc(2024, 3, 31, hour=23),
        horizon_end=_utc(2024, 4, 10),
        available_at=_utc(2024, 4, 11),
    )
    result = build_walk_forward_folds(
        episodes=(boundary,),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(
            train_days=90, eval_days=30, step_days=120, min_train_episodes=1, min_eval_episodes=0
        ),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 5, 31),
    )
    assert result.folds
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        build_walk_forward_folds(
            episodes=(boundary,),
            replay_as_of=datetime(2024, 12, 31),  # noqa: DTZ001 — intentional naive
            params=_params(),
            history_start=date(2024, 1, 1),
            history_end=date(2024, 5, 31),
        )


def test_verify_fold_assignments_zero_overlap_property() -> None:
    episodes = tuple(
        _episode(
            episode_key=f"ep-{i}",
            effective_at=_utc(2024, 2, 1) + timedelta(days=i * 2),
            horizon_end=_utc(2024, 2, 1) + timedelta(days=i * 2 + 8),
            available_at=_utc(2024, 2, 1) + timedelta(days=i * 2 + 9),
        )
        for i in range(60)
    )
    result = build_walk_forward_folds(
        episodes=episodes,
        replay_as_of=_utc(2024, 12, 31),
        params=_params(calibration_days=10, step_days=25),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 10, 31),
    )
    assert result.status == WalkForwardBuildStatus.OK
    episode_by_key = {ep.episode_key: ep for ep in episodes}
    for plan in result.folds:
        verify_fold_assignments(plan, episode_by_key=episode_by_key, replay_as_of=_utc(2024, 12, 31))


def test_not_yet_available_excluded() -> None:
    ep = _episode(
        episode_key="future",
        effective_at=_utc(2024, 6, 1),
        horizon_end=_utc(2024, 6, 20),
        available_at=_utc(2024, 8, 1),
    )
    result = build_walk_forward_folds(
        episodes=(ep,),
        replay_as_of=_utc(2024, 7, 1),
        params=_params(min_train_episodes=0, min_eval_episodes=0),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 7, 31),
    )
    for plan in result.folds:
        assert "future" not in plan.train_episode_keys
        assert "future" not in plan.eval_episode_keys
        unavailable = [
            ex for ex in plan.exclusions if ex.reason == WalkForwardExclusionReason.NOT_YET_AVAILABLE
        ]
        assert any(ex.episode_key == "future" for ex in unavailable)


def test_history_span_too_short_returns_insufficient_history() -> None:
    result = build_walk_forward_folds(
        episodes=(
            _episode(
                episode_key="solo",
                effective_at=_utc(2024, 1, 1),
                horizon_end=_utc(2024, 1, 20),
                available_at=_utc(2024, 1, 21),
            ),
        ),
        replay_as_of=_utc(2024, 12, 31),
        params=_params(train_days=120, eval_days=60),
        history_start=date(2024, 1, 1),
        history_end=date(2024, 2, 28),
    )
    assert result.status == WalkForwardBuildStatus.INSUFFICIENT_HISTORY
    assert "history span too short" in result.message


def test_assign_episodes_to_fold_direct_helper() -> None:
    ep = _episode(
        episode_key="direct",
        effective_at=_utc(2024, 4, 1),
        horizon_end=_utc(2024, 4, 20),
        available_at=_utc(2024, 4, 21),
    )
    params = _params()
    folds = build_walk_forward_folds(
        episodes=(ep,),
        replay_as_of=_utc(2024, 12, 31),
        params=params,
        history_start=date(2024, 1, 1),
        history_end=date(2024, 6, 30),
    ).folds
    assert folds
    plan = assign_episodes_to_fold(
        fold=folds[0].fold, episodes=(ep,), replay_as_of=_utc(2024, 12, 31)
    )
    assert plan.fold.fold_id == folds[0].fold.fold_id
    assert episode_label_end(ep) == ep.temporal.horizon_end
