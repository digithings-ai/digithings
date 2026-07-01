"""Plotly chart builders for DigiQuant backtest tearsheets (SIMP-010)."""

from digiquant.charts.common import ChartUnavailable, section_unavailable_html
from digiquant.charts.drawdown import (
    _build_drawdown_chart,
    _build_rolling_drawdown_chart,
    _build_underwater_from_returns,
)
from digiquant.charts.equity import _build_equity_chart, _build_rolling_equity_chart
from digiquant.charts.price import _build_price_chart_inline
from digiquant.charts.returns import (
    _build_distribution_chart,
    _build_monthly_returns_chart,
    _build_monthly_yearly_combined,
    _build_rolling_calmar,
    _build_rolling_sharpe_chart,
    _build_yearly_returns_chart,
)
from digiquant.charts.trades import (
    _build_cumulative_trade_pnl,
    _build_per_trade_pnl_bars,
    _build_realized_pnl_chart,
    _build_trade_pnl_distribution_chart,
    _build_win_rate_donut,
)

__all__ = [
    "ChartUnavailable",
    "section_unavailable_html",
    "_build_cumulative_trade_pnl",
    "_build_distribution_chart",
    "_build_drawdown_chart",
    "_build_equity_chart",
    "_build_monthly_returns_chart",
    "_build_monthly_yearly_combined",
    "_build_per_trade_pnl_bars",
    "_build_price_chart_inline",
    "_build_realized_pnl_chart",
    "_build_rolling_calmar",
    "_build_rolling_drawdown_chart",
    "_build_rolling_equity_chart",
    "_build_rolling_sharpe_chart",
    "_build_trade_pnl_distribution_chart",
    "_build_underwater_from_returns",
    "_build_win_rate_donut",
    "_build_yearly_returns_chart",
]
