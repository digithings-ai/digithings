"""Plotly chart builders for DigiQuant backtest tearsheets (SIMP-010)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any  # noqa: ANN401 — plotly Figure typing

logger = logging.getLogger(__name__)

_CHART_BUILD_ERRORS = (ImportError, AttributeError, TypeError, ValueError, KeyError, IndexError)


@dataclass(frozen=True, slots=True)
class ChartUnavailable:
    """Marker when a chart section failed to build (DESLOP-010)."""

    title: str
    detail: str = ""


def section_unavailable_html(title: str, detail: str = "") -> str:
    """Structured placeholder when a chart cannot be rendered."""
    msg = detail.strip() or "Chart could not be rendered for this section."
    safe_title = title.replace("<", "").replace(">", "")
    safe_msg = msg.replace("<", "").replace(">", "")[:240]
    return (
        f'<div class="chart-unavailable" role="status" data-section="{safe_title}">'
        f'<p class="chart-unavailable-title">{safe_title}</p>'
        f'<p class="chart-unavailable-detail">{safe_msg}</p>'
        "</div>"
    )


def _compute_bollinger_bands(
    close: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[list[float], list[float], list[float]]:
    n = len(close)
    upper, middle, lower = [], [], []
    for i in range(n):
        start = max(0, i - period + 1)
        window = close[start : i + 1]
        if len(window) < period:
            upper.append(close[i])
            middle.append(close[i])
            lower.append(close[i])
            continue
        m = sum(window) / len(window)
        variance = sum((x - m) ** 2 for x in window) / len(window)
        std = variance**0.5 if variance > 0 else 0.0
        upper.append(m + std_dev * std)
        middle.append(m)
        lower.append(m - std_dev * std)
    return upper, middle, lower


_CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(255,255,255,0.03)",
    font=dict(family="'IBM Plex Mono', 'Courier New', monospace", size=11, color="#94a3b8"),
    margin=dict(l=55, r=20, t=36, b=44),
    xaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.05)",
        linecolor="rgba(255,255,255,0.1)",
        tickfont=dict(color="#64748b", size=10),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.05)",
        linecolor="rgba(255,255,255,0.1)",
        tickfont=dict(color="#64748b", size=10),
    ),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color="#64748b"), borderwidth=0),
)


def _apply_layout(fig: Any, height: int = 300, **kwargs: Any) -> None:
    layout = dict(_CHART_LAYOUT)
    layout["height"] = height
    layout.update(kwargs)
    fig.update_layout(**layout)


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


def _build_distribution_chart(returns_series: Any) -> Any:
    if returns_series is None or len(returns_series) == 0:
        return None
    try:
        import plotly.graph_objects as go

        vals = (
            returns_series.tolist() if hasattr(returns_series, "tolist") else list(returns_series)
        )
        vals = [
            float(x) * 100
            for x in vals
            if x is not None and not (isinstance(x, float) and math.isnan(x))
        ]
        if not vals:
            return None
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
        mean_val = sum(vals) / len(vals)
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


def _build_rolling_equity_chart(returns_series: Any, initial_balance: float = 1_000_000.0) -> Any:
    if returns_series is None:
        return None
    try:
        import pandas as pd
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        ret = pd.to_numeric(ret, errors="coerce").dropna()
        ret = ret[~ret.index.isna()] if hasattr(ret.index, "isna") else ret
        if len(ret) == 0:
            return None
        equity = (1 + ret).cumprod() * initial_balance
        vals = equity.values.tolist()
        xs = equity.index.astype(str).tolist()
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


def _build_realized_pnl_chart(realized_pnls_series: Any) -> Any:
    if realized_pnls_series is None:
        return None
    try:
        import pandas as pd
        import plotly.graph_objects as go

        rp = (
            realized_pnls_series.to_pandas()
            if hasattr(realized_pnls_series, "to_pandas")
            else realized_pnls_series
        )
        if not hasattr(rp, "index"):
            return None
        # Drop NaT index entries and NaN values
        rp = pd.to_numeric(rp, errors="coerce")
        if hasattr(rp.index, "isna"):
            rp = rp[~rp.index.isna()]
        rp = rp.dropna()
        if len(rp) == 0:
            return None
        cum = rp.cumsum()
        final = float(cum.iloc[-1])
        xs = cum.index.astype(str).tolist()
        ys = cum.values.tolist()
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


def _build_rolling_drawdown_chart(returns_series: Any, window: int = 60) -> Any:
    """Rolling max drawdown: worst peak-to-trough in each rolling window."""
    if returns_series is None:
        return None
    try:
        import pandas as pd
        import plotly.graph_objects as go

        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        ret = pd.to_numeric(ret, errors="coerce").dropna()
        if hasattr(ret.index, "isna"):
            ret = ret[~ret.index.isna()]
        effective_window = min(window, max(10, len(ret) // 3))
        if len(ret) < effective_window:
            return None
        # Compute full underwater (drawdown) series first
        cum = (1 + ret).cumprod()
        rolling_peak = cum.expanding().max()
        underwater = (cum - rolling_peak) / rolling_peak * 100  # always <= 0
        # Rolling worst drawdown = minimum of underwater in each window
        roll_max_dd = underwater.rolling(effective_window, min_periods=effective_window // 2).min()
        xs = roll_max_dd.index.astype(str).tolist()
        ys = roll_max_dd.values.tolist()
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


def _build_underwater_from_returns(returns_series: Any) -> Any:
    """Underwater equity plot from returns series."""
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
        cum = (1 + ret).cumprod()
        rolling_max = cum.expanding().max()
        underwater = (cum - rolling_max) / rolling_max.clip(lower=1e-10) * 100
        xs = underwater.index.astype(str).tolist()
        ys = underwater.values.tolist()
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


def _build_price_chart_inline(
    ohlcv_df: Any,
    symbol: str,
    period: int,
    std_dev: float,
    fill_ts: list[str],
    fill_px: list[float],
    fill_sides: list[str],
) -> Any:
    import plotly.graph_objects as go

    if ohlcv_df is None:
        return None
    try:
        cols = ohlcv_df.columns if hasattr(ohlcv_df, "columns") else []
        ts_col = "timestamp" if "timestamp" in cols else (cols[0] if cols else None)
        if not ts_col or "close" not in cols:
            return None
        close_ser = ohlcv_df["close"]
        ts_ser = ohlcv_df[ts_col]
        close = close_ser.to_list() if hasattr(close_ser, "to_list") else list(close_ser)
        ts_vals = ts_ser.to_list() if hasattr(ts_ser, "to_list") else list(ts_ser)
        timestamps = [str(t) for t in ts_vals]
    except _CHART_BUILD_ERRORS as exc:
        return ChartUnavailable("Price & Bands", str(exc))
    if not timestamps or not close:
        return None

    upper, middle, lower = _compute_bollinger_bands(close, period, std_dev)
    fig = go.Figure()
    # BB band fill
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=upper,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=lower,
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(148,163,184,0.07)",
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=upper,
            mode="lines",
            name=f"BB ({period},{std_dev}σ)",
            line=dict(color="#475569", width=1, dash="dot"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=middle, mode="lines", name="SMA", line=dict(color="#64748b", width=1)
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=lower,
            mode="lines",
            name="BB Lower",
            line=dict(color="#475569", width=1, dash="dot"),
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=close, mode="lines", name="Close", line=dict(color="#e2e8f0", width=1.5)
        )
    )

    if fill_ts and fill_px and fill_sides:
        buy_ts = [t for t, s in zip(fill_ts, fill_sides) if "BUY" in s or "LONG" in s]
        buy_px = [p for p, s in zip(fill_px, fill_sides) if "BUY" in s or "LONG" in s]
        sell_ts = [t for t, s in zip(fill_ts, fill_sides) if "SELL" in s or "SHORT" in s]
        sell_px = [p for p, s in zip(fill_px, fill_sides) if "SELL" in s or "SHORT" in s]
        if buy_ts:
            fig.add_trace(
                go.Scatter(
                    x=buy_ts,
                    y=buy_px,
                    mode="markers",
                    name="Entry",
                    marker=dict(
                        symbol="triangle-up",
                        size=10,
                        color="#34d399",
                        line=dict(color="#0f172a", width=1),
                    ),
                )
            )
        if sell_ts:
            fig.add_trace(
                go.Scatter(
                    x=sell_ts,
                    y=sell_px,
                    mode="markers",
                    name="Exit",
                    marker=dict(
                        symbol="triangle-down",
                        size=10,
                        color="#f87171",
                        line=dict(color="#0f172a", width=1),
                    ),
                )
            )

    _apply_layout(
        fig,
        height=480,
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)",
            tickfont=dict(color="#64748b", size=10),
            # ── Range slider + selector ─────────────────────────────────────
            rangeslider=dict(
                visible=True,
                thickness=0.06,
                bgcolor="rgba(255,255,255,0.03)",
                bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1,
            ),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="ALL"),
                ],
                bgcolor="rgba(15,28,46,0.95)",
                activecolor="#38bdf8",
                bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1,
                font=dict(color="#94a3b8", size=10),
                x=0,
                y=1.02,
            ),
        ),
        yaxis=dict(
            title="Price",
            tickformat=",.4f",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)",
            tickfont=dict(color="#64748b", size=10),
            domain=[0.08, 1],  # leave room for rangeslider
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color="#64748b"),
            borderwidth=0,
        ),
        # ── Linear / Log toggle ─────────────────────────────────────────
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.0,
                y=1.13,
                xanchor="left",
                yanchor="top",
                pad=dict(r=4, t=4),
                showactive=True,
                bgcolor="rgba(15,28,46,0.95)",
                bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1,
                font=dict(color="#94a3b8", size=10),
                buttons=[
                    dict(label="Linear", method="relayout", args=[{"yaxis.type": "linear"}]),
                    dict(label="Log", method="relayout", args=[{"yaxis.type": "log"}]),
                ],
            )
        ],
    )
    return fig
