"""Measure the gold 200-week Mayer multiple from GLD daily bars (analysis only).

Reads digiquant/data/price-history/GLD-USD.csv ONLY. No engine imports.
Writes digiquant/.scratch/gold_mayer_multiple.json (untracked analysis output).

Week-assembly rule (causal, completed weeks only): calendar weeks run
Monday-Friday; a week's close is the close of its last trading day in the
file; a week counts as complete only when a strictly later trading day
exists in the file (this excludes the possibly in-progress latest week).
The 200-week SMA at a completed week-end is the mean of the trailing 1000
daily closes ending on that week-end date (200 weeks x 5 trading days).
Multiple = week-end close / that SMA. No partial-week data ever enters.
Event rows use the completed week-end on/after the anchor month's extreme
close day (max for tops, min for bottoms/dips). Numbers only: no thresholds
are frozen and no recommendation is made here.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
CSV_PATH = HERE.parent.parent / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = HERE.parent.parent / ".scratch" / "gold_mayer_multiple.json"

WINDOW_DAYS = 1000  # 200 weeks x 5 trading days
TOP_2011_ANCHOR = date(2011, 9, 6)  # spot-gold peak day; exclusion window anchor only

# (label, anchor month YYYY-MM, extreme kind)
EVENTS = [
    ("sep_2011_top", "2011-09", "max"),
    ("dec_2015_bottom", "2015-12", "min"),
    ("aug_2020_high", "2020-08", "max"),
    ("oct_2022_dip", "2022-10", "min"),
]


def parse_date(raw: str) -> date:
    return datetime.fromisoformat(raw).date()


def load_bars(path: Path) -> list[tuple[date, float]]:
    bars: list[tuple[date, float]] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            bars.append((parse_date(row["timestamp"]), float(row["close"])))
    bars.sort(key=lambda b: b[0])
    return bars


def main() -> None:
    bars = load_bars(CSV_PATH)
    if len(bars) < WINDOW_DAYS + 1:
        raise SystemExit(f"need >{WINDOW_DAYS} bars, have {len(bars)}")

    closes = [c for _, c in bars]
    dates = [d for d, _ in bars]
    last_date = dates[-1]

    # Daily trailing-1000-day SMA + multiple, causal (uses closes up to day t only).
    sma: list[float | None] = [None] * len(bars)
    mult: list[float | None] = [None] * len(bars)
    run = sum(closes[:WINDOW_DAYS])
    for t in range(WINDOW_DAYS - 1, len(bars)):
        if t >= WINDOW_DAYS:
            run += closes[t] - closes[t - WINDOW_DAYS]
        sma[t] = run / WINDOW_DAYS
        mult[t] = closes[t] / sma[t]  # type: ignore[operator]

    first_valid = dates[WINDOW_DAYS - 1]

    # Completed week-ends: last trading day of each Mon-Fri week, excluding any
    # week containing the file's last bar (possibly in progress).
    week_end: dict[date, int] = {}
    for t, d in enumerate(dates):
        if d == last_date:
            continue  # latest week may be in progress; never emit it
        if t + 1 < len(dates) and dates[t + 1].isocalendar()[:2] == d.isocalendar()[:2]:
            continue  # not the last trading day of its week
        week_end[d] = t

    def event_row(label: str, month: str, kind: str) -> dict:
        month_ts = [t for t, d in enumerate(dates) if d.isoformat()[:7] == month]
        if not month_ts:
            raise SystemExit(f"no bars for anchor month {month}")
        pick = (
            max(month_ts, key=lambda t: closes[t])
            if kind == "max"
            else min(month_ts, key=lambda t: closes[t])
        )
        extreme_day = dates[pick]
        # Completed week-end on/after the extreme day.
        wk = next(d for d in sorted(week_end) if d >= extreme_day)
        t = week_end[wk]
        return {
            "label": label,
            "anchor_month": month,
            "extreme_day": extreme_day.isoformat(),
            "extreme_close": round(closes[pick], 4),
            "week_end": wk.isoformat(),
            "close": round(closes[t], 4),
            "sma200w": round(sma[t], 4),  # type: ignore[arg-type]
            "multiple": round(mult[t], 4),  # type: ignore[arg-type]
        }

    events = [event_row(label, month, kind) for label, month, kind in EVENTS]
    lt = week_end[max(week_end)]
    events.append(
        {
            "label": "latest_bar",
            "anchor_month": last_date.isoformat()[:7],
            "extreme_day": None,
            "extreme_close": None,
            "week_end": dates[lt].isoformat(),
            "close": round(closes[lt], 4),
            "sma200w": round(sma[lt], 4),  # type: ignore[arg-type]
            "multiple": round(mult[lt], 4),  # type: ignore[arg-type]
        }
    )

    # Whipsaw read on the daily series: days multiple fires outside +/-6mo of
    # the Sep-2011 top anchor (would a threshold have fired during the grind?).
    lo = date(2011, 3, 6)  # TOP_2011_ANCHOR minus 6 calendar months
    hi = date(2012, 3, 6)  # TOP_2011_ANCHOR plus 6 calendar months

    def count_outside(thr: float) -> tuple[int, int, str | None, str | None]:
        hits = [
            dates[t]
            for t in range(len(bars))
            if mult[t] is not None and mult[t] > thr and not (lo <= dates[t] <= hi)  # type: ignore[operator]
        ]
        total = sum(1 for t in range(len(bars)) if mult[t] is not None and mult[t] > thr)  # type: ignore[operator]
        return (
            len(hits),
            total,
            hits[0].isoformat() if hits else None,
            hits[-1].isoformat() if hits else None,
        )

    n15_out, n15_all, first15, last15 = count_outside(1.5)
    n17_out, n17_all, first17, last17 = count_outside(1.7)

    series = [
        {
            "date": dates[t].isoformat(),
            "close": round(closes[t], 4),
            "sma200w": round(sma[t], 4),  # type: ignore[arg-type]
            "multiple": round(mult[t], 4),  # type: ignore[arg-type]
            "week_end": dates[t] in week_end,
        }
        for t in range(WINDOW_DAYS - 1, len(bars))
    ]

    payload = {
        "source": str(CSV_PATH.name),
        "bars_total": len(bars),
        "bars_first": dates[0].isoformat(),
        "bars_last": last_date.isoformat(),
        "window_days": WINDOW_DAYS,
        "first_valid_date": first_valid.isoformat(),
        "week_rule": "Mon-Fri calendar weeks; week close = last trading day close; "
        "complete only if a later trading day exists in file; "
        "sma200w = mean of trailing 1000 daily closes at completed week-ends",
        "events": events,
        "whipsaw": {
            "exclusion_window": [lo.isoformat(), hi.isoformat()],
            "days_gt_1_5_outside": n15_out,
            "days_gt_1_5_all": n15_all,
            "first_gt_1_5_outside": first15,
            "last_gt_1_5_outside": last15,
            "days_gt_1_7_outside": n17_out,
            "days_gt_1_7_all": n17_all,
            "first_gt_1_7_outside": first17,
            "last_gt_1_7_outside": last17,
        },
        "series": series,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"first_valid_date={first_valid}")
    for e in events:
        print(
            f"{e['label']}: week_end={e['week_end']} close={e['close']} "
            f"sma200w={e['sma200w']} multiple={e['multiple']}"
        )
    print(f"days>1.5 outside={n15_out} (all={n15_all}) first={first15} last={last15}")
    print(f"days>1.7 outside={n17_out} (all={n17_all}) first={first17} last={last17}")
    print(f"wrote {OUT_PATH} rows={len(series)}")


if __name__ == "__main__":
    main()
