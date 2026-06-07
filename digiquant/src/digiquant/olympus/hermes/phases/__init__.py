"""Hermes phase nodes — analysis, debate, PM allocation, reflection.

Each phase composes :class:`digigraph.graph.pipeline_builder.PipelinePhase`
objects that operate on :class:`digiquant.olympus.hermes.state.HermesState` (today
an alias for :class:`digiquant.olympus.atlas.state.AtlasResearchState`).

Phases:
    - ``phase7c_analyst``   — 4-axis analyst specialisation (#430).
    - ``phase7cd_debate``   — Bull/Bear adversarial debate per ticker (#429).
    - ``phase7d_pm``        — risk-aggressive vs risk-conservative debate +
                              portfolio-manager allocation memo (#431).
    - ``phase9_evolution``  — closed-loop reflection / alpha scoring (#432).
"""

from __future__ import annotations
