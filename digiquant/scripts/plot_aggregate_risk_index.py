#!/usr/bin/env python3
"""Plot the aggregate SDCA valuation index (composite risk, 0-100) over time.

Context: Chris reviewed the per-indicator diagnostic charts
(plot_indicator_diagnostics.py) and, after a detour into M2 rate-of-change
period tuning (which failed the walk-forward stability gate -- see
run_m2_short_roc_walk_forward.py), wants to go back to reviewing charts and
see the *aggregate* composite index itself: BTC price on top, the blended
risk score (0-100) below with the buy/sell curve knee thresholds shaded as
reference bands, so he can see how the combined signal actually behaves
across cycles (not just each indicator individually).

Uses load_frozen_index() with today's published settings.json weights (the
validated baseline: power_law=1.0, m2=0.5, dxy=0.5) -- i.e. exactly the
index the live btc_optimized curve trades against. Not a new indicator or
signal -- pure visualization of existing production output.

Diagnostic only. No settings.json/RESEARCH_STATE.md writes.

Usage:
    uv run python -m scripts.plot_aggregate_risk_index
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from digiquant.strategies.sdca.curve_optimize import load_frozen_index, published_curve_shape

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"
OUTPUT_PATH = DIGIQUANT_ROOT / "reports" / "aggregate_risk_index.html"


def run(cache_dir: Path = DEFAULT_CACHE_DIR, output_path: Path = OUTPUT_PATH) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir)
    shape = published_curve_shape()

    dates_l = dates.to_list()
    prices_l = prices.to_list()
    risk_l = risk.to_list()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.45],
        vertical_spacing=0.05,
        subplot_titles=("BTC-USD close (log)", "Aggregate composite risk (0-100)"),
    )

    fig.add_trace(
        go.Scatter(x=dates_l, y=prices_l, name="BTC-USD close", line=dict(color="#1f77b4")),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(x=dates_l, y=risk_l, name="composite risk", line=dict(color="#d62728")),
        row=2,
        col=1,
    )

    # Reference bands: buy zone (risk <= buy_knee_risk), sell zone (risk >= sell_knee_risk).
    fig.add_hrect(
        y0=0,
        y1=shape.buy_knee_risk,
        fillcolor="#2ca02c",
        opacity=0.12,
        line_width=0,
        row=2,
        col=1,
        annotation_text=f"buy zone (<= {shape.buy_knee_risk:.1f})",
        annotation_position="top left",
    )
    fig.add_hrect(
        y0=shape.sell_knee_risk,
        y1=100,
        fillcolor="#d62728",
        opacity=0.10,
        line_width=0,
        row=2,
        col=1,
        annotation_text=f"sell zone (>= {shape.sell_knee_risk:.1f})",
        annotation_position="bottom left",
    )
    fig.add_hline(y=50, line=dict(color="gray", dash="dot", width=1), row=2, col=1)

    fig.update_yaxes(type="log", title_text="price ($)", row=1, col=1)
    fig.update_yaxes(range=[0, 100], title_text="risk", row=2, col=1)
    fig.update_layout(
        title=(
            f"Aggregate composite risk index vs. BTC price "
            f"(weights: power_law={weights.power_law}, m2={weights.m2}, dxy={weights.dxy})"
        ),
        height=800,
        margin=dict(t=80, b=40, l=60, r=60),
        legend=dict(orientation="h", y=1.05),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs="cdn")
    print(f"wrote aggregate risk index chart to {output_path}")


if __name__ == "__main__":
    run()
