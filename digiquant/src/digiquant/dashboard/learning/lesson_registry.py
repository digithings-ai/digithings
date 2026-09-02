"""WP15.5 — compile immutable structured lesson versions (#2971).

Summarizes eligible outcome episodes and component attribution reports into
versioned :class:`OutcomeLessonVersion` records using Polars aggregation,
low-sample prior/shrinkage, and deterministic content hashes. Rendered prose
is never authoritative — only structured episode/report IDs and typed metrics
feed compilation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import polars as pl
from pydantic import ConfigDict

from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentAttributionReport,
    LessonQualityState,
    OutcomeEpisode,
    OutcomeLearningModel,
    OutcomeLessonVersion,
    lesson_content_hash,
    lesson_version_id,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore
from digiquant.olympus.temporal import require_utc_datetime

_ZERO = Decimal("0")
_ONE = Decimal("1")


class LessonCompilationError(RuntimeError):
    """Compiler could not produce a lesson — no partial payload is emitted."""


class LessonCompilationPolicy(OutcomeLearningModel):
    """Immutable compilation policy referenced by every lesson version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    component: AttributionComponent
    metric: str
    min_sample: int
    prior: Decimal


def cohort_key(episode: OutcomeEpisode) -> str:
    """Canonical typed cohort key for mandate/instrument grouping."""
    return f"{episode.mandate_id}:{episode.instrument_id}"


@dataclass(frozen=True)
class _EligibleObservation:
    episode_version_id: UUID
    report_id: UUID
    value: Decimal
    available_at: datetime


def _is_effective_method(method: AttributionMethod) -> bool:
    return method in (
        AttributionMethod.OBSERVED,
        AttributionMethod.COUNTERFACTUAL_REPLAY,
        AttributionMethod.MODEL_ESTIMATE,
    )


def _episode_eligible(
    episode: OutcomeEpisode,
    *,
    cohort: str,
    horizon_id: str,
    compilation_cutoff: datetime,
    knowledge_cutoff_at: datetime,
    consuming_run_id: str | None,
) -> bool:
    if cohort_key(episode) != cohort:
        return False
    if episode.horizon_id != horizon_id:
        return False
    if consuming_run_id is not None and episode.source_run_id == consuming_run_id:
        return False
    if episode.temporal.available_at > compilation_cutoff:
        return False
    if episode.temporal.known_at > knowledge_cutoff_at:
        return False
    return True


