"""digiquant.portfolio — analysis, portfolio mgmt, risk debate, reflection.

Sibling sub-package of :mod:`digiquant.research`. See
[ADR-0015](../../../docs/adr/0015-atlas-vs-hermes.md) for the responsibility
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

Historical note (#472 / #473, both closed):
    research's :func:`digiquant.research.graph.build_research_graph` used to wire the
    portfolio phases as a temporary direction violation. Issue #473 landed the
    top-level chain orchestrator (:mod:`digiquant.portfolio.chain`), which composes
    research and portfolio outside either package, and research no longer imports
    portfolio phases.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
