#!/usr/bin/env python3
"""Run the SDCA turn detector on GLD closes over the frozen sensitivity grid (#4804).

Plan 22 Engine 1 shipped a *generic* paired peak/trough detector
(``strategies/sdca/turn_detect.py``) whose ``min_move_pct`` default (15) was
inherited from the owner's ruling, never calibrated on data. This script is that
calibration read: it runs the unmodified detector over the real GLD close
series and scores each level against the owner's **approved set A** pins.

**The grid is frozen and the numbers are reported as found.** ``min_move_pct``
varies over {15, 10, 5}; ``min_separation_days`` is held at the frozen default
of 45 and the confirmation half-width at 5 bars, because this run is about the
magnitude crank alone. A level that misses set A pins is a **finding about the
detector**, not a failure to tune — so nothing here adjusts the grid, the
separator, the confirmation width or the pins after seeing the output. Choosing
the level (if any) that reproduces set A is the owner's call.

Matching rule: a detected turn coincides with a set A pin when the two are
within **±3 trading days**, measured in bars of the loaded series (so a
non-trading pin date snaps to its nearest bar first). Matching is one-to-one and
greedy on the smallest gap, each pin and each turn used at most once; the kind
each side claims is recorded per match, but date coincidence alone counts as a
match so a kind disagreement stays visible instead of hiding inside "missed".

Windows come from ``turns_to_cycle_windows`` at ±45 days (the pin factories'
half-width), and the per-level day-share is the coverage stat
``TurnSet.window_day_share`` reports at that same width.

Writes `.scratch/gold_turn_detection.json` (untracked research output).

Usage (from the worktree root):
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_turn_detection.py
"""

from __future__ import annotations

