"""
DigiQuant Backtest Tearsheet — Premium Edition.
Modern trading-terminal aesthetic, tabbed, exportable HTML.
Requires: digiquant[visualization] (plotly).
"""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from digiquant.models import BacktestResult


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_logo_base64() -> str:
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        logo_path = repo_root / "assets" / "dg_transparent.png"
        if logo_path.exists():
            data = logo_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except Exception:
        pass
    return ""


def _parse_balance(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    if " " in s:
        s = s.split()[0]
    s = s.replace("_", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_equity_curve(account_report: "pd.DataFrame" | None) -> tuple[list[str], list[float]]:
    if account_report is None or account_report.empty:
        return [], []
    timestamps: list[str] = []
    balances: list[float] = []
    balance_col = next((c for c in ("total", "balance", "free") if c in account_report.columns), None)
    if not balance_col:
        return [], []
    for idx, row in account_report.iterrows():
        ts = row.get("ts_event", idx)
        if ts is not None:
            timestamps.append(str(ts))
        total = _parse_balance(row.get(balance_col))
        balances.append(total)
    return timestamps, balances


def _compute_drawdown(balances: list[float]) -> list[float]:
    if not balances:
        return []
    peak = balances[0]
    dd = []
    for b in balances:
        peak = max(peak, b)
        dd.append(((b - peak) / peak * 100) if peak > 0 else 0.0)
    return dd


def _extract_fill_markers(fills_report: "pd.DataFrame" | None) -> tuple[list[str], list[float], list[str]]:
    if fills_report is None or fills_report.empty:
        return [], [], []
    ts_col = next((c for c in ("ts_event", "ts_last", "ts_init") if c in fills_report.columns), None)
    px_col = next((c for c in ("avg_px", "last_px", "price") if c in fills_report.columns), None)
    side_col = next((c for c in ("order_side", "side") if c in fills_report.columns), None)
    if not ts_col or not px_col:
        return [], [], []
    timestamps: list[str] = []
    prices: list[float] = []
    sides: list[str] = []
    for _, row in fills_report.iterrows():
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(str(ts))
        try:
            px = float(str(row.get(px_col, 0)).replace(",", "").replace("_", ""))
        except (ValueError, TypeError):
            px = 0.0
        prices.append(px)
        side = str(row.get(side_col, "")).upper()
        sides.append(side)
    return timestamps, prices, sides


def _compute_bollinger_bands(close: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[list[float], list[float], list[float]]:
    n = len(close)
    upper, middle, lower = [], [], []
    for i in range(n):
        start = max(0, i - period + 1)
        window = close[start: i + 1]
        if len(window) < period:
            upper.append(close[i]); middle.append(close[i]); lower.append(close[i])
            continue
        m = sum(window) / len(window)
        variance = sum((x - m) ** 2 for x in window) / len(window)
        std = variance ** 0.5 if variance > 0 else 0.0
        upper.append(m + std_dev * std)
        middle.append(m)
        lower.append(m - std_dev * std)
    return upper, middle, lower


def _get_stat(pnl_dict: dict, returns_dict: dict, general_dict: dict, key: str) -> float | None:
    for d in (pnl_dict, returns_dict, general_dict):
        if key in d:
            v = d[key]
            if isinstance(v, (int, float)) and not math.isnan(v):
                return float(v)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────────────────────────────

_CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(255,255,255,0.03)",
    font=dict(family="'IBM Plex Mono', 'Courier New', monospace", size=11, color="#94a3b8"),
    margin=dict(l=55, r=20, t=36, b=44),
    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#64748b", size=10)),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#64748b", size=10)),
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
    fig.add_trace(go.Scatter(
        x=timestamps, y=balances, mode="lines", name="Equity",
        line=dict(color="#38bdf8", width=2),
        fill="tonexty", fillcolor="rgba(56,189,248,0.06)",
    ))
    # Pad range by 2% above/below the actual data range
    if balances:
        lo, hi = min(balances), max(balances)
        pad = (hi - lo) * 0.05 if hi != lo else abs(hi) * 0.02 or 1
        y_range = [lo - pad, hi + pad]
    else:
        y_range = None
    _apply_layout(
        fig, height=300,
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
        "#dc2626" if v < -15 else
        "#f87171" if v < -5 else
        "#fca5a5" if v < 0 else
        "rgba(100,116,139,0.3)"
        for v in dd_d
    ]
    fig = go.Figure(data=[go.Bar(
        x=ts_d, y=dd_d,
        marker_color=colors,
        marker_line_width=0,
        name="Drawdown",
        hovertemplate="%{x}<br>Drawdown: %{y:.2f}%<extra></extra>",
    )])
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
    _apply_layout(
        fig, height=220,
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
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        x_labels = month_names
        text_vals = [[f"{v:.1f}%" for v in row] for row in monthly.values]
        fig = go.Figure(data=go.Heatmap(
            z=monthly.values, x=x_labels, y=[str(y) for y in monthly.index],
            text=text_vals, texttemplate="%{text}",
            colorscale=[[0, "#7f1d1d"], [0.35, "#991b1b"], [0.5, "#1e293b"], [0.65, "#14532d"], [1, "#15803d"]],
            zmid=0, showscale=False,
            hovertemplate="<b>%{y} %{x}</b><br>Return: %{z:.2f}%<extra></extra>",
        ))
        _apply_layout(fig, height=200)
        return fig
    except Exception:
        return None


def _build_distribution_chart(returns_series: Any) -> Any:
    if returns_series is None or len(returns_series) == 0:
        return None
    try:
        import plotly.graph_objects as go
        vals = returns_series.tolist() if hasattr(returns_series, "tolist") else list(returns_series)
        vals = [float(x) * 100 for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
        if not vals:
            return None
        fig = go.Figure(data=[go.Histogram(
            x=vals, nbinsx=40,
            marker=dict(color="#38bdf8", opacity=0.8, line=dict(color="rgba(56,189,248,0.3)", width=0.5)),
            name="Returns",
        )])
        mean_val = sum(vals) / len(vals)
        fig.add_vline(x=mean_val, line=dict(color="#fbbf24", width=1.5, dash="dash"), annotation_text=f"μ={mean_val:.2f}%", annotation_font_color="#fbbf24", annotation_font_size=10)
        fig.add_vline(x=0, line=dict(color="rgba(255,255,255,0.2)", width=1))
        _apply_layout(fig, height=280, xaxis_title="Return %", yaxis_title="Count")
        return fig
    except Exception:
        return None


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
        sharpe = (mean / std.where(std > 1e-10, 1e-10) * (252 ** 0.5)).fillna(0)
        xs = sharpe.index.astype(str).tolist()
        ys = sharpe.values.tolist()
        max_y = max(ys) if ys else 3
        fig = go.Figure()
        fig.add_hrect(y0=1, y1=max(max_y * 1.1, 2), fillcolor="rgba(52,211,153,0.05)", line_width=0)
        fig.add_hrect(y0=min(min(ys) * 1.1 if ys else -3, -0.01), y1=0, fillcolor="rgba(248,113,113,0.05)", line_width=0)
        fig.add_hline(y=1, line=dict(color="rgba(52,211,153,0.4)", width=1, dash="dot"),
                      annotation_text="SR=1", annotation_font_color="#34d399", annotation_font_size=9)
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            name=f"Rolling Sharpe ({window}d)",
            line=dict(color="#38bdf8", width=2),
        ))
        _apply_layout(fig, height=260, yaxis_title="Sharpe Ratio")
        return fig
    except Exception:
        return None


def _build_yearly_returns_chart(returns_series: Any) -> Any:
    if returns_series is None or len(returns_series) == 0:
        return None
    try:
        import plotly.graph_objects as go
        ret = returns_series.to_pandas() if hasattr(returns_series, "to_pandas") else returns_series
        yearly = ret.groupby(ret.index.year).sum() * 100
        colors = ["#34d399" if v >= 0 else "#f87171" for v in yearly.values]
        fig = go.Figure(data=[go.Bar(
            x=[str(y) for y in yearly.index], y=yearly.values,
            marker_color=colors, marker_line_width=0,
            text=[f"{v:+.1f}%" for v in yearly.values], textposition="outside",
            textfont=dict(size=10, color="#94a3b8"),
            hovertemplate="<b>%{x}</b><br>Return: %{y:.2f}%<extra></extra>",
        )])
        _apply_layout(fig, height=260, yaxis_title="Return %")
        return fig
    except Exception:
        return None


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
        fig.add_trace(go.Scatter(
            x=xs, y=vals, mode="lines", name="Daily Equity",
            line=dict(color="#38bdf8", width=2),
        ))
        _apply_layout(
            fig, height=300,
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
    except Exception:
        return None


def _build_realized_pnl_chart(realized_pnls_series: Any) -> Any:
    if realized_pnls_series is None:
        return None
    try:
        import pandas as pd
        import plotly.graph_objects as go
        rp = realized_pnls_series.to_pandas() if hasattr(realized_pnls_series, "to_pandas") else realized_pnls_series
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
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", name="Cumulative PnL",
            line=dict(color=color, width=2),
            fill="tozeroy", fillcolor=fill_color,
        ))
        _apply_layout(
            fig, height=300,
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
    except Exception:
        return None


def _build_trade_pnl_distribution_chart(realized_pnls_series: Any) -> Any:
    if realized_pnls_series is None:
        return None
    try:
        import pandas as pd
        import plotly.graph_objects as go
        raw = realized_pnls_series.to_pandas() if hasattr(realized_pnls_series, "to_pandas") else realized_pnls_series
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
            fig.add_trace(go.Histogram(
                x=wins, nbinsx=25,
                marker_color="rgba(52,211,153,0.75)",
                name="Winners",
                marker_line_width=0,
            ))
        if losses:
            fig.add_trace(go.Histogram(
                x=losses, nbinsx=25,
                marker_color="rgba(248,113,113,0.75)",
                name="Losers",
                marker_line_width=0,
            ))
        fig.add_vline(x=0, line=dict(color="rgba(255,255,255,0.25)", width=1.5))
        _apply_layout(
            fig, height=280,
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
    except Exception:
        return None


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
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            name=f"Rolling Max DD ({effective_window}d)",
            line=dict(color="#f87171", width=2),
            fill="tozeroy",
            fillcolor="rgba(248,113,113,0.12)",
        ))
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(fig, height=280, yaxis_title="Drawdown %")
        return fig
    except Exception:
        return None


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
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        x_labels = month_names + ["  YEAR  "]
        colorscale = [
            [0.0, "#7f1d1d"], [0.35, "#991b1b"], [0.5, "#1e293b"],
            [0.65, "#14532d"], [1.0, "#15803d"]
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
        fig = go.Figure(data=go.Heatmap(
            z=z_combined,
            x=x_labels,
            y=[str(y) for y in monthly.index],
            colorscale=colorscale,
            showscale=False,
            text=text_rows,
            texttemplate="%{text}",
            textfont=dict(size=9, color="#f1f5f9"),
            hovertemplate="<b>%{y} %{x}</b><br>Return: %{text}<extra></extra>",
            zmin=0, zmax=1,
        ))
        layout = dict(_CHART_LAYOUT)
        layout.update(height=max(180, len(monthly.index) * 26 + 60), showlegend=False, margin=dict(l=45, r=12, t=30, b=30))
        fig.update_layout(**layout)
        return fig
    except Exception:
        return None


# ─── NEW: Per-trade PnL waterfall bars ────────────────────────────────────────

def _build_per_trade_pnl_bars(realized_pnls_series: Any) -> Any:
    """Bar chart of each trade's realized PnL in chronological order."""
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go
        raw = realized_pnls_series.to_pandas() if hasattr(realized_pnls_series, "to_pandas") else realized_pnls_series
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
        fig = go.Figure(data=[go.Bar(
            x=trade_nums, y=vals,
            marker_color=colors, marker_line_width=0,
            name="Trade PnL",
            hovertemplate="Trade #%{x}<br>PnL: $%{y:,.2f}<extra></extra>",
        )])
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(
            fig, height=300,
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
    except Exception:
        return None


# ─── NEW: Win rate donut chart ────────────────────────────────────────────────

def _build_win_rate_donut(win_rate: float | None, num_trades: int) -> Any:
    """Donut chart showing win/loss split."""
    if win_rate is None:
        return None
    try:
        import plotly.graph_objects as go
        wr = max(0.0, min(1.0, win_rate))
        wins = round(wr * num_trades)
        losses = num_trades - wins
        fig = go.Figure(data=[go.Pie(
            labels=["Winners", "Losers"],
            values=[wins, losses],
            hole=0.65,
            marker=dict(colors=["#34d399", "#f87171"], line=dict(color="rgba(0,0,0,0)", width=0)),
            textinfo="none",
            hovertemplate="%{label}: %{value} trades (%{percent})<extra></extra>",
        )])
        fig.add_annotation(
            text=f"<b>{wr*100:.1f}%</b><br><span style='font-size:9px;color:#64748b'>WIN RATE</span>",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font=dict(size=18, color="#f1f5f9", family="'IBM Plex Mono', monospace"),
            align="center",
        )
        layout = dict(_CHART_LAYOUT)
        layout.update(height=260, showlegend=True, legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"))
        fig.update_layout(**layout)
        return fig
    except Exception:
        return None


# ─── NEW: Rolling Calmar ratio ─────────────────────────────────────────────────

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
            w_ret = ret.iloc[start: i + 1]
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
        fig.add_hline(y=1, line=dict(color="rgba(52,211,153,0.4)", width=1, dash="dot"),
                      annotation_text="CR=1", annotation_font_color="#34d399", annotation_font_size=9)
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            name="Rolling Calmar",
            line=dict(color="#a78bfa", width=2),
        ))
        _apply_layout(fig, height=260, yaxis_title="Calmar Ratio")
        return fig
    except Exception:
        return None


# ─── NEW: Cumulative trade PnL (step chart) ────────────────────────────────────

def _build_cumulative_trade_pnl(realized_pnls_series: Any) -> Any:
    """Step-function cumulative PnL per trade number."""
    if realized_pnls_series is None:
        return None
    try:
        import plotly.graph_objects as go
        raw = realized_pnls_series.to_pandas() if hasattr(realized_pnls_series, "to_pandas") else realized_pnls_series
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
        fig.add_trace(go.Scatter(
            x=list(range(1, len(cum) + 1)), y=cum,
            mode="lines", name="Cumulative PnL",
            line=dict(color=color, width=2, shape="hv"),
            fill="tozeroy", fillcolor=fill_color,
        ))
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        _apply_layout(
            fig, height=300,
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
    except Exception:
        return None


# ─── NEW: Underwater equity plot ──────────────────────────────────────────────

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
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            fill="tozeroy", name="Underwater %",
            line=dict(color="#f87171", width=1.5),
            fillcolor="rgba(248,113,113,0.15)",
        ))
        _apply_layout(fig, height=220, yaxis_title="Underwater %")
        return fig
    except Exception:
        return None


def _build_price_chart_inline(ohlcv_df: Any, symbol: str, period: int, std_dev: float, fill_ts: list[str], fill_px: list[float], fill_sides: list[str]) -> Any:
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
    except Exception:
        return None
    if not timestamps or not close:
        return None

    upper, middle, lower = _compute_bollinger_bands(close, period, std_dev)
    fig = go.Figure()
    # BB band fill
    fig.add_trace(go.Scatter(x=timestamps, y=upper, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=timestamps, y=lower, mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(148,163,184,0.07)", showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=timestamps, y=upper, mode="lines", name=f"BB ({period},{std_dev}σ)", line=dict(color="#475569", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=timestamps, y=middle, mode="lines", name="SMA", line=dict(color="#64748b", width=1)))
    fig.add_trace(go.Scatter(x=timestamps, y=lower, mode="lines", name="BB Lower", line=dict(color="#475569", width=1, dash="dot"), showlegend=False))
    fig.add_trace(go.Scatter(x=timestamps, y=close, mode="lines", name="Close", line=dict(color="#e2e8f0", width=1.5)))

    if fill_ts and fill_px and fill_sides:
        buy_ts = [t for t, s in zip(fill_ts, fill_sides) if "BUY" in s or "LONG" in s]
        buy_px = [p for p, s in zip(fill_px, fill_sides) if "BUY" in s or "LONG" in s]
        sell_ts = [t for t, s in zip(fill_ts, fill_sides) if "SELL" in s or "SHORT" in s]
        sell_px = [p for p, s in zip(fill_px, fill_sides) if "SELL" in s or "SHORT" in s]
        if buy_ts:
            fig.add_trace(go.Scatter(x=buy_ts, y=buy_px, mode="markers", name="Entry",
                                     marker=dict(symbol="triangle-up", size=10, color="#34d399", line=dict(color="#0f172a", width=1))))
        if sell_ts:
            fig.add_trace(go.Scatter(x=sell_ts, y=sell_px, mode="markers", name="Exit",
                                     marker=dict(symbol="triangle-down", size=10, color="#f87171", line=dict(color="#0f172a", width=1))))

    _apply_layout(
        fig, height=480,
        xaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#64748b", size=10),
            # ── Range slider + selector ─────────────────────────────────────
            rangeslider=dict(visible=True, thickness=0.06, bgcolor="rgba(255,255,255,0.03)", bordercolor="rgba(255,255,255,0.1)", borderwidth=1),
            rangeselector=dict(
                buttons=[
                    dict(count=1,  label="1M", step="month", stepmode="backward"),
                    dict(count=3,  label="3M", step="month", stepmode="backward"),
                    dict(count=6,  label="6M", step="month", stepmode="backward"),
                    dict(count=1,  label="1Y", step="year",  stepmode="backward"),
                    dict(step="all", label="ALL"),
                ],
                bgcolor="rgba(15,28,46,0.95)",
                activecolor="#38bdf8",
                bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1,
                font=dict(color="#94a3b8", size=10),
                x=0, y=1.02,
            ),
        ),
        yaxis=dict(
            title="Price", tickformat=",.4f",
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#64748b", size=10),
            domain=[0.08, 1],  # leave room for rangeslider
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10, color="#64748b"), borderwidth=0),
        # ── Linear / Log toggle ─────────────────────────────────────────
        updatemenus=[dict(
            type="buttons",
            direction="left",
            x=0.0, y=1.13,
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
                dict(label="Log",    method="relayout", args=[{"yaxis.type": "log"}]),
            ],
        )],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Stats table builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_categorized_stats(stats_returns: dict | None, stats_pnls: dict | None, stats_general: dict | None, result: BacktestResult) -> str:
    """Build categorized stats grid replacing the dropdown."""
    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {})
    ret = stats_returns or {}
    gen = stats_general or {}
    combined = {**pnl, **ret, **gen}

    def fv(k: str, fmt: str = ".2f") -> str:
        v = combined.get(k)
        if v is None and k == "Max Drawdown %" and result.max_drawdown_pct is not None:
            v = result.max_drawdown_pct
        if v is None:
            return "—"
        if isinstance(v, (int, float)) and not math.isnan(v):
            return f"{v:{fmt}}"
        return str(v)

    def row(label: str, key: str, fmt: str = ".2f", is_pct: bool = False, positive_good: bool = True) -> str:
        v = combined.get(key)
        if v is None and key == "Max Drawdown %":
            v = result.max_drawdown_pct
        if v is None:
            val_str = "—"
            cls = ""
        elif isinstance(v, (int, float)) and not math.isnan(v):
            if is_pct:
                val_str = f"{v:{fmt}}%"
            else:
                val_str = f"{v:{fmt}}"
            good = v > 0 if positive_good else v < 0
            cls = " pos" if good else " neg"
        else:
            val_str = str(v)
            cls = ""
        return f'<tr><td class="sk">{label}</td><td class="sv{cls}">{val_str}</td></tr>'

    def section(title: str, rows_html: str) -> str:
        return f'<div class="stats-section"><div class="stats-section-title">{title}</div><table class="stats-mini-table">{rows_html}</table></div>'

    perf = (
        row("Total Return", "Total Return", ".2f", True) +
        row("Total PnL", "PnL (USD)", ",.2f") +
        row("Ann. Return", "Annualized Return", ".2f", True) +
        row("Best Day", "Max Return", ".2f", True) +
        row("Worst Day", "Min Return", ".2f", True)
    )
    risk = (
        row("Sharpe (252d)", "Sharpe Ratio (252 days)", ".2f") +
        row("Sortino (252d)", "Sortino Ratio (252 days)", ".2f") +
        row("Calmar Ratio", "Calmar Ratio", ".2f") +
        row("Max Drawdown", "Max Drawdown %", ".1f", True, False) +
        row("Volatility", "Returns Volatility (252 days)", ".4f") +
        row("Value at Risk", "Value at Risk", ".4f")
    )
    trade_stats = (
        row("# Trades", "Total Trades", ".0f") +
        row("Win Rate", "Win Rate", ".2f", True) +
        row("Avg Winner", "Avg Winner", ",.2f") +
        row("Avg Loser", "Avg Loser", ",.2f") +
        row("Max Winner", "Max Winner", ",.2f") +
        row("Max Loser", "Max Loser", ",.2f")
    )
    ratios = (
        row("Profit Factor", "Profit Factor", ".2f") +
        row("Expectancy", "Expectancy", ",.2f") +
        row("Risk/Return", "Risk Return Ratio", ".2f") +
        row("Avg Trade", "Avg Trade", ",.2f") +
        row("Win Streak", "Max Win Streak", ".0f") +
        row("Loss Streak", "Max Loss Streak", ".0f")
    )

    return (
        f'<div class="stats-grid">'
        f'{section("Performance", perf)}'
        f'{section("Risk & Ratios", risk)}'
        f'{section("Trade Stats", trade_stats)}'
        f'{section("Additional", ratios)}'
        f'</div>'
    )


def _build_full_stats_table(stats_returns: dict | None, stats_pnls: dict | None, stats_general: dict | None, result: BacktestResult) -> str:
    rows: list[tuple[str, str]] = []
    _fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)
    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {})
    for k, v in (pnl or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    for k, v in (stats_returns or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    for k, v in (stats_general or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    if result.max_drawdown_pct is not None and not any("Max Drawdown" in r[0] for r in rows):
        rows.append(("Max Drawdown %", f"{result.max_drawdown_pct:.1f}%"))
    trs = "".join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in rows)
    return f'<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{trs}</tbody></table>' if trs else "<p class='no-data'>No stats available.</p>"


def _build_risk_metrics_table(stats_pnls: dict | None, stats_returns: dict | None, result: BacktestResult) -> str:
    risk_keys = ("Max Drawdown %", "Max Loser", "Max Winner", "Avg Loser", "Avg Winner", "Min Loser", "Min Winner", "Win Rate", "Expectancy", "Returns Volatility (252 days)", "Sharpe Ratio (252 days)", "Sortino Ratio (252 days)", "Profit Factor", "Risk Return Ratio")
    rows: list[tuple[str, str]] = []
    _fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)
    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {}) or {}
    combined = {**(pnl or {}), **(stats_returns or {})}
    for k in risk_keys:
        v = combined.get(k)
        if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    if result.max_drawdown_pct is not None and not any("Max Drawdown" in r[0] for r in rows):
        rows.insert(0, ("Max Drawdown %", f"{result.max_drawdown_pct:.1f}%"))
    trs = "".join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in rows)
    return f'<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{trs}</tbody></table>' if trs else "<p class='no-data'>No risk metrics.</p>"


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def create_tearsheet(
    result: BacktestResult,
    output_path: str | Path,
    *,
    strategy_params: dict[str, float | int | str] | None = None,
    account_report: "pd.DataFrame" | None = None,
    fills_report: "pd.DataFrame" | None = None,
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

    def _fig_to_html(fig: Any, div_id: str, include_plotlyjs: bool | str = False, fallback: str = "") -> str:
        if fig is None:
            return fallback
        return fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs, div_id=div_id)

    initial_balance = 1_000_000.0

    # Build core figures (always)
    equity_fig = _build_equity_chart(timestamps, balances) if timestamps else None
    dd_fig = _build_drawdown_chart(timestamps, drawdown_pct) if drawdown_pct else None
    price_fig = _build_price_chart_inline(ohlcv_df, symbol, period, std_dev, fill_ts, fill_px, fill_sides)
    win_rate_donut_fig = _build_win_rate_donut(win_rate, result.num_trades)
    realized_pnl_fig = _build_realized_pnl_chart(realized_pnls_series)
    per_trade_pnl_fig = _build_per_trade_pnl_bars(realized_pnls_series)
    cum_trade_pnl_fig = _build_cumulative_trade_pnl(realized_pnls_series)
    # Build extended figures only when full=True
    monthly_fig = _build_monthly_returns_chart(returns_series) if full else None
    dist_fig = _build_distribution_chart(returns_series) if full else None
    rolling_fig = _build_rolling_sharpe_chart(returns_series) if full else None
    yearly_fig = _build_yearly_returns_chart(returns_series) if full else None
    rolling_equity_fig = _build_rolling_equity_chart(returns_series, initial_balance) if full else None
    trade_pnl_dist_fig = _build_trade_pnl_distribution_chart(realized_pnls_series) if full else None
    rolling_dd_fig = _build_rolling_drawdown_chart(returns_series) if full else None
    monthly_yearly_fig = _build_monthly_yearly_combined(returns_series) if full else None
    rolling_calmar_fig = _build_rolling_calmar(returns_series) if full else None
    underwater_fig = _build_underwater_from_returns(returns_series) if full else None

    # Convert to HTML
    def fh(fig: Any, div_id: str, fallback: str = "<p class='no-data'>No data available.</p>") -> str:
        return _fig_to_html(fig, div_id, fallback=fallback)

    price_gen = _fig_to_html(price_fig, "price-gen", include_plotlyjs="cdn", fallback="<p class='no-data'>No price data.</p>")
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
    categorized_stats_html = _build_categorized_stats(stats_returns, stats_pnls, stats_general, result)
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
        price_gen=price_gen, price_tab=price_tab,
        equity_gen=equity_gen, equity_tab=equity_tab,
        dd_gen=dd_gen, dd_tab=dd_tab,
        monthly_gen=monthly_gen, dist_gen=dist_gen, dist_tab=dist_tab,
        rolling_gen=rolling_gen, rolling_tab=rolling_tab,
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


