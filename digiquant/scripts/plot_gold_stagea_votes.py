"""Stage-A vote behavior charts as stdlib-only SVG (#4804, Plan 18 Task 3).

Same 960-wide hand-rolled SVG pattern as plot_gold_reselect_equity.py (no
plotting library in .venv; pip installs forbidden). Reads precomputed
series ONLY from the Stage-A diagnostic tearsheet JSONs (recomputes
nothing): per vote, one SVG with two panels — (top) risk 0-100 with
buy/sell fill dots, (bottom) fills-per-year bars (buys + sells grouped).
Subtitle carries fills/yr, sell-days/yr, risk-band occupancy, the ranking
separation, and the diagnostic label.

Outputs: digiquant/.scratch/gold_pngs/gold_stagea_v1_risk_fills.svg +
gold_stagea_v2_risk_fills.svg plus public/ copies for the preview server.
All stay untracked.
"""

import json
import math
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STRATEGIES = ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"

W, H = 960, 620
ML, MR, MT, MB = 64, 16, 76, 40
SPLIT = 400  # y-pixel where the fills/yr panel starts
MAX_POINTS = 1500

VOTES = {
    "v1": ("gold_sdca_stagea_v1", "V1 valuation-only (rank #1, diagnostic — promotion-barred)"),
    "v2": ("gold_sdca_stagea_v2", "V2 real_rate-only (rank #49, steer-compliant candidate)"),
}


def parse_curve(raw: list[dict]) -> list[tuple[date, float]]:
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


