#!/usr/bin/env python3
"""Owner decision chart for the LONG-FIRST period set (GLD, #4804 / Plan 21 Task 3c).

ONE stdlib SVG (``gold_long_first_windows.svg``) with three stacked panels,
rendered from the POST-FIX run artifact
``.scratch/gold_period_ladder_postfix.json`` (Ruling 3: the per-kind trough
budget is spent on coverage before prominence):

  A. GLD close, the 28 kept long windows (trough = buy, green; peak = sell,
     red), the 12 COVERAGE-PLACED troughs outlined, the 6 DISPLACED trough pins
     struck out, and the 7 UNCOVERED segments as hatched grey bands labelled
     with their gap_days -- the out-of-market stretches, which are the whole
     decision;
  B. the coverage-placement lane: one dot per placement, at the placed window's
     mid, labelled with the pin and the gap_days it was bought against;
  C. metrics with NO time axis: exposure vs the frozen 70% floor, oracle Sharpe
     vs lump + flat DCA, and the peak/trough day shares vs the 25% cap.

**No run happens here.** No discovery, no scoring, no optimizer, no oracle:
this script reads the numbers the gold run already wrote. The price series is
read (never scored) so panel A shares one axis with the other gold charts, and
its sha256 is checked against the ``data_sha256`` the run recorded -- a
mismatched cache fails loudly instead of drawing an axis that belongs to other
data.

**Every panel carries the ceiling.** These are IN-SAMPLE CEILINGS on the same
history the periods were fit on (the JSON's own ``ceiling_label``): they
measure PERIOD QUALITY, never achievable performance.

**Two caption claims are qualified, deliberately.** (1) The +17pp / -0.15
Sharpe / +14pp maxDD deltas are measured against the ``3b-equivalent``
ablation arm, which was scored REPORT-ONLY (task-3c-report.md section 5) and is
in no JSON -- the post-fix side of that comparison is the only side this
script reads from the artifact, so the arm is drawn as a clearly-labelled
reference, never as a filed row. (2) "residual holes bounded by the 15% hit
bar, not the budget" holds for the two largest holes; the 313d hole is instead
CAP-bound (the JSON's own uncovered reason quotes the day budget), so the
caption says which holes it speaks for.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import load_closes

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / ".scratch" / "gold_period_ladder_postfix.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_long_first_windows.svg"

# Min-max binning keeps the polyline under this many points (2 per bin).
MAX_POLYLINE_POINTS = 2000

# Binding caption, drawn verbatim in the subtitle and repeated as the figure's
# <desc>. Every rendering of this chart carries it.
BINDING_CAPTION = (
    "LONG-FIRST period set - NOT selected (exposure 55.6% vs 70% floor); coverage bought "
    "exposure (+17pp) and paid Sharpe (-0.15) + maxDD (+14pp); 7 uncovered segments, longest "
    "1433d; residual holes bounded by the 15% hit bar, not the budget"
)

# The Rule-3 ablation arm. REPORT-ONLY: scored in
# .superpowers/sdd/2026-10-02-long-first-periods/task-3c-report.md section 5 and
# filed in NO JSON, so it is drawn as a hatched reference bar, never as a filed
# row. The filed pre-fix ladder JSON is a DIFFERENT arm (15p/13t prominence-first,
# no hit gate), which is why the deltas are not derivable from the artifact.
ABLATION_ARM = {
    "label": "3b-equiv arm (report-only)",
    "exposure_pct": 38.17,
    "sharpe": 0.6529,
    "max_drawdown_pct": 26.25,
}

W = 1500
MARGIN_L, MARGIN_R = 70, 40
PRICE_H, MARKER_ROW_H, LANE_H, METRIC_H = 300, 15, 92, 250

INK = "#222"
MUTED = "#666"
PEAK_COL = "#cc2222"
TROUGH_COL = "#2a7a2a"
PLACED_COL = "#0b6b0b"
DISP_COL = "#a11"
GAP_FILL = "#8a8a8a"
FLOOR_COL = "#b8860b"
LUMP_COL = "#1f5fa8"
FLAT_COL = "#7a5195"
BAND_BG = "#f7f7f7"
WARN = "#a11"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 10,
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
    size: int = 10,
    fill: str = INK,
    weight: str = "normal",
    anchor: str = "start",
) -> str:
    """Text over a white pad, so a row label survives whatever it crosses."""
    per_char = 0.56 * size
    width = per_char * len(text) + 6
    pad_x = x - width + 3 if anchor == "end" else x - 3
    return (
        f'<rect x="{pad_x:.1f}" y="{y - size + 1:.1f}" width="{width:.1f}" '
        f'height="{size + 3}" fill="white" fill-opacity="0.88"/>'
        + _text(x, y, text, size=size, fill=fill, weight=weight, anchor=anchor)
    )


def _minmax_series(
    dates: list[date], prices: list[float], max_points: int
) -> list[tuple[date, float]]:
    """Min-max binned (date, price) pairs: at most two points per bin, in order.

    Plain stride-sampling would drop the 2011-2013 lows and the 2020 spike that
    the uncovered bands are drawn around; a per-bin min/max pair keeps both the
    extremes of every bin while bounding the file size.
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


