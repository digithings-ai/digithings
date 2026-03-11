"""Tool schema for analysis_agent. Orchestrator calls this with dataset_ref and task."""

from __future__ import annotations

ANALYSIS_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "analysis_agent",
        "description": "Run analytics on a stored dataset: correlation, regression, summary stats, group-by, pivot table, or clustering. Use when the user asks for statistics or analysis of search results.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {"type": "string", "description": "Path or ref to the dataset."},
                "task": {"type": "string", "description": "What to compute, e.g. 'correlation matrix', 'summary stats for score and rank'."},
                "options": {"type": "object", "description": "Optional overrides."},
            },
            "required": ["dataset_ref", "task"],
        },
    },
}
