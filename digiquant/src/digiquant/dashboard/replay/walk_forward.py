"""WP16.5 — purged and embargoed walk-forward fold builder (#2995).

Produces deterministic non-overlapping training/calibration/evaluation roles with
purge and embargo for dashboard policy replay. Versioned schedule parameters;
undersampled history fails with ``insufficient_history`` — never silent drop.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.dashboard.learning.outcome_models import OutcomeEpisode
from digiquant.dashboard.replay.canonical import walk_forward_fold_content_hash
from digiquant.dashboard.replay.models import WalkForwardFold
from digiquant.dashboard.temporal import require_utc_datetime

__all__ = [
    "WalkForwardBuildResult",
    "WalkForwardBuildStatus",
    "WalkForwardEpisodeExclusion",
    "WalkForwardExclusionReason",
    "WalkForwardFoldPlan",
    "WalkForwardRole",
    "WalkForwardScheduleParams",
    "assign_episodes_to_fold",
    "build_walk_forward_folds",
    "episode_label_end",
    "is_late_known_for_role",
    "is_purged_for_eval",
    "params_content_hash",
    "verify_fold_assignments",
]

NonEmptyId = Annotated[str, Field(min_length=1)]


class WalkForwardContractModel(BaseModel):
    """Strict immutable base for walk-forward contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class WalkForwardBuildStatus(StrEnum):
    """Typed build outcomes — undersampled history is explicit."""

    OK = "ok"
    INSUFFICIENT_HISTORY = "insufficient_history"


class WalkForwardRole(StrEnum):
    """Episode assignment role within one fold."""

    TRAIN = "train"
    CALIBRATION = "calibration"
    EVAL = "eval"


class WalkForwardExclusionReason(StrEnum):
    """Why an episode was excluded from a role attempt."""

    PURGED_HORIZON_CROSSING = "purged_horizon_crossing"
    LATE_KNOWN = "late_known"
    NOT_YET_AVAILABLE = "not_yet_available"
    OUTSIDE_WINDOW = "outside_window"


class WalkForwardScheduleParams(WalkForwardContractModel):
    """Versioned fold-generation parameters (all fields material to output)."""

    schema_version: str = "1.0"
    params_id: NonEmptyId
    train_days: Annotated[int, Field(ge=1)]
    eval_days: Annotated[int, Field(ge=1)]
    calibration_days: Annotated[int, Field(ge=0)] = 0
    step_days: Annotated[int, Field(ge=1)]
    embargo_days: Annotated[int, Field(ge=0)] = 0
    purge_horizon_days: Annotated[int, Field(ge=0)] = 0
    min_train_episodes: Annotated[int, Field(ge=0)] = 1
    min_eval_episodes: Annotated[int, Field(ge=0)] = 1


class WalkForwardEpisodeExclusion(WalkForwardContractModel):
    """One excluded episode with typed reason."""

    episode_key: NonEmptyId
    reason: WalkForwardExclusionReason
    role_attempted: WalkForwardRole


class WalkForwardFoldPlan(WalkForwardContractModel):
    """One fold window with episode assignments and explicit exclusions."""

    fold: WalkForwardFold
    fold_content_hash: NonEmptyId
    train_episode_keys: tuple[str, ...] = ()
    calibration_episode_keys: tuple[str, ...] = ()
    eval_episode_keys: tuple[str, ...] = ()
    exclusions: tuple[WalkForwardEpisodeExclusion, ...] = ()

    @field_validator(
        "train_episode_keys",
        "calibration_episode_keys",
        "eval_episode_keys",
        "exclusions",
        mode="before",
    )
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_disjoint_roles(self) -> WalkForwardFoldPlan:
        train = set(self.train_episode_keys)
        cal = set(self.calibration_episode_keys)
        ev = set(self.eval_episode_keys)
        if train & ev:
            raise ValueError("episode cannot appear in both train and eval")
        if cal & ev:
            raise ValueError("episode cannot appear in both calibration and eval")
        if train & cal:
            raise ValueError("episode cannot appear in both train and calibration")
        return self