def _uncovered(sel: dict) -> list[dict]:
    """Segments the coverage walk could not close (gap dates + gap_days)."""
    segs = [s for s in sel["coverage_segments"] if not s["covered"] and s["gap_days"] > 0]
    segs.sort(key=lambda s: s["gap_days"], reverse=True)
    return segs


def _window_for_pin(sel: dict, pin: str) -> dict | None:
    """The kept window a placement pin bought (name convention, then containment)."""
    wanted = f"long_trough_{pin.replace('-', '')}_pm{sel['half_width_days']}"
    for win in sel["windows"]:
        if win["name"] == wanted:
            return win
    pd = date.fromisoformat(pin)
    for win in sel["windows"]:
        if win["kind"] == "trough" and date.fromisoformat(win["start"]) <= pd <= date.fromisoformat(
            win["end"]
        ):
            return win
    return None


def _defs() -> str:
    return (
        "<defs>"
        '<pattern id="gapHatch" width="7" height="7" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        f'<rect width="7" height="7" fill="{GAP_FILL}" fill-opacity="0.10"/>'
        f'<line x1="0" y1="0" x2="0" y2="7" stroke="#5f5f5f" stroke-opacity="0.55" '
        'stroke-width="1.5"/>'
        "</pattern>"
        '<pattern id="armHatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        f'<rect width="6" height="6" fill="{MUTED}" fill-opacity="0.10"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{MUTED}" stroke-opacity="0.5" '
        'stroke-width="1.2"/>'
        "</pattern>"
        "</defs>"
    )


