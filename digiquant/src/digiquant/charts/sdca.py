"""matplotlib SDCA diagnostic figures (log equity, index, indicators, allocation).

Reads a published ``TearsheetData`` JSON (schema 1.3, with or without the
allocation / fill / indicator overlays). Allocation is always
``100 * units * price / (cash + units * price)`` — never ``capital_deployed``.

Fill dots: ``book_frac = |trade_usd| / portfolio`` that day, from actual fills
(or reconstructed Δunits when the payload predates ``fill_markers``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from digiquant.strategies.sdca.chart_series import (
    SdcaFillMarker,
    SdcaIndicatorCurve,
    chart_inputs_from_payload,
)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
except ImportError:  # pragma: no cover — optional visualization extra
    matplotlib = None  # type: ignore[assignment]
    _plt = None  # type: ignore[assignment]

_MPL_RC = {
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "figure.facecolor": "white",
    "axes.facecolor": "#fbfbfc",
    "axes.grid": True,
    "grid.color": "#e5e7eb",
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.edgecolor": "#d1d5db",
}

_BUY = "#1a7f37"
_SELL = "#c0392b"
_SDCA = "#0b5fff"
_HOLD = "#6b7280"
_INDEX = "#111827"
_CASH = "#9ca3af"
_BTC_FAINT = "#9ca3af"


def _dates(values: Sequence[str]) -> list[datetime]:
    return [datetime.fromisoformat(str(t)[:10]) for t in values]


def _require_mpl():
    if _plt is None:
        raise ImportError(
            "matplotlib is required for SDCA diagnostic charts (install digiquant[visualization])"
        )
    _plt.rcParams.update(_MPL_RC)
    return _plt


def plot_equity_vs_hold(inputs: Mapping[str, object], path: Path) -> Path:
    """SDCA mark-to-market equity vs lump (BTC buy-and-hold), log scale."""
    plt = _require_mpl()
    dates = _dates(inputs["dates"])  # type: ignore[arg-type]
    fig, ax = plt.subplots(figsize=(12.5, 6.2), dpi=160)
    ax.set_yscale("log")
    ax.plot(dates, inputs["equity"], color=_SDCA, lw=1.8, label="SDCA equity")
    lump = inputs["lump"]
    if lump:
        lump_t = _dates([t for t, _ in lump])  # type: ignore[misc]
        lump_v = [v for _, v in lump]  # type: ignore[misc]
        ax.plot(
            lump_t,
            lump_v,
            color=_HOLD,
            lw=1.3,
            ls="--",
            label="BTC buy-and-hold (lump)",
        )
    ax.set_ylabel("Portfolio value (USD, log)")
    ax.set_title(
        f"{inputs['strategy']} equity vs BTC buy-and-hold  "
        f"({inputs['period_start']} → {inputs['period_end']})"
    )
    ax.legend(frameon=False, loc="upper left")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"${v:,.0f}"))
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_valuation_index(inputs: Mapping[str, object], path: Path) -> Path:
    """Power-law risk 0–100 with accumulate/distribute knees and faint log BTC."""
    plt = _require_mpl()
    risk = inputs["risk"]
    if not risk:
        raise ValueError("plot_valuation_index requires risk_curve")
    risk_t = _dates([t for t, _ in risk])  # type: ignore[misc]
    risk_v = [v for _, v in risk]  # type: ignore[misc]
    knees = inputs["knees"]
    buy_k = float(knees.buy_knee_risk)  # type: ignore[union-attr]
    sell_k = float(knees.sell_knee_risk)  # type: ignore[union-attr]

    fig, ax = plt.subplots(figsize=(12.5, 6.2), dpi=160)
    ax.set_ylim(0, 100)
    ax.plot(risk_t, risk_v, color=_INDEX, lw=1.5, label="power-law risk")
    ax.axhline(
        buy_k,
        color=_BUY,
        ls="--",
        lw=1.2,
        label=f"accumulate starts (oversold, risk {buy_k:.0f})",
    )
    ax.axhline(
        sell_k,
        color=_SELL,
        ls="--",
        lw=1.2,
        label=f"distribute starts (overbought, risk {sell_k:.0f})",
    )
    ax.set_ylabel("Composite valuation index (0 cheap → 100 rich)")

    prices = inputs["prices"]
    dates = _dates(inputs["dates"])  # type: ignore[arg-type]
    finite = [(d, p) for d, p in zip(dates, prices, strict=True) if p == p and p > 0]
    if finite:
        ax2 = ax.twinx()
        ax2.set_yscale("log")
        ax2.plot(
            [d for d, _ in finite],
            [p for _, p in finite],
            color=_BTC_FAINT,
            lw=1.0,
            alpha=0.35,
            label="BTC (log)",
            zorder=0,
        )
        ax2.set_ylabel("BTC price (USD, log)", color=_HOLD)
        ax2.tick_params(axis="y", colors=_HOLD)
        ax2.spines["right"].set_color(_HOLD)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"${v:,.0f}"))
        ax.set_zorder(ax2.get_zorder() + 1)
        ax.patch.set_visible(False)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left", fontsize=9)
    else:
        ax.legend(frameon=False, loc="upper left", fontsize=9)

    ax.set_title("Composite valuation index — accumulate / distribute knees")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_indicator_multiples(inputs: Mapping[str, object], path: Path) -> Path:
    """Small multiples of catalog indicators. Included members first; extras unused."""
    plt = _require_mpl()
    indicators: list[SdcaIndicatorCurve] = list(inputs["indicators"])  # type: ignore[arg-type]
    n = max(len(indicators), 1)
    cols = 2
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(12.5, 2.6 * rows + 0.8), dpi=160, sharex=True)
    flat = list(axes.ravel()) if n > 1 or rows * cols > 1 else [axes]
    for i, ax in enumerate(flat):
        if i >= n:
            ax.set_visible(False)
            continue
        ind = indicators[i]
        color = _INDEX if ind.in_index else _HOLD
        alpha = 1.0 if ind.in_index else 0.45
        title = ind.display_name
        if ind.in_index:
            title = f"{title}  (in index, weight {ind.weight:g})"
        else:
            title = f"{title}  (not in index, weight 0)"
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_ylim(0, 100)
        if ind.points:
            ts = _dates([str(p["t"]) for p in ind.points])
            vs = [float(p["v"]) for p in ind.points]
            ax.plot(ts, vs, color=color, lw=1.2, alpha=alpha)
        else:
            ax.text(
                0.5,
                0.5,
                "no series (weight 0, not blended)",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color=_HOLD,
                fontsize=9,
            )
        ax.set_ylabel("0–100")
    fig.suptitle("Underlying indicators (included members in the composite; weight 0 unused)", y=1.01)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_allocation(inputs: Mapping[str, object], path: Path) -> Path:
    """Step % allocated / % cash, log BTC overlay, sized green/red fill dots."""
    plt = _require_mpl()
    dates = _dates(inputs["dates"])  # type: ignore[arg-type]
    allocated: list[float] = list(inputs["allocated_pct"])  # type: ignore[arg-type]
    cash_pct: list[float] = list(inputs["cash_pct"])  # type: ignore[arg-type]
    markers: list[SdcaFillMarker] = list(inputs["fill_markers"])  # type: ignore[arg-type]

    fig, ax = plt.subplots(figsize=(12.5, 6.4), dpi=160)
    ax.set_ylim(0, 100)
    ax.step(dates, allocated, where="post", color=_SDCA, lw=1.6, label="% allocated")
    ax.fill_between(dates, allocated, step="post", color=_SDCA, alpha=0.12)
    ax.step(dates, cash_pct, where="post", color=_CASH, lw=1.2, label="% cash")

    date_ix = {d.date(): (d, a) for d, a in zip(dates, allocated, strict=True)}
    buy_x, buy_y, buy_s, sell_x, sell_y, sell_s = [], [], [], [], [], []
    for m in markers:
        key = datetime.fromisoformat(m.t[:10]).date()
        hit = date_ix.get(key)
        if hit is None:
            continue
        x, y = hit
        size = 12.0 + 180.0 * min(m.book_frac, 0.25)
        if m.side == "buy":
            buy_x.append(x)
            buy_y.append(y)
            buy_s.append(size)
        else:
            sell_x.append(x)
            sell_y.append(y)
            sell_s.append(size)
    if buy_x:
        ax.scatter(
            buy_x,
            buy_y,
            s=buy_s,
            c=_BUY,
            alpha=0.55,
            zorder=5,
            linewidths=0,
            label="buy (dot size ∝ |trade|/portfolio)",
        )
    if sell_x:
        ax.scatter(
            sell_x,
            sell_y,
            s=sell_s,
            c=_SELL,
            alpha=0.55,
            zorder=5,
            linewidths=0,
            label="sell (dot size ∝ |trade|/portfolio)",
        )

    prices = inputs["prices"]
    finite = [(d, p) for d, p in zip(dates, prices, strict=True) if p == p and p > 0]
    if finite:
        ax2 = ax.twinx()
        ax2.set_yscale("log")
        ax2.plot(
            [d for d, _ in finite],
            [p for _, p in finite],
            color=_BTC_FAINT,
            lw=1.0,
            alpha=0.4,
            label="BTC (log)",
        )
        ax2.set_ylabel("BTC price (USD, log)", color=_HOLD)
        ax2.tick_params(axis="y", colors=_HOLD)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"${v:,.0f}"))
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left", fontsize=8)
    else:
        ax.legend(frameon=False, loc="upper left", fontsize=8)

    ax.set_ylabel("Percent of book")
    ax.set_title(
        "Allocation — % in BTC vs % cash (step). "
        "Dots are actual fills, sized by |trade_usd| / portfolio that day."
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _window_chart_inputs(
    inputs: dict[str, object],
    date_start: str | None,
    date_end: str | None,
) -> dict[str, object]:
    """Inclusive YYYY-MM-DD slice of daily series (for a 2025 zoom, etc.)."""
    dates: list[str] = list(inputs["dates"])  # type: ignore[arg-type]
    keep = [
        (date_start is None or d >= date_start) and (date_end is None or d <= date_end)
        for d in dates
    ]
    if all(keep):
        return inputs
    idx = [i for i, ok in enumerate(keep) if ok]
    if not idx:
        raise ValueError(f"date window {date_start} → {date_end} is empty")
    lo, hi = idx[0], idx[-1] + 1
    windowed = dict(inputs)
    windowed["dates"] = dates[lo:hi]
    windowed["equity"] = list(inputs["equity"])[lo:hi]  # type: ignore[index]
    windowed["prices"] = list(inputs["prices"])[lo:hi]  # type: ignore[index]
    windowed["allocated_pct"] = list(inputs["allocated_pct"])[lo:hi]  # type: ignore[index]
    windowed["cash_pct"] = list(inputs["cash_pct"])[lo:hi]  # type: ignore[index]
    start_d, end_d = dates[lo], dates[hi - 1]
    windowed["period_start"] = start_d
    windowed["period_end"] = end_d

    def _clip_pairs(pairs: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
        return [(t, v) for t, v in pairs if start_d <= t[:10] <= end_d]

    windowed["risk"] = _clip_pairs(inputs["risk"])  # type: ignore[arg-type]
    windowed["lump"] = _clip_pairs(inputs["lump"])  # type: ignore[arg-type]
    windowed["flat_dca"] = _clip_pairs(inputs["flat_dca"])  # type: ignore[arg-type]
    markers: list[SdcaFillMarker] = list(inputs["fill_markers"])  # type: ignore[arg-type]
    windowed["fill_markers"] = [m for m in markers if start_d <= m.t[:10] <= end_d]
    indicators: list[SdcaIndicatorCurve] = []
    for ind in inputs["indicators"]:  # type: ignore[union-attr]
        pts = [p for p in ind.points if start_d <= str(p["t"])[:10] <= end_d]
        indicators.append(ind.model_copy(update={"points": pts}))
    windowed["indicators"] = indicators
    return windowed


def render_sdca_diagnostic_charts(
    payload: Mapping[str, object],
    out_dir: Path,
    *,
    prefix: str = "sdca",
    date_start: str | None = None,
    date_end: str | None = None,
) -> list[Path]:
    """Write the four diagnostic PNGs. Returns paths in chart order."""
    inputs = chart_inputs_from_payload(payload)
    if date_start or date_end:
        inputs = _window_chart_inputs(inputs, date_start, date_end)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        plot_equity_vs_hold(inputs, out_dir / f"{prefix}_equity_vs_hold.png"),
        plot_valuation_index(inputs, out_dir / f"{prefix}_power_law_risk.png"),
        plot_indicator_multiples(inputs, out_dir / f"{prefix}_indicator_multiples.png"),
        plot_allocation(inputs, out_dir / f"{prefix}_allocation.png"),
    ]


__all__ = [
    "plot_allocation",
    "plot_equity_vs_hold",
    "plot_indicator_multiples",
    "plot_valuation_index",
    "render_sdca_diagnostic_charts",
]
