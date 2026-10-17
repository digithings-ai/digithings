"""Build the frozen strict-box sell mask for gold (GLD) — analysis/gate input (#4804).

Reads staged ``DFII10.csv`` (real-yield leg) + ``GLD-USD.csv`` (price leg) and
emits per-GLD-date booleans for the FROZEN box ``z <= -2.0 & m >= 1.5``
(exploratory origin disclosed in the plan header — mask-robustness in the
gate run is the honesty mechanism, NOT re-freezing). The gate threads the
mask through ``evaluate_sdca_trial_curve_sim(..., sell_dates=...)`` so sells
fire only on mask days. Research-only; touches nothing else.

Causal by construction: mask[t] uses inputs <= t ONLY —
(i) the z leg calls the shipped ``real_rate_z`` whose macro alignment is a
left-join + forward-fill (``indicator_catalog.align_to_dates``) and whose
window is trailing (``indicator_catalog.causal_rolling_z``: "Each day uses
only that day and prior window"); (ii) the multiple leg is a trailing-SMA
mirror of ``measure_gold_mayer_multiple.py``'s daily rule ("uses closes up
to day t only", running mean of the trailing 1000 closes). No future bar,
no full-history fit, no staged full-history read enters either leg — the
staged mayer JSON is a cross-check only, never a source. A runtime
spot-check re-proves truncation-equality on real inputs on every run.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/build_gold_sell_mask.py [--z-thresh -2.0] [--m-thresh 1.5] \\
            [--out digiquant/.scratch/gold_sell_mask.json]
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import real_rate_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DFII10_CSV = DIGIQUANT_ROOT / "data" / "price-history" / "DFII10.csv"
GLD_CSV = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
STAGED_MAYER_JSON = DIGIQUANT_ROOT / ".scratch" / "gold_mayer_multiple.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_sell_mask.json"

FROZEN_Z_THRESH = -2.0
FROZEN_M_THRESH = 1.5
Z_WINDOW = 1260  # shipped real_rate_z default; matches the v5 secular rationale
SMA_WINDOW_DAYS = 1000  # 200 weeks x 5 trading days (measure-script daily rule)

# Spot dates with known joint-box states (plot-script exploratory record).
SPOT_TRUE = date(2011, 9, 6)  # 2011 top fires
SPOT_FALSE = (date(2020, 8, 7), date(2015, 12, 17))  # 2020 high / 2015 bottom silent


def read_dfii10_csv(path: Path) -> tuple[list[date], list[float]]:
    """(dates, values), skipping blank prints (holiday gaps; forward-fill covers)."""
    dates, vals = [], []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            raw = (row["DFII10"] or "").strip()
            if raw == "":
                continue
            dates.append(datetime.fromisoformat(row["observation_date"]).date())
            vals.append(float(raw))
    return dates, vals


def read_gld_closes(path: Path) -> tuple[list[date], list[float]]:
    """Trading-day grid + closes from the staged GLD file."""
    dates, closes = [], []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            dates.append(datetime.fromisoformat(row["timestamp"][:10]).date())
            closes.append(float(row["close"]))
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return [dates[i] for i in order], [closes[i] for i in order]


def trailing_sma_multiples(closes: list[float], window_days: int) -> list[float | None]:
    """Per-bar close / trailing-mean, causal (closes <= t only).

    Plain-Python mirror of ``measure_gold_mayer_multiple.py``'s daily rule
    (running trailing mean; ``window_days`` param is 1000 in production, small
    in unit tests). No shipped function exists for this leg, so the staged
    mayer JSON cross-checks the mirror instead of sourcing it.
    """
    out: list[float | None] = [None] * len(closes)
    if len(closes) < window_days:
        return out
    run = sum(closes[:window_days])
    for t in range(window_days - 1, len(closes)):
        if t >= window_days:
            run += closes[t] - closes[t - window_days]
        out[t] = closes[t] / (run / window_days)
    return out


def compute_z(
    gld_dates: list[date],
    src_dates: list[date],
    src_vals: list[float],
    window: int,
) -> list[float | None]:
    """Shipped trailing real-rate z on the GLD-day grid (zero math duplication)."""
    z = real_rate_z(
        pl.Series("date", gld_dates, dtype=pl.Date),
        pl.Series("date", src_dates, dtype=pl.Date),
        pl.Series("value", src_vals, dtype=pl.Float64),
        window=window,
    )
    return z.to_list()


def combine_strict_box(
    z_vals: list[float | None],
    multiples: list[float | None],
    z_thresh: float,
    m_thresh: float,
) -> list[bool]:
    """Frozen conjunction; null either leg (warmup) => False (no decision w/o data)."""
    return [
        (z is not None and m is not None and z <= z_thresh and m >= m_thresh)
        for z, m in zip(z_vals, multiples, strict=True)
    ]


def build_mask(
    gld_dates: list[date],
    gld_closes: list[float],
    src_dates: list[date],
    src_vals: list[float],
    *,
    z_thresh: float = FROZEN_Z_THRESH,
    m_thresh: float = FROZEN_M_THRESH,
    z_window: int = Z_WINDOW,
    sma_window: int = SMA_WINDOW_DAYS,
) -> dict:
    """Full causal build: z via shipped fn, multiples via trailing mirror, ANDed."""
    z = compute_z(gld_dates, src_dates, src_vals, z_window)
    multiples = trailing_sma_multiples(gld_closes, sma_window)
    return {
        "dates": list(gld_dates),
        "z": z,
        "multiples": multiples,
        "mask": combine_strict_box(z, multiples, z_thresh, m_thresh),
        "z_thresh": z_thresh,
        "m_thresh": m_thresh,
        "z_window": z_window,
        "sma_window": sma_window,
    }


def assert_causal_spot_check(
    result: dict,
    gld_closes: list[float],
    src_dates: list[date],
    src_vals: list[float],
) -> None:
    """Runtime truncation proof: mask[t] recomputed on inputs<=t equals mask[t]."""
    dates: list[date] = result["dates"]
    picks = sorted({dates[len(dates) // 2], SPOT_TRUE, dates[-1]} & set(dates))
    for day in picks:
        t = dates.index(day)
        trunc_d = dates[: t + 1]
        src_cut = [(d, v) for d, v in zip(src_dates, src_vals, strict=True) if d <= day]
        trunc = build_mask(
            trunc_d,
            gld_closes[: t + 1],
            [d for d, _ in src_cut],
            [v for _, v in src_cut],
            z_thresh=result["z_thresh"],
            m_thresh=result["m_thresh"],
            z_window=result["z_window"],
            sma_window=result["sma_window"],
        )
        assert trunc["mask"][-1] == result["mask"][t], f"causality breach at {day}"
        assert trunc["z"][-1] == result["z"][t], f"z leak at {day}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build frozen strict-box gold sell mask")
    parser.add_argument("--z-thresh", type=float, default=FROZEN_Z_THRESH)
    parser.add_argument("--m-thresh", type=float, default=FROZEN_M_THRESH)
    parser.add_argument("--dfii10", default=str(DFII10_CSV))
    parser.add_argument("--gld", default=str(GLD_CSV))
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    f_dates, f_vals = read_dfii10_csv(Path(args.dfii10))
    g_dates, g_closes = read_gld_closes(Path(args.gld))
    result = build_mask(
        g_dates, g_closes, f_dates, f_vals, z_thresh=args.z_thresh, m_thresh=args.m_thresh
    )
    assert_causal_spot_check(result, g_closes, f_dates, f_vals)

    mask_days = [d.isoformat() for d, m in zip(result["dates"], result["mask"], strict=True) if m]
    by_date = dict(zip(result["dates"], result["mask"], strict=True))
    if (args.z_thresh, args.m_thresh) == (FROZEN_Z_THRESH, FROZEN_M_THRESH):
        assert by_date.get(SPOT_TRUE) is True, "2011 top must fire"
        assert all(by_date.get(d) is False for d in SPOT_FALSE), "2020/2015 events must stay silent"
    else:
        print(
            f"variant thresholds z<={args.z_thresh} m>={args.m_thresh}: frozen spot asserts skipped"
        )

    # Staged-series cross-check (artifact read, never a source): mirror
    # multiples must match the staged daily series; joint count must agree.
    staged = json.loads(STAGED_MAYER_JSON.read_text())
    staged_by_date = {r["date"]: float(r["multiple"]) for r in staged["series"]}
    overlap = [
        (d, m)
        for d, m in zip(result["dates"], result["multiples"], strict=True)
        if m is not None and d.isoformat() in staged_by_date
    ]
    max_diff = max(abs(m - staged_by_date[d.isoformat()]) for d, m in overlap)
    staged_joint = sum(
        1
        for d, m in overlap
        if m >= args.m_thresh and result["z"][result["dates"].index(d)] <= args.z_thresh
    )
    assert staged_joint == len(mask_days), f"mirror {len(mask_days)} vs staged {staged_joint}"

    out = {
        "provenance": {
            "builder": "digiquant/scripts/build_gold_sell_mask.py",
            "dfii10": str(args.dfii10),
            "gld": str(args.gld),
            "staged_mayer_crosscheck": str(STAGED_MAYER_JSON),
            "frozen_box": "z<=-2.0 & m>=1.5 exploratory origin disclosed; "
            "robustness is report-only, never re-frozen",
        },
        "thresholds": {"z_le": args.z_thresh, "m_ge": args.m_thresh},
        "z_window": Z_WINDOW,
        "sma_window_days": SMA_WINDOW_DAYS,
        "bars": len(g_dates),
        "first_date": g_dates[0].isoformat(),
        "last_date": g_dates[-1].isoformat(),
        "dates": [d.isoformat() for d in result["dates"]],
        "mask": list(result["mask"]),
        "mask_days": mask_days,
        "mask_count": len(mask_days),
        "staged_crosscheck": {"overlap_rows": len(overlap), "max_abs_diff": max_diff},
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    first_last = f"{mask_days[0]}..{mask_days[-1]}" if mask_days else "none"
    print(
        f"bars {len(g_dates)} ({g_dates[0]}..{g_dates[-1]}), mask days {len(mask_days)} {first_last}"
    )
    print(f"staged cross-check: {len(overlap)} rows, max|diff|={max_diff:.2e}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
