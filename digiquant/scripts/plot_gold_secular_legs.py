"""Secular-leg firing charts as stdlib-only SVG (#4804).

Why SVG: no plotting library exists in .venv or system python and pip
installs are forbidden in this task, so both charts are hand-rolled SVG
(stdlib only). Outputs sit beside the existing gld_*.png files; the .svg
extension is deliberate and the SVGs stay untracked.

Reads precomputed series only (recomputes nothing except the DFII10
rolling z, which has no precomputed file):
- digiquant/data/price-history/DFII10.csv (read-only staging input)
- digiquant/.scratch/gold_mayer_multiple.json (multiple series as-is)

z-mirror fidelity: plain-Python causal rolling mean/std with
window=1260, min_samples=20 (shipped _MIN_SAMPLES; the task brief said 2
- zero effect here: the window is full at every charted/event date),
sigma floor 1e-12 (shipped _SIGMA_FLOOR; brief said 1e-8 - never binds,
typical sigma is ~0.5), clip to [-3.0, 3.0]. This mirrors
indicator_catalog.causal_rolling_z, whose body is quoted here:

    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)

Polars rolling_std defaults to sample std (ddof=1), matched below.
real_rate_z itself is NOT sign-flipped (washout semantics) and needs no
flip here either.

Date grid: GLD trading days from GLD-USD.csv (read for dates only), with
DFII10 forward-filled onto them - the same align_to_dates forward-fill the
shipped real_rate_z call uses. This reproduces the Ruling-3 measurement
basis (5480 valid z days = 5499 GLD bars minus min_samples 19 nulls).

Decimation: min-max per bin - split the series into <=750 bins, emit each
bin's min-y and max-y points (<=1500 points total), so extremes survive.
"""

import csv
import json
import math
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
DFII10_CSV = ROOT / "data" / "price-history" / "DFII10.csv"
GLD_CSV = ROOT / "data" / "price-history" / "GLD-USD.csv"
MAYER_JSON = ROOT / ".scratch" / "gold_mayer_multiple.json"
MASK_JSON = ROOT / ".scratch" / "gold_sell_mask.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"

WINDOW = 1260
MIN_SAMPLES = 20  # shipped _MIN_SAMPLES (see module docstring re brief's 2)
SIGMA_FLOOR = 1e-12  # shipped _SIGMA_FLOOR (see module docstring re brief's 1e-8)
Z_CLIP = 3.0
MAX_POINTS = 1500

EVENTS = ["2011-09-06", "2015-12-17", "2020-08-07", "2022-10-21"]

W, H = 960, 440
ML, MR, MT, MB = 64, 16, 54, 40


def read_dfii10(path: Path) -> tuple[list[date], list[float]]:
    dates, vals = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            raw = (row["DFII10"] or "").strip()
            if raw == "":
                continue  # holiday gap; forward-fill covers it below
            y, m, d = (int(p) for p in row["observation_date"].split("-"))
            dates.append(date(y, m, d))
            vals.append(float(raw))
    return dates, vals


def read_gld_dates(path: Path) -> list[date]:
    """Trading-day grid from GLD-USD.csv (timestamp column, dates only)."""
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            y, m, d = (int(p) for p in row["timestamp"][:10].split("-"))
            out.append(date(y, m, d))
    return out


def forward_fill_onto(grid: list[date], src: dict[date, float]) -> list[float]:
    """align_to_dates forward-fill mirror: last src value at or before each day."""
    keys = sorted(src)
    aligned, last, k = [], None, 0
    for g in grid:
        while k < len(keys) and keys[k] <= g:
            last = src[keys[k]]
            k += 1
        aligned.append(last)  # grid starts after first src date, never None
    return aligned  # type: ignore[return-value]


