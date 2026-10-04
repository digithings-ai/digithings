#!/usr/bin/env python3
"""The two shipped gold cycle-window pin sets on one GLD close chart (#4804, Plan 22).

One hand-rolled stdlib SVG (no matplotlib — it is not installed in this environment;
no numpy/pandas/nautilus) showing what ``cycle_windows.py`` actually ships:

- **Set A** — ``SdcaCycleWindows.gold_v1()``, the six owner-approved close-based pins.
- **the algorithmic set** — ``SdcaCycleWindows.gold_v2()``, the 20 turns
  ``turn_detect.detect_turns`` produces at ``min_move_pct=15.0`` /
  ``min_separation_days=45``, the level ``sensitivity_consolidate.select_sensitivity_level``
  chose by the depth-weighted fitted-direction rule.

Both sets' ±45d windows are shaded and distinguishable (Set A as coloured bands over
the panel, the algorithmic set as a separate hatched rail beneath it), and a third
lane draws the **buy/sell alternation** itself — the pairing invariant (owner ruling 2)
as a strip you can read left to right, with Set A's six picks ticked onto it.

The pins are read from the live factories rather than restated here: this figure
documents what is SHIPPED, so a second copy of the dates would be a second thing to
forget to update. ``check_pins()`` re-asserts every pin's date/close against the CSV
and refuses to draw on any mismatch — this file exists to make the pin sets auditable,
so a marker that does not reconcile with the price file is a stop, not a footnote.

The input is the ``close`` COLUMN of ``digiquant/data/price-history/GLD-USD.csv``;
column index 1 is ``open``, and reading that once caused a wrong-date incident.

**IN-SAMPLE. These windows are a SCORING TARGET for the Stage A indicator-weight search
— not execution periods, and not a performance claim.** They carry no exposure floor,
they say nothing about time in market, and no return, Sharpe or trade count is claimed
anywhere in this figure. Set A was chosen by looking at this same series, which is
exactly what "in-sample" means.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import load_closes

from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "GLD-USD"
DATA_PATH = ROOT / "data" / "price-history" / f"{SYMBOL}.csv"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_pin_sets_v2.svg"

# ``cycle_windows.py::_HALF_WINDOW``, restated so the figure cannot silently follow a
# later change to the production module.
HALF_WINDOW_DAYS = 45

# Min-max binning keeps the close polyline under this many points (2 per bin).
MAX_POLYLINE_POINTS = 2000

# Close tolerance: the CSV carries float32 prices (184.58999633789062).
CLOSE_TOL = 0.005

TITLE = (
    "Gold cycle-window pin sets v2: Set A (6 approved pins) and the algorithmic 20 "
    "on GLD closes, +-45d scoring windows"
)
SUBTITLE = (
    "gold_v1() = 6 close-based pins, owner-approved and detector-corroborated at 0-bar "
    "offsets | gold_v2() = 20 turns from detect_turns at min_move_pct=15.0, the level "
    "selected by capture depth 15.7457 (vs 10.6792 / 7.1547)"
)

FOOTER = (
    "IN-SAMPLE. Every pin on this chart is a close-based turning point of GLD-USD, read "
    "from the close column (column index 1 is open). The +-45d bands are a SCORING TARGET "
    "for the Stage A indicator-weight search — they are NOT execution periods, they carry "
    "NO exposure floor, and they say nothing about time in market. Set A was chosen by "
    "looking at this same series. Nothing here is a performance claim: no return, no "
    "Sharpe, no trade count. Regenerate: digiquant/scripts/plot_gold_pin_sets_v2.py"
)

W = 1560
MARGIN_L, MARGIN_R = 122, 138
TITLE_Y = 22
SUB_Y = 40
AXIS_Y = 92
PRICE_H = 400
RAIL_TOP = AXIS_Y + PRICE_H + 26
RAIL_H = 26
RAIL_GAP = 10
BAND_TOP = RAIL_TOP + 2 * (RAIL_H + RAIL_GAP) + 34
BAND_H = 30
NOTE_H = 232

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#ebebeb"
PEAK_COL = "#c62828"
TROUGH_COL = "#2e7d32"
PRICE_COL = "#1f5fa8"
SET_B_COL = "#4a4e8c"
SET_B_RAIL = "#5c619e"
BOX = "#dcdcdc"
GAP_FILL = "#f2f2f2"


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
    dates: list[date], prices: list[float], max_points: int
) -> list[tuple[date, float]]:
    """Min-max binned (date, price) pairs: at most two points per bin, in order.

    Stride-sampling would drop the 2011/2013 lows and the 2020 spike the pin bands are
    drawn around; a per-bin min/max pair keeps both extremes while bounding the count.
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


