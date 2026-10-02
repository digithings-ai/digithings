#!/usr/bin/env python3
"""Diagnostic chart for the GLD period-optimization close-out (#4804, Plan 20).

ONE stdlib SVG (``gold_period_optimization_ceiling.svg``) with three panels,
rendered from the Task-3 artifact ``.scratch/gold_period_optimization.json``:

  A. GLD close plus the pivot PIN rows that generated the windows (peak = a
     sell/flat bar, trough = a buy bar), one truncated exit named in the caption;
  B. time-in-market exposure per candidate against the frozen 70.0% floor;
  C. oracle Sharpe per candidate against lump + flat DCA.

**No run happens here.** This script performs no discovery, no scoring and no
backtest: it reads the JSON the gold run already wrote and plots those numbers.
The price series is read (never scored) so panel A shares one axis with the
other gold charts, and its sha256 is checked against the ``data_sha256`` the
gold run recorded — a mismatched cache fails loudly instead of drawing a chart
whose axis belongs to different data.

**No equity panel.** The JSON carries metrics + window sets, not the oracle's
daily equity path, so panel C draws the SCORE (Sharpe), not an equity curve;
drawing equity paths would mean re-running the oracle for numbers that are not
in the recorded artifact.

**Every panel carries the warning.** The window set is dense, ~45% flat, and
NOT selected: no candidate at either horizon cleared the frozen time-in-market
floor, so ``best`` is ``None`` for medium, long and combined. The rank-1 rows
are diagnostics, never "the optimizer's best". The metrics are IN-SAMPLE
CEILINGS that measure PERIOD QUALITY, not achievable performance.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import load_closes

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / ".scratch" / "gold_period_optimization.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_period_optimization_ceiling.svg"

# Binding caption. Printed to the console and drawn verbatim in the SVG (top
# subtitle and panel C footnote), so no rendering of these windows can lose it.
DIAGNOSTIC_CAPTION = (
    "dense, ~45% flat, NOT selected: no candidate at either horizon cleared the "
    "frozen 70.0% time-in-market floor, so best is None for medium, long and combined"
)

W = 1500
MARGIN_L, MARGIN_R = 70, 40
PRICE_H, BAR_H, PIN_ROW_H = 322, 208, 13

INK = "#222"
MUTED = "#666"
PEAK_COL = "#cc2222"
TROUGH_COL = "#2a7a2a"
PEAK_LIGHT_COL = "#e08a8a"
TROUGH_LIGHT_COL = "#8bbd8b"
FLOOR_COL = "#b8860b"
LUMP_COL = "#1f5fa8"
FLAT_COL = "#7a5195"
BAND_BG = "#f7f7f7"
WARN = "#a11"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _candidates(payload: dict) -> list[dict]:
    """Every scored row, medium then long then combined, each under its own grid."""
    rows: list[dict] = []
    for name in ("medium", "long"):
        for cand in sorted(
            payload["horizons"][name]["candidates"], key=lambda c: c["half_width_days"] or 0
        ):
            rows.append(
                {
                    "group": name,
                    "label": f"{name} {cand['label']} ({cand['half_width_days']}d)",
                    "cand": cand,
                }
            )
    rows.append(
        {
            "group": "combined",
            "label": f"combined (pm60+pm180, {payload['combined']['n_windows']} windows)",
            "cand": payload["combined"]["rank1_ineligible_diagnostic"],
        }
    )
    return rows


def _header_lines(payload: dict) -> tuple[list[str], float]:
    """Title + binding caption + the ceiling label, wrapped to the panel width.

    Returns the elements and the y of the last one; the caller sizes the
    ``viewBox`` once every panel bottom is known.
    """
    parts = [
        f'<text x="{W / 2:.0f}" y="24" text-anchor="middle" font-size="16" '
        f'font-weight="bold" fill="{INK}">GLD period optimizer: in-sample ceilings, '
        "NO selectable candidate (Plan 20 close-out)</text>",
        f'<text x="{W / 2:.0f}" y="43" text-anchor="middle" font-size="11" '
        f'fill="{WARN}" font-weight="bold">{escape(DIAGNOSTIC_CAPTION)}</text>',
    ]
    body = [
        *_wrap(payload["ceiling_label"], 168),
        "",
        *_wrap(f"{payload['objective_label']}.", 168),
        *_wrap(f"{payload['risk_conventions_label']}.", 168),
        *_wrap(
            f"{payload['calendar']['first']}..{payload['calendar']['last']}, "
            f"{payload['calendar']['bars']} bars; source "
            f".scratch/gold_period_optimization.json (data sha256 "
            f"{payload['data_sha256'][:12]}..., verified).",
            168,
        ),
    ]
    y = 62.0
    for line in body:
        if line:
            parts.append(
                f'<text x="{MARGIN_L}" y="{y:.0f}" font-size="10" fill="{MUTED}">'
                f"{escape(line)}</text>"
            )
        y += 13
    return parts, y


def price_panel(
    payload: dict,
    dates: list[date],
    prices: list[float],
    top: float,
) -> tuple[list[str], float]:
    """GLD close + the pivot PIN rows; pin density made visible."""
    parts: list[str] = []
    pw = W - MARGIN_L - MARGIN_R
    n_pin_rows = 4
    price_h = PRICE_H - n_pin_rows * PIN_ROW_H - 20
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    p_lo, p_hi = min(prices), max(prices)
    pad = (p_hi - p_lo) * 0.08

    def sx(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        hi_t, lo_t = top + 8.0, top + 8.0 + price_h
        return hi_t + (1.0 - (v - (p_lo - pad)) / ((p_hi + pad) - (p_lo - pad))) * (lo_t - hi_t)

    medium = payload["horizons"]["medium"]
    long_h = payload["horizons"]["long"]
    rows = [
        ("medium peak", PEAK_COL, medium["peak_pins"]),
        ("medium trough", TROUGH_COL, medium["trough_pins"]),
        ("long peak", PEAK_LIGHT_COL, long_h["peak_pins"]),
        ("long trough", TROUGH_LIGHT_COL, long_h["trough_pins"]),
    ]
    trunc = payload["combined"]["rank1_ineligible_diagnostic"]["truncated_windows"]

    parts.append(
        f'<text x="{MARGIN_L}" y="{top - 4:.0f}" font-size="12" font-weight="bold" '
        f'fill="{INK}">A. GLD close and the pivot pins behind the period sets '
        f"({payload['combined']['n_windows']} combined windows = pm60 + pm180)</text>"
    )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{top + 8:.0f}" width="{pw:.0f}" height="{price_h:.0f}" '
        f'fill="{BAND_BG}"/>'
    )
    step = max(1, len(dates) // 1500)
    pts = " ".join(
        f"{sx(d):.1f},{sy(p):.1f}" for d, p in list(zip(dates, prices, strict=True))[::step]
    )
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.1"/>')
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 3):
        x = sx(date(yr, 1, 1))
        parts.append(
            f'<line x1="{x:.1f}" y1="{top + 8:.0f}" x2="{x:.1f}" '
            f'y2="{top + 8 + price_h:.0f}" stroke="#e4e4e4"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{top + 8 + price_h + 12:.0f}" text-anchor="middle" '
            f'font-size="10" fill="{MUTED}">{yr}</text>'
        )
    for price in (p_lo, p_hi):
        parts.append(
            f'<text x="{MARGIN_L - 6}" y="{sy(price) + 3:.1f}" text-anchor="end" '
            f'font-size="9" fill="{MUTED}">{price:.0f}</text>'
        )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{top + 8:.0f}" width="{pw:.0f}" height="{price_h:.0f}" '
        'fill="none" stroke="#bbb"/>'
    )

    pin_top = top + 8 + price_h + 20
    for i, (name, col, pins) in enumerate(rows):
        y = pin_top + i * PIN_ROW_H
        parts.append(
            f'<rect x="{MARGIN_L}" y="{y:.1f}" width="{pw:.0f}" height="{PIN_ROW_H - 3:.0f}" '
            f'fill="{BAND_BG}"/>'
        )
        for iso in pins:
            x = sx(date.fromisoformat(iso))
            parts.append(
                f'<rect x="{x - 0.6:.1f}" y="{y:.1f}" width="1.2" '
                f'height="{PIN_ROW_H - 3:.0f}" fill="{col}"/>'
            )
        label = f"{name} x {len(pins)}"
        label_x = W - MARGIN_R - 12 - 6.2 * len(label)
        parts.append(
            f'<rect x="{label_x - 4:.1f}" y="{y:.1f}" width="{6.2 * len(label) + 8:.1f}" '
            f'height="{PIN_ROW_H - 2:.0f}" fill="white" fill-opacity="0.85"/>'
        )
        parts.append(
            f'<text x="{label_x:.1f}" y="{y + PIN_ROW_H - 3:.1f}" font-size="9" '
            f'fill="{INK}">{escape(label)}</text>'
        )
    end = pin_top + len(rows) * PIN_ROW_H
    parts.append(
        f'<text x="{MARGIN_L}" y="{end + 13:.0f}" font-size="10" fill="{MUTED}">'
        "Every tick is a pivot the price series produced: the oracle sells flat at a peak pin "
        "and buys at a trough pin, so dense pins buy the flat time. Medium finds one pin every "
        f"~{round(len(dates) / max(len(medium['peak_pins']), 1))} bars (pivot widths are "
        f"counted in bars); "
        f"{len(trunc)} window exit is truncated at the last bar "
        f"({escape(', '.join(trunc))}).</text>"
    )
    return parts, end + 13


def _bar_rows(
    payload: dict,
    value_of,
    top: float,
    height: float,
    title: str,
    subtitle: str,
    floor_pct: float | None,
    vmax: float,
    colors: dict[str, str],
    fmt: str,
) -> tuple[list[str], float]:
    """One horizontal bar per scored row, then the two comparators."""
    rows = _candidates(payload)
    row_h = (height - 46) / (len(rows) + 2)
    label_w = 250
    track = W - MARGIN_L - MARGIN_R - label_w - 66
    parts = [
        f'<text x="{MARGIN_L}" y="{top - 4:.0f}" font-size="12" font-weight="bold" '
        f'fill="{INK}">{escape(title)}</text>',
    ]
    sub_lines = _wrap(subtitle, 170)
    for i, line in enumerate(sub_lines):
        parts.append(
            f'<text x="{MARGIN_L}" y="{top + 11 + i * 12:.0f}" font-size="10" '
            f'fill="{MUTED}">{escape(line)}</text>'
        )
    base = top + 22 + 12 * (len(sub_lines) - 1)
    if floor_pct is not None:
        x_floor = MARGIN_L + label_w + floor_pct / vmax * track
        bottom = base + row_h * (len(rows) + 2)
        parts.append(
            f'<line x1="{x_floor:.1f}" y1="{base - 6:.0f}" x2="{x_floor:.1f}" '
            f'y2="{bottom:.0f}" stroke="{FLOOR_COL}" stroke-width="1.4" '
            f'stroke-dasharray="5,3"/>'
        )
        parts.append(
            f'<text x="{x_floor + 5:.1f}" y="{base - 10:.0f}" font-size="9" '
            f'fill="{FLOOR_COL}" font-weight="bold">frozen floor {floor_pct:.1f}% '
            "(every candidate is left of it)</text>"
        )
    for i, row in enumerate(rows):
        y = base + i * row_h
        value = value_of(row["cand"])
        w = max(value, 0.0) / vmax * track
        parts.append(
            f'<text x="{MARGIN_L}" y="{y + row_h / 2 + 3:.1f}" font-size="10" '
            f'fill="{INK}">{escape(row["label"])}</text>'
        )
        parts.append(
            f'<rect x="{MARGIN_L + label_w}" y="{y + 1:.1f}" width="{w:.1f}" '
            f'height="{row_h - 4:.1f}" fill="{colors[row["group"]]}" fill-opacity="0.8"/>'
        )
        parts.append(
            f'<text x="{MARGIN_L + label_w + w + 6:.1f}" y="{y + row_h / 2 + 3:.1f}" '
            f'font-size="10" fill="{INK}">{value:{fmt}}</text>'
        )
    y = base + row_h * (len(rows) + 1)
    for key, col in (("lump_mark_to_market", LUMP_COL), ("flat_dca_mark_to_market", FLAT_COL)):
        comp = payload["comparators"][key]
        value = value_of(comp)
        w = max(value, 0.0) / vmax * track
        parts.append(
            f'<text x="{MARGIN_L}" y="{y + row_h / 2 + 3:.1f}" font-size="10" '
            f'fill="{INK}" font-weight="bold">{escape(comp["label"])} '
            "(comparator)</text>"
        )
        parts.append(
            f'<rect x="{MARGIN_L + label_w}" y="{y + 1:.1f}" width="{w:.1f}" '
            f'height="{row_h - 4:.1f}" fill="{col}"/>'
        )
        parts.append(
            f'<text x="{MARGIN_L + label_w + w + 6:.1f}" y="{y + row_h / 2 + 3:.1f}" '
            f'font-size="10" fill="{INK}" font-weight="bold">{value:{fmt}}</text>'
        )
        y += row_h
    return parts, y


def exposure_panel(payload: dict, top: float) -> tuple[list[str], float]:
    floor = float(payload["exposure_floor_pct"])
    parts, end = _bar_rows(
        payload,
        lambda c: c["exposure_pct"],
        top,
        BAR_H,
        "B. Time in market (oracle exposure) — every candidate misses the floor",
        "Exposure barely moves across the search width (< 1.5 pp spread per horizon): pivot "
        "DENSITY, not the candidate width, decides how much time is flat, and density is "
        "asset-independent. Each horizon is its OWN grid — never a cross-grid contest.",
        floor,
        100.0,
        {"medium": "#5b8db8", "long": "#3f7d4f", "combined": FLOOR_COL},
        ".2f",
    )
    parts.append(
        f'<text x="{MARGIN_L}" y="{end + 26:.0f}" font-size="10" fill="{MUTED}">'
        "Flat share is the complement: the rank-1 medium set is 45.26% flat (exposure "
        "54.74%), the combined set 48.66% (51.34%). Both comparators are invested from day "
        "0, so 100.00% is a property of those two paths.</text>"
    )
    return parts, end + 26


def sharpe_panel(payload: dict, top: float) -> tuple[list[str], float]:
    vmax = max(r["cand"]["sharpe"] for r in _candidates(payload)) * 1.15
    parts, end = _bar_rows(
        payload,
        lambda c: c["sharpe"],
        top,
        BAR_H,
        "C. Oracle Sharpe — even the diagnostic ceilings LOSE to buy-and-hold",
        "In-sample ceilings on the same history the periods were fit on: they measure PERIOD "
        "QUALITY, never achievable performance. Every candidate row above is a rank-1 row "
        "that FAILED the floor, never a selection.",
        None,
        vmax,
        {"medium": "#5b8db8", "long": "#3f7d4f", "combined": FLOOR_COL},
        ".4f",
    )
    parts.append(
        f'<text x="{MARGIN_L}" y="{end + 26:.0f}" font-size="10" fill="{MUTED}">'
        "Sharpe alone is not the whole read: the period sets buy lower drawdown (combined "
        "31.57% vs lump 45.56%) at about half the exposure (panel B).</text>"
    )
    parts.append(
        f'<text x="{MARGIN_L}" y="{end + 41:.0f}" font-size="10" fill="{WARN}">'
        f"{escape(DIAGNOSTIC_CAPTION)}.</text>"
    )
    return parts, end + 41


def build(payload: dict, dates: list[date], prices: list[float]) -> str:
    head, y = _header_lines(payload)
    body: list[str] = []
    panel, y = price_panel(payload, dates, prices, y + 14)
    body += panel
    panel, y = exposure_panel(payload, y + 22)
    body += panel
    panel, y = sharpe_panel(payload, y + 26)
    body += panel
    height = y + 16
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height:.0f}" '
        'font-family="sans-serif">',
        "<title>GLD period optimization — in-sample ceilings, no selectable candidate</title>",
        f'<rect x="0" y="0" width="{W}" height="{height:.0f}" fill="white"/>',
        *head,
        *body,
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


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

    svg = build(payload, dates, prices)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / SVG_NAME).write_text(svg)
    copied = ""
    if PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / SVG_NAME).write_text(svg)
        copied = f" (+ {PUBLIC_DIR}/{SVG_NAME})"

    print(DIAGNOSTIC_CAPTION)
    print(f"wrote {OUT_DIR}/{SVG_NAME}{copied}")
    print(f"source JSON {RESULT_PATH} (untracked); no optimizer, oracle or backtest run here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
