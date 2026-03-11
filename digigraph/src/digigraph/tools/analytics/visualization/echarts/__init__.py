"""ECharts builders: return echarts_option JSON for frontend rendering."""

from __future__ import annotations

from digigraph.tools.analytics.visualization.echarts.bar import echarts_bar
from digigraph.tools.analytics.visualization.echarts.line import echarts_line
from digigraph.tools.analytics.visualization.echarts.pie import echarts_pie
from digigraph.tools.analytics.visualization.echarts.scatter import echarts_scatter
from digigraph.tools.analytics.visualization.echarts.from_code import echarts_from_code

__all__ = [
    "echarts_line",
    "echarts_bar",
    "echarts_scatter",
    "echarts_pie",
    "echarts_from_code",
]
