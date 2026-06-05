"""Price and Bollinger band chart builder."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — plotly Figure typing

from digiquant.charts.common import (
    ChartUnavailable,
    _CHART_BUILD_ERRORS,
    _apply_layout,
    _compute_bollinger_bands,
)


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
