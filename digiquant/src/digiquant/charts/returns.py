"""Return distribution and rolling metric chart builders."""

from __future__ import annotations

import math
from typing import Any  # noqa: ANN401 — plotly Figure typing

import polars as pl

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _CHART_LAYOUT,
    _apply_layout,
    _extract_frame,
)


def _build_distribution_chart(returns_series: Any) -> Any:
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None
        vals = (df["value"] * 100).to_list()
        if not vals:
            return None
        mean_val = sum(vals) / len(vals)
        fig = go.Figure(
            data=[
                go.Histogram(
                    x=vals,
                    nbinsx=40,
                    marker=dict(
                        color="#38bdf8",
                        opacity=0.8,
                        line=dict(color="rgba(56,189,248,0.3)", width=0.5),
                    ),
                    name="Returns",
                )
            ]
        )
        fig.add_vline(
            x=mean_val,
            line=dict(color="#fbbf24", width=1.5, dash="dash"),
            annotation_text=f"μ={mean_val:.2f}%",
            annotation_font_color="#fbbf24",
            annotation_font_size=10,
        )
        fig.add_vline(x=0, line=dict(color="rgba(255,255,255,0.2)", width=1))
        _apply_layout(fig, height=280, xaxis_title="Return %", yaxis_title="Count")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Return Distribution", str(exc))


def _build_monthly_returns_chart(returns_series: Any) -> Any:
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None

        # Parse dates — drop rows where the date column isn't a valid ISO date.
        df = df.with_columns(
            pl.col("date").str.to_date("%Y-%m-%d", strict=False).alias("date_obj")
        ).filter(pl.col("date_obj").is_not_null())
        if len(df) == 0:
            return None

        df = df.with_columns(
            pl.col("date_obj").dt.year().alias("year"),
            pl.col("date_obj").dt.month().alias("month"),
        )
        monthly = (
            df.group_by(["year", "month"])
            .agg((pl.col("value").sum() * 100).alias("ret_pct"))
            .sort(["year", "month"])
        )
        pivot = monthly.pivot(
            index="year", on="month", values="ret_pct", aggregate_function="first"
        )
        # Ensure all 12 month columns exist.
        for m in range(1, 13):
            col = str(m)
            if col not in pivot.columns:
                pivot = pivot.with_columns(pl.lit(0.0).alias(col))
        pivot = pivot.select(["year"] + [str(m) for m in range(1, 13)]).fill_null(0.0)
        if len(pivot) == 0:
            return None

        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        z_matrix = [[pivot[str(m)][i] for m in range(1, 13)] for i in range(len(pivot))]
        text_vals = [[f"{z_matrix[i][j]:.1f}%" for j in range(12)] for i in range(len(pivot))]
        y_labels = [str(y) for y in pivot["year"].to_list()]

        fig = go.Figure(
            data=go.Heatmap(
                z=z_matrix,
                x=month_names,
                y=y_labels,
                text=text_vals,
                texttemplate="%{text}",
                colorscale=[
                    [0, "#7f1d1d"],
                    [0.35, "#991b1b"],
                    [0.5, "#1e293b"],
                    [0.65, "#14532d"],
                    [1, "#15803d"],
                ],
                zmid=0,
                showscale=False,
                hovertemplate="<b>%{y} %{x}</b><br>Return: %{z:.2f}%<extra></extra>",
            )
        )
        _apply_layout(fig, height=200)
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Monthly Returns", str(exc))


