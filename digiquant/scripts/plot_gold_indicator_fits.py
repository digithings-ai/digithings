#!/usr/bin/env python3
"""Per-indicator fitted z panels + the aggregate, as one stdlib-only SVG (#4804).

Why SVG: no plotting library exists in .venv or system python and pip installs
are forbidden in this task, so this is hand-rolled SVG (stdlib only) — the same
960-wide pattern as ``plot_gold_secular_legs.py`` /
``plot_gold_stagea_verdict.py``. Stays untracked, with a public/ copy for the
preview server.

One panel per FITTED indicator (14 panels, every wired leg — including the two
unscoreable credit legs and the two degenerate oscillator passes, so an omission
is never silent) plus ONE aggregate panel. Each panel draws that leg's
manipulated, z-scored series at its OWN fitted parameters against the pinned
``SdcaCycleWindows.gold_v1()`` ±45d windows: trough windows shaded green (BUY /
cheap), peak windows shaded red (SELL / rich). The panel title carries the
fitted params, the separation, the per-side shares and the verdict.

The AGGREGATE panel draws two series: the anchor alone (equal weight
``{valuation: 1.0}`` — what the selection actually kept) and the report-only
cross-check blend (anchor + every non-degenerate passer at once, no pruning).
Both come from the SHIPPED ``compute_composite_risk``; the selection file's
stored separations are re-verified against the rebuilt series before anything
is drawn, so no number here is retyped.

Reads precomputed results ONLY from the two Plan-19 artifacts
(``.scratch/gold_indicator_fits.json``, ``.scratch/gold_indicator_selection.json``)
and rebuilds each leg's z with the SAME shipped z-functions the fit harness
called (``fit_gold_indicators.build_z``) — it fits nothing and selects nothing.

Outputs (both UNTRACKED):
    digiquant/.scratch/gold_pngs/gold_indicator_fits.svg
    apps/digiquant-web/public/gold_charts/gold_indicator_fits.svg

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/plot_gold_indicator_fits.py
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import NamedTuple
from xml.sax.saxutils import escape

import polars as pl

from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv

# The fit harness is a sibling research script (never a package); put this
# directory on the path so the z vectors and the frozen metric are the SAME code
# the fits file was produced with — no reimplementation here.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fit_gold_indicators import (  # noqa: E402 — sibling research script, path set above
    DATA_PATH,
    SYMBOL,
    aggregate_z,
    anchor_z,
    build_z,
    separation,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
FITS_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_fits.json"
SELECTION_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_selection.json"
OUT_DIR = DIGIQUANT_ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
OUT_NAME = "gold_indicator_fits.svg"

PASS_LIST = "PASS: valuation anchor only — no indicator added"

# Every panel shares this y scale so the legs are directly comparable; z is
# clipped to [-3, 3] by the shipped z-functions (see fit_gold_indicators).
Y_LO, Y_HI = -3.2, 3.2
Y_TICKS = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)

W = 960
ML, MR = 62, 18
PANEL_H = 140
PANEL_TITLE_H = 40
PANEL_GAP = 28
HEADER_H = 116
FOOTER_H = 62

BUY_FILL = "#2a7a2a"
SELL_FILL = "#cc0000"
SERIES = "#1f5fa8"
CROSS_SERIES = "#b36b00"

MAX_POINTS = 1400
VERIFY_TOL = 1e-9

Point = tuple[date, float]


class Panel(NamedTuple):
    """One stacked panel: title lines plus one or more drawn series."""

    title_lines: tuple[str, ...]
    series: tuple[tuple[Sequence[Point], str, str], ...]


def _params_text(params: Mapping[str, int]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(params.items()))


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


def pinned_windows(fits: Mapping[str, object], selection: Mapping[str, object]) -> SdcaCycleWindows:
    """The pinned scoring windows, asserted against BOTH artifacts' pin label."""
    windows = SdcaCycleWindows.gold_v1()
    label = f"{windows.__class__.__name__}.gold_v1()"
    for artifact, name in ((fits, FITS_PATH.name), (selection, SELECTION_PATH.name)):
        if not str(artifact["windows"]).startswith(label):
            raise AssertionError(
                f"{name} pins are {artifact['windows']!r}, expected {label} — refusing "
                "to chart a different pin set than the fits were scored on"
            )
    return windows