def _header(payload: dict, sel: dict, deltas: dict) -> tuple[list[str], float]:
    """Title + binding caption + the ceiling and qualification notes."""
    parts = [
        _text(
            W / 2,
            24,
            "GLD long-first period set: NOT selected - 55.6% time in market vs the frozen "
            "70.0% floor (in-sample ceiling)",
            size=16,
            weight="bold",
            anchor="middle",
        )
    ]
    y = 43.0
    for line in _wrap(BINDING_CAPTION, 150):
        parts.append(_text(W / 2, y, line, size=11, fill=WARN, anchor="middle", weight="bold"))
        y += 13
    y += 4
    notes = [
        payload["ceiling_label"],
        payload["objective_label"],
        "",
        f"Qualification 1: the +17pp exposure / -0.15 Sharpe / +14pp maxDD deltas are vs the "
        f"{ABLATION_ARM['label']}, scored REPORT-ONLY in "
        f".superpowers/sdd/2026-10-02-long-first-periods/task-3c-report.md section 5 and filed "
        f"in NO json ({deltas['exp_pp']:+.1f}pp / {deltas['sharpe']:+.2f} / "
        f"{deltas['dd_pp']:+.1f}pp as printed there); it is drawn hatched below, never as a "
        f"filed row.",
        f"Qualification 2: the hit-bar bound speaks for the two largest holes "
        f"({sel['longest_uncovered_gap_days']}d and 1228d, no hit trough candidate inside them). "
        f"The 313d hole is CAP-bound instead: trough budget {sel['trough_days']} of "
        f"{int(sel['max_peak_days_pct'] / 100 * sel['calendar_days'])} days is already spent, "
        f"and the two kinds are capped independently.",
        f"{payload['calendar']['first']}..{payload['calendar']['last']}, "
        f"{payload['calendar']['bars']} bars; source .scratch/gold_period_ladder_postfix.json "
        f"(variant {payload['variant']}), data sha256 {payload['data_sha256'][:12]}... verified.",
    ]
    for line in notes:
        for wrapped in _wrap(line, 172) or [""]:
            if wrapped:
                parts.append(_text(MARGIN_L, y, wrapped, size=10, fill=MUTED))
            y += 12.5
    return parts, y