def _eligible_episodes(
    store: OutcomeLearningStore,
    *,
    cohort: str,
    horizon_id: str,
    compilation_cutoff: datetime,
    knowledge_cutoff_at: datetime,
    consuming_run_id: str | None,
) -> tuple[OutcomeEpisode, ...]:
    """One as-of-visible episode version per logical ``episode_key``."""
    keys = {episode.episode_key for episode in store.list_episode_versions()}
    eligible: list[OutcomeEpisode] = []
    for key in sorted(keys):
        selected = store.select_episode_as_of(
            episode_key=key,
            as_of=compilation_cutoff,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        if selected is None:
            continue
        if not _episode_eligible(
            selected,
            cohort=cohort,
            horizon_id=horizon_id,
            compilation_cutoff=compilation_cutoff,
            knowledge_cutoff_at=knowledge_cutoff_at,
            consuming_run_id=consuming_run_id,
        ):
            continue
        eligible.append(selected)
    return tuple(eligible)


def _latest_report(
    store: OutcomeLearningStore,
    episode_version_id: UUID,
) -> ComponentAttributionReport | None:
    return store.latest_report_for_episode(episode_version_id)


def _collect_observations(
    store: OutcomeLearningStore,
    *,
    policy: LessonCompilationPolicy,
    cohort: str,
    horizon_id: str,
    compilation_cutoff: datetime,
    knowledge_cutoff_at: datetime,
    consuming_run_id: str | None,
) -> tuple[_EligibleObservation, ...]:
    rows: list[_EligibleObservation] = []
    for episode in _eligible_episodes(
        store,
        cohort=cohort,
        horizon_id=horizon_id,
        compilation_cutoff=compilation_cutoff,
        knowledge_cutoff_at=knowledge_cutoff_at,
        consuming_run_id=consuming_run_id,
    ):
        report = _latest_report(store, episode.episode_version_id)
        if report is None:
            continue
        for obs in report.observations:
            if obs.component != policy.component:
                continue
            if obs.metric != policy.metric:
                continue
            if obs.method == AttributionMethod.UNAVAILABLE or obs.value is None:
                continue
            if not _is_effective_method(obs.method):
                continue
            rows.append(
                _EligibleObservation(
                    episode_version_id=episode.episode_version_id,
                    report_id=report.report_id,
                    value=obs.value,
                    available_at=episode.temporal.available_at,
                )
            )
            break
    return tuple(rows)


def _aggregate_values(values: tuple[Decimal, ...]) -> tuple[Decimal, Decimal]:
    """Polars mean and population std of observation values."""
    frame = pl.DataFrame({"value": [float(v) for v in values]})
    stats = frame.select(
        pl.col("value").mean().alias("mean"),
        pl.col("value").std(ddof=0).fill_null(0.0).alias("std"),
    ).row(0)
    mean_val = Decimal(str(stats[0])).quantize(Decimal("0.0000001"))
    std_val = Decimal(str(stats[1])).quantize(Decimal("0.0000001"))
    return mean_val, std_val


def _apply_shrinkage(
    *,
    sample_mean: Decimal,
    effective_sample_count: int,
    min_sample: int,
    prior: Decimal,
) -> tuple[Decimal, Decimal | None, Decimal | None, LessonQualityState]:
    if effective_sample_count <= 0:
        raise LessonCompilationError("no effective observations for aggregation")

    if effective_sample_count >= min_sample:
        return sample_mean, None, None, LessonQualityState.ADEQUATE

    weight = Decimal(effective_sample_count) / Decimal(min_sample)
    shrinkage = _ONE - weight
    estimate = (weight * sample_mean) + (shrinkage * prior)
    return (
        estimate.quantize(Decimal("0.0000001")),
        prior,
        shrinkage.quantize(Decimal("0.0000001")),
        LessonQualityState.LOW_SAMPLE,
    )


class LessonCompiler:
    """Compile structured lesson versions from store episodes and reports."""

    def __init__(self, *, store: OutcomeLearningStore) -> None:
        self._store = store

    def compile(
        self,
        *,
        policy: LessonCompilationPolicy,
        cohort: str,
        horizon_id: str,
        compilation_cutoff: datetime,
        knowledge_cutoff_at: datetime,
        consuming_run_id: str | None = None,
        regime: str | None = None,
        supersedes_version_id: UUID | None = None,
        rendered_summary: str | None = None,
    ) -> OutcomeLessonVersion:
        """Build one immutable lesson from eligible store state.

        ``rendered_summary`` is ignored — prose cannot replace structured payload.
        """
        _ = rendered_summary

        bound = require_utc_datetime(compilation_cutoff, field_name="compilation_cutoff")
        knowledge = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")

        observations = _collect_observations(
            self._store,
            policy=policy,
            cohort=cohort,
            horizon_id=horizon_id,
            compilation_cutoff=bound,
            knowledge_cutoff_at=knowledge,
            consuming_run_id=consuming_run_id,
        )
        if not observations:
            raise LessonCompilationError("no eligible episodes for lesson compilation")

        if len({row.episode_version_id for row in observations}) != len(observations):
            raise LessonCompilationError("duplicate episode observations in lesson aggregation")

        values = tuple(row.value for row in observations)
        sample_mean, uncertainty = _aggregate_values(values)
        sample_count = len({row.episode_version_id for row in observations})
        effective_sample_count = len(observations)

        estimate, prior, shrinkage, quality_state = _apply_shrinkage(
            sample_mean=sample_mean,
            effective_sample_count=effective_sample_count,
            min_sample=policy.min_sample,
            prior=policy.prior,
        )

        episode_version_ids = tuple(
            sorted({row.episode_version_id for row in observations}, key=str)
        )
        report_ids = tuple(sorted({row.report_id for row in observations}, key=str))
        latest_source_available = max(row.available_at for row in observations)
        available_at = max(bound, latest_source_available)

        warning_codes: tuple[str, ...] = ()
        if quality_state is LessonQualityState.LOW_SAMPLE:
            warning_codes = ("low_sample_shrinkage",)

        content_hash = lesson_content_hash(
            compilation_policy_id=policy.policy_id,
            compilation_cutoff=bound,
            episode_version_ids=episode_version_ids,
            report_ids=report_ids,
            component=policy.component,
            estimate=estimate,
            uncertainty=uncertainty,
            sample_count=sample_count,
            effective_sample_count=effective_sample_count,
            quality_state=quality_state,
        )
        version_id = lesson_version_id(
            compilation_policy_id=policy.policy_id,
            content_hash=content_hash,
            supersedes_version_id=supersedes_version_id,
        )

        return OutcomeLessonVersion(
            lesson_version_id=version_id,
            content_hash=content_hash,
            supersedes_version_id=supersedes_version_id,
            compilation_policy_id=policy.policy_id,
            compilation_cutoff=bound,
            episode_version_ids=episode_version_ids,
            report_ids=report_ids,
            cohort=cohort,
            regime=regime,
            horizon_id=horizon_id,
            component=policy.component,
            sample_count=sample_count,
            effective_sample_count=effective_sample_count,
            estimate=estimate,
            uncertainty=uncertainty,
            prior=prior,
            shrinkage=shrinkage,
            quality_state=quality_state,
            recommendation_code=None,
            warning_codes=warning_codes,
            available_at=available_at,
        )

    def compile_and_persist(
        self,
        *,
        policy: LessonCompilationPolicy,
        cohort: str,
        horizon_id: str,
        compilation_cutoff: datetime,
        knowledge_cutoff_at: datetime,
        consuming_run_id: str | None = None,
        regime: str | None = None,
        supersedes_version_id: UUID | None = None,
        rendered_summary: str | None = None,
    ) -> OutcomeLessonVersion:
        """Compile and append via :meth:`OutcomeLearningStore.append_lesson`."""
        lesson = self.compile(
            policy=policy,
            cohort=cohort,
            horizon_id=horizon_id,
            compilation_cutoff=compilation_cutoff,
            knowledge_cutoff_at=knowledge_cutoff_at,
            consuming_run_id=consuming_run_id,
            regime=regime,
            supersedes_version_id=supersedes_version_id,
            rendered_summary=rendered_summary,
        )
        return self._store.append_lesson(lesson)


__all__ = [
    "LessonCompilationError",
    "LessonCompilationPolicy",
    "LessonCompiler",
    "cohort_key",
]
