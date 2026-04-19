"""Run the data engineer sub-agent: LLM + execute_python_on_datasets tool."""

from __future__ import annotations

import json
from typing import Any

from digigraph.llm import chat_completion_with_tools, get_model_for_mode
from digigraph.project_config import DigiProjectConfig
from digigraph.run_storage import resolve_dataset_ref
from digigraph.tools.analytics.execute_python import execute_python_on_datasets

ENGINEER_SYSTEM = """You are a data engineer. The user wants to run custom Python code on the dataset(s). You have one tool: execute_python_on_datasets.
- dataset_paths: list of resolved paths (you will receive the primary path; additional refs become df_1, df_2).
- output_name: name for the result dataset.
- code: Python code using Polars (pl). Datasets are in df_0, df_1, ... You must assign the result DataFrame to 'result', e.g. result = df_0.filter(pl.col('x') > 0).
Only use polars, math, datetime. No file I/O, no network. Write clear, short code. Then summarize what you produced."""

ENGINEER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_python_on_datasets",
            "description": "Run Python (Polars) code on datasets. Sets df_0, df_1, ...; code must set 'result' to a Polars DataFrame.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output_name": {
                        "type": "string",
                        "description": "Name for the output dataset.",
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code. Use pl for Polars. Assign result to 'result'.",
                    },
                },
                "required": ["output_name", "code"],
            },
        },
    },
]


def run_data_engineer_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    additional_dataset_refs: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """
    Run the data engineer sub-agent; returns JSON of the tool result (dataset_ref, rows, etc.).
    """
    try:
        path = resolve_dataset_ref(session_id, dataset_ref)
        dataset_paths = [str(path)]
    except Exception as e:
        return json.dumps({"error": str(e)})

    for ref in additional_dataset_refs or []:
        try:
            dataset_paths.append(str(resolve_dataset_ref(session_id, ref)))
        except Exception:
            pass

    timeout_s = DigiProjectConfig.load().get_limits().data_engineer_timeout_s

    last_tool_output: dict[str, Any] | None = None

    def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_tool_output
        args = dict(args or {})
        if name != "execute_python_on_datasets":
            last_tool_output = {"error": f"Unknown tool: {name}"}
            return {"content": json.dumps(last_tool_output)}
        out = execute_python_on_datasets(
            dataset_paths,
            session_id,
            args.get("output_name") or "engineered",
            args.get("code") or "",
            timeout_seconds=timeout_s,
        )
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = chat_completion_with_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": ENGINEER_SYSTEM},
            {
                "role": "user",
                "content": f"User request: {task}\n\nWrite code to produce the result. The dataset(s) are loaded as df_0, df_1, ...",
            },
        ],
        tools=ENGINEER_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    if last_tool_output is not None:
        payload = dict(last_tool_output)
        if content and isinstance(content, str) and content.strip():
            payload["message"] = content.strip()
        return json.dumps(payload, default=str)
    return json.dumps(
        {"error": "No tool was called", "message": (content or "Data engineer completed.")}
    )
