# score:allow pandas, pd.
"""Return distribution and rolling metric chart builders."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — plotly Figure typing

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _CHART_LAYOUT,
    _apply_layout,
)


def _build_monthly_returns_chart(returns_series: Any) -> Any:
    if returns_series is None or len(returns_series) == 0:
        return None
    try:
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        if not hasattr(ret, "index"):
            return None
        df = ret.to_frame("ret")
        df["year"] = df.index.year
        df["month"] = df.index.month
        monthly = df.groupby(["year", "month"])["ret"].sum().unstack(fill_value=0) * 100
        if monthly.empty:
            return None
        monthly = monthly.reindex(columns=range(1, 13), fill_value=0)
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
        x_labels = month_names
        text_vals = [[f"{v:.1f}%" for v in row] for row in monthly.values]
        fig = go.Figure(
            data=go.Heatmap(
                z=monthly.values,
                x=x_labels,
                y=[str(y) for y in monthly.index],
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
        import pandas as pd
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        ret = pd.to_numeric(ret, errors="coerce").dropna()
        ret = ret[~ret.index.isna()] if hasattr(ret.index, "isna") else ret
        if len(ret) < 20:
            return None
        window = min(60, len(ret) // 2)
        roll = ret.rolling(window, min_periods=max(10, window // 3))
        mean = roll.mean()
        std = roll.std()
        sharpe = (mean / std.where(std > 1e-10, 1e-10) * (252**0.5)).fillna(0)
        xs = sharpe.index.astype(str).tolist()
        ys = sharpe.values.tolist()
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
    if returns_series is None or len(returns_series) == 0:
        return None
    try:
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        yearly = ret.groupby(ret.index.year).sum() * 100
        colors = ["#34d399" if v >= 0 else "#f87171" for v in yearly.values]
        fig = go.Figure(
            data=[
                go.Bar(
                    x=[str(y) for y in yearly.index],
                    y=yearly.values,
                    marker_color=colors,
                    marker_line_width=0,
                    text=[f"{v:+.1f}%" for v in yearly.values],
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
        import pandas as pd
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        ret = pd.to_numeric(ret, errors="coerce").dropna()
        if hasattr(ret.index, "isna"):
            ret = ret[~ret.index.isna()]
        if len(ret) == 0:
            return None
        df = ret.to_frame("ret")
        df["year"] = df.index.year
        df["month"] = df.index.month
        monthly = df.groupby(["year", "month"])["ret"].sum().unstack(fill_value=0) * 100
        yearly = ret.groupby(ret.index.year).sum() * 100
        if monthly.empty or yearly.empty:
            return None
        monthly = monthly.reindex(columns=range(1, 13), fill_value=0)
        yearly_aligned = yearly.reindex(monthly.index, fill_value=0)
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
        # Build z matrix: normalise monthly and yearly columns INDEPENDENTLY
        # so the yearly total doesn't dominate the monthly colour range
        m_vals = monthly.values  # shape (years, 12)
        y_vals = yearly_aligned.values  # shape (years,)
        # Normalise monthly: scale to [-1, 1] range
        m_abs_max = max(abs(m_vals.min()), abs(m_vals.max()), 1e-6)
        y_abs_max = max(abs(y_vals.min()), abs(y_vals.max()), 1e-6)
        m_norm = m_vals / m_abs_max  # [-1..1]
        y_norm = (y_vals / y_abs_max).reshape(-1, 1)  # [-1..1]
        # Shift to [0..1] for colorscale
        z_combined = [
            list((m_norm[i] + 1) / 2) + [float((y_norm[i][0] + 1) / 2)]
            for i in range(len(monthly.index))
        ]
        text_rows = [
            [f"{m_vals[i][j]:.1f}%" for j in range(12)] + [f"{y_vals[i]:+.1f}%"]
            for i in range(len(monthly.index))
        ]
        fig = go.Figure(
            data=go.Heatmap(
                z=z_combined,
                x=x_labels,
                y=[str(y) for y in monthly.index],
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
            height=max(180, len(monthly.index) * 26 + 60),
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
        import pandas as pd
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        ret = pd.to_numeric(ret, errors="coerce").dropna()
        if hasattr(ret.index, "isna"):
            ret = ret[~ret.index.isna()]
        effective_window = min(window, max(20, len(ret) // 2))
        if len(ret) < effective_window:
            return None
        calmar = []
        for i in range(len(ret)):
            start = max(0, i - effective_window + 1)
            w_ret = ret.iloc[start : i + 1]
            if len(w_ret) < 5:
                calmar.append(float("nan"))
                continue
            ann_ret = w_ret.sum() * (252 / len(w_ret))
            cum = (1 + w_ret).cumprod()
            rolling_peak = cum.expanding().max()
            dd = ((cum - rolling_peak) / rolling_peak.clip(lower=1e-10)).min()
            if dd < -1e-6:
                calmar.append(float(ann_ret / abs(dd)))
            else:
                calmar.append(float("nan"))
        calmar_s = pd.Series(calmar, index=ret.index).rolling(20, min_periods=5).mean().dropna()
        if len(calmar_s) == 0:
            return None
        xs = calmar_s.index.astype(str).tolist()
        ys = calmar_s.values.tolist()
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
