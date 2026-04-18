"""Run the visualization sub-agent: LLM + visualization tools with injected dataset_path."""

from __future__ import annotations

import json
import tempfile
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
from digigraph.tools.analytics.visualization.echarts import (
    echarts_bar,
    echarts_from_code,
    echarts_line,
    echarts_pie,
    echarts_scatter,
)
from digigraph.tools.analytics.visualization.echarts.render_svg import echarts_option_to_svg

VIZ_SYSTEM = """You are a visualization specialist. The user has requested a visualization. You have access to a dataset (already loaded). For charts that will be shown in the web UI, prefer ECharts tools (echarts_line, echarts_bar, echarts_scatter, echarts_pie) so the frontend receives echarts_option JSON. Use exactly one of:

ECharts (preferred for web): echarts_line (date_column, value_column?, aggregation), echarts_bar (column, top_n?), echarts_scatter (x_column, y_column, color_by?), echarts_pie (column, top_n?), echarts_from_code (option_spec JSON, column_refs?)
Plot/mermaid: plot_distribution, plot_time_series, plot_categorical, plot_scatter, plot_sankey, build_relationship_graph, entity_co_occurrence, generate_mermaid_diagram

Choose the tool that best matches the user request. Then summarize what you produced in one short sentence."""

VIZ_TOOLS = [
    {"type": "function", "function": {"name": "echarts_line", "description": "ECharts line chart (time series). Returns echarts_option for web.", "parameters": {"type": "object", "properties": {"date_column": {"type": "string"}, "value_column": {"type": "string"}, "aggregation": {"type": "string", "enum": ["count", "sum", "mean"]}, "title": {"type": "string"}}, "required": ["date_column"]}}},
    {"type": "function", "function": {"name": "echarts_bar", "description": "ECharts bar chart. Returns echarts_option for web.", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "top_n": {"type": "integer"}, "title": {"type": "string"}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "echarts_scatter", "description": "ECharts scatter plot. Returns echarts_option for web.", "parameters": {"type": "object", "properties": {"x_column": {"type": "string"}, "y_column": {"type": "string"}, "color_by": {"type": "string"}, "title": {"type": "string"}}, "required": ["x_column", "y_column"]}}},
    {"type": "function", "function": {"name": "echarts_pie", "description": "ECharts pie chart. Returns echarts_option for web.", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "top_n": {"type": "integer"}, "title": {"type": "string"}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "echarts_from_code", "description": "ECharts from JSON option spec; inject dataset columns.", "parameters": {"type": "object", "properties": {"option_spec": {"type": "string"}, "column_refs": {"type": "object"}}, "required": ["option_spec"]}}},
    {"type": "function", "function": {"name": "plot_distribution", "description": "Plot distribution of a column (image).", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "kind": {"type": "string", "enum": ["histogram", "kde", "box"]}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "plot_time_series", "description": "Time series plot by date column (image).", "parameters": {"type": "object", "properties": {"date_column": {"type": "string"}, "value_column": {"type": "string"}, "aggregation": {"type": "string", "enum": ["count", "sum", "mean"]}}, "required": ["date_column"]}}},
    {"type": "function", "function": {"name": "plot_categorical", "description": "Bar or pie chart of categorical column (image).", "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "top_n": {"type": "integer"}, "kind": {"type": "string", "enum": ["bar", "pie"]}}, "required": ["column"]}}},
    {"type": "function", "function": {"name": "plot_scatter", "description": "Scatter plot x vs y (image).", "parameters": {"type": "object", "properties": {"x_column": {"type": "string"}, "y_column": {"type": "string"}, "color_by": {"type": "string"}}, "required": ["x_column", "y_column"]}}},
    {"type": "function", "function": {"name": "plot_sankey", "description": "Sankey diagram (image).", "parameters": {"type": "object", "properties": {"source_column": {"type": "string"}, "target_column": {"type": "string"}, "value_column": {"type": "string"}}, "required": ["source_column", "target_column"]}}},
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
            if name == "echarts_line":
                out = echarts_line(dataset_path, args.get("date_column", ""), args.get("value_column"), args.get("aggregation", "count"), args.get("title"))
            elif name == "echarts_bar":
                out = echarts_bar(dataset_path, args.get("column", ""), args.get("top_n", 20), args.get("title"))
            elif name == "echarts_scatter":
                out = echarts_scatter(dataset_path, args.get("x_column", ""), args.get("y_column", ""), args.get("color_by"), args.get("title"))
            elif name == "echarts_pie":
                out = echarts_pie(dataset_path, args.get("column", ""), args.get("top_n", 15), args.get("title"))
            elif name == "echarts_from_code":
                out = echarts_from_code(dataset_path, args.get("option_spec", "{}"), args.get("column_refs"))
            elif name == "plot_distribution":
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
        if name.startswith("echarts_") and out.get("echarts_option") and not out.get("error"):
            svg = echarts_option_to_svg(out["echarts_option"])
            if svg:
                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="wb") as f:
                    f.write(svg.encode("utf-8"))
                    out["image_path"] = f.name
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