def _build_rolling_sharpe_chart(returns_series: Any) -> Any:
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) < 20:
            return None
        window = min(60, len(df) // 2)
        min_p = max(10, window // 3)
        df = (
            df.with_columns(
                pl.col("value")
                .rolling_mean(window_size=window, min_periods=min_p)
                .alias("roll_mean"),
                pl.col("value")
                .rolling_std(window_size=window, min_periods=min_p)
                .alias("roll_std"),
            )
            .with_columns(
                (pl.col("roll_mean") / pl.col("roll_std").clip(lower_bound=1e-10) * (252**0.5))
                .fill_null(0.0)
                .alias("sharpe")
            )
            .filter(pl.col("roll_mean").is_not_null())
        )

        if len(df) == 0:
            return None
        xs = df["date"].to_list()
        ys = df["sharpe"].to_list()
        max_y = max(ys) if ys else 3
        fig = go.Figure()
        fig.add_hrect(y0=1, y1=max(max_y * 1.1, 2), fillcolor="rgba(52,211,153,0.05)", line_width=0)
        fig.add_hrect(
            y0=min(min(ys) * 1.1 if ys else -3, -0.01),
            y1=0,
            fillcolor="rgba(248,113,113,0.05)",
            line_width=0,
        )
        fig.add_hline(
            y=1,
            line=dict(color="rgba(52,211,153,0.4)", width=1, dash="dot"),
            annotation_text="SR=1",
            annotation_font_color="#34d399",
            annotation_font_size=9,
        )
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name=f"Rolling Sharpe ({window}d)",
                line=dict(color="#38bdf8", width=2),
            )
        )
        _apply_layout(fig, height=260, yaxis_title="Sharpe Ratio")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Rolling Sharpe", str(exc))


def _build_yearly_returns_chart(returns_series: Any) -> Any:
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None

        df = df.with_columns(
            pl.col("date").str.to_date("%Y-%m-%d", strict=False).alias("date_obj")
        ).filter(pl.col("date_obj").is_not_null())
        if len(df) == 0:
            return None

        yearly = (
            df.with_columns(pl.col("date_obj").dt.year().alias("year"))
            .group_by("year")
            .agg((pl.col("value").sum() * 100).alias("ret_pct"))
            .sort("year")
        )
        if len(yearly) == 0:
            return None

        y_vals = yearly["ret_pct"].to_list()
        x_vals = [str(y) for y in yearly["year"].to_list()]
        colors = ["#34d399" if v >= 0 else "#f87171" for v in y_vals]
        fig = go.Figure(
            data=[
                go.Bar(
                    x=x_vals,
                    y=y_vals,
                    marker_color=colors,
                    marker_line_width=0,
                    text=[f"{v:+.1f}%" for v in y_vals],
                    textposition="outside",
                    textfont=dict(size=10, color="#94a3b8"),
                    hovertemplate="<b>%{x}</b><br>Return: %{y:.2f}%<extra></extra>",
                )
            ]
        )
        _apply_layout(fig, height=260, yaxis_title="Return %")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Yearly Returns", str(exc))


