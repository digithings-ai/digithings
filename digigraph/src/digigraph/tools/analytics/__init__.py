"""Dataset-backed analytics tools for visualization, analysis, and data prep. Polars only.

Tools are grouped by agent:
- visualization/: plots, relationship_graph, mermaid_diagram (visualization_agent)
- analysis/: correlation, regression, stats, aggregations, cluster (analysis_agent)
- data_prep/: prep (data_prep_agent)
- load: shared load_dataset for all.
"""

from __future__ import annotations

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.analysis import (
    cluster_metadata,
    correlation_matrix,
    group_by_summary,
    pivot_table,
    simple_regression,
    summary_stats,
)
from digigraph.tools.analytics.data_prep import export_dataset, filter_dataset, sample_dataset
from digigraph.tools.analytics.visualization import (
    build_relationship_graph,
    entity_co_occurrence,
    generate_mermaid_diagram,
    plot_categorical,
    plot_distribution,
    plot_sankey,
    plot_scatter,
    plot_time_series,
)

__all__ = [
    "load_dataset",
    "plot_distribution",
    "plot_time_series",
    "plot_categorical",
    "plot_scatter",
    "plot_sankey",
    "build_relationship_graph",
    "entity_co_occurrence",
    "generate_mermaid_diagram",
    "correlation_matrix",
    "simple_regression",
    "summary_stats",
    "group_by_summary",
    "pivot_table",
    "cluster_metadata",
    "export_dataset",
    "filter_dataset",
    "sample_dataset",
]