Pin = tuple[str, date, CycleKind]


def _pin_rows(windows: SdcaCycleWindows) -> list[Pin]:
    """``(name, pin, kind)`` in the order the factory declares them (chronological).

    The pin is the window's midpoint: ``CycleWindow`` stores the window, and the pin IS
    the centre by construction (``_window`` builds ``pin +- _HALF_WINDOW``).
    """
    return [(w.name, w.start + (w.end - w.start) // 2, w.kind) for w in windows.windows]


def check_pins(pins: list[Pin], dates: list[date]) -> None:
    """Every pin must be a real bar in the price file. Refuses rather than drawing."""
    bad = [
        f"{name} {kind} {pin.isoformat()}: no row in {DATA_PATH.name}"
        for name, pin, kind in pins
        if pin not in set(dates)
    ]
    if bad:
        raise SystemExit("pins are not bars in the price file:\n  " + "\n  ".join(bad))


def _check_close_extremes(pins: list[Pin], closes: dict[date, float], confirm: int = 5) -> None:
    """A pin must be the first bar of its +-``confirm`` neighbourhood to attain the extreme.

    This is ``detect_turns``' candidate rule, and it is what makes a pin a turning point
    rather than a date somebody liked. It is also what killed the shipped 2026-09-29 pin:
    that date is the final bar of the series, so it has no +5 bars and cannot be a
    candidate at all.
    """
    order = sorted(closes)
    position = {day: i for i, day in enumerate(order)}
    bad: list[str] = []
    for name, pin, kind in pins:
        i = position.get(pin)
        if i is None:
            continue
        if i < confirm or i > len(order) - 1 - confirm:
            bad.append(f"{name} {kind} {pin.isoformat()}: within {confirm} bars of a series edge")
            continue
        neighbourhood = [closes[day] for day in order[i - confirm : i + confirm + 1]]
        here = closes[pin]
        want_max = kind == "peak"
        if (here == max(neighbourhood)) is not want_max:
            bad.append(
                f"{name} {kind} {pin.isoformat()}: close {here:.2f} is not the neighbourhood extreme"
            )
        elif neighbourhood.index(here) != confirm:
            bad.append(f"{name} {kind} {pin.isoformat()}: not the first bar to attain the extreme")
    if bad:
        raise SystemExit("pins are not close-based extrema:\n  " + "\n  ".join(bad))


def _window_dates(pin: date) -> tuple[date, date]:
    half = timedelta(days=HALF_WINDOW_DAYS)
    return pin - half, pin + half


def _axis(
    dates: list[date],
    x_of: Callable[[date], float],
    y_top: float,
    y_bot: float,
    *,
    labels: bool = True,
) -> list[str]:
    """Vertical year gridlines across a region. ``labels=False`` for the lower regions:
    a second row of year numbers under the rails reads as a second x-axis and collides
    with the source line."""
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


def _panel(dates: list[date], closes: list[float], set_a: list[Pin], set_b: list[Pin]) -> str:
    """Close line, Set A windows shaded over the panel, the algorithmic set as a rail."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    lo, hi = min(closes), max(closes)
    pad = (hi - lo) * 0.08

    def x_of(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def y_of(v: float) -> float:
        top, bot = AXIS_Y, AXIS_Y + PRICE_H
        return top + (1.0 - (v - (lo - pad)) / ((hi + pad) - (lo - pad))) * (bot - top)

    by_date = dict(zip(dates, closes, strict=True))
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

    # The algorithmic set's 20 windows, as a faint wash. Drawn first so Set A's bands and
    # both sets' markers read on top of them.
    for _name, pin, kind in set_b:
        start, end = _window_dates(pin)
        x0, x1 = x_of(start), x_of(end)
        parts.append(
            f'<rect x="{x0:.1f}" y="{AXIS_Y}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="{PRICE_H}" fill="{_color(kind)}" fill-opacity="0.05"/>'
        )

    # Set A's six windows, stronger and with a solid bar on the panel's bottom edge.
    for _name, pin, kind in set_a:
        start, end = _window_dates(pin)
        x0, x1 = x_of(start), x_of(end)
        col = _color(kind)
        parts.append(
            f'<rect x="{x0:.1f}" y="{AXIS_Y}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="{PRICE_H}" fill="{col}" fill-opacity="0.11"/>'
        )
        parts.append(
            f'<rect x="{x0:.1f}" y="{AXIS_Y + PRICE_H - 8}" width="{max(x1 - x0, 1.0):.1f}" '
            f'height="8" fill="{col}" fill-opacity="0.8"/>'
        )

    series = _minmax_series(dates, closes, MAX_POLYLINE_POINTS)
    pts = " ".join(f"{x_of(d):.1f},{y_of(p):.1f}" for d, p in series)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{PRICE_COL}" stroke-width="1.5"/>')

    # The 20 algorithmic turns: small diamonds, no labels (there is no room, and the rail
    # below carries their identity). Shared pins get a ring so the eye finds them.
    a_pins = {pin for _n, pin, _k in set_a}
    for _name, pin, kind in set_b:
        x, y, col = x_of(pin), y_of(by_date[pin]), _color(kind)
        shared = pin in a_pins
        size = 5.0 if shared else 4.0
        parts.append(
            f'<polygon points="{x:.1f},{y - size:.1f} {x + size:.1f},{y:.1f} '
            f'{x:.1f},{y + size:.1f} {x - size:.1f},{y:.1f}" fill="{col}" '
            f'fill-opacity="{0.95 if shared else 0.6}" stroke="white" stroke-width="0.7"/>'
        )

    # Set A: prominent labelled circles, alternating above/below so the 2015-2022 cluster
    # stays legible. A pin in the top quarter of the panel always labels DOWNWARD: the
    # 2026-01-29 high sits near the panel top, where an upward label runs into the
    # header row.
    ceiling = AXIS_Y + PRICE_H * 0.28
    for i, (_name, pin, kind) in enumerate(set_a):
        x, y, col = x_of(pin), y_of(by_date[pin]), _color(kind)
        up = i % 2 == 0 and y > ceiling
        parts.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" '
            f'y2="{y - 38 if up else y + 38:.1f}" stroke="{col}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{col}" stroke="white" stroke-width="1.6"/>'
        )
        ly = y - 42 if up else y + 50
        anchor = "middle"
        if x < MARGIN_L + 46:
            anchor = "start"
        elif x > W - MARGIN_R - 46:
            anchor = "end"
        parts.append(
            _backed_text(
                x, ly, f"{pin.isoformat()}  ${by_date[pin]:.2f}", size=11, fill=col, anchor=anchor
            )
        )
        parts.append(
            _text(
                x,
                ly + (-12 if up else 12),
                f"{kind} · Set A",
                size=9,
                fill=MUTED,
                anchor=anchor,
            )
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
            "Set A ±45d bands (strong, bar at panel foot) over the 20-turn gold_v2() wash (faint)",
            size=10,
            fill=MUTED,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R,
            AXIS_Y - 10,
            f"{dates[0].isoformat()} → {dates[-1].isoformat()} · {len(dates)} closes",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def _rails(dates: list[date], set_a: list[Pin], set_b: list[Pin]) -> str:
    """Two window rails + the buy/sell alternation band."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()

    def x_of(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    parts: list[str] = []
    parts += _axis(dates, x_of, RAIL_TOP - 18, BAND_TOP + BAND_H + 18, labels=False)

    # Rail 1 — Set A. Rail 2 — the algorithmic 20, hatched so the two read apart even in
    # greyscale or for a colour-vision deficiency (colour alone never carries the split).
    for row, (label, pins, hatch) in enumerate(
        [("gold_v1() Set A", set_a, None), ("gold_v2() algorithmic", set_b, "url(#hatch)")]
    ):
        y = RAIL_TOP + row * (RAIL_H + RAIL_GAP)
        parts.append(
            f'<rect x="{MARGIN_L}" y="{y}" width="{pw}" height="{RAIL_H}" fill="{GAP_FILL}" '
            f'stroke="{BOX}"/>'
        )
        for _name, pin, kind in pins:
            start, end = _window_dates(pin)
            x0, x1 = x_of(start), x_of(end)
            width = max(x1 - x0, 2.0)
            col = _color(kind)
            parts.append(
                f'<rect x="{x0:.1f}" y="{y}" width="{width:.1f}" height="{RAIL_H}" '
                f'fill="{col}" fill-opacity="0.30"/>'
            )
            if hatch:
                parts.append(
                    f'<rect x="{x0:.1f}" y="{y}" width="{width:.1f}" height="{RAIL_H}" '
                    f'fill="{hatch}"/>'
                )
            parts.append(
                f'<line x1="{x_of(pin):.1f}" y1="{y:.1f}" x2="{x_of(pin):.1f}" '
                f'y2="{y + RAIL_H:.1f}" stroke="{col}" stroke-width="1.6"/>'
            )
        parts.append(
            _backed_text(
                MARGIN_L + 8,
                y + RAIL_H / 2 + 4,
                f"{label} · ±{HALF_WINDOW_DAYS}d · {len(pins)} pins",
                size=11,
                fill=INK,
                weight="bold",
                pad=GAP_FILL,
            )
        )

    # The alternation band: one segment per turn window, coloured by kind, so buy / sell /
    # buy / sell is readable left to right rather than inferred from a pin list.
    parts.append(
        _backed_text(
            MARGIN_L + 2,
            BAND_TOP - 9,
            "buy / sell alternation · P = peak (sell side), T = trough (buy side) "
            "· vertical tick = the turn is also in Set A",
            size=11,
            fill=INK,
            weight="bold",
            pad="white",
        )
    )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{BAND_TOP}" width="{pw}" height="{BAND_H}" '
        f'fill="{GAP_FILL}" stroke="{BOX}"/>'
    )
    letter_x = MARGIN_L - 100.0
    for _name, pin, kind in set_b:
        start, end = _window_dates(pin)
        x0, x1 = x_of(start), x_of(end)
        col = _color(kind)
        parts.append(
            f'<rect x="{x0:.1f}" y="{BAND_TOP}" width="{max(x1 - x0, 1.5):.1f}" '
            f'height="{BAND_H}" fill="{col}" fill-opacity="0.55"/>'
        )
        # A letter only where it fits: the 2011-2014 turns are 61 days apart, so printing
        # one letter per turn would overlap three deep. Skipping keeps the rest readable.
        x = x_of(pin)
        if x - letter_x >= 13.0:
            letter_x = x
            parts.append(
                _text(
                    x,
                    BAND_TOP + BAND_H / 2 + 4,
                    kind[0].upper(),
                    size=11,
                    fill="white",
                    anchor="middle",
                    weight="bold",
                )
            )
    # Set A's six picks ticked onto the band: the approved set is a subset of the
    # alternation, not a competing sequence. Ticks stay INSIDE the band so they never
    # cross the legend line above it.
    a_pins = {pin for _n, pin, _k in set_a}
    for _name, pin, _kind in set_b:
        if pin not in a_pins:
            continue
        x = x_of(pin)
        parts.append(
            f'<line x1="{x:.1f}" y1="{BAND_TOP:.1f}" x2="{x:.1f}" '
            f'y2="{BAND_TOP + BAND_H:.1f}" stroke="{INK}" stroke-width="1.1"/>'
        )
    return "\n".join(parts)


def _legend_block(set_a: list[Pin], set_b: list[Pin]) -> str:
    top = BAND_TOP + BAND_H + 62
    parts: list[str] = []
    rows = [
        (
            "Set A — gold_v1(), 6 pins",
            "owner-approved, close-based, detector-corroborated at 0-bar offsets",
        ),
        (
            "gold_v2() — 20 turns",
            "detect_turns at min_move_pct=15.0, min_separation_days=45, confirmation_bars=5",
        ),
        (
            "granularity by rule",
            "select_sensitivity_level: capture depth 15.7457 vs 10.6792 (10%) / 7.1547 (5%)",
        ),
        (
            "pairing",
            "strictly alternating peak/trough, every peak paired; Set A ⊆ gold_v2(), same kinds",
        ),
        (
            "Set A pins",
            " · ".join(f"{pin.isoformat()} {kind[0].upper()}" for _n, pin, kind in set_a),
        ),
        (
            "gold_v2() extras",
            " · ".join(
                f"{pin.isoformat()} {kind[0].upper()}"
                for _n, pin, kind in set_b
                if pin not in {p for _n, p, _k in set_a}
            ),
        ),
    ]
    for i, (key, value) in enumerate(rows):
        y = top + i * 18
        parts.append(_text(MARGIN_L + 6, y, key, size=11, fill=INK, weight="bold"))
        parts.append(_text(MARGIN_L + 200, y, value, size=11, fill=MUTED))
    note_top = top + len(rows) * 18 + 14
    parts.append(
        f'<line x1="{MARGIN_L}" y1="{note_top - 14:.1f}" x2="{W - MARGIN_R}" '
        f'y2="{note_top - 14:.1f}" stroke="{BOX}"/>'
    )
    for i, line in enumerate(_wrap(FOOTER, 150)):
        parts.append(
            _text(
                MARGIN_L + 6,
                note_top + i * 15,
                line,
                size=11,
                fill=PEAK_COL if i == 0 else INK,
                weight="bold" if i == 0 else "normal",
            )
        )
    parts.append(
        _text(
            W - MARGIN_R,
            top - 18,
            f"source: {DATA_PATH.name} close column / {len(set_a) + len(set_b)} pins drawn",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def build_svg(dates: list[date], closes: list[float]) -> str:
    set_a = _pin_rows(SdcaCycleWindows.gold_v1())
    set_b = _pin_rows(SdcaCycleWindows.gold_v2())
    total_h = BAND_TOP + BAND_H + 62 + 6 * 18 + 14 + len(_wrap(FOOTER, 150)) * 15 + 26
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" '
        f'viewBox="0 0 {W} {total_h}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(FOOTER) + "</desc>",
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" '
        f'stroke="{INK}" stroke-width="1.1" stroke-opacity="0.30"/></pattern></defs>',
        f'<rect x="0" y="0" width="{W}" height="{total_h}" fill="white"/>',
        _text(W / 2, TITLE_Y, TITLE, size=15, weight="bold", anchor="middle"),
        _text(W / 2, SUB_Y, SUBTITLE, size=11, fill=MUTED, anchor="middle"),
        _panel(dates, closes, set_a, set_b),
        _rails(dates, set_a, set_b),
        _legend_block(set_a, set_b),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    dates, closes = load_closes(SYMBOL, DATA_PATH)
    by_date = dict(zip(dates, closes, strict=True))
    set_a = _pin_rows(SdcaCycleWindows.gold_v1())
    set_b = _pin_rows(SdcaCycleWindows.gold_v2())
    check_pins(set_a, dates)
    check_pins(set_b, dates)
    _check_close_extremes(set_a, by_date)
    _check_close_extremes(set_b, by_date)

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
    print(
        f"Set A: {len(set_a)} pins, {sum(1 for _, _, k in set_a if k == CycleKind.PEAK)} peaks / "
        f"{sum(1 for _, _, k in set_a if k == CycleKind.TROUGH)} troughs"
    )
    print(
        f"gold_v2(): {len(set_b)} pins, {sum(1 for _, _, k in set_b if k == CycleKind.PEAK)} peaks / "
        f"{sum(1 for _, _, k in set_b if k == CycleKind.TROUGH)} troughs"
    )
    a_pins = {p for _n, p, _k in set_a}
    missing = [p for _n, p, _k in set_b if p not in a_pins]
    print(
        f"Set A subset of gold_v2(): {len(a_pins & {p for _n, p, _k in set_b})}/6; "
        f"gold_v2() adds {len(missing)}"
    )
    print("every pin verified as a close-based +-5-bar extremum of the CSV")


if __name__ == "__main__":
    main()