def causal_rolling_z(vals: list[float]) -> list[float | None]:
    """Plain-Python mirror of causal_rolling_z (causal window, sample std)."""
    out: list[float | None] = []
    for i, x in enumerate(vals):
        lo = max(0, i - WINDOW + 1)
        win = vals[lo : i + 1]
        if len(win) < MIN_SAMPLES:
            out.append(None)
            continue
        n = len(win)
        mu = sum(win) / n
        var = (sum(v * v for v in win) - n * mu * mu) / (n - 1)  # ddof=1
        sigma = max(math.sqrt(max(var, 0.0)), SIGMA_FLOOR)
        z = (x - mu) / sigma
        out.append(max(-Z_CLIP, min(Z_CLIP, z)))
    return out


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile over pre-sorted values (Polars quantile default)."""
    if not sorted_vals:
        raise ValueError("empty series")
    rank = round(pct / 100.0 * (len(sorted_vals) - 1))
    return sorted_vals[max(0, min(rank, len(sorted_vals) - 1))]


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


def svg_chart(
    pts: list[tuple[date, float]],
    title: str,
    ylabel: str,
    hlines: list[tuple[float, str, str]],
    y_lo: float,
    y_hi: float,
    y_ticks: list[float],
) -> str:
    pw, ph = W - ML - MR, H - MT - MB
    d0, d1 = pts[0][0].toordinal(), pts[-1][0].toordinal()

    def sx(d: date) -> float:
        return ML + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        return MT + (1.0 - (v - y_lo) / (y_hi - y_lo)) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f"<title>{escape(title)}</title>",
        f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
        f'<text x="14" y="{MT + ph / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {MT + ph / 2})">{escape(ylabel)}</text>',
    ]
    for t in y_ticks:
        y = sy(t)
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t:g}</text>'
        )
    for yr in range(pts[0][0].year, pts[-1][0].year + 1):
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
    for level, color, label in hlines:
        y = sy(level)
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="6,3"/>'
        )
        parts.append(
            f'<text x="{W - MR - 4}" y="{y - 5:.1f}" text-anchor="end" '
            f'font-size="11" fill="{color}">{escape(label)}</text>'
        )
    for ev in EVENTS:
        y, m, d = (int(p) for p in ev.split("-"))
        ed = date(y, m, d)
        if not (pts[0][0] <= ed <= pts[-1][0]):
            continue
        x = sx(ed)
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT}" x2="{x:.1f}" y2="{MT + ph}" '
            'stroke="#999999" stroke-width="1" stroke-dasharray="3,3"/>'
        )
        parts.append(
            f'<text x="{x + 3:.1f}" y="{MT + 12}" font-size="10" fill="#555555">{escape(ev)}</text>'
        )
    pts_str = " ".join(f"{sx(d):.1f},{sy(v):.1f}" for d, v in pts)
    parts.append(f'<polyline points="{pts_str}" fill="none" stroke="#1f5fa8" stroke-width="1.5"/>')
    parts.append(
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="none" stroke="#000000"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def svg_scatter(
    pts: list[tuple[float, float]],
    events: list[tuple[float, float, str]],
    title: str,
    xlabel: str,
    ylabel: str,
    box: tuple[float, float, float, float],
    box_label: str,
    x_lo: float,
    x_hi: float,
    x_ticks: list[float],
    y_lo: float,
    y_hi: float,
    y_ticks: list[float],
) -> str:
    """Scatter (x=mayer multiple, y=rate z) with the sell-box shaded.

    Points are pre-decimated by the caller (every-Nth). Events are
    highlighted red with labels. Box = (x0, x1, y0, y1) sell region.
    """
    pw, ph = W - ML - MR, H - MT - MB

    def sx(v: float) -> float:
        return ML + (v - x_lo) / (x_hi - x_lo) * pw

    def sy(v: float) -> float:
        return MT + (1.0 - (v - y_lo) / (y_hi - y_lo)) * ph

    x0, x1, y0, y1 = box
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f"<title>{escape(title)}</title>",
        f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
        f'<text x="{W / 2}" y="{H - 6}" text-anchor="middle" font-size="12">{escape(xlabel)}</text>',
        f'<text x="14" y="{MT + ph / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {MT + ph / 2})">{escape(ylabel)}</text>',
    ]
    for t in y_ticks:
        y = sy(t)
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t:g}</text>'
        )
    for t in x_ticks:
        x = sx(t)
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT}" x2="{x:.1f}" y2="{MT + ph}" '
            'stroke="#e8e8e8" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{MT + ph + 16}" text-anchor="middle" font-size="11">{t:g}</text>'
        )
    parts.append(
        f'<rect x="{sx(x0):.1f}" y="{sy(y1):.1f}" width="{sx(x1) - sx(x0):.1f}" '
        f'height="{sy(y0) - sy(y1):.1f}" fill="#cc0000" fill-opacity="0.10" '
        'stroke="#cc0000" stroke-width="1.5" stroke-dasharray="6,3"/>'
    )
    parts.append(
        f'<text x="{sx(x1) - 4:.1f}" y="{sy(y1) + 14:.1f}" text-anchor="end" '
        f'font-size="11" fill="#cc0000">{escape(box_label)}</text>'
    )
    for xv, yv in pts:
        parts.append(
            f'<circle cx="{sx(xv):.1f}" cy="{sy(yv):.1f}" r="1.6" '
            'fill="#1f5fa8" fill-opacity="0.30"/>'
        )
    for xv, yv, label in events:
        parts.append(
            f'<circle cx="{sx(xv):.1f}" cy="{sy(yv):.1f}" r="4.5" '
            'fill="#cc0000" stroke="#ffffff" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{sx(xv) + 7:.1f}" y="{sy(yv) - 6:.1f}" font-size="11" '
            f'fill="#cc0000">{escape(label)}</text>'
        )
    parts.append(
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="none" stroke="#000000"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def read_gld_closes(path: Path) -> list[tuple[date, float]]:
    """Full-history (date, close) from GLD-USD.csv (timestamp + close columns)."""
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            y, m, d = (int(p) for p in row["timestamp"][:10].split("-"))
            out.append((date(y, m, d), float(row["close"])))
    out.sort(key=lambda p: p[0])
    return out


def svg_price_with_mask_rug(
    pts: list[tuple[date, float]],
    mask_days: set[date],
    events: list[tuple[str, str]],
    title: str,
    y_lo: float,
    y_hi: float,
    y_ticks: list[float],
) -> str:
    """Full-history GLD close with strict-box mask days as a red rug.

    Same 960x440 pattern as svg_chart: price polyline, year grid, event
    vlines + labels; mask days are short ticks along the bottom axis
    (dense 2011 cluster vs sparse elsewhere shows at a glance how rarely
    the mask binds). Veto accounting: ticks mark sell-allow days, not
    fills — fills need curve + book state (see the v6 tearsheet's
    fill_sell_days, keyed off daily_trade_usd, not rate sign).
    """
    pw, ph = W - ML - MR, H - MT - MB
    d0, d1 = pts[0][0].toordinal(), pts[-1][0].toordinal()

    def sx(d: date) -> float:
        return ML + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        return MT + (1.0 - (v - y_lo) / (y_hi - y_lo)) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f"<title>{escape(title)}</title>",
        f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
        f'<text x="14" y="{MT + ph / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {MT + ph / 2})">GLD close (USD)</text>',
    ]
    for t in y_ticks:
        y = sy(t)
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            'stroke="#cccccc" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t:g}</text>'
        )
    for yr in range(pts[0][0].year, pts[-1][0].year + 1):
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
    for ev, state in events:
        y, m, d = (int(p) for p in ev.split("-"))
        ed = date(y, m, d)
        if not (pts[0][0] <= ed <= pts[-1][0]):
            continue
        x = sx(ed)
        color = "#cc0000" if state == "fires" else "#555555"
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT}" x2="{x:.1f}" y2="{MT + ph}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="3,3"/>'
        )
        parts.append(
            f'<text x="{x + 3:.1f}" y="{MT + 12}" font-size="10" fill="{color}">{escape(ev)} {state}</text>'
        )
    pts_str = " ".join(f"{sx(d):.1f},{sy(v):.1f}" for d, v in pts)
    parts.append(f'<polyline points="{pts_str}" fill="none" stroke="#1f5fa8" stroke-width="1.5"/>')
    for md in sorted(mask_days):
        if not (pts[0][0] <= md <= pts[-1][0]):
            continue
        x = sx(md)
        parts.append(
            f'<line x1="{x:.1f}" y1="{MT + ph - 12}" x2="{x:.1f}" y2="{MT + ph}" '
            'stroke="#cc0000" stroke-width="1.5"/>'
        )
    parts.append(
        f'<text x="{W - MR - 4}" y="{MT + ph - 16:.1f}" text-anchor="end" '
        f'font-size="11" fill="#cc0000">mask rug ({len(mask_days)} days)</text>'
    )
    parts.append(
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="none" stroke="#000000"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- real-rate z chart (GLD-day grid, DFII10 forward-filled) ---
    f_dates, f_vals = read_dfii10(DFII10_CSV)
    src = dict(zip(f_dates, f_vals))
    grid = read_gld_dates(GLD_CSV)
    aligned = forward_fill_onto(grid, src)
    z = causal_rolling_z(aligned)
    full = [(d, v) for d, v in zip(grid, z) if v is not None]
    by_date = dict(full)
    zvals = sorted(v for _, v in full)
    p10, p90 = percentile(zvals, 10), percentile(zvals, 90)
    z2011 = by_date[date(2011, 9, 6)]
    z2015 = by_date[date(2015, 12, 17)]
    title_r = (
        f"DFII10 real-rate z (window 1260): 2011 top z={z2011:.2f} "
        f"top-decile rich | 2015 bottom z={z2015:.2f} ~75th pct "
        "- NOT top-decile"
    )
    svg_r = svg_chart(
        decimate(full),
        title_r,
        "rolling z",
        [(p10, "#2a7a2a", f"10th pct {p10:.2f}"), (p90, "#2a7a2a", f"90th pct {p90:.2f}")],
        -3.2,
        3.2,
        [-3, -2, -1, 0, 1, 2, 3],
    )
    out_r = OUT_DIR / "secular_real_rate_z.svg"
    out_r.write_text(svg_r)

    # --- mayer multiple chart (series read as-is, recompute nothing) ---
    payload = json.loads(MAYER_JSON.read_text())
    mpts = [
        (
            date(*[int(p) for p in r["date"].split("-")]),
            float(r["multiple"]),
        )
        for r in payload["series"]
    ]
    top_mult = next(e["multiple"] for e in payload["events"] if e["label"] == "sep_2011_top")
    grind = payload["whipsaw"]["days_gt_1_5_outside"]
    title_m = (
        f"GLD 200w Mayer multiple: 2011 {top_mult:.2f} >=1.5 | {grind} "
        "grind-days >1.5 (7.8% >= 5% bar)"
    )
    lo = min(v for _, v in mpts)
    hi = max(v for _, v in mpts)
    pad = (hi - lo) * 0.08
    step = 0.2
    ticks = [round(lo + i * step, 1) for i in range(int((hi - lo) / step) + 2)]
    svg_m = svg_chart(
        decimate(mpts),
        title_m,
        "multiple",
        [(1.5, "#cc0000", "1.5"), (1.7, "#cc0000", "1.7")],
        lo - pad,
        hi + pad,
        [t for t in ticks if lo - pad <= t <= hi + pad],
    )
    out_m = OUT_DIR / "mayer_multiple.svg"
    out_m.write_text(svg_m)

    # --- joint sell-box scatter (mayer x, rate-z y; exploratory, no thresholds frozen) ---
    m_by_date = {r["date"]: float(r["multiple"]) for r in payload["series"]}
    joint = [
        (m_by_date[ds], zv) for ds, zv in ((d.isoformat(), v) for d, v in full) if ds in m_by_date
    ]
    scatter_pts = joint[::3]  # 4500 -> 1500 evenly; scatter needs no extremes logic
    lo_win, hi_win = date(2011, 3, 6), date(2012, 3, 6)
    n_joint = sum(1 for m, z in joint if z <= -2.0 and m >= 1.5)
    n_out = sum(
        1
        for ds, (m, z) in (
            (d.isoformat(), (m_by_date[d.isoformat()], v))
            for d, v in full
            if d.isoformat() in m_by_date
        )
        if z <= -2.0 and m >= 1.5 and not (lo_win.isoformat() <= ds <= hi_win.isoformat())
    )
    ev_labels = {
        "2011-09-06": "2011 top (fires)",
        "2015-12-17": "2015 bottom (no fire)",
        "2020-08-07": "2020 high (no fire)",
        "2022-10-21": "2022 dip (no fire)",
    }
    ev_pts = [
        (m_by_date[ds], by_date[date(*[int(p) for p in ds.split("-")])], label)
        for ds, label in ev_labels.items()
    ]
    title_j = (
        f"Sell-box conjunction (z<=-2 & m>=1.5): {n_joint} joint days, "
        f"{n_out} outside 2011 window ({100.0 * n_out / len(joint):.1f}%) "
        "vs 349 mayer-alone"
    )
    svg_j = svg_scatter(
        scatter_pts,
        ev_pts,
        title_j,
        "200w Mayer multiple",
        "real-rate z",
        (1.5, 1.85, -3.2, -2.0),
        "sell box",
        0.7,
        1.85,
        [0.8, 1.0, 1.2, 1.4, 1.5, 1.6, 1.8],
        -3.2,
        3.2,
        [-3, -2, -1, 0, 1, 2, 3],
    )
    out_j = OUT_DIR / "joint_conjunction.svg"
    out_j.write_text(svg_j)

    # --- mask-rug chart (v6, #4804): full-history GLD close + strict-box rug ---
    close_pts = read_gld_closes(GLD_CSV)
    mask_doc = json.loads(MASK_JSON.read_text())
    mask_set = {date(*[int(p) for p in ds.split("-")]) for ds in mask_doc["mask_days"]}
    lo_c = min(v for _, v in close_pts)
    hi_c = max(v for _, v in close_pts)
    pad_c = (hi_c - lo_c) * 0.08
    step_c = 50.0
    ticks_c = [lo_c + i * step_c for i in range(int((hi_c - lo_c) / step_c) + 2)]
    title_k = (
        f"GLD close with strict-box sell mask rug: {len(mask_set)} days "
        "(2011 cluster binds, 2020+/now silent) — NEGATIVE v6 evidence"
    )
    svg_k = svg_price_with_mask_rug(
        decimate(close_pts),
        mask_set,
        [
            ("2011-09-06", "fires"),
            ("2015-12-17", "silent"),
            ("2020-08-07", "silent"),
            ("2022-10-21", "silent"),
        ],
        title_k,
        lo_c - pad_c,
        hi_c + pad_c,
        [t for t in ticks_c if lo_c - pad_c <= t <= hi_c + pad_c],
    )
    out_k = OUT_DIR / "gold_mask_rug.svg"
    out_k.write_text(svg_k)

    # --- verification block (stdout; quoted in the SDD report) ---
    print(f"z 2011-09-06 = {z2011:.4f} (Ruling-3 -2.522, delta {z2011 + 2.522:+.4f})")
    print(f"z 2015-12-17 = {z2015:.4f} (Ruling-3 +1.066, delta {z2015 - 1.066:+.4f})")
    print(f"p10 = {p10:.4f} (Ruling-3 -2.115), p90 = {p90:.4f} (Ruling-3 +1.743)")
    for d in ("2011-09-06", "2015-12-17", "2020-08-07"):
        y, m, dd = (int(p) for p in d.split("-"))
        print(f"spot {d}: DFII10={src[date(y, m, dd)]}")
    m_by_date = {r["date"]: r["multiple"] for r in payload["series"]}
    print(f"mayer 2011-09-02 multiple={m_by_date['2011-09-02']}")
    print(f"mask days: {len(mask_set)} ({mask_doc['thresholds']})")
    for p in (out_r, out_m, out_j, out_k):
        print(f"{p.name}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
