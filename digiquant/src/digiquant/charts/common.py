"""Shared chart layout and helpers for DigiQuant tearsheets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any  # noqa: ANN401 — plotly Figure typing

import polars as pl

logger = logging.getLogger(__name__)


def _extract_frame(series: Any) -> pl.DataFrame | None:
    """Normalise a returns/PnL series to a Polars DataFrame (date: Utf8, value: Float64).

    Accepts:
    - A duck-typed pandas Series (from the NautilusTrader boundary in nautilus_runner.py).
      Accessed via ``.values`` / ``.index`` only — no pandas module import needed.
    - A Polars Series (via ``.to_list()``).
    - Any iterable with a ``.tolist()`` or ``list()`` fallback (values-only; date column
      will be sequential integer strings).

    Non-finite and null values are dropped. Returns ``None`` if the result is empty.
    """
    if series is None:
        return None

    try:
        if hasattr(series, "values") and hasattr(series, "index"):
            # Duck-typed pandas Series — extract without importing pandas.
            raw_vals = series.values.tolist()
            raw_dates = [str(d)[:10] for d in series.index]
        elif hasattr(series, "to_list"):
            # Polars Series (or similar).
            raw_vals = series.to_list()
            raw_dates = [str(i) for i in range(len(raw_vals))]
        elif hasattr(series, "tolist"):
            raw_vals = series.tolist()
            raw_dates = [str(i) for i in range(len(raw_vals))]
        else:
            raw_vals = list(series)
            raw_dates = [str(i) for i in range(len(raw_vals))]

        pl_vals = pl.Series("value", raw_vals).cast(pl.Float64, strict=False)
        df = pl.DataFrame({"date": raw_dates, "value": pl_vals})
        df = df.filter(pl.col("value").is_not_null() & pl.col("value").is_finite())
        return df if len(df) > 0 else None
    except Exception:
        return None


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