import json
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from digiquant.strategies.sdca.cycle_windows import CycleKind
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.turn_detect import (
    TurnDetectionConfig,
    TurnSet,
    detect_turns,
    turns_to_cycle_windows,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_turn_detection.json"

SYMBOL = "GLD-USD"

# Frozen grid. ``MOVE_PCT_LEVELS`` is the only thing that varies: this run is
# about the magnitude crank, so the time filter stays at the owner's default and
# the confirmation width at the detector's own.
MOVE_PCT_LEVELS: tuple[float, ...] = (15.0, 10.0, 5.0)
FROZEN_SEPARATION_DAYS = 45
FROZEN_CONFIRMATION_BARS = 5
WINDOW_HALF_WIDTH_DAYS = 45

# ±3 trading days, in bars of the loaded series.
MATCH_TOLERANCE_BARS = 3


@dataclass(frozen=True, slots=True)
class SetAPin:
    """One of the owner's approved set A pins, as the comparison target."""

    label: str
    kind: CycleKind
    pin: date
    close: float


# Owner-approved set A (2026-10-03), close-based, chronological. Reproduced here
# as read-only ground truth for the comparison; the detector never sees it.
SET_A: tuple[SetAPin, ...] = (
    SetAPin("A1_2011_peak", CycleKind.PEAK, date(2011, 8, 22), 184.59),
    SetAPin("A2_2015_trough", CycleKind.TROUGH, date(2015, 12, 17), 100.50),
    SetAPin("A3_2020_peak", CycleKind.PEAK, date(2020, 8, 6), 193.89),
    SetAPin("A4_2022_trough", CycleKind.TROUGH, date(2022, 9, 26), 151.23),
    SetAPin("A5_2026_peak", CycleKind.PEAK, date(2026, 1, 29), 495.90),
    SetAPin("A6_2026_trough", CycleKind.TROUGH, date(2026, 7, 16), 364.96),
)


def nearest_bar(dates: list[date], day: date) -> int:
    """Index of the bar closest to ``day`` (the pin itself when it is a bar).

    Set A pins are calendar dates and the series is trading days, so a pin has
    to snap onto the series before "within N trading days" means anything.
    """
    position = bisect_left(dates, day)
    if position < len(dates) and dates[position] == day:
        return position
    before = position - 1
    after = position
    if before < 0:
        return after
    if after >= len(dates):
        return before
    return before if (day - dates[before]) <= (dates[after] - day) else after


def match_against_set_a(turnset: TurnSet, dates: list[date]) -> dict[str, Any]:
    """One-to-one match of detected turns to set A pins within the tolerance.

    Greedy on the smallest bar gap so a turn that could serve two nearby pins
    is spent on the nearer one, and the leftover is reported as extra/missed
    rather than quietly double-counted.
    """
    pin_bars = {pin.label: nearest_bar(dates, pin.pin) for pin in SET_A}
    by_index = {turn.index: turn for turn in turnset.turns}
    by_label = {pin.label: pin for pin in SET_A}
    gaps: list[tuple[int, str, int]] = []
    for pin in SET_A:
        for turn in turnset.turns:
            apart = abs(turn.index - pin_bars[pin.label])
            if apart <= MATCH_TOLERANCE_BARS:
                gaps.append((apart, pin.label, turn.index))
    gaps.sort()

    claimed_pins: set[str] = set()
    claimed_turns: set[int] = set()
    matched: list[dict[str, Any]] = []
    for apart, label, turn_index in gaps:
        if label in claimed_pins or turn_index in claimed_turns:
            continue
        claimed_pins.add(label)
        claimed_turns.add(turn_index)
        pin = by_label[label]
        turn = by_index[turn_index]
        matched.append(
            {
                "set_a_label": label,
                "set_a_kind": str(pin.kind),
                "set_a_pin": str(pin.pin),
                "set_a_close": pin.close,
                "turn_kind": str(turn.kind),
                "turn_pin": str(turn.pin),
                "turn_close": turn.price,
                "turn_prominence": turn.prominence,
                "bars_apart": apart,
                "kind_agrees": turn.kind is pin.kind,
            }
        )
    matched.sort(key=lambda record: record["set_a_pin"])
    extra = [
        {
            "kind": str(turn.kind),
            "pin": str(turn.pin),
            "close": turn.price,
            "prominence": turn.prominence,
            "index": turn.index,
        }
        for turn in turnset.turns
        if turn.index not in claimed_turns
    ]
    missed = [
        {
            "set_a_label": pin.label,
            "kind": str(pin.kind),
            "pin": str(pin.pin),
            "close": pin.close,
            "nearest_turn_pin": min(
                (str(turn.pin) for turn in turnset.turns),
                key=lambda day: abs((date.fromisoformat(day) - pin.pin).days),
                default=None,
            ),
        }
        for pin in SET_A
        if pin.label not in claimed_pins
    ]
    return {
        "tolerance_bars": MATCH_TOLERANCE_BARS,
        "set_a_pins": len(SET_A),
        "matched": matched,
        "matched_count": len(matched),
        "extra": extra,
        "extra_count": len(extra),
        "missed": missed,
        "missed_count": len(missed),
        "kind_disagreements": sum(1 for record in matched if not record["kind_agrees"]),
    }


def run_level(min_move_pct: float, dates: list[date], prices: list[float]) -> dict[str, Any]:
    """Detect turns at one frozen level and compare the result against set A."""
    config = TurnDetectionConfig(
        min_move_pct=min_move_pct,
        min_separation_days=FROZEN_SEPARATION_DAYS,
        confirmation_bars=FROZEN_CONFIRMATION_BARS,
        window_half_width_days=WINDOW_HALF_WIDTH_DAYS,
    )
    turnset = detect_turns(dates, prices, config)
    windows = turns_to_cycle_windows(turnset, WINDOW_HALF_WIDTH_DAYS)
    drop_counts: dict[str, int] = {}
    for record in turnset.dropped:
        key = str(record.reason)
        drop_counts[key] = drop_counts.get(key, 0) + 1
    return {
        "min_move_pct": min_move_pct,
        "min_separation_days": FROZEN_SEPARATION_DAYS,
        "confirmation_bars": FROZEN_CONFIRMATION_BARS,
        "bars": turnset.bars,
        "days_in_span": turnset.days_in_span,
        "window_half_width_days": turnset.window_half_width_days,
        "window_day_share": turnset.window_day_share,
        "n_turns": len(turnset.turns),
        "n_peaks": turnset.n_peaks,
        "n_troughs": turnset.n_troughs,
        "turns": [
            {
                "kind": str(turn.kind),
                "pin": str(turn.pin),
                "close": turn.price,
                "prominence": turn.prominence,
                "index": turn.index,
            }
            for turn in turnset.turns
        ],
        "dropped": [
            {
                "kind": str(record.kind),
                "pin": str(record.pin),
                "close": record.price,
                "index": record.index,
                "reason": str(record.reason),
                "survivor_pin": str(record.survivor_pin) if record.survivor_pin else None,
            }
            for record in turnset.dropped
        ],
        "drop_reason_counts": drop_counts,
        "set_a_comparison": match_against_set_a(turnset, dates),
        "windows": [
            {
                "name": window.name,
                "kind": str(window.kind),
                "start": str(window.start),
                "end": str(window.end),
            }
            for window in windows.windows
        ],
    }


def print_level(level: dict[str, Any]) -> None:
    """The per-level comparison table, printed as found — no pass/fail verdict."""
    comparison = level["set_a_comparison"]
    print()
    print(
        f"=== min_move_pct={level['min_move_pct']}% "
        f"(min_separation_days={level['min_separation_days']}, "
        f"confirmation_bars={level['confirmation_bars']}) ==="
    )
    print(
        f"{'turns found':>13} | {'n peaks/n troughs':>17} | {'matched to Set A':>16} | "
        f"{'extra':>5} | {'missed Set A pins':>18} | {'window-day share':>16}"
    )
    print(
        f"{level['n_turns']:>13} | {str(level['n_peaks']) + '/' + str(level['n_troughs']):>17} | "
        f"{str(comparison['matched_count']) + '/' + str(comparison['set_a_pins']):>16} | "
        f"{comparison['extra_count']:>5} | {comparison['missed_count']:>18} | "
        f"{level['window_day_share']:>16.4f}"
    )
    print("  turns:")
    for turn in level["turns"]:
        print(
            f"    {turn['pin']}  {turn['kind']:<6} close {turn['close']:>8.2f}  "
            f"prominence {turn['prominence']:>6.2f}%"
        )
    print(f"  dropped: {level['drop_reason_counts'] or '{} (nothing filtered)'}")
    print(f"  matched (within +-{comparison['tolerance_bars']} trading days):")
    for record in comparison["matched"]:
        agree = "kind agrees" if record["kind_agrees"] else "KIND DISAGREES"
        print(
            f"    {record['set_a_pin']} {record['set_a_kind']:<6} -> {record['turn_pin']} "
            f"{record['turn_kind']:<6} close {record['turn_close']:>8.2f} "
            f"({record['bars_apart']} bars, {agree})"
        )
    if not comparison["matched"]:
        print("    none")
    print("  extra turns (no set A pin within tolerance):")
    for turn in comparison["extra"]:
        print(f"    {turn['pin']} {turn['kind']:<6} close {turn['close']:>8.2f}")
    if not comparison["extra"]:
        print("    none")
    print("  missed set A pins (no turn within tolerance):")
    for pin in comparison["missed"]:
        print(
            f"    {pin['pin']} {pin['kind']:<6} close {pin['close']:>8.2f} "
            f"(nearest turn: {pin['nearest_turn_pin']})"
        )
    if not comparison["missed"]:
        print("    none")


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    print(
        f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars, "
        f"close {min(prices):.2f}..{max(prices):.2f})"
    )
    print(
        f"grid: min_move_pct {list(MOVE_PCT_LEVELS)} x min_separation_days "
        f"[{FROZEN_SEPARATION_DAYS}] (time filter frozen; magnitude crank only)"
    )
    print(f"set A under test: {len(SET_A)} approved close-based pins")
    print(
        f"{'min_move_pct':>12} | {'turns':>5} | {'peaks':>5} | {'troughs':>7} | "
        f"{'matched':>7} | {'extra':>5} | {'missed':>6} | {'window_day_share':>16}"
    )
    levels = [run_level(level, dates, prices) for level in MOVE_PCT_LEVELS]
    for level in levels:
        comparison = level["set_a_comparison"]
        print(
            f"{level['min_move_pct']:>12} | {level['n_turns']:>5} | {level['n_peaks']:>5} | "
            f"{level['n_troughs']:>7} | {comparison['matched_count']:>7} | "
            f"{comparison['extra_count']:>5} | {comparison['missed_count']:>6} | "
            f"{level['window_day_share']:>16.4f}"
        )
    for level in levels:
        print_level(level)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "symbol": SYMBOL,
                "source": str(DATA_PATH),
                "price_column": "close",
                "bars": len(dates),
                "first_date": str(dates[0]),
                "last_date": str(dates[-1]),
                "grid": {
                    "min_move_pct_levels": list(MOVE_PCT_LEVELS),
                    "min_separation_days": [FROZEN_SEPARATION_DAYS],
                    "confirmation_bars": FROZEN_CONFIRMATION_BARS,
                    "window_half_width_days": WINDOW_HALF_WIDTH_DAYS,
                    "match_tolerance_bars": MATCH_TOLERANCE_BARS,
                },
                "set_a": [
                    {
                        "label": pin.label,
                        "kind": str(pin.kind),
                        "pin": str(pin.pin),
                        "close": pin.close,
                    }
                    for pin in SET_A
                ],
                "levels": levels,
            },
            indent=2,
        )
    )
    print()
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