def price_panel(
    payload: dict, sel: dict, dates: list[date], prices: list[float], top: float
) -> tuple[list[str], float]:
    """GLD close, the kept windows, the placed/displaced troughs, the open gaps."""
    pw = W - MARGIN_L - MARGIN_R
    box_top = top + 8.0
    box_h = PRICE_H - MARKER_ROW_H * 2 - 22
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    p_lo, p_hi = min(prices), max(prices)
    pad = (p_hi - p_lo) * 0.08

    def sx(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        return box_top + (1.0 - (v - (p_lo - pad)) / ((p_hi + pad) - (p_lo - pad))) * box_h

    def clip(d: date) -> float:
        return min(max(sx(d), MARGIN_L), MARGIN_L + pw)

    placed_pins = {p["pin"] for p in sel["coverage_placements"]}
    parts = [
        _text(
            MARGIN_L,
            top - 4,
            f"A. GLD close, the {len(sel['windows'])} kept long windows "
            f"({sel['n_peaks']} peak / {sel['n_troughs']} trough) and the "
            f"{sel['n_uncovered_segments']} stretches left uncovered",
            size=12,
            weight="bold",
        ),
        f'<rect x="{MARGIN_L}" y="{box_top:.0f}" width="{pw:.0f}" height="{box_h:.0f}" '
        f'fill="{BAND_BG}"/>',
    ]

    # Uncovered segments first: they are the out-of-market stretches, so they sit
    # UNDER everything (the price line stays readable on top of the hatch).
    for seg in _uncovered(sel):
        xa, xb = (
            clip(date.fromisoformat(seg["gap_start"])),
            clip(date.fromisoformat(seg["gap_end"])),
        )
        w = max(xb - xa, 1.0)
        parts.append(
            f'<rect x="{xa:.1f}" y="{box_top:.0f}" width="{w:.1f}" height="{box_h:.0f}" '
            f'fill="url(#gapHatch)" stroke="#5f5f5f" stroke-dasharray="4,3" stroke-width="0.9"/>'
        )
        label = f"{seg['gap_days']}d"
        lw = 5.4 * len(label) + 6
        lx = min(max((xa + xb) / 2 - lw / 2, MARGIN_L + 2), MARGIN_L + pw - lw - 2)
        parts.append(
            f'<rect x="{lx:.1f}" y="{box_top + 2:.0f}" width="{lw:.1f}" height="12" '
            f'fill="white" fill-opacity="0.85"/>'
        )
        parts.append(
            _text(lx + lw / 2, box_top + 11.5, label, size=9, fill="#444", anchor="middle")
        )

    # Kept windows: trough = buy side (green), peak = sell side (red).
    for win in sel["windows"]:
        xa = clip(date.fromisoformat(win["start"]))
        xb = clip(date.fromisoformat(win["end"]))
        is_trough = win["kind"] == "trough"
        fill = TROUGH_COL if is_trough else PEAK_COL
        parts.append(
            f'<rect x="{xa:.1f}" y="{box_top:.0f}" width="{max(xb - xa, 0.8):.1f}" '
            f'height="{box_h:.0f}" fill="{fill}" '
            f'fill-opacity="{0.30 if is_trough else 0.20}"/>'
        )

    # Placed troughs get a distinct outline on top of the shared shading.
    for pin in sorted(placed_pins):
        win = _window_for_pin(sel, pin)
        if win is None:
            continue
        xa = clip(date.fromisoformat(win["start"]))
        xb = clip(date.fromisoformat(win["end"]))
        parts.append(
            f'<rect x="{xa:.1f}" y="{box_top:.0f}" width="{max(xb - xa, 1.2):.1f}" '
            f'height="{box_h:.0f}" fill="none" stroke="{PLACED_COL}" stroke-width="1.5"/>'
        )

    # Displaced pins: the band they would have taken, drawn hollow and struck.
    hw = sel["half_width_days"]
    for rec in sel["displaced_troughs"]:
        pd = date.fromisoformat(rec["pin"])
        xa, xb = clip(pd - timedelta(days=hw)), clip(pd + timedelta(days=hw))
        parts.append(
            f'<rect x="{xa:.1f}" y="{box_top:.0f}" width="{max(xb - xa, 1.2):.1f}" '
            f'height="{box_h:.0f}" fill="none" stroke="{DISP_COL}" stroke-width="1" '
            f'stroke-dasharray="3,2"/>'
        )

    series = _minmax_series(dates, prices, MAX_POLYLINE_POINTS)
    pts = " ".join(f"{sx(d):.1f},{sy(p):.1f}" for d, p in series)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.1"/>')

    for yr in range(dates[0].year + 1, dates[-1].year + 1, 3):
        x = sx(date(yr, 1, 1))
        parts.append(
            f'<line x1="{x:.1f}" y1="{box_top:.0f}" x2="{x:.1f}" y2="{box_top + box_h:.0f}" '
            'stroke="#ffffff" stroke-width="0.7"/>'
        )
        parts.append(_text(x, box_top + box_h + 12, str(yr), size=10, fill=MUTED, anchor="middle"))
    for price in (p_lo, p_hi):
        parts.append(
            _text(MARGIN_L - 6, sy(price) + 3, f"{price:.0f}", size=9, fill=MUTED, anchor="end")
        )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{box_top:.0f}" width="{pw:.0f}" height="{box_h:.0f}" '
        'fill="none" stroke="#bbb"/>'
    )

    # Two marker rows: what coverage bought, and what it took.
    rows = [
        (
            f"coverage-placed x{len(placed_pins)}",
            [date.fromisoformat(p) for p in sorted(placed_pins)],
            "dot",
            PLACED_COL,
        ),
        (
            f"displaced x{len(sel['displaced_troughs'])}",
            [date.fromisoformat(r["pin"]) for r in sel["displaced_troughs"]],
            "strike",
            DISP_COL,
        ),
    ]
    row_top = box_top + box_h + 20
    for i, (label, pins, kind, col) in enumerate(rows):
        y = row_top + i * MARKER_ROW_H
        parts.append(
            f'<rect x="{MARGIN_L}" y="{y:.1f}" width="{pw:.0f}" height="{MARKER_ROW_H - 3:.0f}" '
            f'fill="{BAND_BG}"/>'
        )
        cy = y + (MARKER_ROW_H - 3) / 2
        for pd in pins:
            x = sx(pd)
            if kind == "dot":
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{cy:.1f}" r="3" fill="{col}" fill-opacity="0.9"/>'
                )
            else:
                parts.append(
                    f'<line x1="{x - 3.5:.1f}" y1="{cy - 3.5:.1f}" x2="{x + 3.5:.1f}" '
                    f'y2="{cy + 3.5:.1f}" stroke="{col}" stroke-width="1.6"/>'
                )
                parts.append(
                    f'<line x1="{x - 3.5:.1f}" y1="{cy + 3.5:.1f}" x2="{x + 3.5:.1f}" '
                    f'y2="{cy - 3.5:.1f}" stroke="{col}" stroke-width="1.6"/>'
                )
        parts.append(
            _backed_text(
                MARGIN_L + pw - 2, y + MARKER_ROW_H - 4, label, size=9, fill=col, anchor="end"
            )
        )

    end = row_top + len(rows) * MARKER_ROW_H
    gaps = ", ".join(f"{s['gap_days']}d" for s in _uncovered(sel))
    spans = ", ".join(f"{s['gap_start']}..{s['gap_end']}" for s in _uncovered(sel)[:2])
    disp = ", ".join(r["pin"] for r in sel["displaced_troughs"])
    lines = [
        "green band = trough window (buy) | red band = peak window (sell) | dark green "
        "outline = coverage-placed trough | red dashed = displaced trough | hatched grey = "
        "uncovered stretch",
        f"Hatched bands = the {sel['n_uncovered_segments']} segments coverage could not close "
        f"({gaps}); the two biggest are {spans}. Each is a stretch with NO trough window, "
        f"i.e. flat.",
        f"Struck pins are troughs coverage spent elsewhere ({disp}) - all {len(disp.split())} "
        f"were hit windows; dashed outlines are the bands they gave up.",
    ]
    for i, line in enumerate(lines):
        parts.append(_text(MARGIN_L, end + 13 + i * 13, line, size=10, fill=MUTED))
    return parts, end + 13 * len(lines)


