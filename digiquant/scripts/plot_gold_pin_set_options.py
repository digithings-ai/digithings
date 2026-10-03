#!/usr/bin/env python3
"""Gold cycle-pin SET OPTIONS for owner approval (#4804).

One stdlib SVG comparing THREE candidate ``SdcaCycleWindows.gold_v1`` pin sets
against the GLD close series, plus three delta lanes that make the choice
explicit rather than implicit:

    A  6 pins (3 peaks / 3 troughs)  strict BTC-parallel: one pin per primary turn
    B  8 pins            A + the two intermediate bear lows
    C 10 pins            B + the GFC pair (roughly today's gold_v1 density)

Research-only. This script draws; it NEVER writes pins. Approving a set is an
OWNER decision that lands in
``digiquant/src/digiquant/strategies/sdca/cycle_windows.py`` separately — until
that edit happens, no set is live.

Inputs are the ``close`` COLUMN of ``digiquant/data/price-history/GLD-USD.csv``,
not the intraday high/low: the engine scores risk against closes and the BTC
pins are close-based, so an intraday extreme would put the gold pins on a
different footing from the set they are being paralleled to. Every pin below is
a verified daily CLOSE extreme of that file; ``check_pins()`` re-asserts the
value/date pair against the loaded series and refuses to draw on any mismatch,
because this figure exists to get a pin set approved and an unverifiable label
under an approval arrow is worse than no figure.

The bands are a SCORING TARGET for indicator weights, not execution periods.
Per ``cycle_windows.py``'s own module docstring: "Documented per-asset cycle
extrema for Stage A weight search. ... the optimizer must not invent ad-hoc
peak/trough lists." Windows are +-45 calendar days (``_HALF_WINDOW``) around each
pin; they carry NO exposure floor and say nothing about time in market.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import load_closes

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "GLD-USD"
DATA_PATH = ROOT / "data" / "price-history" / f"{SYMBOL}.csv"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_pin_set_options.svg"

# ``cycle_windows.py::_HALF_WINDOW``. Duplicated as a constant (not imported) so
# the figure cannot silently follow a future change to the production module.
HALF_WINDOW_DAYS = 45

# Min-max binning keeps the close polyline under this many points (2 per bin).
MAX_POLYLINE_POINTS = 2000

# The three candidate sets. (kind, pin date, close at pin) — every entry is a
# verified daily close extreme of DATA_PATH. Order is chronological within each
# set so the price-panel ticks read left to right.
SET_A: tuple[tuple[str, date, float], ...] = (
    ("peak", date(2011, 8, 22), 184.59),
    ("trough", date(2015, 12, 17), 100.50),
    ("peak", date(2020, 8, 6), 193.89),
    ("trough", date(2022, 9, 26), 151.23),
    ("peak", date(2026, 1, 29), 495.90),
    ("trough", date(2026, 7, 16), 364.96),
)
SET_B_EXTRA: tuple[tuple[str, date, float], ...] = (
    ("trough", date(2013, 12, 19), 114.82),
    ("trough", date(2018, 8, 16), 111.10),
)
SET_C_EXTRA: tuple[tuple[str, date, float], ...] = (
    ("peak", date(2008, 3, 17), 99.17),
    ("trough", date(2008, 11, 12), 70.00),
)

SET_A_PINS = {p for _, p, _ in SET_A}
SET_B_PINS = SET_A_PINS | {p for _, p, _ in SET_B_EXTRA}
SET_C_PINS = SET_B_PINS | {p for _, p, _ in SET_C_EXTRA}

# Shipped ``gold_v1()`` pins that NO candidate set contains. Drawn so the owner
# sees exactly what changes if they approve A, B or C.
DROPPED_FROM_SHIPPED: tuple[tuple[str, date], ...] = (
    ("peak", date(2020, 8, 7)),
    ("trough", date(2022, 10, 21)),
    ("peak", date(2026, 9, 29)),
)

# Display-only BTC reference (cycle_windows.py::btc_v1). Not plotted on this
# time axis — BTC's history does not overlap gold's.
BTC_REFERENCE = "btc_v1() = 5 pins (3 peaks / 2 troughs), 2017-12-17 -> 2025-01-20, +-45d"

TITLE = (
    "Gold cycle pins - three candidate sets (BTC method: exact daily CLOSE extremes, "
    "one per primary turn, +-45d, scoring target only) - AWAITING OWNER APPROVAL"
)

SCORING_NOTE = (
    "These windows are a SCORING TARGET for indicator weights, not execution periods. "
    'cycle_windows.py: "Documented per-asset cycle extrema for Stage A weight search. ... '
    'the optimizer must not invent ad-hoc peak/trough lists." They carry NO exposure '
    "floor and say nothing about time in market."
)

W = 1560
MARGIN_L, MARGIN_R = 118, 132
PRICE_H = 430
LANE_H, LANE_GAP = 74, 14
NOTE_H = 236
TITLE_Y = 22
SUB_Y = 40
AXIS_Y = 62

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#e8e8e8"
PEAK_COL = "#c62828"
TROUGH_COL = "#2e7d32"
PRICE_COL = "#1f5fa8"
DROP_COL = "#5a2d82"
ADD_B_COL = "#1565c0"
ADD_C_COL = "#ef6c00"
BAND_BG = "#fbfbfb"
BOX = "#dcdcdc"


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
    opacity: float = 0.9,
) -> str:
    """Text over a pad, so a lane label survives whatever band it crosses."""
    width = 0.56 * size * len(text) + 8
    pad_x = x - width + 4 if anchor == "end" else x - 4
    return (
        f'<rect x="{pad_x:.1f}" y="{y - size + 1:.1f}" width="{width:.1f}" '
        f'height="{size + 4}" fill="{pad}" fill-opacity="{opacity}"/>'
        + _text(x, y, text, size=size, fill=fill, weight=weight, anchor=anchor)
    )


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def _minmax_series(
    dates: list[date], prices: list[float], max_points: int
) -> list[tuple[date, float]]:
    """Min-max binned (date, price) pairs: at most two points per bin, in order.

    Plain stride-sampling would drop the 2011/2013 lows and the 2020 spike that
    the pin bands are drawn around; a per-bin min/max pair keeps both extremes of
    every bin while bounding the polyline point count.
    """
    n = len(prices)
    if n == 0:
        return []
    n_bins = max(1, max_points // 2)
    if n_bins >= n:
        return list(zip(dates, prices, strict=True))
    size = n / n_bins
    out: list[tuple[date, float]] = []
    for b in range(n_bins):
        lo_i = int(b * size)
        hi_i = max(lo_i + 1, int((b + 1) * size)) if b + 1 < n_bins else n
        hi_i = min(hi_i, n)
        if hi_i <= lo_i:
            continue
        seg = range(lo_i, hi_i)
        i_min = min(seg, key=lambda i: prices[i])
        i_max = max(seg, key=lambda i: prices[i])
        first, last = min(i_min, i_max), max(i_min, i_max)
        out.append((dates[first], prices[first]))
        if last != first:
            out.append((dates[last], prices[last]))
    return out


def check_pins(
    pins: tuple[tuple[str, date, float], ...],
    dates: list[date],
    prices: list[float],
) -> None:
    """Assert every pin's date/close pair matches the loaded series exactly.

    Refuses (raises) rather than drawing: the chart's whole job is getting a pin
    set approved, so a label that does not reconcile with the CSV is a stop.
    """
    closes = dict(zip(dates, prices, strict=True))
    bad: list[str] = []
    for kind, pin, stated in pins:
        actual = closes.get(pin)
        if actual is None:
            bad.append(f"{kind} {pin.isoformat()}: no row in {DATA_PATH.name}")
            continue
        if round(actual, 2) != round(stated, 2):
            bad.append(
                f"{kind} {pin.isoformat()}: stated close {stated:.2f} vs file close {actual:.2f}"
            )
    if bad:
        raise SystemExit("pin values disagree with the price file:\n  " + "\n  ".join(bad))


def _color(kind: str) -> str:
    return PEAK_COL if kind == "peak" else TROUGH_COL


def _window_dates(pin: date) -> tuple[date, date]:
    half = timedelta(days=HALF_WINDOW_DAYS)
    return pin - half, pin + half


def _axis(
    dates: list[date], x_of: Callable[[date], float], y_top: float, y_bot: float
) -> list[str]:
    out: list[str] = []
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 2):
        x = x_of(date(yr, 1, 1))
        if not (MARGIN_L <= x <= W - MARGIN_R):
            continue
        out.append(
            f'<line x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" y2="{y_bot:.1f}" stroke="{GRID}"/>'
        )
        out.append(_text(x, y_bot + 15, str(yr), size=10, fill=MUTED, anchor="middle"))
    return out


def _panel(dates: list[date], closes: list[float]) -> str:
    """Price panel: close line, Set-A +-45d bands, per-pin tick + label."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    lo, hi = min(closes), max(closes)
    pad = (hi - lo) * 0.08

    def x_of(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def y_of(v: float) -> float:
        top, bot = AXIS_Y, AXIS_Y + PRICE_H
        return top + (1.0 - (v - (lo - pad)) / ((hi + pad) - (lo - pad))) * (bot - top)

    parts: list[str] = []
    parts += _axis(dates, x_of, AXIS_Y, AXIS_Y + PRICE_H)
    for tick in range(int(lo - pad // 4), int(hi + pad) + 1, 100):
        y = y_of(float(tick))
        if AXIS_Y <= y <= AXIS_Y + PRICE_H:
            parts.append(
                f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" '
                f'stroke="{GRID}"/>'
            )
            parts.append(_text(MARGIN_L - 8, y + 3, f"${tick}", size=10, fill=MUTED, anchor="end"))

    # Set A bands, peak red / trough green, low opacity.
    for kind, pin, _px in SET_A:
        start, end = _window_dates(pin)
        x0, x1 = x_of(start), x_of(end)
        col = _color(kind)
        parts.append(
            f'<rect x="{x0:.1f}" y="{AXIS_Y}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="{PRICE_H}" fill="{col}" fill-opacity="0.10"/>'
        )
        parts.append(
            f'<rect x="{x0:.1f}" y="{AXIS_Y + PRICE_H - 7}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="7" fill="{col}" fill-opacity="0.75"/>'
        )

    series = _minmax_series(dates, closes, MAX_POLYLINE_POINTS)
    pts = " ".join(f"{x_of(d):.1f},{y_of(p):.1f}" for d, p in series)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{PRICE_COL}" stroke-width="1.5"/>')

    # Per-pin vertical tick + date/close label, alternating above/below the pin
    # so neighbouring labels in the 2015-2022 cluster stay legible.
    for i, (kind, pin, px) in enumerate(SET_A):
        x = x_of(pin)
        col = _color(kind)
        y = y_of(px)
        up = i % 2 == 0
        parts.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" '
            f'y2="{y - 34 if up else y + 34:.1f}" stroke="{col}" stroke-width="1.4"/>'
        )
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{col}"/>')
        ly = y - 38 if up else y + 46
        anchor = "middle"
        if x < MARGIN_L + 40:
            anchor = "start"
        elif x > W - MARGIN_R - 40:
            anchor = "end"
        parts.append(
            _backed_text(x, ly, f"{pin.isoformat()} ${px:.2f}", size=10, fill=col, anchor=anchor)
        )
        parts.append(
            _text(x, ly + (-11 if up else 11), f"{kind} (Set A)", size=9, fill=MUTED, anchor=anchor)
        )

    parts.append(
        f'<rect x="{MARGIN_L}" y="{AXIS_Y}" width="{pw}" height="{PRICE_H}" '
        f'fill="none" stroke="{BOX}"/>'
    )
    parts.append(
        _text(
            MARGIN_L - 8,
            AXIS_Y - 10,
            "GLD close (USD)",
            size=11,
            fill=INK,
            anchor="end",
            weight="bold",
        )
    )
    parts.append(
        _text(
            MARGIN_L + 6,
            AXIS_Y + 16,
            "Set A +-45d scoring bands: red = peak, green = trough",
            size=10,
            fill=MUTED,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R,
            AXIS_Y - 10,
            f"first {dates[0].isoformat()} / last {dates[-1].isoformat()} / {len(dates)} closes",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def _band(
    x_of: Callable[[date], float],
    y: float,
    pin: date,
    col: str,
    height: float,
    opacity: float = 0.28,
) -> list[str]:
    start, end = _window_dates(pin)
    x0, x1 = x_of(start), x_of(end)
    return [
        f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(x1 - x0, 1.0):.1f}" '
        f'height="{height:.1f}" fill="{col}" fill-opacity="{opacity}"/>',
        f'<line x1="{x_of(pin):.1f}" y1="{y:.1f}" x2="{x_of(pin):.1f}" '
        f'y2="{y + height:.1f}" stroke="{col}" stroke-width="1.2"/>',
    ]


def _strike(x: float, y: float, width: float, col: str) -> list[str]:
    """Strike-through marker: this shipped pin is in NO candidate set."""
    cy = y + width / 2
    out = [
        f'<rect x="{x - width / 2:.1f}" y="{y:.1f}" width="{width:.1f}" height="{width:.1f}" '
        f'fill="{col}" fill-opacity="0.06"/>',
        f'<line x1="{x - width / 2:.1f}" y1="{cy:.1f}" x2="{x + width / 2:.1f}" y2="{cy:.1f}" '
        f'stroke="{col}" stroke-width="2.4"/>',
    ]
    r = width * 0.32
    out.append(
        f'<line x1="{x - r:.1f}" y1="{cy - r:.1f}" x2="{x + r:.1f}" y2="{cy + r:.1f}" '
        f'stroke="{col}" stroke-width="2"/>'
    )
    out.append(
        f'<line x1="{x - r:.1f}" y1="{cy + r:.1f}" x2="{x + r:.1f}" y2="{cy - r:.1f}" '
        f'stroke="{col}" stroke-width="2"/>'
    )
    return out


def _lanes(dates: list[date]) -> str:
    """Three thin delta lanes: what B adds, what C adds, what is dropped."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()

    def x_of(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    top = AXIS_Y + PRICE_H + 34
    parts: list[str] = []

    lane_defs = [
        ("B adds (B - A)", ADD_B_COL, "8 pins"),
        ("C adds (C - B)", ADD_C_COL, "10 pins"),
        ("dropped from shipped gold_v1", DROP_COL, "0 pins"),
    ]
    for i, (label, col, count) in enumerate(lane_defs):
        y = top + i * (LANE_H + LANE_GAP)
        parts.append(
            f'<rect x="{MARGIN_L}" y="{y:.1f}" width="{pw}" height="{LANE_H}" '
            f'fill="{BAND_BG}" stroke="{BOX}"/>'
        )
        parts.append(
            _text(MARGIN_L - 8, y + 18, label, size=11, fill=col, anchor="end", weight="bold")
        )
        parts.append(_text(MARGIN_L - 8, y + 34, count, size=10, fill=MUTED, anchor="end"))

    # Lane 0: B - A  (two intermediate bear lows).
    y_b = top
    parts.append(
        _text(
            MARGIN_L + 8,
            y_b + 16,
            "B - A = the two intermediate bear lows A skips",
            size=10,
            fill=MUTED,
        )
    )
    for _kind, pin, px in SET_B_EXTRA:
        parts += _band(x_of, y_b + 24, pin, ADD_B_COL, 26, 0.30)
        x = x_of(pin)
        anchor = "end" if x > W - MARGIN_R - 120 else ("start" if x < MARGIN_L + 120 else "middle")
        parts.append(
            _backed_text(
                x,
                y_b + 62,
                f"{pin.isoformat()} trough ${px:.2f}",
                size=10,
                fill=ADD_B_COL,
                anchor=anchor,
            )
        )

    # Lane 1: C - B  (the GFC pair).
    y_c = top + LANE_H + LANE_GAP
    parts.append(
        _text(
            MARGIN_L + 8,
            y_c + 16,
            "C - B = the GFC pair (2008 high, then 2008 washout)",
            size=10,
            fill=MUTED,
        )
    )
    for kind, pin, px in SET_C_EXTRA:
        parts += _band(x_of, y_c + 24, pin, ADD_C_COL, 26, 0.30)
        x = x_of(pin)
        anchor = "end" if x > W - MARGIN_R - 120 else ("start" if x < MARGIN_L + 120 else "middle")
        parts.append(
            _backed_text(
                x,
                y_c + 62,
                f"{pin.isoformat()} {kind} ${px:.2f}",
                size=10,
                fill=ADD_C_COL,
                anchor=anchor,
            )
        )

    # Lane 2: shipped gold_v1 pins that NO candidate set contains.
    y_d = top + 2 * (LANE_H + LANE_GAP)
    parts.append(
        _text(
            MARGIN_L + 8,
            y_d + 16,
            "shipped pins in A, B and C: none (struck through)",
            size=10,
            fill=MUTED,
        )
    )
    for kind, pin in DROPPED_FROM_SHIPPED:
        x = x_of(pin)
        parts += _strike(x, y_d + 24, 26, DROP_COL)
        anchor = "end" if x > W - MARGIN_R - 140 else ("start" if x < MARGIN_L + 140 else "middle")
        parts.append(
            _backed_text(
                x, y_d + 62, f"{pin.isoformat()} {kind}", size=10, fill=DROP_COL, anchor=anchor
            )
        )
    parts.append(
        _backed_text(
            MARGIN_L + 8,
            y_d + 62,
            '2026-09-29 is the shipped "incomplete top"; the real 2026 high is 2026-01-29',
            size=10,
            fill=DROP_COL,
            anchor="start",
        )
    )

    parts += _axis(dates, x_of, top, y_d + LANE_H)
    return "\n".join(parts)


def _annotation_block(dates: list[date]) -> str:
    """Counts per set, the BTC reference line, and the scoring-target note."""
    pw = W - MARGIN_L - MARGIN_R
    top = AXIS_Y + PRICE_H + 34 + 3 * (LANE_H + LANE_GAP) + 30
    height = NOTE_H
    parts = [
        f'<rect x="{MARGIN_L}" y="{top:.1f}" width="{pw}" height="{height}" '
        f'fill="{BAND_BG}" stroke="{BOX}"/>',
        _text(
            MARGIN_L + 12,
            top + 22,
            "Candidate sets (all pins are exact daily CLOSE extremes of GLD-USD.csv)",
            size=12,
            weight="bold",
        ),
    ]
    rows = [
        (
            "A - strict BTC-parallel, 6 pins = 3 peaks / 3 troughs, one per primary turn 2011 -> 2026",
            PEAK_COL,
        ),
        (
            "B - A + 2 intermediate bear lows (2013-12-19, 2018-08-16), 8 pins = 3 peaks / 5 troughs",
            ADD_B_COL,
        ),
        (
            "C - B + the GFC pair (2008-03-17 peak, 2008-11-12 trough), 10 pins = 4 peaks / 6 troughs",
            ADD_C_COL,
        ),
    ]
    for i, (text, col) in enumerate(rows):
        parts.append(
            f'<rect x="{MARGIN_L + 12}" y="{top + 36 + i * 19:.1f}" width="10" height="10" fill="{col}"/>'
        )
        parts.append(_text(MARGIN_L + 30, top + 45 + i * 19, text, size=11, fill=INK))

    y = top + 104
    parts.append(
        _text(
            MARGIN_L + 12, y, "BTC reference (display only): " + BTC_REFERENCE, size=11, fill=MUTED
        )
    )
    parts.append(
        _text(
            MARGIN_L + 12,
            y + 17,
            "Bands are +-45 calendar days (cycle_windows.py::_HALF_WINDOW).",
            size=11,
            fill=MUTED,
        )
    )

    y += 40
    for i, line in enumerate(_wrap(SCORING_NOTE, 118)):
        parts.append(_text(MARGIN_L + 12, y + i * 15, line, size=11, fill=INK))

    parts.append(
        _text(
            MARGIN_L + 12,
            top + height - 12,
            "AWAITING OWNER APPROVAL - no set is written to cycle_windows.py by this script",
            size=13,
            fill=PEAK_COL,
            weight="bold",
        )
    )
    parts.append(
        _text(
            W - MARGIN_R - 12,
            top + height - 12,
            f"source: {DATA_PATH.name} close column / {len(dates)} rows",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def build_svg(dates: list[date], closes: list[float]) -> str:
    total_h = AXIS_Y + PRICE_H + 34 + 3 * (LANE_H + LANE_GAP) + 30 + NOTE_H + 24
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" '
        f'viewBox="0 0 {W} {total_h}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(SCORING_NOTE) + "</desc>",
        f'<rect x="0" y="0" width="{W}" height="{total_h}" fill="white"/>',
        _text(W / 2, TITLE_Y, TITLE, size=15, weight="bold", anchor="middle"),
        _text(
            W / 2,
            SUB_Y,
            "Which set becomes SdcaCycleWindows.gold_v1? "
            "A = strict BTC-parallel | B = +2 intermediate bear lows | C = + GFC pair",
            size=11,
            fill=MUTED,
            anchor="middle",
        ),
        _panel(dates, closes),
        _lanes(dates),
        _annotation_block(dates),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    dates, closes = load_closes(SYMBOL, DATA_PATH)
    check_pins(SET_A, dates, closes)
    check_pins(SET_B_EXTRA, dates, closes)
    check_pins(SET_C_EXTRA, dates, closes)

    svg = build_svg(dates, closes)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / SVG_NAME).write_text(svg)
    if PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / SVG_NAME).write_text(svg)

    n_points = len(_minmax_series(dates, closes, MAX_POLYLINE_POINTS))
    n_bytes = (OUT_DIR / SVG_NAME).stat().st_size
    print(f"wrote {OUT_DIR / SVG_NAME}")
    if PUBLIC_DIR.exists():
        print(f"wrote {PUBLIC_DIR / SVG_NAME}")
    print(f"closes: {len(dates)} rows, {dates[0].isoformat()} -> {dates[-1].isoformat()}")
    print(f"polyline points: {n_points} (cap {MAX_POLYLINE_POINTS})")
    print(f"bytes: {n_bytes}")
    print("\nsets:")
    print(
        f"  A  {len(SET_A)} pins ({sum(1 for k, _, _ in SET_A if k == 'peak')} peaks / "
        f"{sum(1 for k, _, _ in SET_A if k == 'trough')} troughs)"
    )
    print(f"  B  {len(SET_B_PINS)} pins (A + {len(SET_B_EXTRA)})")
    print(f"  C  {len(SET_C_PINS)} pins (B + {len(SET_C_EXTRA)})")
    print(f"  lanes: B adds {sorted(p.isoformat() for p in SET_B_PINS - SET_A_PINS)}")
    print(f"         C adds {sorted(p.isoformat() for p in SET_C_PINS - SET_B_PINS)}")
    print(f"         dropped from shipped: {[p.isoformat() for _, p in DROPPED_FROM_SHIPPED]}")
    print("  AWAITING OWNER APPROVAL - no pins written to cycle_windows.py")


if __name__ == "__main__":
    main()
