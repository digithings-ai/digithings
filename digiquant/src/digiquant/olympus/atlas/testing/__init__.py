"""Atlas pipeline simulation harness.

Use ``simulated_pipeline()`` from your tests to run the full LangGraph
pipeline end-to-end without touching the real LLM provider or Supabase.
The harness patches ``digigraph.graph.research_agent.completion_text``
with a deterministic dispatcher keyed by output schema name and threads
a ``FakeSupabaseClient`` everywhere a real client would go.

See ``simulator.py`` for the dispatch table + override mechanism.
"""

from __future__ import annotations

from digiquant.olympus.atlas.testing.simulator import (
    DEFAULT_RESPONSES,
    SimulationRun,
    parse_schema_name,
    seed_supabase_client,
    simulate_chat_completion,
    simulated_pipeline,
)

__all__ = [
    "DEFAULT_RESPONSES",
    "SimulationRun",
    "parse_schema_name",
    "seed_supabase_client",
    "simulate_chat_completion",
    "simulated_pipeline",
]