def placements_panel(sel: dict, dates: list[date], top: float) -> tuple[list[str], float]:
    """One dot per coverage placement, at the placed window's mid."""
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()

    def sx(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    parts = [
        _text(
            MARGIN_L,
            top - 4,
            f"B. Where the trough budget went: {sel['n_coverage_placements']} coverage "
            f"placements (dot = placed window mid; label = pin + gap_days bought)",
            size=12,
            weight="bold",
        )
    ]
    lane_top = top + 10.0
    lane_h = 34.0
    parts.append(
        f'<rect x="{MARGIN_L}" y="{lane_top:.0f}" width="{pw:.0f}" height="{lane_h:.0f}" '
        f'fill="{BAND_BG}"/>'
    )
    mid = lane_top + lane_h / 2
    parts.append(
        f'<line x1="{MARGIN_L}" y1="{mid:.1f}" x2="{MARGIN_L + pw:.0f}" y2="{mid:.1f}" '
        f'stroke="#c9c9c9"/>'
    )
    last_label_x = -(10**6)
    placed = sorted(sel["coverage_placements"], key=lambda p: p["pin"])
    for rec in placed:
        win = _window_for_pin(sel, rec["pin"])
        if win is None:
            continue
        start, end = date.fromisoformat(win["start"]), date.fromisoformat(win["end"])
        x = sx(start + (end - start) / 2)
        parts.append(f'<circle cx="{x:.1f}" cy="{mid:.1f}" r="3.6" fill="{PLACED_COL}"/>')
        # Greedy skip: labels only where the previous one left room, so a dense
        # cluster of pins stays a cluster instead of an unreadable pile of text.
        if x - last_label_x > 74:
            parts.append(
                _text(
                    x,
                    lane_top + lane_h + 11,
                    f"{rec['pin']} / {rec['gap_days']}d",
                    size=8,
                    fill=PLACED_COL,
                    anchor="middle",
                )
            )
            last_label_x = x
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 3):
        x = sx(date(yr, 1, 1))
        parts.append(
            f'<line x1="{x:.1f}" y1="{lane_top:.0f}" x2="{x:.1f}" '
            f'y2="{lane_top + lane_h:.0f}" stroke="#ffffff" stroke-width="0.7"/>'
        )
        parts.append(
            _text(x, lane_top + lane_h + 24, str(yr), size=10, fill=MUTED, anchor="middle")
        )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{lane_top:.0f}" width="{pw:.0f}" height="{lane_h:.0f}" '
        'fill="none" stroke="#bbb"/>'
    )
    order = "longest gap first, earliest on a tie, best hit trough by prominence"
    parts.append(
        _text(
            MARGIN_L,
            lane_top + lane_h + 40,
            f"Walk order ({sel['coverage_rule'].split(':')[0]}): {order}. gap_days is the "
            f"segment length AT PLACEMENT TIME, so later placements quote a partly closed "
            f"map - read panel A for the holes that stayed.",
            size=10,
            fill=MUTED,
        )
    )
    return parts, lane_top + lane_h + 40


