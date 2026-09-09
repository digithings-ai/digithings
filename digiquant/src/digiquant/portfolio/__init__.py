"""digiquant.portfolio — analysis, portfolio mgmt, risk debate, reflection.

Sibling sub-package of :mod:`digiquant.research`. See
[ADR-0015](../../../docs/adr/0015-research-vs-portfolio.md) for the responsibility
boundary: research owns research (phases 1–7a, terminating at
``phase7_synthesis``), portfolio owns analysis + PM + risk + reflection
(phases 7c, 7cd, 7d, 9).

Public surface:
    - :class:`digiquant.portfolio.state.PortfolioState` — sub-graph state model.
    - :func:`digiquant.portfolio.graph.build_portfolio_graph` — portfolio phases as
      composable :class:`PipelinePhase` list (full chain orchestrator lands
      in #473).

Import direction (target state, ADR-0015):
    - research never imports from portfolio.
    - portfolio imports only the digest contract types from
      :mod:`digiquant.research.snapshot` plus shared state types from
      :mod:`digiquant.research.state`.

Transitional state in #472 (the package skeleton ticket):
    research's :func:`digiquant.research.graph.build_research_graph` still wires the
    portfolio phases to keep the cron baseline / delta / monthly behaviour
    identical across the package split — i.e. the four
    ``from digiquant.portfolio.phases.* import build_phase*`` lines in
    ``digiquant/src/digiquant/research/graph.py`` are a temporary direction
    violation. Issue #473 (portfolio graph + research→portfolio chain) removes them
    by introducing a top-level chain orchestrator that composes research and
    portfolio outside either package.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
