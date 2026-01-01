"""Tool schema for data_engineer_agent. Orchestrator calls with dataset_ref(s) and task."""

from __future__ import annotations

DATA_ENGINEER_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "data_engineer_agent",
        "description": "Run custom Python (Polars) code on one or more stored datasets to produce a new dataset. Use when the user needs a transformation beyond basic ops (e.g. custom formulas, multi-step logic). Code receives df_0, df_1, ... and must set 'result' to a Polars DataFrame.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {
                    "type": "string",
                    "description": "Path or ref to the primary dataset.",
                },
                "task": {
                    "type": "string",
                    "description": "What to compute, e.g. 'add a column that is the sum of columns A and B'.",
                },
                "additional_dataset_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra datasets (as df_1, df_2, ...).",
                },
                "options": {"type": "object", "description": "Optional overrides."},
            },
            "required": ["dataset_ref", "task"],
        },
    },
}
