#!/usr/bin/env python3
"""Gold buy/sell PERIOD charts for owner validation (#4804).

Two stdlib SVG charts + one period-definition JSON, built from the
FROZEN plan-19 fits (each indicator at ITS OWN best-fit parameters) and
the shipped z-functions (reused via fit_gold_indicators.build_z — no
reimplemented math).

Frozen band convention (stated up front, same 25/75 convention the v4
seed script used for its buy-zone count; 45/65 dead-zone edges from the
v4/reselect curve drawn as secondary reference lines):

    z > +1.5  -> risk < 25  -> BUY period (cheap)
    |z| < 1.5 -> 25..75     -> neutral (hold / accumulate slowly)
    z < -1.5  -> risk > 75  -> SELL period (rich)

Charts:
  gold_price_buy_sell_periods.svg  price + anchor periods + pinned cycle
                                  windows + fitted-candidate period ticks
  gold_indicator_period_matrix.svg one strip per fitted indicator
                                  (cheap=green / neutral=grey / rich=red)
                                  on a shared time axis + pin markers

Outputs are untracked; the JSON carries the explicit definitions + counts
so the later time-in-market gate can be frozen against real numbers.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fit_gold_indicators import (  # noqa: E402
    DATA_PATH,
    SYMBOL,
    anchor_z,
    build_z,
    load_fits,
)

from digiquant.strategies.sdca.optimize import (  # noqa: E402
    load_sdca_extra_sources,
    load_sdca_ohlcv,
)

OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
FITS_PATH = ROOT / ".scratch" / "gold_indicator_fits.json"
PERIODS_PATH = ROOT / ".scratch" / "gold_buy_sell_periods.json"

# Frozen band convention (z units).
Z_CHEAP = 1.5
Z_RICH = -1.5
# Secondary reference: the v4/reselect curve dead-zone edges in risk space.
RISK_BUY_EDGE = 45.0
RISK_SELL_EDGE = 65.0

PINS: list[tuple[str, str]] = [
    ("2008-03-17", "peak"),
    ("2008-10-24", "trough"),
    ("2011-09-06", "peak"),
    ("2015-12-17", "trough"),
    ("2020-08-07", "peak"),
    ("2022-10-21", "trough"),
]

W, MARGIN_L, MARGIN_R = 1500, 64, 130
ROW_H, PANEL_GAP = 13, 8


def _period(z: float | None) -> str:
    if z is None:
        return "gap"
    if z > Z_CHEAP:
        return "buy"
    if z < Z_RICH:
        return "sell"
    return "flat"


def _runs(dates: list[date], z: list[float | None]) -> list[tuple[date, date, str]]:
    """Contiguous same-period runs (for shading) with the last day's date."""
    out: list[tuple[date, date, str]] = []
    start_i = 0
    cur = _period(z[0]) if z else "gap"
    for i in range(1, len(z) + 1):
        p = _period(z[i]) if i < len(z) else None
        if p != cur:
            if i > start_i and cur in ("buy", "sell"):
                out.append((dates[start_i], dates[i - 1], cur))
            start_i = i
            cur = p or "gap"
    return out


def _period_counts(z: list[float | None]) -> dict[str, int]:
    counts = {"buy": 0, "sell": 0, "flat": 0, "gap": 0}
    for v in z:
        counts[_period(v)] += 1
    return counts


def _transitions(z: list[float | None]) -> int:
    seq = [_period(v) for v in z if v is not None]
    return sum(1 for a, b in zip(seq, seq[1:], strict=False) if a != b)


