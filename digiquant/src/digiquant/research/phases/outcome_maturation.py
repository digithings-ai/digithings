"""WP15.6 — mature prior outcomes and pin structured lessons at preflight (#2975).

Runs under the pinned knowledge cutoff before WP14 context compile:
pin cutoff → mature prior outcomes → compile/pin lesson → WP14 prerequisites.

No new research graph node — invoked from :mod:`phases.preflight` only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
)
from uuid import UUID

from pydantic import ConfigDict

from digiquant.dashboard.learning.component_attribution import ComponentAttributor
from digiquant.dashboard.learning.lesson_registry import (
    LessonCompilationError,
    LessonCompilationPolicy,
    LessonCompiler,
)
from digiquant.dashboard.learning.outcome_assembly import OutcomeEpisodeAssembler
from digiquant.dashboard.learning.outcome_models import (
    AttributionComponent,
    OutcomeLearningModel,
    OutcomeLessonVersion,
)
from digiquant.dashboard.learning.outcome_store import OutcomeLearningStore
from digiquant.dashboard.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

LESSON_PINNED = "pinned"
LESSON_UNAVAILABLE = "lesson_unavailable"
STORE_UNAVAILABLE = "store_unavailable"

DEFAULT_OUTCOME_LESSON_POLICY = LessonCompilationPolicy(
    policy_id="forecast-error-v1",
    component=AttributionComponent.FORECAST,
    metric="forecast_error_bps",
    min_sample=1,
    prior=Decimal("-10.0"),
)

DEFAULT_OUTCOME_LESSON_COHORT = "mandate-daily:portfolio"
DEFAULT_OUTCOME_LESSON_HORIZON = "h-21s"


class OutcomeLessonPin(OutcomeLearningModel):
    """Exact structured lesson version selected once at preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson_version_id: UUID
    content_hash: str
    compilation_policy_id: str
    cohort: str
    horizon_id: str
    component: AttributionComponent
    compilation_cutoff: datetime
    available_at: datetime
    schema_version: int = 1


@dataclass(frozen=True)
class OutcomeMaturationDeps:
    """Injected learning stack for one preflight maturation pass."""

    store: OutcomeLearningStore
    assembler: OutcomeEpisodeAssembler
    attributor: ComponentAttributor
    compiler: LessonCompiler
    policy: LessonCompilationPolicy = DEFAULT_OUTCOME_LESSON_POLICY
    cohort: str = DEFAULT_OUTCOME_LESSON_COHORT
    horizon_id: str = DEFAULT_OUTCOME_LESSON_HORIZON


@dataclass(frozen=True)
class OutcomeMaturationResult:
    """Outcome of one preflight maturation + lesson pin attempt."""

    status: Literal["pinned", "lesson_unavailable", "store_unavailable", "skipped"]
    pin: OutcomeLessonPin | None
    unavailable_reason: str | None
    assembled: int = 0
    blocked: int = 0
    skipped: int = 0


def _pin_from_lesson(
    lesson: OutcomeLessonVersion,
    *,
    policy: LessonCompilationPolicy,
) -> OutcomeLessonPin:
    return OutcomeLessonPin(
        lesson_version_id=lesson.lesson_version_id,
        content_hash=lesson.content_hash,
        compilation_policy_id=lesson.compilation_policy_id,
        cohort=lesson.cohort,
        horizon_id=lesson.horizon_id,
        component=policy.component,
        compilation_cutoff=lesson.compilation_cutoff,
        available_at=lesson.available_at,
    )


