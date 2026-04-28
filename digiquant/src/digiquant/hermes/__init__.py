"""digiquant.hermes — analysis, portfolio mgmt, risk debate, reflection.

Sibling sub-package of :mod:`digiquant.atlas`. See
[ADR-0015](../../../docs/adr/0015-atlas-vs-hermes.md) for the responsibility
boundary: Atlas owns research (phases 1–7a, terminating at
``phase7_synthesis``), Hermes owns analysis + PM + risk + reflection
(phases 7c, 7cd, 7d, 9).

Public surface:
    - :class:`digiquant.hermes.state.HermesState` — sub-graph state model.
    - :func:`digiquant.hermes.graph.build_hermes_graph` — Hermes phases as
      composable :class:`PipelinePhase` list (full chain orchestrator lands
      in #473).

Import direction (target state, ADR-0015):
    - Atlas never imports from Hermes.
    - Hermes imports only the digest contract types from
      :mod:`digiquant.atlas.snapshot` plus shared state types from
      :mod:`digiquant.atlas.state`.

Transitional state in #472 (the package skeleton ticket):
    Atlas's :func:`digiquant.atlas.graph.build_atlas_graph` still wires the
    Hermes phases to keep the cron baseline / delta / monthly behaviour
    identical across the package split — i.e. the four
    ``from digiquant.hermes.phases.* import build_phase*`` lines in
    ``digiquant/src/digiquant/atlas/graph.py`` are a temporary direction
    violation. Issue #473 (Hermes graph + atlas→hermes chain) removes them
    by introducing a top-level chain orchestrator that composes Atlas and
    Hermes outside either package.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