def _build_monthly_yearly_combined(returns_series: Any) -> Any:
    """Heatmap: Jan–Dec monthly returns + Year column (separately colour-normalised)."""
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None or len(df) == 0:
            return None

        df = df.with_columns(
            pl.col("date").str.to_date("%Y-%m-%d", strict=False).alias("date_obj")
        ).filter(pl.col("date_obj").is_not_null())
        if len(df) == 0:
            return None

        df = df.with_columns(
            pl.col("date_obj").dt.year().alias("year"),
            pl.col("date_obj").dt.month().alias("month"),
        )
        monthly = (
            df.group_by(["year", "month"])
            .agg((pl.col("value").sum() * 100).alias("ret_pct"))
            .sort(["year", "month"])
        )
        yearly = df.group_by("year").agg((pl.col("value").sum() * 100).alias("yr_pct")).sort("year")
        pivot = monthly.pivot(
            index="year", on="month", values="ret_pct", aggregate_function="first"
        )
        for m in range(1, 13):
            col = str(m)
            if col not in pivot.columns:
                pivot = pivot.with_columns(pl.lit(0.0).alias(col))
        pivot = pivot.select(["year"] + [str(m) for m in range(1, 13)]).fill_null(0.0)
        yearly_map = dict(zip(yearly["year"].to_list(), yearly["yr_pct"].to_list()))

        if len(pivot) == 0:
            return None

        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        x_labels = month_names + ["  YEAR  "]
        colorscale = [
            [0.0, "#7f1d1d"],
            [0.35, "#991b1b"],
            [0.5, "#1e293b"],
            [0.65, "#14532d"],
            [1.0, "#15803d"],
        ]

        years = pivot["year"].to_list()
        m_vals = [[pivot[str(m)][i] for m in range(1, 13)] for i in range(len(years))]
        y_vals = [yearly_map.get(yr, 0.0) for yr in years]

        import numpy as np

        m_arr = np.array(m_vals, dtype=float)
        y_arr = np.array(y_vals, dtype=float)
        m_abs_max = max(float(abs(m_arr).max()), 1e-6)
        y_abs_max = max(float(abs(y_arr).max()), 1e-6)
        m_norm = m_arr / m_abs_max
        y_norm = y_arr / y_abs_max

        z_combined = [
            list((m_norm[i] + 1) / 2) + [float((y_norm[i] + 1) / 2)] for i in range(len(years))
        ]
        text_rows = [
            [f"{m_vals[i][j]:.1f}%" for j in range(12)] + [f"{y_vals[i]:+.1f}%"]
            for i in range(len(years))
        ]

        fig = go.Figure(
            data=go.Heatmap(
                z=z_combined,
                x=x_labels,
                y=[str(y) for y in years],
                colorscale=colorscale,
                showscale=False,
                text=text_rows,
                texttemplate="%{text}",
                textfont=dict(size=9, color="#f1f5f9"),
                hovertemplate="<b>%{y} %{x}</b><br>Return: %{text}<extra></extra>",
                zmin=0,
                zmax=1,
            )
        )
        layout = dict(_CHART_LAYOUT)
        layout.update(
            height=max(180, len(years) * 26 + 60),
            showlegend=False,
            margin=dict(l=45, r=12, t=30, b=30),
        )
        fig.update_layout(**layout)
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Monthly / Yearly Returns", str(exc))


def _build_rolling_calmar(returns_series: Any, window: int = 252) -> Any:
    """Rolling Calmar ratio (annualized return / max drawdown)."""
    if returns_series is None:
        return None
    try:
        import plotly.graph_objects as go

        df = _extract_frame(returns_series)
        if df is None:
            return None

        effective_window = min(window, max(20, len(df) // 2))
        if len(df) < effective_window:
            return None

        vals = df["value"].to_list()
        calmar: list[float] = []
        for i in range(len(vals)):
            start = max(0, i - effective_window + 1)
            w_ret = vals[start : i + 1]
            if len(w_ret) < 5:
                calmar.append(float("nan"))
                continue
            ann_ret = sum(w_ret) * (252 / len(w_ret))
            # Compute max drawdown over the window.
            cum = 1.0
            peak = 1.0
            max_dd = 0.0
            for r in w_ret:
                cum *= 1 + r
                if cum > peak:
                    peak = cum
                dd = (cum - peak) / max(peak, 1e-10)
                if dd < max_dd:
                    max_dd = dd
            if max_dd < -1e-6:
                calmar.append(float(ann_ret / abs(max_dd)))
            else:
                calmar.append(float("nan"))

        calmar_s = pl.Series("calmar", calmar)
        calmar_smooth = calmar_s.rolling_mean(window_size=20, min_periods=5)
        dates = df["date"].to_list()

        # Pair dates with smoothed calmar, drop nulls.
        pairs = [
            (d, float(c))
            for d, c in zip(dates, calmar_smooth.to_list())
            if c is not None and math.isfinite(c)
        ]
        if not pairs:
            return None

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]

        fig = go.Figure()
        fig.add_hline(
            y=1,
            line=dict(color="rgba(52,211,153,0.4)", width=1, dash="dot"),
            annotation_text="CR=1",
            annotation_font_color="#34d399",
            annotation_font_size=9,
        )
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name="Rolling Calmar",
                line=dict(color="#a78bfa", width=2),
            )
        )
        _apply_layout(fig, height=260, yaxis_title="Calmar Ratio")
        return fig
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Rolling Calmar", str(exc))
