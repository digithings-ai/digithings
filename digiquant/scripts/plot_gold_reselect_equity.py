"""Reselected-shape equity vs benchmarks as stdlib-only SVG (#4804, Plan 16).

Same 960x440 hand-rolled SVG pattern as plot_gold_secular_legs.py (no
plotting library in .venv; pip installs forbidden). Reads precomputed
series ONLY from the reselected diagnostic tearsheet JSON (recomputes
nothing): equity_curve vs lump_equity_curve vs flat_dca_equity_curve,
with the selection marked in the subtitle (rank #1 shape + frozen
criterion value + BEATS-BOTH conditional verdict + disclosures pointer).

Veto accounting: the strategy leg is the masked curve-sim render whose
fills key off daily_trade_usd / fill sell days (34), NOT rate sign —
this chart only draws the resulting equity levels.

Outputs: digiquant/.scratch/gold_pngs/gold_reselect_equity.svg plus a
public/ copy for the preview server. Both stay untracked.
"""

import json
import math
import shutil
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
TEARSHEET = (
    ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies" / "gold_sdca_v6_reselect.json"
)
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
OUT_NAME = "gold_reselect_equity.svg"

W, H = 960, 440
ML, MR, MT, MB = 64, 16, 64, 40
MAX_POINTS = 1500


def parse_series(raw: list[dict]) -> list[tuple[date, float]]:
    pts = []
    for r in raw:
        y, m, d = (int(p) for p in r["t"].split("-"))
        pts.append((date(y, m, d), float(r["v"])))
    pts.sort(key=lambda p: p[0])
    return pts


def decimate(pts: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Min-max per bin: each bin contributes its min-y and max-y points."""
    n = len(pts)
    bins = min(max(n // 2, 1), MAX_POINTS // 2)
    size = math.ceil(n / bins)
    kept: list[tuple[date, float]] = []
    for b in range(bins):
        chunk = pts[b * size : (b + 1) * size]
        if not chunk:
            continue
        mn = min(chunk, key=lambda p: p[1])
        mx = max(chunk, key=lambda p: p[1])
        kept.append(mn)
        if mx != mn:
            kept.append(mx)
    kept.sort(key=lambda p: p[0])
    return kept


def svg_equity(
    series: list[tuple[str, list[tuple[date, float]], str]],
    title: str,
    subtitle: str,
    y_lo: float,
    y_hi: float,
    y_ticks: list[float],
) -> str:
    pw, ph = W - ML - MR, H - MT - MB
    d0 = min(p[0] for _, pts, _ in series for p in pts).toordinal()
    d1 = max(p[0] for _, pts, _ in series for p in pts).toordinal()

    def sx(d: date) -> float:
        return ML + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        return MT + (1.0 - (v - y_lo) / (y_hi - y_lo)) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f"<title>{escape(title)}</title>",
        f'<text x="{W / 2}" y="20" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
        f'<text x="{W / 2}" y="38" text-anchor="middle" font-size="11" '
        f'fill="#333333">{escape(subtitle)}</text>',
        f'<text x="14" y="{MT + ph / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {MT + ph / 2})">equity (USD)</text>',
    ]
    for t in y_ticks:
        y = sy(t)
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t:,.0f}</text>'
        )
    yrs = range(
        min(p[0] for _, pts, _ in series for p in pts).year,
        max(p[0] for _, pts, _ in series for p in pts).year + 1,
    )
    for yr in yrs:
        x = sx(date(yr, 1, 1))
        if ML - 1 <= x <= W - MR + 1:
            parts.append(
                f'<line x1="{x:.1f}" y1="{MT}" x2="{x:.1f}" y2="{MT + ph}" '
                'stroke="#e8e8e8" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{MT + ph + 16}" text-anchor="middle" '
                f'font-size="11">{yr}</text>'
            )
    for name, pts, color in series:
        pts_str = " ".join(f"{sx(d):.1f},{sy(v):.1f}" for d, v in pts)
        parts.append(
            f'<polyline points="{pts_str}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        )
    lx = ML + 8
    ly = MT + 8
    for i, (name, pts, color) in enumerate(series):
        y = ly + i * 18
        parts.append(
            f'<line x1="{lx}" y1="{y}" x2="{lx + 28}" y2="{y}" '
            f'stroke="{color}" stroke-width="2.5"/>'
        )
        parts.append(
            f'<text x="{lx + 34}" y="{y + 4}" font-size="11">{escape(name)} '
            f"(end ${pts[-1][1]:,.0f})</text>"
        )
    parts.append(
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="none" stroke="#000000"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    payload = json.loads(TEARSHEET.read_text())
    strat = parse_series(payload["equity_curve"])
    lump = parse_series(payload["lump_equity_curve"])
    flat = parse_series(payload["flat_dca_equity_curve"])
    lo = min(v for pts in (strat, lump, flat) for _, v in pts)
    hi = max(v for pts in (strat, lump, flat) for _, v in pts)
    pad = (hi - lo) * 0.06
    step = 500.0
    ticks = [lo + i * step for i in range(int((hi - lo) / step) + 2)]
    title = (
        "GLD reselected rank #1 (buy 35/60, sell 65/30): equity vs lump + flat "
        "— BEATS-BOTH (conditional)"
    )
    subtitle = (
        "Selection: frozen argmax min(mean_flat, mean_lump) = +3.85 "
        "(flat +24.32 / lump +3.85); sens STABLE 1.63; disclosures in tearsheet notes"
    )
    svg = svg_equity(
        [
            ("reselected equity", decimate(strat), "#1f5fa8"),
            ("lump DCA", decimate(lump), "#2a7a2a"),
            ("flat DCA", decimate(flat), "#cc7700"),
        ],
        title,
        subtitle,
        lo - pad,
        hi + pad,
        [t for t in ticks if lo - pad <= t <= hi + pad],
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / OUT_NAME
    out.write_text(svg)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, PUBLIC_DIR / OUT_NAME)
    print(f"{OUT_NAME}: {out.stat().st_size} bytes (+ public/ copy)")


if __name__ == "__main__":
    main()
