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
    LlmCallTelemetry,
    QUIET_DAY_LLM_BUDGET,
    QUIET_DAY_MIN_PATCH_RATIO,
    SimulationRun,
    build_quiet_day_canned_extras,
    client_store_to_canned_extras,
    llm_telemetry_from_calls,
    parse_schema_name,
    seed_supabase_client,
    simulate_chat_completion,
    simulated_pipeline,
)

__all__ = [
    "DEFAULT_RESPONSES",
    "LlmCallTelemetry",
    "QUIET_DAY_LLM_BUDGET",
    "QUIET_DAY_MIN_PATCH_RATIO",
    "SimulationRun",
    "build_quiet_day_canned_extras",
    "client_store_to_canned_extras",
    "llm_telemetry_from_calls",
    "parse_schema_name",
    "seed_supabase_client",
    "simulate_chat_completion",
    "simulated_pipeline",
]