def price_chart(
    dates: list[date],
    prices: list[float],
    members: list[tuple[str, list[float | None], str]],
) -> str:
    """Price + anchor buy/sell shading + pins + per-candidate period ticks."""
    ph = 380
    pw = W - MARGIN_L - MARGIN_R
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()
    p_lo, p_hi = min(prices), max(prices)
    pad = (p_hi - p_lo) * 0.06

    def sx(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    def sy(v: float) -> float:
        top, bot = 24.0, ph - 26.0
        return top + (1.0 - (v - (p_lo - pad)) / ((p_hi + pad) - (p_lo - pad))) * (bot - top)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {ph}" font-family="sans-serif">',
        "<title>GLD price with indicator-defined buy/sell periods</title>",
        f'<text x="{W / 2}" y="16" text-anchor="middle" font-size="14" font-weight="bold">'
        "GLD price with buy/sell periods from the fitted indicators "
        "(buy: z&gt;+1.5 / sell: z&lt;-1.5; green=buy, red=sell)</text>",
    ]
    for label, kind in PINS:
        y, m, dd = (int(p) for p in label.split("-"))
        ed = date(y, m, dd)
        if not (dates[0] <= ed <= dates[-1]):
            continue
        x = sx(ed)
        col = "#d23" if kind == "peak" else "#2a7"
        parts.append(
            f'<rect x="{x - 26:.1f}" y="24" width="52" height="{ph - 50:.1f}" '
            f'fill="{col}" fill-opacity="0.07"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{ph - 30:.1f}" text-anchor="middle" font-size="9" '
            f'fill="{col}">{escape(label)} {kind}</text>'
        )
    anchor_z_vals = members[0][1]
    for a, b, kind in _runs(dates, anchor_z_vals):
        xa, xb = sx(a), sx(b)
        col = "#2a7a2a" if kind == "buy" else "#cc2222"
        parts.append(
            f'<rect x="{xa:.1f}" y="{ph - 22:.1f}" width="{max(xb - xa, 0.8):.1f}" '
            f'height="10" fill="{col}" fill-opacity="0.85"/>'
        )
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 2):
        x = sx(date(yr, 1, 1))
        parts.append(f'<line x1="{x:.1f}" y1="24" x2="{x:.1f}" y2="{ph - 26}" stroke="#eee"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{ph - 16:.1f}" text-anchor="middle" font-size="10">{yr}</text>'
        )
    step = max(1, len(dates) // 1600)
    pts = " ".join(
        f"{sx(d):.1f},{sy(p):.1f}" for d, p in list(zip(dates, prices, strict=True))[::step]
    )
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#1f5fa8" stroke-width="1.4"/>')
    counts = _period_counts(anchor_z_vals)
    parts.append(
        f'<text x="{MARGIN_L}" y="{ph - 4}" font-size="10" fill="#333">'
        f"anchor periods: buy {counts['buy']}d / sell {counts['sell']}d / "
        f"neutral {counts['flat']}d ({counts['gap']}d unscored)</text>"
    )
    legend_y = 34.0
    for i, (name, _z, params) in enumerate(members[1:], start=1):
        y = legend_y + (i - 1) * 13
        counts_i = _period_counts(members[i][1])
        parts.append(
            f'<text x="{W - MARGIN_R + 6}" y="{y:.0f}" font-size="10" fill="#444">'
            f"{escape(name)} {escape(params)}</text>"
        )
        parts.append(
            f'<text x="{W - MARGIN_R + 6}" y="{y + 11:.0f}" font-size="9" fill="#777">'
            f"buy {counts_i['buy']}d / sell {counts_i['sell']}d</text>"
        )
    parts.append(
        f'<rect x="{MARGIN_L}" y="24" width="{pw:.1f}" height="{ph - 50}" fill="none" '
        'stroke="#999"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def period_matrix(dates: list[date], rows: list[tuple[str, list[float | None], str]]) -> str:
    """One cheap/neutral/rich strip per indicator on a shared time axis."""
    pw = W - MARGIN_L - MARGIN_R
    ph = 40 + len(rows) * (ROW_H + PANEL_GAP)
    d0, d1 = dates[0].toordinal(), dates[-1].toordinal()

    def sx(d: date) -> float:
        return MARGIN_L + (d.toordinal() - d0) / max(d1 - d0, 1) * pw

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {ph}" font-family="sans-serif">',
        "<title>Buy/sell period matrix per fitted indicator</title>",
        f'<text x="{W / 2}" y="16" text-anchor="middle" font-size="14" font-weight="bold">'
        "Buy/sell periods per fitted indicator (green=buy z&gt;+1.5, grey=neutral, "
        "red=sell z&lt;-1.5, white=unscored)</text>",
    ]
    for label, kind in PINS:
        y, m, dd = (int(p) for p in label.split("-"))
        ed = date(y, m, dd)
        if not (dates[0] <= ed <= dates[-1]):
            continue
        x = sx(ed)
        col = "#d23" if kind == "peak" else "#2a7"
        parts.append(
            f'<line x1="{x:.1f}" y1="22" x2="{x:.1f}" y2="{ph - 20}" stroke="{col}" '
            'stroke-width="1" stroke-dasharray="3,3"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="32" text-anchor="start" font-size="9" fill="{col}">'
            f"{escape(label)}</text>"
        )
    for i, (name, z, params) in enumerate(rows):
        y = 36 + i * (ROW_H + PANEL_GAP)
        parts.append(
            f'<text x="4" y="{y + ROW_H - 3}" font-size="9" fill="#333">{escape(name)}</text>'
        )
        last = None
        for d, v in zip(dates, z, strict=True):
            p = _period(v)
            if p == last:
                continue
            x = sx(d)
            if last is not None:
                parts.append(
                    f'<rect x="{x:.1f}" y="{y}" width="0.9" height="{ROW_H}" '
                    f'fill="{_color(last)}"/>'
                )
            last = p
        parts.append(
            f'<rect x="{sx(dates[-1]):.1f}" y="{y}" width="0.9" height="{ROW_H}" '
            f'fill="{_color(last)}"/>'
        )
        parts.append(
            f'<text x="{W - MARGIN_R + 4}" y="{y + ROW_H - 3}" font-size="9" fill="#555">'
            f"{escape(params)}</text>"
        )
    for yr in range(dates[0].year + 1, dates[-1].year + 1, 2):
        x = sx(date(yr, 1, 1))
        parts.append(
            f'<text x="{x:.1f}" y="{ph - 6}" text-anchor="middle" font-size="10">{yr}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _color(period: str) -> str:
    return {
        "buy": "#2a7a2a",
        "sell": "#cc2222",
        "flat": "#c9c9c9",
        "gap": "#ffffff",
    }.get(period, "#ffffff")


def main() -> None:
    fits = load_fits(FITS_PATH)
    raw_dates, raw_prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", raw_dates, dtype=pl.Date)
    price_s = pl.Series("price", raw_prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    dates = list(date_s)
    prices = price_s.to_list()

    members: list[tuple[str, list[float | None], str]] = [
        ("valuation anchor", anchor_z(date_s, price_s), "rolling90/z1.0")
    ]
    for name, fits_rec in sorted(fits.items(), key=lambda kv: kv[0]):
        if fits_rec.best_overall is None or fits_rec.best_overall.params is None:
            continue
        params = dict(fits_rec.best_overall.params)
        z = build_z(name, params, date_s, price_s, sources)
        members.append((name, list(z), _params_text(params)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gold_price_buy_sell_periods.svg").write_text(price_chart(dates, prices, members))
    (OUT_DIR / "gold_indicator_period_matrix.svg").write_text(
        period_matrix(dates, [(n, z, p) for n, z, p in members])
    )

    payload = {
        "band_convention": {
            "buy": f"z > {Z_CHEAP} (risk < 25)",
            "neutral": f"{Z_RICH} <= z <= {Z_CHEAP} (risk 25..75)",
            "sell": f"z < {Z_RICH} (risk > 75)",
            "secondary_curve_edges": [RISK_BUY_EDGE, RISK_SELL_EDGE],
            "frozen": True,
        },
        "window_pins": {
            "peaks": [label for label, kind in PINS if kind == "peak"],
            "troughs": [label for label, kind in PINS if kind == "trough"],
        },
        "indicators": [
            {
                "name": name,
                "params": params,
                "counts": _period_counts(z),
                "transitions": _transitions(z),
            }
            for name, z, params in members
        ],
        "in_sample": True,
        "note": "Periods are z-threshold definitions on fitted indicators; "
        "in-sample against the same pinned windows used for fitting. Holdout untouched.",
    }
    PERIODS_PATH.write_text(json.dumps(payload, indent=2))
    if PUBLIC_DIR.exists() or PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        for name in ("gold_price_buy_sell_periods.svg", "gold_indicator_period_matrix.svg"):
            (PUBLIC_DIR / name).write_text((OUT_DIR / name).read_text())

    print("PERIODS (buy z>+1.5 | neutral | sell z<-1.5) — 2004-11 → 2026-09")
    for rec in payload["indicators"]:
        c = rec["counts"]
        total = max(sum(c.values()), 1)
        print(
            f"  {rec['name']:<18} {rec['params']:<28} "
            f"buy {c['buy']:>4}d ({100 * c['buy'] / total:>4.1f}%)  "
            f"sell {c['sell']:>4}d ({100 * c['sell'] / total:>4.1f}%)  "
            f"neutral {c['flat']:>4}d  flips {rec['transitions']:>3}"
        )
    print(f"\nwrote {OUT_DIR}/gold_price_buy_sell_periods.svg")
    print(f"wrote {OUT_DIR}/gold_indicator_period_matrix.svg")
    print(f"wrote {PERIODS_PATH}")


def _params_text(params: dict[str, int]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(params.items()))


if __name__ == "__main__":
    main()
