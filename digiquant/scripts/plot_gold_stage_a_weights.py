#!/usr/bin/env python3
"""The four gold Stage A weight runs on one GLD history (#4804).

One hand-rolled stdlib SVG (no matplotlib — it is not installed in this environment;
no numpy/pandas/nautilus), mirroring ``plot_gold_pin_sets_v2.py``. Four stacked
panels, one per run of ``digiquant/scripts/run_gold_stage_a_weights.py``: both
approved gold pin sets x both ``require_extras`` settings, so the reader can see the
valuation-only rows and the forced-blend rows side by side rather than only the
flattering one.

Each panel draws:

- the composite **risk** curve that run's winning weights produce, over the same GLD
  calendar (min-max binned, so the 2011/2015 lows survive);
- the **35.0 accumulate / 80.0 distribute bands** as labelled rules — the two rails
  the cycle-overlap objective actually measures against;
- the **pin-set windows** for that panel's pin set, shaded and marked: trough windows
  green (the buy side), peak windows red (the sell side).

The runs are **recomputed here by importing the runner**, not read from a cached
curve: the weights are the artifact, and recomputing means the figure cannot drift
away from the numbers the script reports. The risk curve is a SHAPE, not a price
path, and it is not a portfolio curve — no dollars, no equity, no allocation.

**IN-SAMPLE, and the objective is a DIAGNOSTIC.** Every leg's params are a max over
a frozen indicator grid and every weight is a max over the weight grid, both scored
against cycle windows derived from the SAME GLD history the z-series are built from,
so these are partly-selected upper bounds — not out-of-sample evidence. The scored
objective is cycle-window **overlap**, a shape diagnostic. **This is NOT a
performance claim and NOT a backtest result:** the published keep/drop is
``optimize_stage_a_by_backtest`` on in-sample ``vs_flat_dca_pct`` under a 10%
deployed floor and a 50% drawdown cap. No return, Sharpe, drawdown, trade count or
time-in-market is claimed anywhere in this figure, and the risk axis is unitless
composite risk, not a portfolio value.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from xml.sax.saxutils import escape

import polars as pl

from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import ACCUMULATE_RISK_MAX, DISTRIBUTE_RISK_MIN

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_gold_stage_a_weights.py"
SYMBOL = "GLD-USD"
DATA_PATH = ROOT / "data" / "price-history" / f"{SYMBOL}.csv"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_stage_a_weights.svg"

# ``cycle_windows.py::_HALF_WINDOW``, restated so the figure cannot silently follow a
# later change to the production module.
HALF_WINDOW_DAYS = 45

# Min-max binning keeps each risk polyline under this many points.
MAX_POLYLINE_POINTS = 2000

# The composite-risk axis is 0..100 by construction (composite_risk.py maps
# z in [-3, 3] onto risk in [100, 0]); drawn with headroom either side.
RISK_MIN, RISK_MAX = -6.0, 106.0

TITLE = (
    "Gold Stage A variable-weight calibration: composite risk under each winning "
    "weight set, both pin sets x both require_extras"
)
SUBTITLE = (
    "four runs over GLD-USD 2004-11-18..2026-09-29 | accumulate band <= "
    f"{ACCUMULATE_RISK_MAX:.0f} / distribute band >= {DISTRIBUTE_RISK_MIN:.0f} | "
    "objective = spread + 25 x (trough_frac + peak_frac), a cycle-overlap SHAPE "
    "diagnostic"
)

FOOTER = (
    "IN-SAMPLE, AND THE OBJECTIVE IS A DIAGNOSTIC. Composite risk above is the shipped "
    "blend at each run's winning weights: a unitless 0..100 index, NOT a portfolio "
    "value, NOT an equity curve, NOT an allocation. Every indicator's params are a MAX "
    "over a frozen grid and every weight is a MAX over the weight grid, both scored "
    "against cycle windows derived from the SAME GLD history the series are built from, "
    "so these are partly-selected upper bounds, not out-of-sample evidence. The scored "
    "objective is cycle-window overlap, a shape diagnostic: THIS IS NOT A PERFORMANCE "
    "CLAIM AND NOT A BACKTEST RESULT. The published keep/drop is "
    "optimize_stage_a_by_backtest on in-sample vs_flat_dca_pct under a 10% deployed "
    "floor and a 50% drawdown cap; nothing here was kept or dropped on this figure. No "
    "return, Sharpe, drawdown, trade count or time-in-market is claimed. Stage A only: "
    "Stage B freezes weights, then regularize. Regenerate: "
    "digiquant/scripts/plot_gold_stage_a_weights.py"
)

W = 1560
MARGIN_L, MARGIN_R = 148, 138
TITLE_Y = 22
SUB_Y = 40
PANEL_H = 236
PANEL_GAP = 18
AXIS_Y = 74
LABEL_W = 140

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#ebebeb"
PEAK_COL = "#c62828"
TROUGH_COL = "#2e7d32"
RISK_COL = "#1f5fa8"
ACCUM_COL = "#2e7d32"
DISTRIB_COL = "#c62828"
BOX = "#dcdcdc"
BAND_FILL = "#f7f7f7"
RUN_COLS = ("#1f5fa8", "#7a5195", "#1b7f79", "#b35c00")


def _load_runner() -> ModuleType:
    """The Stage A runner, by file path. A research script, not a package module."""
    spec = importlib.util.spec_from_file_location("run_gold_stage_a_weights", RUNNER_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover — loader contract
        raise ImportError(f"cannot load the Stage A runner at {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_gold_stage_a_weights", module)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 11,
    fill: str = INK,
    anchor: str = "start",
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(text)}</text>'
    )


def _backed_text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 11,
    fill: str = INK,
    weight: str = "normal",
    anchor: str = "start",
    pad: str = "white",
    opacity: float = 0.88,
) -> str:
    """Text over a pad, so a label survives whatever band or rail it crosses."""
    width = 0.56 * size * len(text) + 8
    pad_x = x - width + 4 if anchor == "end" else x - 4
    return (
        f'<rect x="{pad_x:.1f}" y="{y - size + 1:.1f}" width="{width:.1f}" '
        f'height="{size + 4}" fill="{pad}" fill-opacity="{opacity}"/>'
        + _text(x, y, text, size=size, fill=fill, weight=weight, anchor=anchor)
    )


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if len(current) + len(word) + 1 > width and current:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _color(kind: str) -> str:
    return PEAK_COL if kind == "peak" else TROUGH_COL


def _minmax_series(
    dates: list[date], values: list[float | None], max_points: int
) -> list[tuple[date, float]]:
    """Min-max binned (date, value) pairs over the NON-NULL stretch, in order.

    Stride-sampling would drop the 2011/2015 lows and the 2020 spike the pin bands are
    drawn around; a per-bin min/max pair keeps both extremes while bounding the count.
    A null breaks the polyline (see ``_segmented_series``).
    """
    kept = [(d, v) for d, v in zip(dates, values, strict=True) if v is not None]
    if not kept:
        return []
    k_dates = [d for d, _ in kept]
    k_values = [float(v) for _, v in kept]
    n = len(k_values)
    n_bins = max(1, max_points // 2)
    if n_bins >= n:
        return list(zip(k_dates, k_values, strict=True))
    size = n / n_bins
    out: list[tuple[date, float]] = []
    for b in range(n_bins):
        lo_i = int(b * size)
        hi_i = max(lo_i + 1, int((b + 1) * size)) if b + 1 < n_bins else n
        hi_i = min(hi_i, n)
        if hi_i <= lo_i:
            continue
        seg = range(lo_i, hi_i)
        i_min = min(seg, key=lambda i: k_values[i])
        i_max = max(seg, key=lambda i: k_values[i])
        first, last = min(i_min, i_max), max(i_min, i_max)
        out.append((k_dates[first], k_values[first]))
        if last != first:
            out.append((k_dates[last], k_values[last]))
    return out


def _segmented_series(
    dates: list[date], values: list[float | None], max_points: int
) -> list[list[tuple[date, float]]]:
    """``_minmax_series`` split on nulls, so a warmup gap is a gap, not a straight line.

    Drawing across a null would invent risk on days the engine never scored — the one
    thing this figure must not do.
    """
    segments: list[list[tuple[date, float]]] = []
    current: list[date] = []
    current_values: list[float] = []
    for day, value in zip(dates, values, strict=True):
        if value is None:
            if current:
                segments.append(_minmax_series(current, current_values, max_points))
                current, current_values = [], []
            continue
        current.append(day)
        current_values.append(float(value))
    if current:
        segments.append(_minmax_series(current, current_values, max_points))
    return [segment for segment in segments if segment]


def _pin_rows(windows: SdcaCycleWindows) -> list[tuple[str, date, CycleKind]]:
    """``(name, pin, kind)`` in the order the factory declares them (chronological).

    The pin is the window's midpoint: ``CycleWindow`` stores the window, and the pin IS
    the centre by construction (``_window`` builds ``pin +- _HALF_WINDOW``).
    """
    return [(w.name, w.start + (w.end - w.start) // 2, w.kind) for w in windows.windows]


def _window_dates(pin: date) -> tuple[date, date]:
    half = timedelta(days=HALF_WINDOW_DAYS)
    return pin - half, pin + half


def check_pins(pins: list[tuple[str, date, CycleKind]], dates: list[date]) -> None:
    """Every pin must be a real bar in the price file. Refuses rather than drawing."""
    known = set(dates)
    bad = [
        f"{name} {kind} {pin.isoformat()}: no row in {DATA_PATH.name}"
        for name, pin, kind in pins
        if pin not in known
    ]
    if bad:
        raise SystemExit("pins are not bars in the price file:\n  " + "\n  ".join(bad))


def _axis(
    dates: list[date],
    x_of: Callable[[date], float],
    y_top: float,
    y_bot: float,
    *,
    labels: bool,
) -> list[str]:
    """Vertical year gridlines across a region. ``labels=False`` for every panel but
    the last: a second row of year numbers per panel reads as four x-axes."""
    out: list[str] = []
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 2):
        x = x_of(date(yr, 1, 1))
        if not (MARGIN_L <= x <= W - MARGIN_R):
            continue
        out.append(
            f'<line x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" y2="{y_bot:.1f}" stroke="{GRID}"/>'
        )
        if labels:
            out.append(_text(x, y_bot + 15, str(yr), size=10, fill=MUTED, anchor="middle"))
    return out


def _panel(
    index: int,
    run: object,
    dates: list[date],
    pins: list[tuple[str, date, CycleKind]],
) -> str:
    """One run's composite-risk panel: curve, both band rails, shaded pin windows."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    top = AXIS_Y + index * (PANEL_H + PANEL_GAP)
    bot = top + PANEL_H
    risk = list(run.risk)  # type: ignore[attr-defined]
    score = run.score  # type: ignore[attr-defined]
    weights = run.weights  # type: ignore[attr-defined]

    def x_of(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def y_of(v: float) -> float:
        return top + (1.0 - (v - RISK_MIN) / (RISK_MAX - RISK_MIN)) * PANEL_H

    parts: list[str] = [
        f'<rect x="{MARGIN_L}" y="{top:.1f}" width="{pw}" height="{PANEL_H}" fill="{BAND_FILL}"/>'
    ]
    parts += _axis(dates, x_of, top, bot, labels=False)

    # The pin-set windows, shaded: trough green (buy side), peak red (sell side).
    for _name, pin, kind in pins:
        start, end = _window_dates(pin)
        x0, x1 = x_of(start), x_of(end)
        parts.append(
            f'<rect x="{x0:.1f}" y="{top:.1f}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="{PANEL_H}" fill="{_color(kind)}" fill-opacity="0.13"/>'
        )
        parts.append(
            f'<line x1="{x_of(pin):.1f}" y1="{top:.1f}" x2="{x_of(pin):.1f}" '
            f'y2="{bot:.1f}" stroke="{_color(kind)}" stroke-width="1.1" '
            f'stroke-opacity="0.75"/>'
        )
        parts.append(
            f'<circle cx="{x_of(pin):.1f}" cy="{top + 7:.1f}" r="3.4" '
            f'fill="{_color(kind)}" stroke="white" stroke-width="1"/>'
        )

    # The two band rails the objective measures against.
    for value, colour, label in (
        (ACCUMULATE_RISK_MAX, ACCUM_COL, f"accumulate <= {ACCUMULATE_RISK_MAX:.0f}"),
        (DISTRIBUTE_RISK_MIN, DISTRIB_COL, f"distribute >= {DISTRIBUTE_RISK_MIN:.0f}"),
    ):
        y = y_of(value)
        parts.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" '
            f'stroke="{colour}" stroke-width="1.4" stroke-dasharray="7 5"/>'
        )
        parts.append(_backed_text(MARGIN_L + 6, y - 5, label, size=10, fill=colour))

    # Risk axis ticks, shared scale across all four panels so the panels compare.
    for tick in range(0, 101, 25):
        y = y_of(float(tick))
        if top <= y <= bot:
            parts.append(
                f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" '
                f'stroke="{GRID}" stroke-width="1"/>'
            )
            parts.append(_text(MARGIN_L - 8, y + 3, str(tick), size=10, fill=MUTED, anchor="end"))

    for segment in _segmented_series(dates, risk, MAX_POLYLINE_POINTS):
        pts = " ".join(f"{x_of(d):.1f},{y_of(v):.1f}" for d, v in segment)
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{RUN_COLS[index]}" stroke-width="1.5"/>'
        )

    parts.append(
        f'<rect x="{MARGIN_L}" y="{top:.1f}" width="{pw}" height="{PANEL_H}" '
        f'fill="none" stroke="{BOX}"/>'
    )

    # Row label, in the left margin: the run, its weights and its objective.
    enabled = weights.enabled_extras()  # type: ignore[attr-defined]
    weight_text = f"val={weights.valuation:g}"  # type: ignore[attr-defined]
    weight_text += (
        "".join(f" {n}={w:g}" for n, w in enabled.items()) if enabled else "  (valuation-only)"
    )
    label_col = RUN_COLS[index]
    parts.append(
        _text(
            MARGIN_L - 8,
            top + 16,
            f"{run.pin_set}",
            size=12,
            fill=label_col,
            anchor="end",
            weight="bold",
        )  # type: ignore[attr-defined]
    )
    parts.append(
        _text(
            MARGIN_L - 8,
            top + 33,
            f"require_extras={str(run.require_extras).lower()}",  # type: ignore[attr-defined]
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    for i, line in enumerate(_wrap(weight_text, 20)):
        parts.append(_text(MARGIN_L - 8, top + 50 + i * 13, line, size=10, fill=INK, anchor="end"))
    stats = [
        f"objective {score.objective:.4f}",  # type: ignore[attr-defined]
        f"spread {score.spread:.4f} | trough {score.trough_in_accumulate_frac:.4f} | peak {score.peak_in_distribute_frac:.4f}",  # type: ignore[attr-defined]
        f"{run.num_evaluations} evals | "  # type: ignore[attr-defined]
        f"{score.trough_days} trough / {score.peak_days} peak days",  # type: ignore[attr-defined]
    ]
    for i, line in enumerate(stats):
        parts.append(
            _text(MARGIN_L - 8, top + 90 + i * 13, line, size=10, fill=MUTED, anchor="end")
        )
    parts.append(
        _text(MARGIN_L - 8, bot, "composite risk", size=11, fill=INK, anchor="end", weight="bold")
    )
    return "\n".join(parts)


def _footer_block(
    panel_bottoms: list[float], pins_by_set: dict[str, list[tuple[str, date, CycleKind]]]
) -> str:
    top = panel_bottoms[-1] + 44
    parts: list[str] = []
    legend = [
        (
            "bands (frozen)",
            f"accumulate risk <= {ACCUMULATE_RISK_MAX:.0f} (green rule) | "
            f"distribute risk >= {DISTRIBUTE_RISK_MIN:.0f} (red rule) | "
            "objective = spread + 25 x (trough_frac + peak_frac)",
        ),
        (
            "shading",
            "trough window (green, buy side) and peak window (red, sell side) for that "
            f"panel's pin set, ±{HALF_WINDOW_DAYS}d; the dot on a panel's top edge marks "
            "the pin itself",
        ),
        (
            "gold_v1() Set A",
            " · ".join(
                f"{pin.isoformat()} {kind[0].upper()}" for _n, pin, kind in pins_by_set["gold_v1"]
            ),
        ),
        (
            "gold_v2() algorithmic",
            f"{len(pins_by_set['gold_v2'])} turns from detect_turns at min_move_pct=15.0 "
            "(not individually listed; shaded on panels 3 and 4)",
        ),
        (
            "require_extras",
            "False may return valuation-only — reported, not buried. True forces at "
            "least one extra so a real blend has to win on the same objective. Both "
            "rows are shown for both pin sets.",
        ),
        (
            "composite risk",
            "the shipped blend's unitless 0..100 index (z clipped to [-3, 3]), NOT a "
            "portfolio value and NOT an equity curve",
        ),
    ]
    for i, (key, value) in enumerate(legend):
        y = top + i * 18
        parts.append(_text(MARGIN_L - 8, y, key, size=11, fill=INK, anchor="end", weight="bold"))
        parts.append(_text(MARGIN_L + 4, y, value, size=11, fill=MUTED))
    note_top = top + len(legend) * 18 + 16
    parts.append(
        f'<line x1="{MARGIN_L - 130}" y1="{note_top - 15:.1f}" x2="{W - MARGIN_R}" '
        f'y2="{note_top - 15:.1f}" stroke="{BOX}"/>'
    )
    lines = _wrap(FOOTER, 158)
    for i, line in enumerate(lines):
        bold = "IN-SAMPLE" in line or "NOT A PERFORMANCE CLAIM" in line
        parts.append(
            _text(
                MARGIN_L - 130,
                note_top + i * 15,
                line,
                size=11,
                fill=PEAK_COL if i == 0 else INK,
                weight="bold" if bold else "normal",
            )
        )
    parts.append(
        _text(
            W - MARGIN_R,
            top - 18,
            f"source: {DATA_PATH.name} close column (column index 1 is open) / "
            f"{len(pins_by_set['gold_v1'])} + {len(pins_by_set['gold_v2'])} pins verified "
            "as bars in the calendar",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def build_svg(dates: list[date], runs: Sequence[object]) -> str:
    pins_by_set = {
        "gold_v1": _pin_rows(SdcaCycleWindows.gold_v1()),
        "gold_v2": _pin_rows(SdcaCycleWindows.gold_v2()),
    }
    if len(runs) != 4:
        raise SystemExit(f"expected 4 runs (2 pin sets x 2 require_extras), got {len(runs)}")
    panel_bottoms: list[float] = []
    panels: list[str] = []
    for index, run in enumerate(runs):  # type: ignore[arg-type]
        label = getattr(run, "pin_set")
        panels.append(_panel(index, run, dates, pins_by_set[label]))
        panel_bottoms.append(AXIS_Y + index * (PANEL_H + PANEL_GAP) + PANEL_H)
    footer_lines = len(_wrap(FOOTER, 158))
    legend_rows = 6
    total_h = int(panel_bottoms[-1] + 44 + legend_rows * 18 + 16 + footer_lines * 15 + 30)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" '
        f'viewBox="0 0 {W} {total_h}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(FOOTER) + "</desc>",
        f'<rect x="0" y="0" width="{W}" height="{total_h}" fill="white"/>',
        _text(W / 2, TITLE_Y, TITLE, size=15, weight="bold", anchor="middle"),
        _text(W / 2, SUB_Y, SUBTITLE, size=11, fill=MUTED, anchor="middle"),
        *panels,
        _footer_block(panel_bottoms, pins_by_set),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def _series() -> tuple[list[date], list[float], list[object]]:
    # The SHIPPED loader reads the ``close`` COLUMN by name; column index 1 is ``open``
    # and reading that once already caused a wrong-date incident in this repo.
    dates, closes = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", closes, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    artifact = RUNNER.load_fits_artifact()
    runs = RUNNER.run_all(dates, date_s, price_s, sources, artifact)
    return dates, closes, list(runs)


def main() -> None:
    dates, closes, runs = _series()
    for label in ("gold_v1", "gold_v2"):
        check_pins(_pin_rows(RUNNER.pin_set_windows(label)), dates)

    svg = build_svg(dates, runs)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / SVG_NAME).write_text(svg)
    if PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / SVG_NAME).write_text(svg)

    print(f"wrote {OUT_DIR / SVG_NAME}")
    if PUBLIC_DIR.exists():
        print(f"wrote {PUBLIC_DIR / SVG_NAME}")
    print(f"closes: {len(dates)} rows, {dates[0].isoformat()} -> {dates[-1].isoformat()}")
    print(f"runs drawn: {len(runs)}")
    for run in runs:
        print(
            f"  {run.pin_set} require_extras={run.require_extras}: "
            f"objective {run.score.objective:.4f}, {run.num_evaluations} evals, "
            f"weights {RUNNER._weights_text(run)}"  # type: ignore[attr-defined]
        )
    print(f"bytes: {(OUT_DIR / SVG_NAME).stat().st_size}")
    print("every pin verified as a bar in the GLD calendar")


if __name__ == "__main__":
    main()
