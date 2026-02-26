"""Analysis tools: correlation, regression, stats, aggregations, clustering. Used by analysis_agent."""

from __future__ import annotations

from digigraph.tools.analytics.analysis.cluster import cluster_metadata
from digigraph.tools.analytics.analysis.correlation import correlation_matrix
from digigraph.tools.analytics.analysis.group_by import group_by_summary
from digigraph.tools.analytics.analysis.pivot_table import pivot_table
from digigraph.tools.analytics.analysis.regression import simple_regression
from digigraph.tools.analytics.analysis.schema import ANALYSIS_AGENT_TOOL
from digigraph.tools.analytics.analysis.stats import summary_stats

__all__ = [
    "correlation_matrix",
    "simple_regression",
    "summary_stats",
    "group_by_summary",
    "pivot_table",
    "cluster_metadata",
    "ANALYSIS_AGENT_TOOL",
]