def render_params(fit: Mapping[str, object]) -> tuple[str, dict[str, int]]:
    """(label, params) for the series this panel draws.

    A SCORED leg draws at its ``best_overall`` params. An UNSCOREABLE leg has no
    fit, so it draws at its FIRST grid row and says so on the panel — the series
    is shown for completeness, never as a fitted result.
    """
    best = fit.get("best_overall")
    if best is not None:
        return _params_text(best["params"]), dict(best["params"])
    rows = fit.get("rows") or [{}]
    first = rows[0]
    params = dict(first.get("params") or {})
    return f"{_params_text(params)} (FIRST grid row — NO FIT)", params


def decimate(pts: Sequence[Point]) -> list[Point]:
    """Min-max per bin so extremes survive (same rule as plot_gold_secular_legs)."""
    n = len(pts)
    if n <= MAX_POINTS:
        return list(pts)
    bins = max(MAX_POINTS // 2, 1)
    size = math.ceil(n / bins)
    kept: list[Point] = []
    for b in range(bins):
        chunk = list(pts[b * size : (b + 1) * size])
        if not chunk:
            continue
        low = min(chunk, key=lambda p: p[1])
        high = max(chunk, key=lambda p: p[1])
        kept.append(low)
        if high != low:
            kept.append(high)
    kept.sort(key=lambda p: p[0])
    return kept


def _panel_title(
    *,
    name: str,
    params_label: str,
    separation_value: float | None,
    fit: Mapping[str, object],
) -> str:
    best = fit.get("best_overall")
    if best is None:
        return (
            f"{name} ({params_label}) — UNSCOREABLE, no fit: "
            f"{fit.get('reason') or 'no scored grid row'}"
        )
    shares = (
        f"peak<0 {best['peak_negative_share']:.2f} / "
        f"trough>0 {best['trough_positive_share']:.2f} / "
        f"zero {best['zero_z_share']:.2f}"
    )
    flag = "  [DEGENERATE]" if best.get("degenerate") else ""
    return (
        f"{name} ({params_label}) — separation {_signed(separation_value)} "
        f"({fit['verdict']}) | {shares}{flag}"
    )


def _grid_and_windows(
    parts: list[str],
    *,
    top: int,
    windows: SdcaCycleWindows,
    sx: object,
    sy: object,
    span: tuple[date, date],
) -> None:
    """Shared per-panel furniture: window shading, z gridlines, year gridlines."""
    pw = W - ML - MR
    for window in windows.windows:
        fill = BUY_FILL if window.kind is CycleKind.TROUGH else SELL_FILL
        x0, x1 = sx(window.start), sx(window.end)  # type: ignore[operator]
        parts.append(
            f'<rect x="{x0:.1f}" y="{top}" width="{max(x1 - x0, 1.5):.1f}" '
            f'height="{PANEL_H}" fill="{fill}" fill-opacity="0.10"/>'
        )
        parts.append(
            f'<line x1="{x0:.1f}" y1="{top}" x2="{x0:.1f}" y2="{top + PANEL_H}" '
            f'stroke="{fill}" stroke-width="1" stroke-opacity="0.45"/>'
        )
        parts.append(
            f'<line x1="{x1:.1f}" y1="{top}" x2="{x1:.1f}" y2="{top + PANEL_H}" '
            f'stroke="{fill}" stroke-width="1" stroke-opacity="0.45"/>'
        )
        parts.append(
            f'<text x="{(x0 + x1) / 2:.1f}" y="{top + 11}" text-anchor="middle" '
            f'font-size="9" fill="{fill}">{escape(window.name)}</text>'
        )
    for tick in Y_TICKS:
        y = sy(tick)  # type: ignore[operator]
        is_zero = tick == 0.0
        dash = ' stroke-dasharray="4,3"' if is_zero else ""
        stroke = "#999999" if is_zero else "#e0e0e0"
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            f'stroke="{stroke}" stroke-width="1"{dash}/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10">{tick:g}</text>'
        )
    year = span[0].year + (span[0].year % 2)
    while year <= span[1].year:
        x = sx(date(year, 1, 1))  # type: ignore[operator]
        if ML - 1 <= x <= W - MR + 1:
            parts.append(
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + PANEL_H}" '
                'stroke="#f0f0f0" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{top + PANEL_H + 12}" text-anchor="middle" '
                f'font-size="9" fill="#555555">{year}</text>'
            )
        year += 2
    parts.append(
        f'<rect x="{ML}" y="{top}" width="{pw}" height="{PANEL_H}" fill="none" stroke="#000000"/>'
    )


