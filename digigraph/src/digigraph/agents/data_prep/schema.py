"""Tool schema for data_prep_agent. Orchestrator calls this with dataset_ref and task."""

from __future__ import annotations

DATA_PREP_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "data_prep_agent",
        "description": "Export, filter, or sample a stored dataset. Use when the user wants to export data, subset by criteria, or take a random sample.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {"type": "string", "description": "Path or ref to the dataset."},
                "task": {"type": "string", "description": "What to do, e.g. 'export as CSV', 'filter where sourceType eq EXCHANGE', 'sample 50 rows'."},
                "options": {"type": "object", "description": "Optional overrides."},
            },
            "required": ["dataset_ref", "task"],
        },
    },
}