def _bar_column(
    x0: float,
    col_w: float,
    top: float,
    title: str,
    rows: list[tuple[str, float, str, bool]],
    vmax: float,
    marker: tuple[float, str] | None,
    fmt: str,
) -> list[str]:
    """One metrics column: horizontal bars + one vertical reference line."""
    parts = [_text(x0, top, title, size=10, weight="bold")]
    label_w = 118.0
    value_w = 56.0
    track = col_w - label_w - value_w
    row_h = 21.0
    base = top + 16
    n_rows = len(rows)
    if marker is not None:
        val, note = marker
        x_m = x0 + label_w + val / vmax * track
        parts.append(
            f'<line x1="{x_m:.1f}" y1="{base - 4:.0f}" x2="{x_m:.1f}" '
            f'y2="{base + row_h * n_rows:.0f}" stroke="{FLOOR_COL}" stroke-width="1.3" '
            f'stroke-dasharray="5,3"/>'
        )
        parts.append(_text(x_m + 4, base - 7, note, size=9, fill=FLOOR_COL, weight="bold"))
    for i, (label, value, col, reference) in enumerate(rows):
        y = base + i * row_h
        parts.append(_text(x0, y + 13, label, size=9, fill=MUTED if reference else INK))
        w = max(value, 0.0) / vmax * track
        fill = "url(#armHatch)" if reference else col
        parts.append(
            f'<rect x="{x0 + label_w:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="11" '
            f'fill="{fill}" fill-opacity="{0.85 if not reference else 1.0}"/>'
        )
        if reference:
            parts.append(
                f'<rect x="{x0 + label_w:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="11" '
                f'fill="none" stroke="{MUTED}" stroke-dasharray="3,2" stroke-width="1"/>'
            )
        parts.append(
            _text(
                x0 + label_w + w + 5,
                y + 13,
                f"{value:{fmt}}",
                size=9,
                fill=MUTED if reference else INK,
                weight="normal" if reference else "bold",
            )
        )
    return parts


