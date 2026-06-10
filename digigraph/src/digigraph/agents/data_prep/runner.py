"""Run the data prep sub-agent: LLM + export, filter, sample tools."""

from __future__ import annotations

import json
import os
from typing import Any

from digigraph.agents._common import finalize_agent_output, load_dataset_path, run_tool_safe
from digigraph.llm_client import run_tools
from digigraph.model_config import get_model_for_mode
from digigraph.tools.analytics import export_dataset, filter_dataset, sample_dataset

PREP_SYSTEM = """You are a data prep specialist. The user wants to export, filter, or sample the dataset. Use exactly one of:
- export_dataset: format (json | csv | parquet), columns (optional list)
- filter_dataset: filters (required, list of {field, op, value}, e.g. [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}]), columns (optional)
- sample_dataset: n (number of rows) or frac (fraction 0-1), random_state (optional)

Then summarize where the result is (path or new dataset_ref)."""

PREP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "export_dataset",
            "description": "Export to JSON, CSV, or Parquet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["json", "csv", "parquet"]},
                    "columns": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_dataset",
            "description": "Filter rows by conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string"},
                                "value": {},
                            },
                            "required": ["field", "op", "value"],
                        },
                    },
                    "columns": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["filters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_dataset",
            "description": "Random sample of n rows or frac.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "frac": {"type": "number"},
                    "random_state": {"type": "integer"},
                },
            },
        },
    },
]


def run_data_prep_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Run the data prep sub-agent; returns JSON of the last tool result."""
    dataset_path, err = load_dataset_path(session_id, dataset_ref)
    if err is not None:
        return err

    last_tool_output: dict[str, Any] | None = None

    def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_tool_output
        args = dict(args or {})

        def _run() -> dict[str, Any]:
            if name == "export_dataset":
                files_base_url = (
                    os.environ.get("DIGI_FILES_BASE_URL", "").strip() or "http://127.0.0.1:8000"
                )
                return export_dataset(
                    dataset_path,
                    args.get("format", "json"),
                    args.get("columns"),
                    files_base_url=files_base_url,
                )
            if name == "filter_dataset":
                return filter_dataset(dataset_path, args.get("filters") or [], args.get("columns"))
            if name == "sample_dataset":
                return sample_dataset(
                    dataset_path, args.get("n"), args.get("frac"), args.get("random_state")
                )
            return {"error": f"Unknown tool: {name}"}

        out = run_tool_safe(_run)
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = run_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": PREP_SYSTEM},
            {
                "role": "user",
                "content": f"User request: {task}\n\nUse one of the tools. The dataset is loaded.",
            },
        ],
        tools=PREP_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    return finalize_agent_output(
        last_tool_output,
        content,
        no_tool_error="No tool was called",
        fallback_message="Data prep completed.",
    )
