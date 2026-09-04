# score:allow pandas
"""
digiquant Backtest Tearsheet — Premium Edition.
Modern trading-terminal aesthetic, tabbed, exportable HTML.
Requires: digiquant[visualization] (plotly).

Focused helpers live in sibling modules (#1185):
``tearsheet_extract``, ``tearsheet_stats``, ``tearsheet_page``.
JSON payloads for digiquant.io remain in ``tearsheet_data``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any  # score:allow untyped any — tearsheet HTML assembly

from digiquant.charts import (
    ChartUnavailable,
    _build_cumulative_trade_pnl,
    _build_distribution_chart,
    _build_drawdown_chart,
    _build_equity_chart,
    _build_monthly_returns_chart,
    _build_monthly_yearly_combined,
    _build_per_trade_pnl_bars,
    _build_price_chart_inline,
    _build_realized_pnl_chart,
    _build_rolling_calmar,
    _build_rolling_drawdown_chart,
    _build_rolling_equity_chart,
    _build_rolling_sharpe_chart,
    _build_trade_pnl_distribution_chart,
    _build_underwater_from_returns,
    _build_win_rate_donut,
    _build_yearly_returns_chart,
    section_unavailable_html,
)
from digiquant.models import BacktestResult
from digiquant.tearsheet_extract import (
    _compute_drawdown,
    _extract_equity_curve,
    _extract_fill_markers,
    _load_logo_base64,
)
from digiquant.tearsheet_page import _build_page
from digiquant.tearsheet_stats import (
    _build_categorized_stats,
    _build_full_stats_table,
    _build_risk_metrics_table,
)

logger = logging.getLogger(__name__)


def create_tearsheet(
    result: BacktestResult,
    output_path: str | Path,
    *,
    strategy_params: dict[str, float | int | str] | None = None,
    account_report: Any = None,
    fills_report: Any = None,
    ohlcv_df: Any = None,
    symbol: str = "",
    stats_returns: dict | None = None,
    stats_pnls: dict | None = None,
    stats_general: dict | None = None,
    returns_series: Any = None,
    realized_pnls_series: Any = None,
    full: bool = True,
) -> Path:
    try:
        import plotly.graph_objects as go
    except ImportError as e:
        raise ImportError("Tearsheet requires plotly. pip install digiquant[visualization]") from e

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    timestamps, balances = _extract_equity_curve(account_report)
    drawdown_pct = _compute_drawdown(balances) if balances else []
    fill_ts, fill_px, fill_sides = _extract_fill_markers(fills_report)

    strategy_display = result.strategy_name.replace("_", " ").title()
    for acr in ("Mr", "Rsi", "Macd"):
        strategy_display = strategy_display.replace(acr, acr.upper())
    symbols_str = ", ".join(result.symbols) if result.symbols else "—"
    params_str = ", ".join(f"{k}={v}" for k, v in (strategy_params or {}).items()) or "—"
    params = strategy_params or {}
    period = int(params.get("period", 20))
    std_dev = float(params.get("std_dev", 2.0))

    # Extract key derived stats for KPI strip
    pnl_d = stats_pnls or {}
    if isinstance(pnl_d, dict) and any(isinstance(v, dict) for v in pnl_d.values()):
        pnl_d = pnl_d.get("USD", pnl_d) if "USD" in pnl_d else next(iter(pnl_d.values()), {})
    ret_d = stats_returns or {}
    gen_d = stats_general or {}
    combined_stats = {**pnl_d, **ret_d, **gen_d}

    def _gs(key: str) -> float | None:
        v = combined_stats.get(key)
        if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
            return float(v)
        return None

    win_rate = _gs("Win Rate")
    profit_factor = _gs("Profit Factor")
    sortino = _gs("Sortino Ratio (252 days)")
    calmar = _gs("Calmar Ratio")

    def _fig_to_html(
        fig: Any, div_id: str, include_plotlyjs: bool | str = False, fallback: str = ""
    ) -> str:
        if isinstance(fig, ChartUnavailable):
            return section_unavailable_html(fig.title, fig.detail)
        if fig is None:
            return fallback
        return fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs, div_id=div_id)

    initial_balance = 1_000_000.0

    # Build core figures (always)
    equity_fig = _build_equity_chart(timestamps, balances) if timestamps else None
    dd_fig = _build_drawdown_chart(timestamps, drawdown_pct) if drawdown_pct else None
    price_fig = _build_price_chart_inline(
        ohlcv_df, symbol, period, std_dev, fill_ts, fill_px, fill_sides
    )
    win_rate_donut_fig = _build_win_rate_donut(win_rate, result.num_trades)
    realized_pnl_fig = _build_realized_pnl_chart(realized_pnls_series)
    per_trade_pnl_fig = _build_per_trade_pnl_bars(realized_pnls_series)
    cum_trade_pnl_fig = _build_cumulative_trade_pnl(realized_pnls_series)
    # Build extended figures only when full=True
    monthly_fig = _build_monthly_returns_chart(returns_series) if full else None
    dist_fig = _build_distribution_chart(returns_series) if full else None
    rolling_fig = _build_rolling_sharpe_chart(returns_series) if full else None
    yearly_fig = _build_yearly_returns_chart(returns_series) if full else None
    rolling_equity_fig = (
        _build_rolling_equity_chart(returns_series, initial_balance) if full else None
    )
    trade_pnl_dist_fig = _build_trade_pnl_distribution_chart(realized_pnls_series) if full else None
    rolling_dd_fig = _build_rolling_drawdown_chart(returns_series) if full else None
    monthly_yearly_fig = _build_monthly_yearly_combined(returns_series) if full else None
    rolling_calmar_fig = _build_rolling_calmar(returns_series) if full else None
    underwater_fig = _build_underwater_from_returns(returns_series) if full else None

    # Convert to HTML
    def fh(
        fig: Any, div_id: str, fallback: str = "<p class='no-data'>No data available.</p>"
    ) -> str:
        return _fig_to_html(fig, div_id, fallback=fallback)

    price_gen = _fig_to_html(
        price_fig,
        "price-gen",
        include_plotlyjs="cdn",
        fallback="<p class='no-data'>No price data.</p>",
    )
    price_tab = fh(price_fig, "price-tab")
    equity_gen = fh(equity_fig, "equity-gen")
    equity_tab = fh(equity_fig, "equity-tab")
    dd_gen = fh(dd_fig, "dd-gen")
    dd_tab = fh(dd_fig, "dd-tab")
    monthly_gen = fh(monthly_fig, "monthly-gen")
    dist_gen = fh(dist_fig, "dist-gen")
    rolling_gen = fh(rolling_fig, "rolling-gen")
    yearly_gen = fh(yearly_fig, "yearly-gen")
    rolling_equity_html = fh(rolling_equity_fig, "rolling-equity")
    realized_pnl_html = fh(realized_pnl_fig, "realized-pnl")
    trade_pnl_dist_html = fh(trade_pnl_dist_fig, "trade-pnl-dist-risk")
    # Build a second identical figure for the Trades tab with a different div ID
    trade_pnl_dist_trades_html = fh(trade_pnl_dist_fig, "trade-pnl-dist-trades")
    rolling_dd_html = fh(rolling_dd_fig, "rolling-dd")
    monthly_yearly_html = fh(monthly_yearly_fig, "monthly-yearly")
    dist_tab = fh(dist_fig, "dist-tab")
    rolling_tab = fh(rolling_fig, "rolling-tab")
    per_trade_pnl_html = fh(per_trade_pnl_fig, "per-trade-pnl")
    win_rate_donut_html = fh(win_rate_donut_fig, "win-rate-donut")
    rolling_calmar_html = fh(rolling_calmar_fig, "rolling-calmar")
    cum_trade_pnl_html = fh(cum_trade_pnl_fig, "cum-trade-pnl")
    underwater_html = fh(underwater_fig, "underwater")

    full_stats_html = _build_full_stats_table(stats_returns, stats_pnls, stats_general, result)
    risk_metrics_html = _build_risk_metrics_table(stats_pnls, stats_returns, result)
    categorized_stats_html = _build_categorized_stats(
        stats_returns, stats_pnls, stats_general, result
    )
    logo_data_url = _load_logo_base64()

    html = _build_page(
        result=result,
        strategy_display=strategy_display,
        symbols_str=symbols_str,
        params_str=params_str,
        win_rate=win_rate,
        profit_factor=profit_factor,
        sortino=sortino,
        calmar=calmar,
        price_gen=price_gen,
        price_tab=price_tab,
        equity_gen=equity_gen,
        equity_tab=equity_tab,
        dd_gen=dd_gen,
        dd_tab=dd_tab,
        monthly_gen=monthly_gen,
        dist_gen=dist_gen,
        dist_tab=dist_tab,
        rolling_gen=rolling_gen,
        rolling_tab=rolling_tab,
        yearly_gen=yearly_gen,
        rolling_equity_html=rolling_equity_html,
        realized_pnl_html=realized_pnl_html,
        trade_pnl_dist_html=trade_pnl_dist_html,
        trade_pnl_dist_trades_html=trade_pnl_dist_trades_html,
        rolling_dd_html=rolling_dd_html,
        monthly_yearly_html=monthly_yearly_html,
        per_trade_pnl_html=per_trade_pnl_html,
        win_rate_donut_html=win_rate_donut_html,
        rolling_calmar_html=rolling_calmar_html,
        cum_trade_pnl_html=cum_trade_pnl_html,
        underwater_html=underwater_html,
        full_stats_html=full_stats_html,
        risk_metrics_html=risk_metrics_html,
        categorized_stats_html=categorized_stats_html,
        logo_data_url=logo_data_url,
    )
    out.write_text(html, encoding="utf-8")
    return out