def svg_panels(
    panels: Sequence[Panel],
    windows: SdcaCycleWindows,
    *,
    span: tuple[date, date],
    footer: Sequence[str],
) -> str:
    """Stacked panels, each shaded with the pinned buy/sell windows."""
    block = PANEL_H + PANEL_TITLE_H + PANEL_GAP
    height = HEADER_H + len(panels) * block + FOOTER_H
    pw = W - ML - MR
    d0, d1 = span[0].toordinal(), span[1].toordinal()

    def sx(d: date) -> float:
        return ML + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float, top: int) -> float:
        return top + (1.0 - (v - Y_LO) / (Y_HI - Y_LO)) * PANEL_H

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
        'font-family="sans-serif">',
        "<title>GLD per-indicator fitted z panels + aggregate vs the pinned "
        "gold_v1 ±45d buy/sell windows (Plan 19, #4804)</title>",
        f'<text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        'font-weight="bold">GLD indicator fits — every wired leg\'s manipulated, '
        "z-scored series at its own fitted parameters</text>",
        f'<text x="{W / 2}" y="46" text-anchor="middle" font-size="12" fill="#333333">'
        f"pinned SdcaCycleWindows.gold_v1() ±45d windows: "
        f"{len(windows.troughs())} trough shaded GREEN = BUY/cheap, "
        f"{len(windows.peaks())} peak shaded RED = SELL/rich; shared y scale "
        f"[{Y_LO:g}, {Y_HI:g}]</text>",
        f'<text x="{W / 2}" y="66" text-anchor="middle" font-size="12.5" '
        f'font-weight="bold" fill="#1f4f8a">{escape(PASS_LIST)}</text>',
        f'<text x="{W / 2}" y="84" text-anchor="middle" font-size="11" fill="#333333">'
        "separation = mean(z | troughs) − mean(z | peaks); positive = votes cheap "
        "at bottoms; abs() never applied</text>",
        f'<text x="{W / 2}" y="101" text-anchor="middle" font-size="11" fill="#333333">'
        "IN-SAMPLE: fitted against the same pinned windows it is measured on — NOT "
        "out-of-sample skill. HOLDOUT ABSENT (spent, untouched). No gate ran here."
        "</text>",
    ]

    for index, panel in enumerate(panels):
        cursor = HEADER_H + index * block
        title_y = cursor + 14
        plot_top = cursor + PANEL_TITLE_H
        for line_index, line in enumerate(panel.title_lines):
            color = "#1f4f8a" if line_index == 0 and line.startswith("AGGREGATE") else "#111111"
            parts.append(
                f'<text x="{ML}" y="{title_y + line_index * 13}" font-size="11.5" '
                f'fill="{color}">{escape(line)}</text>'
            )
        _grid_and_windows(
            parts,
            top=plot_top,
            windows=windows,
            sx=sx,
            sy=lambda v, t=plot_top: sy(v, t),
            span=span,
        )
        if not panel.series:
            parts.append(
                f'<text x="{W / 2}" y="{plot_top + PANEL_H / 2}" text-anchor="middle" '
                'font-size="11" fill="#888888">no valid z on any bar (series starts '
                "after the pins)</text>"
            )
        for pts, color, extra in panel.series:
            coords = " ".join(f"{sx(d):.1f},{sy(v, plot_top):.1f}" for d, v in decimate(pts))
            parts.append(
                f'<polyline points="{coords}" fill="none" stroke="{color}" '
                f'stroke-width="1.3"{extra}/>'
            )

    footer_top = height - FOOTER_H + 20
    for index, line in enumerate(footer):
        parts.append(
            f'<text x="{W / 2}" y="{footer_top + index * 16}" text-anchor="middle" '
            f'font-size="11" fill="#333333">{escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    fits = json.loads(FITS_PATH.read_text())
    selection = json.loads(SELECTION_PATH.read_text())
    windows = pinned_windows(fits, selection)

    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    span = (dates[0], dates[-1])

    panels: list[Panel] = []
    counts: list[int] = []
    checked = 0
    for name, fit in fits["indicators"].items():
        params_label, params = render_params(fit)
        z = build_z(name, params, date_s, price_s, sources)
        best = fit.get("best_overall")
        rebuilt_sep: float | None = None
        if best is not None:
            rebuilt_sep = separation(dates, z, windows).separation
            if abs(float(best["separation"]) - float(rebuilt_sep or 0.0)) > VERIFY_TOL:
                raise AssertionError(
                    f"{name}: rebuilt separation {rebuilt_sep} != stored "
                    f"{best['separation']} — refusing to draw a drifted curve"
                )
            checked += 1
        pts = [
            (day, float(value)) for day, value in zip(dates, z, strict=True) if value is not None
        ]
        panels.append(
            Panel(
                title_lines=(
                    _panel_title(
                        name=name,
                        params_label=params_label,
                        separation_value=rebuilt_sep,
                        fit=fit,
                    ),
                    f"family {fit['family']} · {fit['grid_rows']} grid rows · "
                    f"{fit['status']} · window_days {best['window_days'] if best else '—'}"
                    + (f" · {fit['reason']}" if best is None or fit.get("reason") else ""),
                ),
                series=((pts, SERIES, ""),),
            )
        )
        counts.append(len(pts))

    # --- aggregate panel: the anchor alone vs the report-only cross-check -----
    anchor = anchor_z(date_s, price_s)
    anchor_agg = aggregate_z([("valuation", anchor)])
    pool = [(c["name"], c["params"]) for c in selection["candidate_pool"]]
    pool_z = [(name, build_z(name, params, date_s, price_s, sources)) for name, params in pool]
    cross_agg = aggregate_z([("valuation", anchor), *pool_z])

    anchor_sep = separation(dates, anchor_agg, windows).separation
    stored_anchor = float(selection["anchor"]["aggregate_separation"])
    if abs(float(anchor_sep) - stored_anchor) > VERIFY_TOL:
        raise AssertionError(
            f"anchor aggregate separation drifted: stored {stored_anchor} vs {anchor_sep}"
        )
    cross_sep = separation(dates, cross_agg, windows).separation
    stored_cross = float(selection["cross_check"]["separation"])
    if abs(float(cross_sep) - stored_cross) > VERIFY_TOL:
        raise AssertionError(
            f"cross-check separation drifted: stored {stored_cross} vs {cross_sep}"
        )

    def _clean(values: Sequence[float | None]) -> list[Point]:
        return [(day, float(v)) for day, v in zip(dates, values, strict=True) if v is not None]

    aggregate_pts = _clean(anchor_agg)
    cross_pts = _clean(cross_agg)
    panels.append(
        Panel(
            title_lines=(
                f"AGGREGATE — {PASS_LIST}",
                f"equal weight {{valuation: 1.0}} on rolling"
                f"{selection['anchor']['rolling_window']}d / z "
                f"{selection['anchor']['rolling_z']} rails, separation "
                f"{_signed(anchor_sep)} — what the selection actually kept",
                f"dashed = report-only cross-check (anchor + "
                f"{', '.join(name for name, _ in pool_z)} at once, no greedy "
                f"pruning), separation {_signed(cross_sep)}",
            ),
            series=(
                (aggregate_pts, SERIES, ""),
                (cross_pts, CROSS_SERIES, ' stroke-dasharray="5,3"'),
            ),
        )
    )
    counts.append(len(aggregate_pts))

    deltas = ", ".join(f"{step['name']} {step['delta']:+.2f}" for step in selection["delta_table"])
    footer = [
        f"Every fitted leg's addition LOWERS the equal-weight aggregate ({deltas}) — "
        f"which is why the pass list is the valuation anchor alone.",
        "IN-SAMPLE: fitted and measured on the same pinned windows. HOLDOUT ABSENT "
        "(spent, untouched). Research-only: no gate ran, nothing published, no "
        "performance claim.",
    ]
    svg = svg_panels(panels, windows, span=span, footer=footer)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / OUT_NAME
    out.write_text(svg)
    shutil.copy(out, PUBLIC_DIR / OUT_NAME)

    print(f"{SYMBOL} {span[0]}..{span[1]} ({len(dates)} bars)")
    print(f"verify: {checked} scored legs rebuilt, separation delta <= {VERIFY_TOL}")
    print(f"verify: anchor {anchor_sep:+.4f} == stored {stored_anchor:+.4f}")
    print(f"verify: cross-check {cross_sep:+.4f} == stored {stored_cross:+.4f}")
    print("")
    print(PASS_LIST)
    print("")
    print(f"panels ({len(panels)} = {len(panels) - 1} fitted legs + 1 aggregate):")
    for panel, count in zip(panels, counts, strict=True):
        print(f"  {count:>5} pts  {panel.title_lines[0]}")
    print("")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"wrote {PUBLIC_DIR / OUT_NAME} (public copy)")


if __name__ == "__main__":
    main()
