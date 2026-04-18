"""Run the data manipulation sub-agent: LLM + transform, round, group, merge, append tools."""

from __future__ import annotations

import json
from typing import Any

from digigraph.llm import chat_completion_with_tools, get_model_for_mode
from digigraph.run_storage import resolve_dataset_ref
from digigraph.tools.analytics.data_manipulation import (
    append_datasets,
    group_and_aggregate,
    merge_datasets,
    round_column,
    transform_columns,
)

MANIPULATION_SYSTEM = """You are a data manipulation specialist. The user wants to transform the dataset. Use exactly one of:
- transform_columns: column_ops (list of {output_col: expression}, e.g. [{"total": "a + b"}, {"doubled": "x * 2"}]), output_name (required). Expressions: col_a + col_b, col * 2, log(col), sqrt(col), exp(col).
- round_column: column (required), decimals (default 2), output_name (required).
- group_and_aggregate: group_by_columns (list), agg_columns (list of {col, agg} with agg in sum|mean|count|min|max), output_name (required).
- merge_datasets: second_dataset_ref (required; the other dataset is already loaded as dataset_2), left_on (column or list), right_on (optional), how (inner|left|outer), output_name (required).
- append_datasets: second_dataset_ref (required), output_name (required).

Always provide output_name. The dataset is loaded; for merge/append you must provide second_dataset_ref (path or name of the second dataset). Then summarize the result in one short sentence."""

MANIPULATION_TOOLS = [
    {"type": "function", "function": {"name": "transform_columns", "description": "Add or transform columns with expressions.", "parameters": {"type": "object", "properties": {"output_name": {"type": "string"}, "column_ops": {"type": "array", "items": {"type": "object"}}}, "required": ["output_name"]}}},
    {"type": "function", "function": {"name": "round_column", "description": "Round a numeric column.", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "decimals": {"type": "integer"}, "output_name": {"type": "string"}}, "required": ["column", "output_name"]}}},
    {"type": "function", "function": {"name": "group_and_aggregate", "description": "Group by columns and aggregate.", "parameters": {"type": "object", "properties": {"group_by_columns": {"type": "array", "items": {"type": "string"}}, "agg_columns": {"type": "array", "items": {"type": "object", "properties": {"col": {"type": "string"}, "agg": {"type": "string"}}}}, "output_name": {"type": "string"}}, "required": ["group_by_columns", "output_name"]}}},
    {"type": "function", "function": {"name": "merge_datasets", "description": "Join with another dataset.", "parameters": {"type": "object", "properties": {"second_dataset_ref": {"type": "string"}, "left_on": {"type": "string"}, "right_on": {"type": "string"}, "how": {"type": "string", "enum": ["inner", "left", "outer"]}, "output_name": {"type": "string"}}, "required": ["second_dataset_ref", "output_name"]}}},
    {"type": "function", "function": {"name": "append_datasets", "description": "Append rows from another dataset.", "parameters": {"type": "object", "properties": {"second_dataset_ref": {"type": "string"}, "output_name": {"type": "string"}}, "required": ["second_dataset_ref", "output_name"]}}},
]


def run_data_manipulation_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    second_dataset_ref: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """
    Run the data manipulation sub-agent; returns JSON of the last tool result (dataset_ref, rows, etc.).
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
        out_name = args.get("output_name") or "result"
        second_path: str | None = None
        ref_2 = args.get("second_dataset_ref") or second_dataset_ref
        if ref_2:
            try:
                second_path = str(resolve_dataset_ref(session_id, ref_2))
            except Exception:
                pass
        try:
            if name == "transform_columns":
                out = transform_columns(dataset_path, session_id, out_name, args.get("column_ops") or [])
            elif name == "round_column":
                out = round_column(dataset_path, session_id, out_name, args.get("column", ""), args.get("decimals", 2))
            elif name == "group_and_aggregate":
                out = group_and_aggregate(
                    dataset_path,
                    session_id,
                    out_name,
                    args.get("group_by_columns") or [],
                    args.get("agg_columns"),
                )
            elif name == "merge_datasets":
                if not second_path:
                    out = {"error": "second_dataset_ref required for merge"}
                else:
                    out = merge_datasets(
                        dataset_path,
                        second_path,
                        session_id,
                        out_name,
                        args.get("left_on", ""),
                        args.get("right_on"),
                        args.get("how", "inner"),
                    )
            elif name == "append_datasets":
                if not second_path:
                    out = {"error": "second_dataset_ref required for append"}
                else:
                    out = append_datasets(dataset_path, second_path, session_id, out_name)
            else:
                out = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            out = {"error": str(e)}
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    user_msg = f"User request: {task}\n\nUse one of the tools. The dataset is loaded."
    if second_dataset_ref:
        user_msg += f"\nSecond dataset ref: {second_dataset_ref}"
    content = chat_completion_with_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": MANIPULATION_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        tools=MANIPULATION_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    if last_tool_output is not None:
        payload = dict(last_tool_output)
        if content and isinstance(content, str) and content.strip():
            payload["message"] = content.strip()
        return json.dumps(payload, default=str)
    return json.dumps({"error": "No tool was called", "message": (content or "Data manipulation completed.")})