class WalkForwardBuildResult(WalkForwardContractModel):
    """Deterministic fold build output for paired replay arms."""

    schema_version: str = "1.0"
    params: WalkForwardScheduleParams
    params_content_hash: NonEmptyId
    replay_as_of: datetime
    status: WalkForwardBuildStatus
    folds: tuple[WalkForwardFoldPlan, ...] = ()
    message: str = ""

    @field_validator("folds", mode="before")
    @classmethod
    def _coerce_folds(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("replay_as_of")
    @classmethod
    def _require_replay_as_of_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="replay_as_of")


def params_content_hash(params: WalkForwardScheduleParams) -> str:
    """Stable digest of versioned schedule parameters."""
    return sha256_hex(params.model_dump(mode="json"))


def _day_start(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _in_inclusive_day_window(ts: datetime, start: datetime, end: datetime) -> bool:
    """Membership on UTC calendar days with inclusive boundaries."""
    day = ts.date()
    return start.date() <= day <= end.date()


def episode_label_end(episode: OutcomeEpisode) -> datetime:
    """Economic label maturity for purge checks."""
    return episode.temporal.horizon_end


def is_purged_for_eval(
    episode: OutcomeEpisode,
    *,
    eval_start: datetime,
    purge_horizon_days: int,
) -> bool:
    """True when label (+ purge buffer) crosses into the evaluation window."""
    label_end = episode_label_end(episode)
    purge_boundary = eval_start - timedelta(days=purge_horizon_days)
    return label_end >= purge_boundary


def is_late_known_for_role(
    episode: OutcomeEpisode,
    *,
    role_cutoff: datetime,
    replay_as_of: datetime,
) -> bool:
    """True when the episode was not knowable at the role cutoff."""
    known_at = episode.temporal.known_at
    return known_at > role_cutoff or known_at > replay_as_of


def _episode_visible(episode: OutcomeEpisode, replay_as_of: datetime) -> bool:
    return episode.temporal.available_at <= replay_as_of


def _try_assign(
    episode: OutcomeEpisode,
    *,
    role: WalkForwardRole,
    window_start: datetime,
    window_end: datetime,
    role_cutoff: datetime,
    eval_start: datetime,
    purge_horizon_days: int,
    replay_as_of: datetime,
) -> tuple[bool, WalkForwardEpisodeExclusion | None]:
    key = episode.episode_key
    if not _episode_visible(episode, replay_as_of):
        return False, WalkForwardEpisodeExclusion(
            episode_key=key,
            reason=WalkForwardExclusionReason.NOT_YET_AVAILABLE,
            role_attempted=role,
        )
    if not _in_inclusive_day_window(episode.temporal.effective_at, window_start, window_end):
        return False, WalkForwardEpisodeExclusion(
            episode_key=key,
            reason=WalkForwardExclusionReason.OUTSIDE_WINDOW,
            role_attempted=role,
        )
    if is_late_known_for_role(episode, role_cutoff=role_cutoff, replay_as_of=replay_as_of):
        return False, WalkForwardEpisodeExclusion(
            episode_key=key,
            reason=WalkForwardExclusionReason.LATE_KNOWN,
            role_attempted=role,
        )
    if role in (WalkForwardRole.TRAIN, WalkForwardRole.CALIBRATION) and is_purged_for_eval(
        episode,
        eval_start=eval_start,
        purge_horizon_days=purge_horizon_days,
    ):
        return False, WalkForwardEpisodeExclusion(
            episode_key=key,
            reason=WalkForwardExclusionReason.PURGED_HORIZON_CROSSING,
            role_attempted=role,
        )
    return True, None


def assign_episodes_to_fold(
    *,
    fold: WalkForwardFold,
    episodes: tuple[OutcomeEpisode, ...],
    replay_as_of: datetime,
) -> WalkForwardFoldPlan:
    """Assign episodes to one fold under purge, embargo, and as-of rules."""
    replay_as_of = require_utc_datetime(replay_as_of, field_name="replay_as_of")
    train: list[str] = []
    cal: list[str] = []
    ev: list[str] = []
    exclusions: list[WalkForwardEpisodeExclusion] = []

    cal_start = fold.calibration_start
    cal_end = fold.calibration_end

    for episode in sorted(episodes, key=lambda e: (e.temporal.effective_at, e.episode_key)):
        assigned = False
        for role, w_start, w_end, cutoff in (
            (
                WalkForwardRole.TRAIN,
                fold.train_start,
                fold.train_end,
                fold.train_end,
            ),
            *(
                [(WalkForwardRole.CALIBRATION, cal_start, cal_end, cal_end)]
                if cal_start is not None and cal_end is not None
                else []
            ),
            (
                WalkForwardRole.EVAL,
                fold.eval_start,
                fold.eval_end,
                fold.eval_end,
            ),
        ):
            ok, exclusion = _try_assign(
                episode,
                role=role,
                window_start=w_start,
                window_end=w_end,
                role_cutoff=cutoff,
                eval_start=fold.eval_start,
                purge_horizon_days=fold.purge_horizon_days,
                replay_as_of=replay_as_of,
            )
            if ok:
                if role == WalkForwardRole.TRAIN:
                    train.append(episode.episode_key)
                elif role == WalkForwardRole.CALIBRATION:
                    cal.append(episode.episode_key)
                else:
                    ev.append(episode.episode_key)
                assigned = True
                break
            if (
                exclusion is not None
                and exclusion.reason != WalkForwardExclusionReason.OUTSIDE_WINDOW
            ):
                exclusions.append(exclusion)
        if not assigned:
            continue

    content_hash = walk_forward_fold_content_hash(fold)
    return WalkForwardFoldPlan(
        fold=fold,
        fold_content_hash=content_hash,
        train_episode_keys=tuple(sorted(train)),
        calibration_episode_keys=tuple(sorted(cal)),
        eval_episode_keys=tuple(sorted(ev)),
        exclusions=tuple(exclusions),
    )


def _generate_fold_windows(
    *,
    params: WalkForwardScheduleParams,
    history_start: date,
    history_end: date,
) -> tuple[WalkForwardFold, ...]:
    folds: list[WalkForwardFold] = []
    anchor = history_start
    fold_idx = 0
    while True:
        train_start = anchor
        train_end_date = train_start + timedelta(days=params.train_days - 1)
        if train_end_date > history_end:
            break

        cal_start_dt: datetime | None = None
        cal_end_dt: datetime | None = None
        if params.calibration_days > 0:
            cal_start_date = train_end_date + timedelta(days=1)
            cal_end_date = cal_start_date + timedelta(days=params.calibration_days - 1)
            if cal_end_date > history_end:
                break
            cal_start_dt = _day_start(cal_start_date)
            cal_end_dt = _day_start(cal_end_date)
            eval_start_date = cal_end_date + timedelta(days=params.embargo_days + 1)
        else:
            eval_start_date = train_end_date + timedelta(days=params.embargo_days + 1)

        eval_end_date = eval_start_date + timedelta(days=params.eval_days - 1)
        if eval_end_date > history_end:
            break

        fold = WalkForwardFold(
            fold_id=f"{params.params_id}-fold-{fold_idx}",
            train_start=_day_start(train_start),
            train_end=_day_start(train_end_date),
            calibration_start=cal_start_dt,
            calibration_end=cal_end_dt,
            eval_start=_day_start(eval_start_date),
            eval_end=_day_start(eval_end_date),
            embargo_days=params.embargo_days,
            purge_horizon_days=params.purge_horizon_days,
        )
        folds.append(fold)
        fold_idx += 1
        anchor = anchor + timedelta(days=params.step_days)
        if anchor > history_end:
            break
    return tuple(folds)


def verify_fold_assignments(
    plan: WalkForwardFoldPlan,
    *,
    episode_by_key: dict[str, OutcomeEpisode],
    replay_as_of: datetime | None = None,
) -> None:
    """Property check: zero temporal/label overlap violations."""
    as_of = replay_as_of if replay_as_of is not None else plan.fold.eval_end
    as_of = require_utc_datetime(as_of, field_name="replay_as_of")
    train_keys = set(plan.train_episode_keys)
    cal_keys = set(plan.calibration_episode_keys)
    eval_keys = set(plan.eval_episode_keys)
    if train_keys & eval_keys:
        raise ValueError("train/eval overlap detected")
    if cal_keys & eval_keys:
        raise ValueError("calibration/eval overlap detected")
    if train_keys & cal_keys:
        raise ValueError("train/calibration overlap detected")

    fold = plan.fold
    if fold.train_end >= fold.eval_start:
        raise ValueError("train_end must precede eval_start")
    embargo_anchor = fold.calibration_end if fold.calibration_end is not None else fold.train_end
    gap = (fold.eval_start.date() - embargo_anchor.date()).days
    if gap <= fold.embargo_days:
        raise ValueError("embargo boundary violated before eval_start")

    for key in train_keys | cal_keys:
        episode = episode_by_key[key]
        if is_purged_for_eval(
            episode,
            eval_start=fold.eval_start,
            purge_horizon_days=fold.purge_horizon_days,
        ):
            raise ValueError(f"purged episode {key} assigned to train/calibration")
        cutoff = fold.train_end if key in train_keys else fold.calibration_end
        assert cutoff is not None
        if is_late_known_for_role(
            episode,
            role_cutoff=cutoff,
            replay_as_of=as_of,
        ):
            raise ValueError(f"late-known episode {key} assigned to train/calibration")

    for key in eval_keys:
        episode = episode_by_key[key]
        if not _in_inclusive_day_window(
            episode.temporal.effective_at,
            fold.eval_start,
            fold.eval_end,
        ):
            raise ValueError(f"eval episode {key} outside eval window")
        if not _episode_visible(episode, replay_as_of=as_of):
            raise ValueError(f"eval episode {key} not yet available at replay_as_of")
        if is_late_known_for_role(
            episode,
            role_cutoff=fold.eval_end,
            replay_as_of=as_of,
        ):
            raise ValueError(f"late-known episode {key} assigned to eval")


def build_walk_forward_folds(
    *,
    episodes: tuple[OutcomeEpisode, ...],
    replay_as_of: datetime,
    params: WalkForwardScheduleParams,
    history_start: date,
    history_end: date,
) -> WalkForwardBuildResult:
    """Build purged, embargoed walk-forward folds shared by paired replay arms."""
    replay_as_of = require_utc_datetime(replay_as_of, field_name="replay_as_of")
    if history_end < history_start:
        raise ValueError("history_end must be >= history_start")

    p_hash = params_content_hash(params)
    if not episodes:
        return WalkForwardBuildResult(
            params=params,
            params_content_hash=p_hash,
            replay_as_of=replay_as_of,
            status=WalkForwardBuildStatus.INSUFFICIENT_HISTORY,
            folds=(),
            message="insufficient_history: no episodes supplied",
        )

    windows = _generate_fold_windows(
        params=params,
        history_start=history_start,
        history_end=history_end,
    )
    if not windows:
        return WalkForwardBuildResult(
            params=params,
            params_content_hash=p_hash,
            replay_as_of=replay_as_of,
            status=WalkForwardBuildStatus.INSUFFICIENT_HISTORY,
            folds=(),
            message="insufficient_history: history span too short for one fold",
        )

    plans = tuple(
        assign_episodes_to_fold(fold=fold, episodes=episodes, replay_as_of=replay_as_of)
        for fold in windows
    )

    valid_plans = [
        plan
        for plan in plans
        if len(plan.train_episode_keys) >= params.min_train_episodes
        and len(plan.eval_episode_keys) >= params.min_eval_episodes
    ]

    if not valid_plans:
        return WalkForwardBuildResult(
            params=params,
            params_content_hash=p_hash,
            replay_as_of=replay_as_of,
            status=WalkForwardBuildStatus.INSUFFICIENT_HISTORY,
            folds=plans,
            message=(
                "insufficient_history: no fold meets min_train_episodes="
                f"{params.min_train_episodes} and min_eval_episodes={params.min_eval_episodes}"
            ),
        )

    return WalkForwardBuildResult(
        params=params,
        params_content_hash=p_hash,
        replay_as_of=replay_as_of,
        status=WalkForwardBuildStatus.OK,
        folds=tuple(valid_plans),
        message=f"built {len(valid_plans)} fold(s)",
    )
