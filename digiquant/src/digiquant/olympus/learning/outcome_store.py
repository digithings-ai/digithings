"""Private append-only outcome-learning store (#2959 / WP15.2).

Persists frozen WP15.1 contracts into one store boundary (in-memory for unit
tests; migration ``093_olympus_outcome_learning.sql`` is the durable schema).

Semantics:
- **Content idempotency:** same primary key + same payload is a no-op.
- **Changed content appends:** a new content-addressed id inserts a new row —
  never UPDATE. Same PK with a different hash raises
  :class:`OutcomeLearningConflict`.
- **As-of selection:** ``available_at <= as_of`` and ``known_at <= knowledge_cutoff_at``
  for episodes; lessons also require ``compilation_cutoff <= as_of``.
- **Exact load** returns byte-equivalent typed state even after newer rows exist.
- **No fabrication:** selectors never synthesize rows absent from the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    ComponentAttributionReport,
    OutcomeEpisode,
    OutcomeLessonVersion,
)
from digiquant.olympus.temporal import require_utc_datetime

T = TypeVar("T", bound=BaseModel)


class OutcomeLearningConflict(RuntimeError):
    """Same identity already stored with incompatible content."""


class OutcomeLearningError(RuntimeError):
    """Store refused a write or could not resolve exact state."""


class OutcomeLearningMissingError(LookupError):
    """Exact version / entity not found."""


@dataclass(frozen=True)
class LoadedOutcomeEpisode:
    """Exact typed reconstruction of one :class:`OutcomeEpisode`."""

    episode: OutcomeEpisode
    reports: tuple[ComponentAttributionReport, ...]


def _payload_bytes(model: BaseModel) -> bytes:
    return model.model_dump_json().encode("utf-8")


def _require_parent(*, label: str, parent_id: UUID | None, present: bool) -> None:
    if parent_id is not None and not present:
        raise OutcomeLearningError(f"{label} references missing parent {parent_id}")


class OutcomeLearningStore:
    """Append-only outcome-learning boundary (no upsert / update / delete)."""

    def __init__(self) -> None:
        self._episodes: dict[UUID, OutcomeEpisode] = {}
        self._reports: dict[UUID, ComponentAttributionReport] = {}
        self._lessons: dict[UUID, OutcomeLessonVersion] = {}
        self._reports_by_episode: dict[UUID, tuple[UUID, ...]] = {}

    def _append_idempotent(
        self,
        *,
        store: dict[UUID, T],
        key: UUID,
        value: T,
        content_hash: str | None,
        existing_hash: str | None,
        label: str,
    ) -> T:
        if key in store:
            if existing_hash is not None and content_hash is not None:
                if existing_hash == content_hash:
                    return store[key]
            elif store[key].model_dump_json() == value.model_dump_json():
                return store[key]
            raise OutcomeLearningConflict(f"{label} {key} exists with different content")
        store[key] = value
        return value

    def append_episode(self, episode: OutcomeEpisode) -> OutcomeEpisode:
        """Insert episode version; exact retry is a no-op; corrections append child."""
        _require_parent(
            label="OutcomeEpisode",
            parent_id=episode.supersedes_version_id,
            present=(
                episode.supersedes_version_id is None
                or episode.supersedes_version_id in self._episodes
            ),
        )
        existing = self._episodes.get(episode.episode_version_id)
        return self._append_idempotent(
            store=self._episodes,
            key=episode.episode_version_id,
            value=episode,
            content_hash=episode.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="episode_version_id",
        )

    def append_report(self, report: ComponentAttributionReport) -> ComponentAttributionReport:
        """Insert attribution report; requires existing episode version."""
        if report.episode_version_id not in self._episodes:
            raise OutcomeLearningError(
                f"report {report.report_id} references missing episode "
                f"{report.episode_version_id}"
            )
        stored = self._append_idempotent(
            store=self._reports,
            key=report.report_id,
            value=report,
            content_hash=None,
            existing_hash=None,
            label="report_id",
        )
        linked = self._reports_by_episode.get(report.episode_version_id, ())
        if report.report_id not in linked:
            self._reports_by_episode[report.episode_version_id] = (*linked, report.report_id)
        return stored

    def append_lesson(self, lesson: OutcomeLessonVersion) -> OutcomeLessonVersion:
        """Insert lesson version; requires declared episode and report membership."""
        _require_parent(
            label="OutcomeLessonVersion",
            parent_id=lesson.supersedes_version_id,
            present=(
                lesson.supersedes_version_id is None
                or lesson.supersedes_version_id in self._lessons
            ),
        )
        for episode_id in lesson.episode_version_ids:
            if episode_id not in self._episodes:
                raise OutcomeLearningError(
                    f"lesson {lesson.lesson_version_id} references missing episode {episode_id}"
                )
        for report_id in lesson.report_ids:
            if report_id not in self._reports:
                raise OutcomeLearningError(
                    f"lesson {lesson.lesson_version_id} references missing report {report_id}"
                )
            report = self._reports[report_id]
            if report.episode_version_id not in lesson.episode_version_ids:
                raise OutcomeLearningError(
                    f"lesson {lesson.lesson_version_id} report {report_id} "
                    f"episode {report.episode_version_id} not in episode_version_ids"
                )
        existing = self._lessons.get(lesson.lesson_version_id)
        return self._append_idempotent(
            store=self._lessons,
            key=lesson.lesson_version_id,
            value=lesson,
            content_hash=lesson.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="lesson_version_id",
        )

    def select_episode_as_of(
        self,
        *,
        episode_key: str,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> OutcomeEpisode | None:
        """Pick the newest eligible episode version for a logical key at a cutoff."""
        cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
        bound = require_utc_datetime(as_of, field_name="as_of")
        candidates: list[OutcomeEpisode] = []
        for episode in self._episodes.values():
            if episode.episode_key != episode_key:
                continue
            if episode.temporal.available_at > bound:
                continue
            if episode.temporal.known_at > cutoff:
                continue
            candidates.append(episode)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                item.temporal.available_at,
                item.temporal.known_at,
                item.temporal.recorded_at,
            ),
            reverse=True,
        )
        return candidates[0]

    def select_lesson_as_of(
        self,
        *,
        compilation_policy_id: str,
        cohort: str,
        component: AttributionComponent,
        horizon_id: str,
        as_of: datetime,
        regime: str | None = None,
    ) -> OutcomeLessonVersion | None:
        """Pick the newest eligible lesson version for a typed cohort slice."""
        bound = require_utc_datetime(as_of, field_name="as_of")
        candidates: list[OutcomeLessonVersion] = []
        for lesson in self._lessons.values():
            if lesson.compilation_policy_id != compilation_policy_id:
                continue
            if lesson.cohort != cohort:
                continue
            if lesson.component != component:
                continue
            if lesson.horizon_id != horizon_id:
                continue
            if lesson.regime != regime:
                continue
            if lesson.compilation_cutoff > bound:
                continue
            if lesson.available_at > bound:
                continue
            candidates.append(lesson)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                item.available_at,
                item.compilation_cutoff,
                item.lesson_version_id,
            ),
            reverse=True,
        )
        return candidates[0]

    def load_episode(self, episode_version_id: UUID) -> OutcomeEpisode:
        """Exact-version load. Never falls back to latest."""
        episode = self._episodes.get(episode_version_id)
        if episode is None:
            raise OutcomeLearningMissingError(
                f"episode_version_id {episode_version_id} not found"
            )
        return episode

    def load_report(self, report_id: UUID) -> ComponentAttributionReport:
        report = self._reports.get(report_id)
        if report is None:
            raise OutcomeLearningMissingError(f"report_id {report_id} not found")
        return report

    def load_lesson(self, lesson_version_id: UUID) -> OutcomeLessonVersion:
        lesson = self._lessons.get(lesson_version_id)
        if lesson is None:
            raise OutcomeLearningMissingError(
                f"lesson_version_id {lesson_version_id} not found"
            )
        return lesson

    def load_episode_with_reports(self, episode_version_id: UUID) -> LoadedOutcomeEpisode:
        """Exact episode plus linked reports — never fabricates missing rows."""
        episode = self.load_episode(episode_version_id)
        report_ids = self._reports_by_episode.get(episode_version_id, ())
        reports: list[ComponentAttributionReport] = []
        for rid in report_ids:
            report = self._reports.get(rid)
            if report is None:
                raise OutcomeLearningError(
                    f"episode {episode_version_id} index references missing report {rid}"
                )
            reports.append(report)
        return LoadedOutcomeEpisode(episode=episode, reports=tuple(reports))

    def exact_episode_bytes(self, episode_version_id: UUID) -> bytes:
        episode = self.load_episode(episode_version_id)
        return _payload_bytes(episode)

    def exact_lesson_bytes(self, lesson_version_id: UUID) -> bytes:
        lesson = self.load_lesson(lesson_version_id)
        return _payload_bytes(lesson)


__all__ = [
    "LoadedOutcomeEpisode",
    "OutcomeLearningConflict",
    "OutcomeLearningError",
    "OutcomeLearningMissingError",
    "OutcomeLearningStore",
]