# ─────────────────────────────────────────────────────────────────────────────
# HTML page builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_page(
    result: BacktestResult,
    strategy_display: str,
    symbols_str: str,
    params_str: str,
    win_rate: float | None,
    profit_factor: float | None,
    sortino: float | None,
    calmar: float | None,
    price_gen: str, price_tab: str,
    equity_gen: str, equity_tab: str,
    dd_gen: str, dd_tab: str,
    monthly_gen: str, dist_gen: str, dist_tab: str,
    rolling_gen: str, rolling_tab: str,
    yearly_gen: str,
    rolling_equity_html: str,
    realized_pnl_html: str,
    trade_pnl_dist_html: str,
    trade_pnl_dist_trades_html: str,
    rolling_dd_html: str,
    monthly_yearly_html: str,
    per_trade_pnl_html: str,
    win_rate_donut_html: str,
    rolling_calmar_html: str,
    cum_trade_pnl_html: str,
    underwater_html: str,
    full_stats_html: str = "",
    risk_metrics_html: str = "",
    categorized_stats_html: str = "",
    logo_data_url: str = "",
) -> str:
    md_val = result.max_drawdown_pct
    md = f"{md_val:.1f}%" if md_val is not None else "—"
    sharpe_str = f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio is not None else "—"
    win_rate_str = f"{win_rate*100:.1f}%" if win_rate is not None else "—"
    pf_str = f"{profit_factor:.2f}" if profit_factor is not None else "—"
    sortino_str = f"{sortino:.2f}" if sortino is not None else "—"
    calmar_str = f"{calmar:.2f}" if calmar is not None else "—"
    ret_cls = "positive" if result.total_return_pct >= 0 else "negative"
    md_cls = "negative" if (md_val is not None and md_val < 0) else ""
    rolling_window_label = "60-day"

    def kpi(label: str, value: str, cls: str = "", sub: str = "") -> str:
        sub_html = f'<span class="kpi-sub">{sub}</span>' if sub else ""
        return f'<div class="kpi"><span class="kpi-label">{label}</span><span class="kpi-value {cls}">{value}</span>{sub_html}</div>'

    kpis = (
        kpi("TOTAL RETURN", f"{result.total_return_pct:+.2f}%", ret_cls) +
        kpi("SHARPE", sharpe_str, "positive" if result.sharpe_ratio and result.sharpe_ratio > 1 else "") +
        kpi("SORTINO", sortino_str, "positive" if sortino and sortino > 1 else "") +
        kpi("MAX DRAWDOWN", md, md_cls) +
        kpi("WIN RATE", win_rate_str, "positive" if win_rate and win_rate > 0.5 else "negative" if win_rate and win_rate < 0.4 else "") +
        kpi("PROFIT FACTOR", pf_str, "positive" if profit_factor and profit_factor > 1.5 else "negative" if profit_factor and profit_factor < 1 else "") +
        kpi("TOTAL TRADES", str(result.num_trades)) +
        kpi("CALMAR", calmar_str, "positive" if calmar and calmar > 1 else "")
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Backtest Report — {strategy_display}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    /* ── Reset & Root ────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #080d14;
      --bg2: #0c1420;
      --card: #0f1c2e;
      --card2: #132035;
      --border: rgba(56,189,248,0.12);
      --border2: rgba(255,255,255,0.06);
      --text: #e2e8f0;
      --text-muted: #64748b;
      --text-dim: #334155;
      --accent: #38bdf8;
      --accent2: #0ea5e9;
      --positive: #34d399;
      --negative: #f87171;
      --warn: #fbbf24;
      --purple: #a78bfa;
      --font-mono: 'IBM Plex Mono', 'Courier New', monospace;
      --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
    }}
    [data-theme="light"] {{
      --bg: #f0f4f8; --bg2: #e8edf3; --card: #ffffff; --card2: #f8fafc;
      --border: rgba(14,165,233,0.15); --border2: rgba(0,0,0,0.07);
      --text: #0f172a; --text-muted: #475569; --text-dim: #94a3b8;
      --accent: #0ea5e9; --accent2: #0284c7;
      --positive: #059669; --negative: #dc2626; --warn: #d97706;
    }}
    body {{
      font-family: var(--font-sans); background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.5;
      background-image: radial-gradient(ellipse at 20% 0%, rgba(56,189,248,0.04) 0%, transparent 50%),
                        radial-gradient(ellipse at 80% 100%, rgba(167,139,250,0.03) 0%, transparent 50%);
    }}
    /* ── Layout ──────────────────────────────────────────── */
    .page {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem 2rem 3rem; }}
    /* ── Header ──────────────────────────────────────────── */
    .header {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 1.5rem; padding-bottom: 1rem;
      border-bottom: 1px solid var(--border2);
    }}
    .header-left {{ display: flex; align-items: center; gap: 1rem; }}
    .logo {{ height: 36px; width: auto; object-fit: contain; }}
    .header-title {{
      display: flex; flex-direction: column; gap: 0.1rem;
    }}
    .header-title h1 {{
      font-family: var(--font-mono); font-size: 1.1rem; font-weight: 600;
      color: var(--text); letter-spacing: 0.05em;
    }}
    .header-title .subtitle {{
      font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted);
      letter-spacing: 0.1em;
    }}
    .header-right {{ display: flex; align-items: center; gap: 1rem; }}
    .date-badge {{
      font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted);
      background: var(--card); border: 1px solid var(--border2); border-radius: 6px;
      padding: 0.35rem 0.75rem; letter-spacing: 0.05em;
    }}
    .theme-btn {{
      padding: 0.35rem 0.75rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 6px; cursor: pointer; font-family: var(--font-sans); font-size: 0.75rem;
      color: var(--text-muted); transition: all 0.15s;
    }}
    .theme-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    /* ── Strategy info bar ───────────────────────────────── */
    .info-bar {{
      display: flex; gap: 2rem; align-items: center; flex-wrap: wrap;
      padding: 0.75rem 1.25rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 10px; margin-bottom: 1.25rem; font-family: var(--font-mono); font-size: 0.75rem;
    }}
    .info-item {{ display: flex; gap: 0.5rem; align-items: center; }}
    .info-label {{ color: var(--text-muted); }}
    .info-value {{ color: var(--accent); font-weight: 500; }}
    /* ── KPI Strip ───────────────────────────────────────── */
    .kpi-strip {{
      display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.6rem;
      margin-bottom: 1.25rem;
    }}
    @media (max-width: 1100px) {{ .kpi-strip {{ grid-template-columns: repeat(4, 1fr); }} }}
    @media (max-width: 600px) {{ .kpi-strip {{ grid-template-columns: repeat(2, 1fr); }} }}
    .kpi {{
      background: var(--card); border: 1px solid var(--border2); border-radius: 10px;
      padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.3rem;
      transition: border-color 0.15s;
      position: relative; overflow: hidden;
    }}
    .kpi::before {{
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
      background: var(--accent); opacity: 0.3; transition: opacity 0.15s;
    }}
    .kpi:hover {{ border-color: var(--border); }}
    .kpi:hover::before {{ opacity: 0.8; }}
    .kpi-label {{ font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-muted); letter-spacing: 0.12em; text-transform: uppercase; }}
    .kpi-value {{ font-family: var(--font-mono); font-size: 1.25rem; font-weight: 600; color: var(--text); }}
    .kpi-value.positive {{ color: var(--positive); }}
    .kpi-value.negative {{ color: var(--negative); }}
    .kpi-sub {{ font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-muted); }}
    /* ── Stats grid (expanded metrics) ──────────────────── */
    .stats-toggle-wrap {{ margin-bottom: 1.25rem; }}
    .stats-toggle-btn {{
      display: flex; align-items: center; gap: 0.5rem; padding: 0.45rem 1rem;
      background: var(--card); border: 1px solid var(--border2); border-radius: 8px;
      cursor: pointer; font-family: var(--font-sans); font-size: 0.8rem; color: var(--text-muted);
      transition: all 0.15s;
    }}
    .stats-toggle-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    .stats-toggle-btn .arrow {{ font-size: 0.6rem; transition: transform 0.2s; }}
    .stats-toggle-btn.open .arrow {{ transform: rotate(180deg); }}
    .stats-panel {{
      display: none; padding: 1.25rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 10px; margin-top: 0.5rem;
    }}
    .stats-panel.open {{ display: block; }}
    .stats-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.25rem;
    }}
    @media (max-width: 900px) {{ .stats-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .stats-section {{ }}
    .stats-section-title {{
      font-family: var(--font-mono); font-size: 0.65rem; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--accent); margin-bottom: 0.6rem;
      padding-bottom: 0.4rem; border-bottom: 1px solid var(--border2);
    }}
    .stats-mini-table {{ width: 100%; border-collapse: collapse; }}
    .stats-mini-table tr:not(:last-child) td {{ border-bottom: 1px solid var(--border2); }}
    .stats-mini-table .sk {{
      padding: 0.3rem 0; font-family: var(--font-sans); font-size: 0.75rem; color: var(--text-muted); width: 60%;
    }}
    .stats-mini-table .sv {{
      padding: 0.3rem 0; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text); text-align: right;
    }}
    .stats-mini-table .sv.pos {{ color: var(--positive); }}
    .stats-mini-table .sv.neg {{ color: var(--negative); }}
    /* ── Tabs ────────────────────────────────────────────── */
    .tabs {{
      display: flex; gap: 0.25rem; margin-bottom: 1rem; flex-wrap: wrap;
      border-bottom: 1px solid var(--border2); padding-bottom: 0.75rem;
    }}
    .tab {{
      padding: 0.4rem 1rem; border: 1px solid transparent; border-radius: 6px;
      cursor: pointer; font-family: var(--font-sans); font-size: 0.8rem; color: var(--text-muted);
      background: transparent; transition: all 0.15s; font-weight: 500;
    }}
    .tab:hover {{ color: var(--text); border-color: var(--border2); }}
    .tab.active {{ background: var(--accent); color: #0c1420; border-color: var(--accent); font-weight: 600; }}
    /* ── Tab content & chart wraps ───────────────────────── */
    .tab-content {{ display: none; }}
    .chart-wrap {{
      background: var(--card); border: 1px solid var(--border2); border-radius: 10px;
      padding: 1rem 1rem 0.75rem; position: relative; overflow: hidden;
    }}
    .chart-wrap-title {{
      font-family: var(--font-mono); font-size: 0.7rem; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 0.5rem;
    }}
    /* Overview tab: 2-col grid */
    #overview.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #overview.active .span-2 {{ grid-column: 1 / -1; }}
    /* Equity & Returns tab */
    #equity-returns.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #equity-returns.active .span-2 {{ grid-column: 1 / -1; }}
    /* Risk tab */
    #risk.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #risk.active .span-2 {{ grid-column: 1 / -1; }}
    /* Trades tab */
    #trades.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #trades.active .span-2 {{ grid-column: 1 / -1; }}
    /* Price tab */
    #price.active {{ display: block; }}
    /* Plotly heights */
    .h-sm  .plotly-graph-div {{ min-height: 220px !important; height: 220px !important; }}
    .h-md  .plotly-graph-div {{ min-height: 280px !important; height: 280px !important; }}
    .h-lg  .plotly-graph-div {{ min-height: 300px !important; height: 300px !important; }}
    .h-xl  .plotly-graph-div {{ min-height: 480px !important; height: 480px !important; }}
    .h-monthly .plotly-graph-div {{ min-height: 200px !important; height: auto !important; }}
    /* ── Risk metrics table ──────────────────────────────── */
    .metrics-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
    .metrics-table th, .metrics-table td {{ padding: 0.45rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border2); }}
    .metrics-table th {{ font-family: var(--font-mono); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }}
    .metrics-table td:first-child {{ color: var(--text-muted); font-family: var(--font-sans); }}
    .metrics-table td:last-child {{ font-family: var(--font-mono); color: var(--text); text-align: right; }}
    /* ── No-data placeholder ─────────────────────────────── */
    .no-data {{ color: var(--text-muted); padding: 3rem 2rem; text-align: center; font-family: var(--font-mono); font-size: 0.8rem; letter-spacing: 0.05em; }}
    /* ── Footer ──────────────────────────────────────────── */
    .footer {{
      margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border2);
      font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-dim);
      display: flex; justify-content: space-between; align-items: center;
    }}
    /* ── Print ───────────────────────────────────────────── */
    @media print {{
      body {{ background: white; color: black; }}
      .theme-btn, .stats-toggle-btn, .tabs {{ display: none; }}
      .tab-content {{ display: block !important; page-break-before: always; }}
    }}
  </style>
