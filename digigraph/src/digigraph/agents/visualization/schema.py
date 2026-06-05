"""Tool schema for visualization_agent. Orchestrator calls this with dataset_ref and task."""

from __future__ import annotations

VISUALIZATION_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "visualization_agent",
        "description": "Generate charts, plots, or Mermaid diagrams from a stored dataset. Use after digisearch when you have a dataset_ref. The specialist will choose the right visualization (distribution, time series, categorical, scatter, relationship graph, or Mermaid diagram).",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {
                    "type": "string",
                    "description": "Path or ref to the dataset (from digisearch tool result).",
                },
                "task": {
                    "type": "string",
                    "description": "What to visualize, e.g. 'plot distribution of sentDateTime', 'relationship graph from fromAddress to conversationId'.",
                },
                "options": {
                    "type": "object",
                    "description": "Optional overrides (column names, etc.).",
                },
            },
            "required": ["dataset_ref", "task"],
        },
    },
}
