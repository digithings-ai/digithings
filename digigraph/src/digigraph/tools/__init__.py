"""DigiGraph tool adapters (primitives). MCP tools from DigiQuant, DigiSearch, etc.

Orchestrator tool schemas live under agents/ and are registered in digigraph.orchestration.
"""

from __future__ import annotations

from digigraph.tools.digisearch import digisearch

__all__ = [
    "digisearch",
]