def mature_prior_outcomes(
    deps: OutcomeMaturationDeps,
    *,
    knowledge_cutoff_at: datetime,
) -> tuple[int, int, int]:
    """Assemble and attribute episodes visible at cutoff (prior runs only)."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    pass_result = deps.assembler.assemble_pass(as_of=cutoff, knowledge_cutoff_at=cutoff)
    for item in pass_result.results:
        if item.episode is not None:
            deps.attributor.attribute_and_persist(item.episode, knowledge_cutoff_at=cutoff)
    return pass_result.assembled, pass_result.blocked, pass_result.skipped


def select_or_compile_lesson(
    deps: OutcomeMaturationDeps,
    *,
    knowledge_cutoff_at: datetime,
    consuming_run_id: str | None,
) -> OutcomeLessonVersion | None:
    """Return the lesson version visible at cutoff, compiling when needed."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    policy = deps.policy

    existing = deps.store.select_lesson_as_of(
        compilation_policy_id=policy.policy_id,
        cohort=deps.cohort,
        component=policy.component,
        horizon_id=deps.horizon_id,
        as_of=cutoff,
    )
    if existing is not None:
        return existing

    try:
        return deps.compiler.compile_and_persist(
            policy=policy,
            cohort=deps.cohort,
            horizon_id=deps.horizon_id,
            compilation_cutoff=cutoff,
            knowledge_cutoff_at=cutoff,
            consuming_run_id=consuming_run_id,
        )
    except LessonCompilationError as exc:
        logger.debug("outcome lesson compile unavailable at preflight: %s", exc)
        return None


def pin_outcome_lesson_for_preflight(
    deps: OutcomeMaturationDeps | None,
    *,
    knowledge_cutoff_at: datetime | None,
    consuming_run_id: str | None,
    resume_pin: dict[str, Any] | None = None,
    resume_status: str | None = None,
) -> OutcomeMaturationResult:
    """Mature prior outcomes and pin one exact lesson version for WP14 context."""
    if resume_status == LESSON_PINNED and isinstance(resume_pin, dict) and resume_pin:
        return OutcomeMaturationResult(status="skipped", pin=None, unavailable_reason=None)

    if deps is None:
        return OutcomeMaturationResult(
            status=STORE_UNAVAILABLE,
            pin=None,
            unavailable_reason=(
                "outcome_maturation deps not wired; structured lessons unavailable"
            ),
        )

    if knowledge_cutoff_at is None:
        return OutcomeMaturationResult(
            status=LESSON_UNAVAILABLE,
            pin=None,
            unavailable_reason="knowledge_cutoff_at missing on state",
        )

    try:
        cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    except ValueError as exc:
        return OutcomeMaturationResult(
            status=LESSON_UNAVAILABLE,
            pin=None,
            unavailable_reason=str(exc),
        )

    assembled, blocked, skipped = mature_prior_outcomes(deps, knowledge_cutoff_at=cutoff)
    lesson = select_or_compile_lesson(
        deps,
        knowledge_cutoff_at=cutoff,
        consuming_run_id=consuming_run_id,
    )
    if lesson is None:
        return OutcomeMaturationResult(
            status=LESSON_UNAVAILABLE,
            pin=None,
            unavailable_reason="no eligible structured lesson at cutoff",
            assembled=assembled,
            blocked=blocked,
            skipped=skipped,
        )

    pin = _pin_from_lesson(lesson, policy=deps.policy)
    return OutcomeMaturationResult(
        status="pinned",
        pin=pin,
        unavailable_reason=None,
        assembled=assembled,
        blocked=blocked,
        skipped=skipped,
    )


def outcome_lesson_preflight_update(
    result: OutcomeMaturationResult,
) -> dict[str, Any]:
    """Map maturation result to ResearchState preflight fields."""
    if result.status == "skipped":
        return {}
    if result.status == "pinned" and result.pin is not None:
        return {
            "outcome_lesson_pin": result.pin.model_dump(mode="json"),
            "outcome_lesson_status": LESSON_PINNED,
            "outcome_lesson_unavailable_reason": None,
        }
    return {
        "outcome_lesson_pin": None,
        "outcome_lesson_status": result.status,
        "outcome_lesson_unavailable_reason": result.unavailable_reason,
    }


__all__ = [
    "DEFAULT_OUTCOME_LESSON_COHORT",
    "DEFAULT_OUTCOME_LESSON_HORIZON",
    "DEFAULT_OUTCOME_LESSON_POLICY",
    "LESSON_PINNED",
    "LESSON_UNAVAILABLE",
    "OutcomeLessonPin",
    "OutcomeMaturationDeps",
    "OutcomeMaturationResult",
    "STORE_UNAVAILABLE",
    "mature_prior_outcomes",
    "outcome_lesson_preflight_update",
    "pin_outcome_lesson_for_preflight",
    "select_or_compile_lesson",
]