</head>
<body>
<div class="page">

  <!-- ── Header ── -->
  <div class="header">
    <div class="header-left">
      {f'<img src="{logo_data_url}" alt="Digi" class="logo" />' if logo_data_url else ''}
      <div class="header-title">
        <h1>BACKTEST REPORT</h1>
        <span class="subtitle">DIGIQUANT · NAUTILUSTRADER</span>
      </div>
    </div>
    <div class="header-right">
      <span class="date-badge">{result.start_time[:10]} → {result.end_time[:10]}</span>
      <button class="theme-btn" id="themeToggle">☀ Light</button>
    </div>
  </div>

  <!-- ── Strategy info bar ── -->
  <div class="info-bar">
    <div class="info-item"><span class="info-label">STRATEGY</span><span class="info-value">{strategy_display}</span></div>
    <div class="info-item"><span class="info-label">INSTRUMENTS</span><span class="info-value">{symbols_str}</span></div>
    <div class="info-item"><span class="info-label">PARAMS</span><span class="info-value">{params_str}</span></div>
    <div class="info-item"><span class="info-label">TOTAL P&L</span><span class="info-value" style="color:{'var(--positive)' if result.total_pnl >= 0 else 'var(--negative)'}">${result.total_pnl:,.2f}</span></div>
  </div>

  <!-- ── KPI Strip ── -->
  <div class="kpi-strip">{kpis}</div>

  <!-- ── Expanded metrics panel ── -->
  <div class="stats-toggle-wrap">
    <button class="stats-toggle-btn" id="statsToggle">
      <span>Detailed metrics</span><span class="arrow">▼</span>
    </button>
    <div class="stats-panel" id="statsPanel">{categorized_stats_html}</div>
  </div>

  <!-- ── Tabs ── -->
  <div class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="equity-returns">Equity &amp; Returns</button>
    <button class="tab" data-tab="risk">Risk</button>
    <button class="tab" data-tab="trades">Trades</button>
    <button class="tab" data-tab="price">Price</button>
  </div>

  <!-- ── Overview tab ── -->
  <div class="tab-content" id="overview">
    <div class="chart-wrap span-2 h-xl"><div class="chart-wrap-title">Price + Bollinger Bands + Entries &amp; Exits</div>{price_gen}</div>
    <div class="chart-wrap h-lg"><div class="chart-wrap-title">Equity Curve</div>{equity_gen}</div>
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Drawdown</div>{dd_gen}</div>
    <div class="chart-wrap span-2 h-monthly"><div class="chart-wrap-title">Monthly &amp; Yearly Returns</div>{monthly_yearly_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Returns Distribution</div>{dist_gen}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Sharpe Ratio</div>{rolling_gen}</div>
  </div>

  <!-- ── Equity & Returns tab ── -->
  <div class="tab-content" id="equity-returns">
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Rolling Equity (Daily)</div>{rolling_equity_html}</div>
    <div class="chart-wrap span-2 h-monthly"><div class="chart-wrap-title">Monthly &amp; Yearly Returns Heatmap</div>{monthly_yearly_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Returns Distribution</div>{dist_tab}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Sharpe ({rolling_window_label})</div>{rolling_tab}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Calmar Ratio</div>{rolling_calmar_html}</div>
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Cumulative Realized P&amp;L</div>{realized_pnl_html}</div>
  </div>

  <!-- ── Risk tab ── -->
  <div class="tab-content" id="risk">
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Drawdown</div>{dd_tab}</div>
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Underwater Equity</div>{underwater_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Max Drawdown (60-day)</div>{rolling_dd_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Trade P&amp;L Distribution</div>{trade_pnl_dist_html}</div>
    <div class="chart-wrap span-2"><div class="chart-wrap-title">Risk Metrics</div>{risk_metrics_html}</div>
  </div>

  <!-- ── Trades tab ── -->
  <div class="tab-content" id="trades">
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Per-Trade P&amp;L</div>{per_trade_pnl_html}</div>
    <div class="chart-wrap h-lg"><div class="chart-wrap-title">Cumulative P&amp;L by Trade #</div>{cum_trade_pnl_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Win / Loss Split</div>{win_rate_donut_html}</div>
    <div class="chart-wrap span-2 h-md"><div class="chart-wrap-title">Trade P&amp;L Distribution (Winners vs Losers)</div>{trade_pnl_dist_trades_html}</div>
  </div>

  <!-- ── Price tab ── -->
  <div class="tab-content" id="price">
    <div class="chart-wrap h-xl"><div class="chart-wrap-title">Price + Bollinger Bands + Entries &amp; Exits</div>{price_tab}</div>
  </div>

  <div class="footer">
    <span>DigiQuant Backtest Report — Generated from NautilusTrader</span>
    <span id="gen-time"></span>
  </div>
</div>

<script>
(function() {{
  // ── Theme ──────────────────────────────────────────────────────────
  const STORAGE_KEY = 'dq-theme';
  const DARK_LAYOUT = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(255,255,255,0.03)',
    font: {{ color: '#94a3b8', family: "'IBM Plex Mono','Courier New',monospace", size: 11 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {{ color: '#64748b', size: 10 }} }},
    yaxis: {{ gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {{ color: '#64748b', size: 10 }} }},
  }};
  const LIGHT_LAYOUT = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0.02)',
    font: {{ color: '#475569', family: "'IBM Plex Mono','Courier New',monospace", size: 11 }},
    xaxis: {{ gridcolor: 'rgba(0,0,0,0.05)', linecolor: 'rgba(0,0,0,0.1)', tickfont: {{ color: '#94a3b8', size: 10 }} }},
    yaxis: {{ gridcolor: 'rgba(0,0,0,0.05)', linecolor: 'rgba(0,0,0,0.1)', tickfont: {{ color: '#94a3b8', size: 10 }} }},
  }};

  function isDark() {{ return document.documentElement.getAttribute('data-theme') !== 'light'; }}

  function applyTheme(dark) {{
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = dark ? '☀ Light' : '☾ Dark';
    try {{ localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light'); }} catch(e) {{}}
    if (typeof Plotly === 'undefined') return;
    const layout = dark ? DARK_LAYOUT : LIGHT_LAYOUT;
    document.querySelectorAll('.plotly-graph-div').forEach(div => {{
      if (!div.id) return;
      try {{ Plotly.relayout(div.id, layout); }} catch(e) {{}}
    }});
  }}

  const stored = (function() {{ try {{ return localStorage.getItem(STORAGE_KEY); }} catch(e) {{ return null; }} }})();
  const darkDefault = stored ? stored === 'dark' : true;
  document.documentElement.setAttribute('data-theme', darkDefault ? 'dark' : 'light');
  document.getElementById('themeToggle').textContent = darkDefault ? '☀ Light' : '☾ Dark';
  setTimeout(() => applyTheme(darkDefault), 200);
  document.getElementById('themeToggle').addEventListener('click', () => applyTheme(!isDark()));

  // ── Tabs ───────────────────────────────────────────────────────────
  document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      const el = document.getElementById(tab.dataset.tab);
      if (el) {{
        el.classList.add('active');
        if (typeof Plotly !== 'undefined') {{
          setTimeout(() => el.querySelectorAll('.plotly-graph-div').forEach(d => Plotly.Plots.resize(d)), 60);
        }}
      }}
    }});
  }});
  // Activate first tab
  const firstTab = document.querySelector('.tab-content[id="overview"]');
  if (firstTab) firstTab.classList.add('active');

  // ── Stats toggle ───────────────────────────────────────────────────
  const toggleBtn = document.getElementById('statsToggle');
  const statsPanel = document.getElementById('statsPanel');
  if (toggleBtn && statsPanel) {{
    toggleBtn.addEventListener('click', () => {{
      toggleBtn.classList.toggle('open');
      statsPanel.classList.toggle('open');
    }});
  }}

  // ── Generation timestamp ───────────────────────────────────────────
  const gt = document.getElementById('gen-time');
  if (gt) gt.textContent = 'Generated ' + new Date().toLocaleString();
}})();
</script>
</body>
</html>"""