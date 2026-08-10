"""Run the analysis sub-agent: LLM + analysis tools with injected dataset_path."""

from __future__ import annotations

import json
from typing import Any

from digigraph.agents._common import finalize_agent_output, load_dataset_path, run_tool_safe
from digigraph.llm_client import run_tools
from digigraph.model_config import get_model_for_mode
from digigraph.tools.analytics import (
    cluster_metadata,
    correlation_matrix,
    group_by_summary,
    pivot_table,
    simple_regression,
    summary_stats,
)

ANALYSIS_SYSTEM = """You are an analysis specialist. The user has requested statistics or analysis. You have access to a dataset. Use exactly one of:
- correlation_matrix: columns (optional list of numeric columns)
- simple_regression: x_column (required), y_column (required)
- summary_stats: columns (optional list)
- group_by_summary: group_by_columns (required, list), agg_columns (optional, e.g. [{"col": "score", "agg": "mean"}])
- pivot_table: index (required), columns (required), values (required), aggfunc (sum | mean | count)
- cluster_metadata: numeric_columns (required, list), n_clusters (optional, default 3)

Choose the tool that best matches the request. Then summarize the result in one short sentence."""

ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "correlation_matrix",
            "description": "Correlation matrix of numeric columns.",
            "parameters": {
                "type": "object",
                "properties": {"columns": {"type": "array", "items": {"type": "string"}}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simple_regression",
            "description": "Simple linear regression y ~ x.",
            "parameters": {
                "type": "object",
                "properties": {"x_column": {"type": "string"}, "y_column": {"type": "string"}},
                "required": ["x_column", "y_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summary_stats",
            "description": "Summary statistics per column.",
            "parameters": {
                "type": "object",
                "properties": {"columns": {"type": "array", "items": {"type": "string"}}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group_by_summary",
            "description": "Group by columns and aggregate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by_columns": {"type": "array", "items": {"type": "string"}},
                    "agg_columns": {"type": "array"},
                },
                "required": ["group_by_columns"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pivot_table",
            "description": "Pivot table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "string"},
                    "columns": {"type": "string"},
                    "values": {"type": "string"},
                    "aggfunc": {"type": "string"},
                },
                "required": ["index", "columns", "values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cluster_metadata",
            "description": "Cluster rows by numeric columns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numeric_columns": {"type": "array", "items": {"type": "string"}},
                    "n_clusters": {"type": "integer"},
                },
                "required": ["numeric_columns"],
            },
        },
    },
]


def run_analysis_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Run the analysis sub-agent; returns JSON of the last tool result."""
    dataset_path, err = load_dataset_path(session_id, dataset_ref)
    if err is not None:
        return err

    last_tool_output: dict[str, Any] | None = None

    def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_tool_output
        args = dict(args or {})

        def _run() -> dict[str, Any]:
            if name == "correlation_matrix":
                return correlation_matrix(dataset_path, args.get("columns"))
            if name == "simple_regression":
                return simple_regression(
                    dataset_path, args.get("x_column", ""), args.get("y_column", "")
                )
            if name == "summary_stats":
                return summary_stats(dataset_path, args.get("columns"))
            if name == "group_by_summary":
                return group_by_summary(
                    dataset_path, args.get("group_by_columns") or [], args.get("agg_columns")
                )
            if name == "pivot_table":
                return pivot_table(
                    dataset_path,
                    args.get("index", ""),
                    args.get("columns", ""),
                    args.get("values", ""),
                    args.get("aggfunc", "sum"),
                )
            if name == "cluster_metadata":
                return cluster_metadata(
                    dataset_path, args.get("numeric_columns") or [], args.get("n_clusters", 3)
                )
            return {"error": f"Unknown tool: {name}"}

        out = run_tool_safe(_run)
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = run_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {
                "role": "user",
                "content": f"User request: {task}\n\nUse one of the tools. The dataset is loaded.",
            },
        ],
        tools=ANALYSIS_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    return finalize_agent_output(
        last_tool_output,
        content,
        no_tool_error="No tool was called",
        fallback_message="Analysis completed.",
    )
