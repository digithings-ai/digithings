"""digiquant.olympus.hermes — analysis, portfolio mgmt, risk debate, reflection.

Sibling sub-package of :mod:`digiquant.olympus.atlas`. See
[ADR-0015](../../../docs/adr/0015-atlas-vs-hermes.md) for the responsibility
boundary: Atlas owns research (phases 1–7a, terminating at
``phase7_synthesis``), Hermes owns analysis + PM + risk + reflection
(phases 7c, 7cd, 7d, 9).

Public surface:
    - :class:`digiquant.olympus.hermes.state.HermesState` — sub-graph state model.
    - :func:`digiquant.olympus.hermes.graph.build_hermes_graph` — Hermes phases as
      composable :class:`PipelinePhase` list (full chain orchestrator lands
      in #473).

Import direction (target state, ADR-0015):
    - Atlas never imports from Hermes.
    - Hermes imports only the digest contract types from
      :mod:`digiquant.olympus.atlas.snapshot` plus shared state types from
      :mod:`digiquant.olympus.atlas.state`.

Transitional state in #472 (the package skeleton ticket):
    Atlas's :func:`digiquant.olympus.atlas.graph.build_atlas_graph` still wires the
    Hermes phases to keep the cron baseline / delta / monthly behaviour
    identical across the package split — i.e. the four
    ``from digiquant.olympus.hermes.phases.* import build_phase*`` lines in
    ``digiquant/src/digiquant/olympus/atlas/graph.py`` are a temporary direction
    violation. Issue #473 (Hermes graph + atlas→hermes chain) removes them
    by introducing a top-level chain orchestrator that composes Atlas and
    Hermes outside either package.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
