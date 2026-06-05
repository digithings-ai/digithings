"""Trade PnL chart builders."""

from __future__ import annotations

import math
from typing import Any  # noqa: ANN401 — plotly Figure typing

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _CHART_LAYOUT,
    _apply_layout,
    _extract_frame,
)


def _build_realized_pnl_chart(realized_pnls_series: Any) -> Any:
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(realized_pnls_series)
        if df is None or len(df) == 0:
            return None

        cum = df["value"].cum_sum()
        final = float(cum[-1])
        xs = df["date"].to_list()
        ys = cum.to_list()
        color = "#34d399" if final >= 0 else "#f87171"
        fill_color = "rgba(52,211,153,0.08)" if final >= 0 else "rgba(248,113,113,0.08)"
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name="Cumulative PnL",
                line=dict(color=color, width=2),
                fill="tozeroy",
                fillcolor=fill_color,
            )
        )
        _apply_layout(
            fig,
            height=300,
            yaxis=dict(
                title="PnL ($)",
                tickformat="$,.0f",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
        )
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Realized PnL", str(exc))


def _build_trade_pnl_distribution_chart(realized_pnls_series: Any) -> Any:
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go

        raw = (
            realized_pnls_series.to_pandas()
            if hasattr(realized_pnls_series, "to_pandas")
            else realized_pnls_series
        )
        if hasattr(raw, "values"):
            raw_vals = raw.values.tolist()
        elif hasattr(raw, "tolist"):
            raw_vals = raw.tolist()
        else:
            raw_vals = list(raw)
        vals = []
        for x in raw_vals:
            try:
                fv = float(x)
                if not math.isnan(fv):
                    vals.append(fv)
            except (TypeError, ValueError):
                pass
        if not vals:
            return None
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v <= 0]
        fig = go.Figure()
        if wins:
            fig.add_trace(
                go.Histogram(
                    x=wins,
                    nbinsx=25,
                    marker_color="rgba(52,211,153,0.75)",
                    name="Winners",
                    marker_line_width=0,
                )
            )
        if losses:
            fig.add_trace(
                go.Histogram(
                    x=losses,
                    nbinsx=25,
                    marker_color="rgba(248,113,113,0.75)",
                    name="Losers",
                    marker_line_width=0,
                )
            )
        fig.add_vline(x=0, line=dict(color="rgba(255,255,255,0.25)", width=1.5))
        _apply_layout(
            fig,
            height=280,
            barmode="overlay",
            xaxis=dict(
                title="PnL ($)",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
            yaxis=dict(
                title="Count",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
        )
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Trade PnL Distribution", str(exc))


def _build_per_trade_pnl_bars(realized_pnls_series: Any) -> Any:
    """Bar chart of each trade's realized PnL in chronological order."""
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go

        raw = (
            realized_pnls_series.to_pandas()
            if hasattr(realized_pnls_series, "to_pandas")
            else realized_pnls_series
        )
        if hasattr(raw, "values"):
            raw_vals = raw.values.tolist()
        elif hasattr(raw, "tolist"):
            raw_vals = raw.tolist()
        else:
            raw_vals = list(raw)
        vals = []
        for x in raw_vals:
            try:
                fv = float(x)
                if not math.isnan(fv) and not math.isinf(fv):
                    vals.append(fv)
            except (TypeError, ValueError):
                pass
        if not vals:
            return None
        trade_nums = list(range(1, len(vals) + 1))
        colors = ["#34d399" if v > 0 else "#f87171" for v in vals]
        fig = go.Figure(
            data=[
                go.Bar(
                    x=trade_nums,
                    y=vals,
                    marker_color=colors,
                    marker_line_width=0,
                    name="Trade PnL",
                    hovertemplate="Trade #%{x}<br>PnL: $%{y:,.2f}<extra></extra>",
                )
            ]
        )
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(
            fig,
            height=300,
            xaxis=dict(
                title="Trade #",
                type="linear",  # force linear so integers aren't parsed as dates
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
            yaxis=dict(
                title="PnL ($)",
                tickformat="$,.0f",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
        )
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Per-Trade PnL", str(exc))


def _build_win_rate_donut(win_rate: float | None, num_trades: int) -> Any:
    """Donut chart showing win/loss split."""
    if win_rate is None:
        return None
    try:
        import plotly.graph_objects as go

        wr = max(0.0, min(1.0, win_rate))
        wins = round(wr * num_trades)
        losses = num_trades - wins
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["Winners", "Losers"],
                    values=[wins, losses],
                    hole=0.65,
                    marker=dict(
                        colors=["#34d399", "#f87171"], line=dict(color="rgba(0,0,0,0)", width=0)
                    ),
                    textinfo="none",
                    hovertemplate="%{label}: %{value} trades (%{percent})<extra></extra>",
                )
            ]
        )
        fig.add_annotation(
            text=f"<b>{wr * 100:.1f}%</b><br><span style='font-size:9px;color:#64748b'>WIN RATE</span>",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=18, color="#f1f5f9", family="'IBM Plex Mono', monospace"),
            align="center",
        )
        layout = dict(_CHART_LAYOUT)
        layout.update(
            height=260,
            showlegend=True,
            legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
        )
        fig.update_layout(**layout)
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Win Rate", str(exc))


def _build_cumulative_trade_pnl(realized_pnls_series: Any) -> Any:
    """Step-function cumulative PnL per trade number."""
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go

        raw = (
            realized_pnls_series.to_pandas()
            if hasattr(realized_pnls_series, "to_pandas")
            else realized_pnls_series
        )
        if hasattr(raw, "values"):
            raw_vals = raw.values.tolist()
        elif hasattr(raw, "tolist"):
            raw_vals = raw.tolist()
        else:
            raw_vals = list(raw)
        vals = []
        for x in raw_vals:
            try:
                fv = float(x)
                if not math.isnan(fv) and not math.isinf(fv):
                    vals.append(fv)
            except (TypeError, ValueError):
                pass
        if not vals:
            return None
        cum = []
        running = 0.0
        for v in vals:
            running += v
            cum.append(running)
        color = "#34d399" if cum[-1] >= 0 else "#f87171"
        fill_color = "rgba(52,211,153,0.07)" if cum[-1] >= 0 else "rgba(248,113,113,0.07)"
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=list(range(1, len(cum) + 1)),
                y=cum,
                mode="lines",
                name="Cumulative PnL",
                line=dict(color=color, width=2, shape="hv"),
                fill="tozeroy",
                fillcolor=fill_color,
            )
        )
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(
            fig,
            height=300,
            xaxis=dict(
                title="Trade #",
                type="linear",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
            yaxis=dict(
                title="Cumulative PnL ($)",
                tickformat="$,.0f",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
        )
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Cumulative Trade PnL", str(exc))