def metrics_panel(payload: dict, sel: dict, top: float, deltas: dict) -> tuple[list[str], float]:
    """Exposure vs the floor, Sharpe vs the comparators, day shares vs the cap."""
    pure = payload["pure_long"]
    comps = payload["comparators"]
    lump = comps["lump_mark_to_market"]
    flat = comps["flat_dca_mark_to_market"]
    cap = sel["max_peak_days_pct"]
    budget = int(cap / 100 * sel["calendar_days"])
    floor = float(payload["exposure_floor_pct"])

    stop = payload["overlay"]["stop_reason"]
    stop = stop.split(": ", 1)[1] if stop.startswith("unhit: ") else stop
    parts = [
        _text(
            MARGIN_L,
            top - 4,
            "C. What the set buys and what it costs (no time axis; in-sample ceilings)",
            size=12,
            weight="bold",
        ),
        _text(
            MARGIN_L,
            top + 11,
            f"pure_long is NOT selected: {payload['pure_long_rejection']}. The ladder adds "
            f"nothing - rung 1 is ABANDONED unhit ({stop[:70]}...), so the medium rungs never "
            f"bought a single day.",
            size=10,
            fill=MUTED,
        ),
    ]
    base = top + 26
    gap = 26.0
    col_w = (W - MARGIN_L - MARGIN_R - 2 * gap) / 3

    parts += _bar_column(
        MARGIN_L,
        col_w,
        base,
        "Time in market (%)",
        [
            ("pure_long (28 win)", pure["exposure_pct"], PLACED_COL, False),
            ("lump", lump["exposure_pct"], LUMP_COL, False),
            ("flat DCA", flat["exposure_pct"], FLAT_COL, False),
            (ABLATION_ARM["label"], ABLATION_ARM["exposure_pct"], MUTED, True),
        ],
        100.0,
        (floor, f"frozen floor {floor:.1f}%"),
        ".2f",
    )
    parts += _bar_column(
        MARGIN_L + col_w + gap,
        col_w,
        base,
        "Oracle Sharpe (in-sample ceiling)",
        [
            ("pure_long", pure["sharpe"], PLACED_COL, False),
            ("lump", lump["sharpe"], LUMP_COL, False),
            ("flat DCA", flat["sharpe"], FLAT_COL, False),
            (ABLATION_ARM["label"], ABLATION_ARM["sharpe"], MUTED, True),
        ],
        max(lump["sharpe"], ABLATION_ARM["sharpe"]) * 1.08,
        None,
        ".4f",
    )
    parts += _bar_column(
        MARGIN_L + 2 * (col_w + gap),
        col_w,
        base,
        f"Window day share (%) of a {budget}d budget",
        [
            ("peak days", sel["peak_days_pct"], PEAK_COL, False),
            ("trough days", sel["trough_days_pct"], TROUGH_COL, False),
        ],
        cap * 1.25,
        (cap, f"{cap:.1f}% per-kind cap"),
        ".2f",
    )

    y = base + 16 + 21 * 4 + 14
    lines = [
        "What coverage bought (vs the report-only 3b-equivalent arm): "
        f"{deltas['exp_pp']:+.1f}pp exposure {pure['exposure_pct']:.2f}% vs "
        f"{ABLATION_ARM['exposure_pct']:.2f}%, {deltas['sharpe']:+.2f} Sharpe "
        f"{pure['sharpe']:.4f} vs {ABLATION_ARM['sharpe']:.4f}, "
        f"{deltas['dd_pp']:+.1f}pp maxDD {pure['max_drawdown_pct']:.2f}% vs "
        f"{ABLATION_ARM['max_drawdown_pct']:.2f}% - and it still missed the floor by "
        f"{floor - pure['exposure_pct']:.2f}pp.",
        f"Both comparators are invested from day 0 (100% by construction) and both beat the "
        f"pure-long ceiling on Sharpe; flat DCA also halves the drawdown "
        f"({flat['max_drawdown_pct']:.2f}% vs {pure['max_drawdown_pct']:.2f}%).",
        f"Day shares are SEPARATE quantities under a per-kind cap - only PEAK days bound the "
        f"exposure floor ({sel['peak_days_pct']:.2f}% peak / {sel['trough_days_pct']:.2f}% "
        f"trough of {budget}d each), so the trough walk cannot borrow from peaks.",
        f"Split-sample out-of-sample side: Sharpe "
        f"{payload['split_sample']['out_of_sample']['sharpe']:.2f}, exposure "
        f"{payload['split_sample']['out_of_sample']['exposure_pct']:.2f}% - "
        f"{payload['split_sample']['acted_dates_out_of_sample']} acted dates on the unseen half "
        f"(the filed binary split-side defect). It is a limitation, not a result.",
    ]
    for line in lines:
        fill = WARN if line.startswith("What coverage bought") else MUTED
        for wrapped in _wrap(line, 168):
            parts.append(_text(MARGIN_L, y, wrapped, size=10, fill=fill))
            y += 12.5
        y += 2
    parts.append(_text(MARGIN_L, y, BINDING_CAPTION + ".", size=10, fill=WARN, weight="bold"))
    return parts, y


