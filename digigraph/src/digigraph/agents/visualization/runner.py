"""Run the visualization sub-agent: LLM + visualization tools with injected dataset_path."""

from __future__ import annotations

import json
from typing import Any

from digigraph.llm import chat_completion_with_tools, get_model_for_mode
from digigraph.run_storage import resolve_dataset_ref
from digigraph.tools.analytics import (
    build_relationship_graph,
    entity_co_occurrence,
    generate_mermaid_diagram,
    plot_categorical,
    plot_distribution,
    plot_sankey,
    plot_scatter,
    plot_time_series,
)

VIZ_SYSTEM = """You are a visualization specialist. The user has requested a visualization. You have access to a dataset (already loaded). Use exactly one of the following tools with the correct parameters:
- plot_distribution: column (required), kind (histogram | kde | box)
- plot_time_series: date_column (required), value_column (optional), aggregation (count | sum | mean)
- plot_categorical: column (required), top_n (optional, default 10), kind (bar | pie)
- plot_scatter: x_column (required), y_column (required), color_by (optional)
- plot_sankey: source_column (required), target_column (required), value_column (optional flow size)
- build_relationship_graph: source_column (required), target_column (required), weight_column (optional)
- entity_co_occurrence: entity_columns (required, list of 1 or 2 column names), min_count (optional)
- generate_mermaid_diagram: diagram_type (flowchart | sequence | graph | er | gantt), source_column, target_column (for graph/flowchart)

Choose the tool that best matches the user request. Then summarize what you produced in one short sentence."""

VIZ_TOOLS = [
    {"type": "function", "function": {"name": "plot_distribution", "description": "Plot distribution of a column.", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "kind": {"type": "string", "enum": ["histogram", "kde", "box"]}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "plot_time_series", "description": "Time series plot by date column.", "parameters": {"type": "object", "properties": {"date_column": {"type": "string"}, "value_column": {"type": "string"}, "aggregation": {"type": "string", "enum": ["count", "sum", "mean"]}}, "required": ["date_column"]}}},
    {"type": "function", "function": {"name": "plot_categorical", "description": "Bar or pie chart of categorical column.", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "top_n": {"type": "integer"}, "kind": {"type": "string", "enum": ["bar", "pie"]}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "plot_scatter", "description": "Scatter plot x vs y.", "parameters": {"type": "object", "properties": {"x_column": {"type": "string"}, "y_column": {"type": "string"}, "color_by": {"type": "string"}}, "required": ["x_column", "y_column"]}}},
    {"type": "function", "function": {"name": "plot_sankey", "description": "Sankey diagram of flows from source to target column; optional value column for flow size.", "parameters": {"type": "object", "properties": {"source_column": {"type": "string"}, "target_column": {"type": "string"}, "value_column": {"type": "string"}}, "required": ["source_column", "target_column"]}}},
    {"type": "function", "function": {"name": "build_relationship_graph", "description": "Build graph from source to target column.", "parameters": {"type": "object", "properties": {"source_column": {"type": "string"}, "target_column": {"type": "string"}, "weight_column": {"type": "string"}}, "required": ["source_column", "target_column"]}}},
    {"type": "function", "function": {"name": "entity_co_occurrence", "description": "Co-occurrence counts for entity columns.", "parameters": {"type": "object", "properties": {"entity_columns": {"type": "array", "items": {"type": "string"}}, "min_count": {"type": "integer"}}, "required": ["entity_columns"]}}},
    {"type": "function", "function": {"name": "generate_mermaid_diagram", "description": "Generate Mermaid diagram source.", "parameters": {"type": "object", "properties": {"diagram_type": {"type": "string", "enum": ["flowchart", "sequence", "graph", "er", "gantt"]}, "source_column": {"type": "string"}, "target_column": {"type": "string"}}, "required": ["diagram_type"]}}},
]


def run_visualization_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """
    Run the visualization sub-agent: resolve dataset_ref, then LLM + tools loop.
    Returns JSON string of the last tool result (image_path, mermaid_source, etc.) so the
    Open WebUI formatter can render the visual; optionally includes "message" with the LLM summary.
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
            if name == "plot_distribution":
                out = plot_distribution(dataset_path, args.get("column", ""), args.get("kind", "histogram"))
            elif name == "plot_time_series":
                out = plot_time_series(dataset_path, args.get("date_column", ""), args.get("value_column"), args.get("aggregation", "count"))
            elif name == "plot_categorical":
                out = plot_categorical(dataset_path, args.get("column", ""), args.get("top_n", 10), args.get("kind", "bar"))
            elif name == "plot_scatter":
                out = plot_scatter(dataset_path, args.get("x_column", ""), args.get("y_column", ""), args.get("color_by"))
            elif name == "plot_sankey":
                out = plot_sankey(dataset_path, args.get("source_column", ""), args.get("target_column", ""), args.get("value_column"))
            elif name == "build_relationship_graph":
                out = build_relationship_graph(dataset_path, args.get("source_column", ""), args.get("target_column", ""), args.get("weight_column"), include_mermaid=True)
            elif name == "entity_co_occurrence":
                out = entity_co_occurrence(dataset_path, args.get("entity_columns") or [], args.get("min_count", 1), include_mermaid=True)
            elif name == "generate_mermaid_diagram":
                out = generate_mermaid_diagram(dataset_path, args.get("diagram_type", "graph"), args.get("source_column"), args.get("target_column"), args.get("label_column"))
            else:
                out = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            out = {"error": str(e)}
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = chat_completion_with_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": VIZ_SYSTEM},
            {"role": "user", "content": f"User request: {task}\n\nUse one of the tools to produce the visualization. The dataset is loaded."},
        ],
        tools=VIZ_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    # Return the tool output JSON so the Open WebUI formatter can render image_path / mermaid_source
    if last_tool_output is not None:
        payload = dict(last_tool_output)
        if content and isinstance(content, str) and content.strip():
            payload["message"] = content.strip()
        return json.dumps(payload, default=str)
    return json.dumps({"error": "No tool was called", "message": (content or "Visualization completed.")})
