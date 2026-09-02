"""dashboard learning-loop helpers (beliefs distillation, spec §11.1)."""

from digiquant.dashboard.learning.beliefs_distillation import (
    BeliefsDistillationDeps,
    build_beliefs_distillation_phase,
    distill_beliefs,
    resolve_beliefs_fold_mode,
    run_beliefs_distillation_if_triggered,
    should_distill_beliefs,
)
from digiquant.dashboard.learning.component_attribution import (
    ComponentAttributor,
    PairedReplayEvidence,
    build_component_attribution_report,
)
from digiquant.dashboard.learning.lesson_registry import (
    LessonCompilationPolicy,
    LessonCompiler,
    cohort_key,
)
from digiquant.dashboard.learning.outcome_assembly import (
    AssemblyPassResult,
    OutcomeEpisodeAssembler,
)
from digiquant.dashboard.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentAttributionReport,
    ComponentObservation,
    EpisodeDisposition,
    OutcomeEpisode,
    OutcomeLessonVersion,
)
from digiquant.dashboard.learning.outcome_store import OutcomeLearningStore

__all__ = [
    "AttributionComponent",
    "AttributionMethod",
    "BeliefsDistillationDeps",
    "ComponentAttributor",
    "ComponentAttributionReport",
    "ComponentObservation",
    "EpisodeDisposition",
    "OutcomeEpisode",
    "OutcomeLessonVersion",
    "AssemblyPassResult",
    "OutcomeEpisodeAssembler",
    "LessonCompilationPolicy",
    "LessonCompiler",
    "OutcomeLearningStore",
    "PairedReplayEvidence",
    "cohort_key",
    "build_component_attribution_report",
    "build_beliefs_distillation_phase",
    "distill_beliefs",
    "resolve_beliefs_fold_mode",
    "run_beliefs_distillation_if_triggered",
    "should_distill_beliefs",
]
