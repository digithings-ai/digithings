"""Run the visualization sub-agent: LLM + visualization tools with injected dataset_path."""

from __future__ import annotations

import json
import tempfile
from typing import Any

from digigraph.agents._common import finalize_agent_output, load_dataset_path, run_tool_safe
from digigraph.agents.visualization.tools_schema import VIZ_TOOLS
from digigraph.llm_client import run_tools
from digigraph.model_config import get_model_for_mode
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


def run_visualization_agent(
    dataset_ref: str,
    task: str,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Run the visualization sub-agent; returns JSON of the last tool result."""
    dataset_path, err = load_dataset_path(session_id, dataset_ref)
    if err is not None:
        return err

    last_tool_output: dict[str, Any] | None = None

    def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_tool_output
        args = dict(args or {})

        def _run() -> dict[str, Any]:
            if name == "echarts_line":
                return echarts_line(
                    dataset_path,
                    args.get("date_column", ""),
                    args.get("value_column"),
                    args.get("aggregation", "count"),
                    args.get("title"),
                )
            if name == "echarts_bar":
                return echarts_bar(
                    dataset_path, args.get("column", ""), args.get("top_n", 20), args.get("title")
                )
            if name == "echarts_scatter":
                return echarts_scatter(
                    dataset_path,
                    args.get("x_column", ""),
                    args.get("y_column", ""),
                    args.get("color_by"),
                    args.get("title"),
                )
            if name == "echarts_pie":
                return echarts_pie(
                    dataset_path, args.get("column", ""), args.get("top_n", 15), args.get("title")
                )
            if name == "echarts_from_code":
                return echarts_from_code(
                    dataset_path, args.get("option_spec", "{}"), args.get("column_refs")
                )
            if name == "plot_distribution":
                return plot_distribution(
                    dataset_path, args.get("column", ""), args.get("kind", "histogram")
                )
            if name == "plot_time_series":
                return plot_time_series(
                    dataset_path,
                    args.get("date_column", ""),
                    args.get("value_column"),
                    args.get("aggregation", "count"),
                )
            if name == "plot_categorical":
                return plot_categorical(
                    dataset_path,
                    args.get("column", ""),
                    args.get("top_n", 10),
                    args.get("kind", "bar"),
                )
            if name == "plot_scatter":
                return plot_scatter(
                    dataset_path,
                    args.get("x_column", ""),
                    args.get("y_column", ""),
                    args.get("color_by"),
                )
            if name == "plot_sankey":
                return plot_sankey(
                    dataset_path,
                    args.get("source_column", ""),
                    args.get("target_column", ""),
                    args.get("value_column"),
                )
            if name == "build_relationship_graph":
                return build_relationship_graph(
                    dataset_path,
                    args.get("source_column", ""),
                    args.get("target_column", ""),
                    args.get("weight_column"),
                    include_mermaid=True,
                )
            if name == "entity_co_occurrence":
                return entity_co_occurrence(
                    dataset_path,
                    args.get("entity_columns") or [],
                    args.get("min_count", 1),
                    include_mermaid=True,
                )
            if name == "generate_mermaid_diagram":
                return generate_mermaid_diagram(
                    dataset_path,
                    args.get("diagram_type", "graph"),
                    args.get("source_column"),
                    args.get("target_column"),
                    args.get("label_column"),
                )
            return {"error": f"Unknown tool: {name}"}

        out = run_tool_safe(_run)
        if name.startswith("echarts_") and out.get("echarts_option") and not out.get("error"):
            svg = echarts_option_to_svg(out["echarts_option"])
            if svg:
                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="wb") as f:
                    f.write(svg.encode("utf-8"))
                    out["image_path"] = f.name
        last_tool_output = out
        return {"content": json.dumps(out, default=str)}

    content = run_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": VIZ_SYSTEM},
            {
                "role": "user",
                "content": f"User request: {task}\n\nUse one of the tools to produce the visualization. The dataset is loaded.",
            },
        ],
        tools=VIZ_TOOLS,
        execute_tool=execute_tool,
        on_tool_step=None,
    )

    return finalize_agent_output(
        last_tool_output,
        content,
        no_tool_error="No tool was called",
        fallback_message="Visualization completed.",
    )
