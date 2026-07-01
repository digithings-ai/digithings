"""Equity curve chart builders."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — plotly Figure typing

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _apply_layout,
    _extract_frame,
)


def _build_equity_chart(timestamps: list[str], balances: list[float]) -> Any:
    import plotly.graph_objects as go

    fig = go.Figure()
    # No fill-to-zero: axis must hug the data range so the line is visible
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=balances,
            mode="lines",
            name="Equity",
            line=dict(color="#38bdf8", width=2),
            fill="tonexty",
            fillcolor="rgba(56,189,248,0.06)",
        )
    )
    # Pad range by 2% above/below the actual data range
    if balances:
        lo, hi = min(balances), max(balances)
        pad = (hi - lo) * 0.05 if hi != lo else abs(hi) * 0.02 or 1
        y_range = [lo - pad, hi + pad]
    else:
        y_range = None
    _apply_layout(
        fig,
        height=300,
        yaxis=dict(
            title="Portfolio Value",
            tickformat="$,.0f",
            range=y_range,
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)",
            tickfont=dict(color="#64748b", size=10),
        ),
    )
    return fig


def _build_rolling_equity_chart(returns_series: Any, initial_balance: float = 1_000_000.0) -> Any:
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None

        equity = (1 + df["value"]).cum_prod() * initial_balance
        vals = equity.to_list()
        xs = df["date"].to_list()
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.04 if hi != lo else abs(hi) * 0.02 or 1
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=vals,
                mode="lines",
                name="Daily Equity",
                line=dict(color="#38bdf8", width=2),
            )
        )
        _apply_layout(
            fig,
            height=300,
            yaxis=dict(
                title="Portfolio Value",
                tickformat="$,.0f",
                range=[lo - pad, hi + pad],
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="#64748b", size=10),
            ),
        )
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Rolling Equity", str(exc))