def svg_vote(
    risk: list[tuple[date, float]],
    fills: list[dict],
    per_year: dict[int, dict[str, int]],
    title: str,
    subtitle: str,
) -> str:
    pw = W - ML - MR
    top_h = SPLIT - MT
    bot_h = H - SPLIT - MB - 24
    d0 = min(p[0] for p in risk).toordinal()
    d1 = max(p[0] for p in risk).toordinal()

    def sx(d: date) -> float:
        return ML + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        return MT + (1.0 - v / 100.0) * top_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f"<title>{escape(title)}</title>",
        f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
        f'<text x="{W / 2}" y="40" text-anchor="middle" font-size="11" '
        f'fill="#333333">{escape(subtitle[0])}</text>',
        f'<text x="{W / 2}" y="56" text-anchor="middle" font-size="11" '
        f'fill="#333333">{escape(subtitle[1])}</text>',
    ]
    # Risk panel: accumulate (<=35) / distribute (>=80) bands + line + fills.
    parts.append(
        f'<rect x="{ML}" y="{sy(35.0):.1f}" width="{pw}" '
        f'height="{sy(0.0) - sy(35.0):.1f}" fill="#e8f4e8"/>'
    )
    parts.append(
        f'<rect x="{ML}" y="{sy(100.0):.1f}" width="{pw}" '
        f'height="{sy(80.0) - sy(100.0):.1f}" fill="#f4e8e8"/>'
    )
    for t in (0, 20, 40, 60, 80, 100):
        y = sy(float(t))
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t}</text>'
        )
    pts_str = " ".join(f"{sx(d):.1f},{sy(v):.1f}" for d, v in decimate(risk))
    parts.append(f'<polyline points="{pts_str}" fill="none" stroke="#1f5fa8" stroke-width="1.2"/>')
    risk_by_date = {d: v for d, v in risk}
    for f in fills:
        y, m, d = (int(p) for p in f["t"].split("-"))
        day = date(y, m, d)
        v = risk_by_date.get(day)
        if v is None:
            continue
        color = "#2a7a2a" if f["side"] == "buy" else "#c00000"
        r = 3.0 if f["side"] == "sell" else 2.0
        parts.append(f'<circle cx="{sx(day):.1f}" cy="{sy(v):.1f}" r="{r}" fill="{color}"/>')
    parts.append(
        f'<text x="{ML + 8}" y="{MT + 16}" font-size="11" fill="#2a7a2a">● buy fill</text>'
    )
    parts.append(
        f'<text x="{ML + 88}" y="{MT + 16}" font-size="11" fill="#c00000">● sell fill</text>'
    )
    parts.append(
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{top_h}" fill="none" stroke="#000000"/>'
    )
    parts.append(
        f'<text x="14" y="{MT + top_h / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {MT + top_h / 2})">risk 0-100</text>'
    )
    # Fills/yr panel: grouped buy/sell bars per calendar year.
    years = sorted(per_year)
    bot_top = SPLIT + 24
    max_n = max(max(v.get("buy", 0), v.get("sell", 0)) for v in per_year.values())
    max_n = max(max_n, 1)
    n = len(years)
    slot = pw / n
    bw = min(slot * 0.32, 18.0)
    step = 1 if max_n <= 12 else math.ceil(max_n / 12)
    for t in range(0, max_n + 1, step):
        y = bot_top + bot_h - (t / max_n) * bot_h
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t}</text>'
        )
    for i, yr in enumerate(years):
        cx = ML + (i + 0.5) * slot
        for j, (key, color) in enumerate((("buy", "#2a7a2a"), ("sell", "#c00000"))):
            cnt = per_year[yr].get(key, 0)
            h = (cnt / max_n) * bot_h
            x = cx + (j - 0.5) * bw - bw / 2
            parts.append(
                f'<rect x="{x:.1f}" y="{bot_top + bot_h - h:.1f}" '
                f'width="{bw:.1f}" height="{h:.1f}" fill="{color}"/>'
            )
        if n <= 20 or yr % 2 == 0:
            parts.append(
                f'<text x="{cx:.1f}" y="{bot_top + bot_h + 16}" text-anchor="middle" '
                f'font-size="10">{yr}</text>'
            )
    parts.append(
        f'<text x="{W / 2}" y="{SPLIT + 12}" text-anchor="middle" font-size="12" '
        'font-weight="bold">fills per calendar year (green=buy, red=sell)</text>'
    )
    parts.append(
        f'<rect x="{ML}" y="{bot_top}" width="{pw}" height="{bot_h}" fill="none" stroke="#000000"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for vote, (slug, vote_title) in VOTES.items():
        payload = json.loads((PUBLIC_STRATEGIES / f"{slug}.json").read_text())
        risk = parse_curve(payload["risk_curve"])
        fills = payload["fill_markers"]
        dca = payload["dca"]
        per_year: dict[int, dict[str, int]] = defaultdict(lambda: {"buy": 0, "sell": 0})
        for f in fills:
            per_year[int(f["t"][:4])][f["side"]] += 1
        start, end = payload["period_start"], payload["period_end"]
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        years = days / 365.25
        fills_yr = dca["fill_sell_days"] / years
        sell_days_yr = dca["sell_days"] / years
        rr = [v for _, v in risk if v is not None]
        acc_pct = sum(1 for v in rr if v <= 35.0) / len(rr) * 100.0
        dst_pct = sum(1 for v in rr if v >= 80.0) / len(rr) * 100.0
        title = f"GLD Stage-A {vote.upper()}: risk with fills + fills/yr — {vote_title}"
        sub1 = (
            f"window {start}→{end} ({years:.1f}yr) | sell fills "
            f"{dca['fill_sell_days']} = {fills_yr:.2f}/yr | sell-days "
            f"{dca['sell_days']} = {sell_days_yr:.1f}/yr | band acc "
            f"{acc_pct:.1f}% / dst {dst_pct:.1f}%"
        )
        sub2 = (
            f"separation {payload['indicator_weights']} | "
            f"vs_flat {dca['vs_flat_dca_pct']:+.1f}% vs_lump {dca['vs_lump_pct']:+.1f}% "
            "(full-history diagnostic, NOT a gate claim)"
        )
        svg = svg_vote(risk, fills, dict(per_year), title, (sub1, sub2))
        out_name = f"gold_stagea_{vote}_risk_fills.svg"
        out = OUT_DIR / out_name
        out.write_text(svg)
        shutil.copy(out, PUBLIC_DIR / out_name)
        print(f"{out_name}: {out.stat().st_size} bytes (+ public/ copy)")


if __name__ == "__main__":
    main()
