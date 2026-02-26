"""Run the analysis sub-agent: LLM + analysis tools with injected dataset_path."""

from __future__ import annotations

import json
from typing import Any

from digigraph.llm import chat_completion_with_tools, get_model_for_mode
from digigraph.run_storage import resolve_dataset_ref
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
    {"type": "function", "function": {"name": "correlation_matrix", "description": "Correlation matrix of numeric columns.", "parameters": {"type": "object", "properties": {"columns": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "simple_regression", "description": "Simple linear regression y ~ x.", "parameters": {"type": "object", "properties": {"x_column": {"type": "string"}, "y_column": {"type": "string"}}, "required": ["x_column", "y_column"]}}},
    {"type": "function", "function": {"name": "summary_stats", "description": "Summary statistics per column.", "parameters": {"type": "object", "properties": {"columns": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "group_by_summary", "description": "Group by columns and aggregate.", "parameters": {"type": "object", "properties": {"group_by_columns": {"type": "array", "items": {"type": "string"}}, "agg_columns": {"type": "array"}}, "required": ["group_by_columns"]}}},
    {"type": "function", "function": {"name": "pivot_table", "description": "Pivot table.", "parameters": {"type": "object", "properties": {"index": {"type": "string"}, "columns": {"type": "string"}, "values": {"type": "string"}, "aggfunc": {"type": "string"}}, "required": ["index", "columns", "values"]}}},
    {"type": "function", "function": {"name": "cluster_metadata", "description": "Cluster rows by numeric columns.", "parameters": {"type": "object", "properties": {"numeric_columns": {"type": "array", "items": {"type": "string"}}, "n_clusters": {"type": "integer"}}, "required": ["numeric_columns"]}}},
]


def run_analysis_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """
    Run the analysis sub-agent; returns JSON of the last tool result (matrix, stats, table, etc.)
    so the Open WebUI formatter can render tables and stats correctly.
    """
    try:
        path = resolve_dataset_ref(session_id, dataset_ref)
        dataset_path = str(path)
    except Exception as e:
        return json.dumps({"error": str(e)})

    last_tool_output: dict[str, Any] | None = None

    def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_tool_output
        args = dict(args or {})
        try:
            if name == "correlation_matrix":
                out = correlation_matrix(dataset_path, args.get("columns"))
            elif name == "simple_regression":
                out = simple_regression(dataset_path, args.get("x_column", ""), args.get("y_column", ""))
            elif name == "summary_stats":
                out = summary_stats(dataset_path, args.get("columns"))
            elif name == "group_by_summary":
                out = group_by_summary(dataset_path, args.get("group_by_columns") or [], args.get("agg_columns"))
            elif name == "pivot_table":
                out = pivot_table(dataset_path, args.get("index", ""), args.get("columns", ""), args.get("values", ""), args.get("aggfunc", "sum"))
            elif name == "cluster_metadata":
                out = cluster_metadata(dataset_path, args.get("numeric_columns") or [], args.get("n_clusters", 3))
            else:
                out = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            out = {"error": str(e)}
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = chat_completion_with_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user", "content": f"User request: {task}\n\nUse one of the tools. The dataset is loaded."},
        ],
        tools=ANALYSIS_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    if last_tool_output is not None:
        payload = dict(last_tool_output)
        if content and isinstance(content, str) and content.strip():
            payload["message"] = content.strip()
        return json.dumps(payload, default=str)
    return json.dumps({"error": "No tool was called", "message": (content or "Analysis completed.")})
