"""digigraph tool adapters (primitives). MCP tools from digiquant, digisearch, etc.

Orchestrator tool schemas live under agents/ and are registered in digigraph.orchestration.
"""

from __future__ import annotations

from digigraph.tools.digisearch import digisearch

__all__ = [
    "digisearch",
]
