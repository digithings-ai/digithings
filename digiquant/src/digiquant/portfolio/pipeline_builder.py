"""REM-059 — digiquant shim over digigraph's declarative phase builder.

research and portfolio sub-graphs share the same LangGraph topology helper. Full
decoupling (copy implementation into digiquant, drop digigraph import) is
tracked in [#579](https://github.com/digithings-ai/digithings/issues/579).

Import from this module instead of ``digigraph.graph.pipeline_builder`` for
portfolio entrypoints; research phases may follow in #579.
"""

from digigraph.graph.pipeline_builder import (
    FanOutPhase,
    NodeSpec,
    PipelinePhase,
    build_pipeline,
)

__all__ = ["FanOutPhase", "NodeSpec", "PipelinePhase", "build_pipeline"]
