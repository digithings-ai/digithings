"""Drawdown and underwater chart builders."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — plotly Figure typing

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _apply_layout,
    _extract_frame,
)


def _build_drawdown_chart(timestamps: list[str], drawdown_pct: list[float]) -> Any:
    """Show each distinct drawdown period as a bar to make individual events readable."""
    import plotly.graph_objects as go

    if not timestamps or not drawdown_pct:
        return None

    # Identify drawdown events: label each contiguous trough period
    # Show every point as a bar — with many points this renders like an area chart
    # but remains a bar chart semantically (bin each bar by period).
    # For readability, downsample to at most 500 bars if data is dense.
    n = len(drawdown_pct)
    if n > 500:
        step = n // 500
        ts_d = timestamps[::step]
        dd_d = drawdown_pct[::step]
    else:
        ts_d = timestamps
        dd_d = drawdown_pct

    colors = [
        "#dc2626"
        if v < -15
        else "#f87171"
        if v < -5
        else "#fca5a5"
        if v < 0
        else "rgba(100,116,139,0.3)"
        for v in dd_d
    ]
    fig = go.Figure(
        data=[
            go.Bar(
                x=ts_d,
                y=dd_d,
                marker_color=colors,
                marker_line_width=0,
                name="Drawdown",
                hovertemplate="%{x}<br>Drawdown: %{y:.2f}%<extra></extra>",
            )
        ]
    )
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
    _apply_layout(
        fig,
        height=220,
        yaxis=dict(
            title="Drawdown %",
            tickformat=".1f",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)",
            tickfont=dict(color="#64748b", size=10),
        ),
        bargap=0,
    )
    return fig


def _build_rolling_drawdown_chart(returns_series: Any, window: int = 60) -> Any:
    """Rolling max drawdown: worst peak-to-trough in each rolling window."""
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None:
            return None

        effective_window = min(window, max(10, len(df) // 3))
        if len(df) < effective_window:
            return None

        # Compute full underwater (drawdown) series first.
        cum = (1 + df["value"]).cum_prod()
        rolling_peak = cum.cum_max()
        underwater = (cum - rolling_peak) / rolling_peak * 100  # always <= 0

        # Rolling worst drawdown = minimum of underwater in each window.
        roll_max_dd = underwater.rolling_min(
            window_size=effective_window, min_periods=effective_window // 2
        )

        # Pair with dates, drop nulls from the leading window.
        pairs = [
            (d, float(v))
            for d, v in zip(df["date"].to_list(), roll_max_dd.to_list())
            if v is not None
        ]
        if not pairs:
            return None

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name=f"Rolling Max DD ({effective_window}d)",
                line=dict(color="#f87171", width=2),
                fill="tozeroy",
                fillcolor="rgba(248,113,113,0.12)",
            )
        )
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(fig, height=280, yaxis_title="Drawdown %")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Rolling Drawdown", str(exc))


def _build_underwater_from_returns(returns_series: Any) -> Any:
    """Underwater equity plot from returns series."""
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None

        cum = (1 + df["value"]).cum_prod()
        rolling_max = cum.cum_max().clip(lower_bound=1e-10)
        underwater = (cum - rolling_max) / rolling_max * 100

        xs = df["date"].to_list()
        ys = underwater.to_list()

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="tozeroy",
                name="Underwater %",
                line=dict(color="#f87171", width=1.5),
                fillcolor="rgba(248,113,113,0.15)",
            )
        )
        _apply_layout(fig, height=220, yaxis_title="Underwater %")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Underwater Equity", str(exc))