def build(payload: dict, dates: list[date], prices: list[float], deltas: dict) -> tuple[str, int]:
    sel = payload["long_selection"]
    head, y = _header(payload, sel, deltas)
    body: list[str] = []
    panel, y = price_panel(payload, sel, dates, prices, y + 14)
    body += panel
    panel, y = placements_panel(sel, dates, y + 26)
    body += panel
    panel, y = metrics_panel(payload, sel, y + 30, deltas)
    body += panel
    height = y + 20
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height:.0f}" '
        'font-family="sans-serif">',
        "<title>GLD long-first period set - not selected, in-sample ceiling</title>",
        f"<desc>{escape(BINDING_CAPTION)}. {escape(payload['ceiling_label'])}</desc>",
        _defs(),
        f'<rect x="0" y="0" width="{W}" height="{height:.0f}" fill="white"/>',
        *head,
        *body,
        "</svg>",
    ]
    return "\n".join(parts) + "\n", len(_minmax_series(dates, prices, MAX_POLYLINE_POINTS))


def main() -> int:
    payload = json.loads(RESULT_PATH.read_text())
    data_path = Path(payload["data_path"])
    digest = _sha256(data_path)
    if digest != payload["data_sha256"]:
        print(
            f"REFUSING to chart: {data_path} sha256 {digest} != the run's "
            f"{payload['data_sha256']} (the price axis would not be the run's data)"
        )
        return 1
    dates, prices = load_closes(payload["symbol"], data_path)
    loaded = (dates[0].isoformat(), dates[-1].isoformat(), len(dates))
    if loaded != (
        payload["calendar"]["first"],
        payload["calendar"]["last"],
        payload["calendar"]["bars"],
    ):
        print(f"REFUSING to chart: loaded calendar {loaded} != the run's {payload['calendar']}")
        return 1

    pure = payload["pure_long"]
    deltas = {
        "exp_pp": pure["exposure_pct"] - ABLATION_ARM["exposure_pct"],
        "sharpe": pure["sharpe"] - ABLATION_ARM["sharpe"],
        "dd_pp": pure["max_drawdown_pct"] - ABLATION_ARM["max_drawdown_pct"],
    }
    svg, n_points = build(payload, dates, prices, deltas)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / SVG_NAME).write_text(svg)
    copied = ""
    if PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / SVG_NAME).write_text(svg)
        copied = f"\n     (+ {PUBLIC_DIR}/{SVG_NAME})"

    print(BINDING_CAPTION)
    print(
        f"\nprice panel: {len(payload['long_selection']['windows'])} windows, "
        f"{payload['long_selection']['n_coverage_placements']} placed, "
        f"{payload['long_selection']['n_displaced_troughs']} displaced, "
        f"{payload['long_selection']['n_uncovered_segments']} uncovered "
        f"(longest {payload['long_selection']['longest_uncovered_gap_days']}d); "
        f"polyline {n_points} pts"
    )
    print(
        f"metrics: pure_long Sharpe {pure['sharpe']:.4f} / exposure {pure['exposure_pct']:.2f}% "
        f"vs floor {payload['exposure_floor_pct']:.1f}% | lump "
        f"{payload['comparators']['lump_mark_to_market']['sharpe']:.4f} | flat "
        f"{payload['comparators']['flat_dca_mark_to_market']['sharpe']:.4f} | vs the "
        f"{ABLATION_ARM['label']}: {deltas['exp_pp']:+.2f}pp / {deltas['sharpe']:+.4f} / "
        f"{deltas['dd_pp']:+.2f}pp"
    )
    print(f"\nwrote {OUT_DIR}/{SVG_NAME} ({len(svg.encode()):,} bytes){copied}")
    print(f"source JSON {RESULT_PATH} (untracked); no optimizer, oracle or backtest run here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
