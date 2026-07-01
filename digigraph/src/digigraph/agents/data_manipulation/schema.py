"""Tool schema for data_manipulation_agent. Orchestrator calls with dataset_ref and task."""

from __future__ import annotations

DATA_MANIPULATION_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "data_manipulation_agent",
        "description": "Basic data ops on a stored dataset: column math, round, transform, group-by aggregate, merge/join two datasets, or append. Use when the user wants to transform columns, round numbers, group and sum/count, merge two result sets, or concatenate tables.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {"type": "string", "description": "Path or ref to the dataset."},
                "task": {
                    "type": "string",
                    "description": "What to do, e.g. 'round column X to 2 decimals', 'group by sourceType and sum score', 'merge with dataset Y on id'.",
                },
                "second_dataset_ref": {
                    "type": "string",
                    "description": "For merge or append: path or ref to the second dataset.",
                },
                "options": {"type": "object", "description": "Optional overrides."},
            },
            "required": ["dataset_ref", "task"],
        },
    },
}
