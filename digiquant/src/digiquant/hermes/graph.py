"""Hermes graph — analysis sub-pipeline.

This module exposes ``build_hermes_phases`` so callers (the existing Atlas
graph builder today; the dedicated atlas→hermes chain orchestrator landing
in #473) can compose the Hermes phases without touching their internals.

The full ``build_hermes_graph(atlas_digest, deps)`` and
``run_atlas_then_hermes(...)`` chain entry points are tracked on issue #473.
For now Hermes phases plug into the existing ``digiquant.atlas.graph.build_atlas_graph``
wiring — this keeps the cron baseline / delta / monthly behaviour identical
across the package split.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from digiquant.hermes.phases.phase7c_analyst import build_phase7c
from digiquant.hermes.phases.phase7cd_debate import build_phase7cd
from digiquant.hermes.phases.phase7d_pm import build_phase7d
from digiquant.hermes.phases.phase9_evolution import Phase9Deps, build_phase9

if TYPE_CHECKING:
    from digigraph.graph.pipeline_builder import PipelinePhase

__all__ = [
    "Phase9Deps",
    "build_hermes_phases",
    "build_phase7c",
    "build_phase7cd",
    "build_phase7d",
    "build_phase9",
]


def build_hermes_phases(
    *,
    watchlist: list[str],
    phase9_deps: Phase9Deps | None = None,
    debate_rounds: int = 1,
) -> list["PipelinePhase"]:
    """Return the four Hermes phases as an ordered list.

    Wiring contract:
        phase7c (4-axis analyst, parallel fan-out) →
        phase7cd (Bull/Bear debate, per-ticker fan-out) →
        phase7d (risk debate + PM allocation memo) →
        phase9 (closed-loop reflection / alpha scoring).
    """
    phases: list[PipelinePhase] = []
    phases.extend(build_phase7c(watchlist))
    phases.extend(build_phase7cd(watchlist, rounds=debate_rounds))
    phases.extend(build_phase7d())
    phases.append(build_phase9(phase9_deps))
    return phases
