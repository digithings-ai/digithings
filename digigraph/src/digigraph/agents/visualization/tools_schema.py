"""OpenAI tool schemas for the visualization sub-agent."""

from __future__ import annotations

VIZ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "echarts_line",
            "description": "ECharts line chart (time series). Returns echarts_option for web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_column": {"type": "string"},
                    "value_column": {"type": "string"},
                    "aggregation": {"type": "string", "enum": ["count", "sum", "mean"]},
                    "title": {"type": "string"},
                },
                "required": ["date_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echarts_bar",
            "description": "ECharts bar chart. Returns echarts_option for web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "top_n": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echarts_scatter",
            "description": "ECharts scatter plot. Returns echarts_option for web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "color_by": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["x_column", "y_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echarts_pie",
            "description": "ECharts pie chart. Returns echarts_option for web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "top_n": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echarts_from_code",
            "description": "ECharts from JSON option spec; inject dataset columns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "option_spec": {"type": "string"},
                    "column_refs": {"type": "object"},
                },
                "required": ["option_spec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_distribution",
            "description": "Plot distribution of a column (image).",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "kind": {"type": "string", "enum": ["histogram", "kde", "box"]},
                },
                "required": ["column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_time_series",
            "description": "Time series plot by date column (image).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_column": {"type": "string"},
                    "value_column": {"type": "string"},
                    "aggregation": {"type": "string", "enum": ["count", "sum", "mean"]},
                },
                "required": ["date_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_categorical",
            "description": "Bar or pie chart of categorical column (image).",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "top_n": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["bar", "pie"]},
                },
                "required": ["column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_scatter",
            "description": "Scatter plot x vs y (image).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "color_by": {"type": "string"},
                },
                "required": ["x_column", "y_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_sankey",
            "description": "Sankey diagram (image).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_column": {"type": "string"},
                    "target_column": {"type": "string"},
                    "value_column": {"type": "string"},
                },
                "required": ["source_column", "target_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_relationship_graph",
            "description": "Build graph from source to target column.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_column": {"type": "string"},
                    "target_column": {"type": "string"},
                    "weight_column": {"type": "string"},
                },
                "required": ["source_column", "target_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "entity_co_occurrence",
            "description": "Co-occurrence counts for entity columns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_columns": {"type": "array", "items": {"type": "string"}},
                    "min_count": {"type": "integer"},
                },
                "required": ["entity_columns"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mermaid_diagram",
            "description": "Generate Mermaid diagram source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagram_type": {
                        "type": "string",
                        "enum": ["flowchart", "sequence", "graph", "er", "gantt"],
                    },
                    "source_column": {"type": "string"},
                    "target_column": {"type": "string"},
                },
                "required": ["diagram_type"],
            },
        },
    },
]
