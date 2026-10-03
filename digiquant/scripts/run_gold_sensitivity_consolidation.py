#!/usr/bin/env python3
"""Run the SDCA sensitivity consolidation on GLD over the frozen sensitivity grid (#4804).

Plan 22 Engine 2 shipped a *generic* capture rule
(``strategies/sdca/sensitivity_consolidate.py``): an indicator captures a level
iff its best grid row is at/above the 0.5 z-unit bar, sign-correct, and not
one-sided; the level chosen is the most sensitive one that loses no indicator
relative to every coarser level. This script is that rule's calibration read on
the real series: it detects turns at the three frozen levels, turns each set into
±45d scoring windows, sweeps every wired indicator's **frozen** grid against
**that level's** windows, and consolidates.

**Nothing is tuned after seeing results.** The magnitude crank
(``min_move_pct`` ∈ {15, 10, 5}), the time filter (``min_separation_days`` = 45),
the confirmation width (5 bars), the window half-width (±45d), the capture bar
(0.5), the dead-zone width (0.06) and every indicator grid come from Engine 1 /
Plan-19 and are imported, not restated. The only thing this script decides is
which level the frozen rule picks — and it reports that as found.

**Windows are a SCORING TARGET only.** They are the ``±45d`` cycle windows the
detector produces; nothing here trades around them, applies an exposure floor,
or consults the perfect-strategy oracle. A window can be captured or missed and
that is all.

**IN-SAMPLE, everywhere.** Every separation is fit against the same turns it is
measured on, at every bar with a valid z. This calibrates indicator windows to
detected history; it is NOT out-of-sample predictive skill, and the holdout
stays spent.

The frozen Plan-19 harness (``digiquant/scripts/fit_gold_indicators.py``) is a
research *script*, not an importable module, so it is loaded by file path here
exactly as its own tests do — which means every grid, every shipped z-function
call and the separation metric itself are the shipped ones, not restatements.

Writes `.scratch/gold_sensitivity_consolidation.json` (untracked research
output). Touches nothing outside ``.scratch/``.

Usage (from the worktree root):
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_sensitivity_consolidation.py
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.sensitivity_consolidate import (
    CAPTURE_BAR,
    CAPTURE_RULE,
    CHOICE_RULE,
    DEGENERATE_MEAN_ABS,
    IndicatorCaptureRow,
    SensitivityChoice,
    SensitivityLevelRow,
    select_sensitivity_level,
)
from digiquant.strategies.sdca.turn_detect import (
    TurnDetectionConfig,
    detect_turns,
    turns_to_cycle_windows,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_sensitivity_consolidation.json"
FITS_SCRIPT = DIGIQUANT_ROOT / "scripts" / "fit_gold_indicators.py"

SYMBOL = "GLD-USD"

# --------------------------------------------------------------------------- #
# Frozen grid. Every value is imported or restated from Engine 1 / Plan-19 and
# is NOT adjusted after seeing the output.
# --------------------------------------------------------------------------- #
MOVE_PCT_LEVELS: tuple[float, ...] = (15.0, 10.0, 5.0)
FROZEN_SEPARATION_DAYS = 45
FROZEN_CONFIRMATION_BARS = 5
WINDOW_HALF_WIDTH_DAYS = 45

# The selection anchor, as one more scored row (not a fit candidate): the v4
# seed's shipped no-trend rails. ``params_note`` carries the float rail because
# the capture row's params are integers by contract.
ANCHOR_NAME = "valuation"
ANCHOR_PARAMS: dict[str, int] = {"rolling_window": 90}
ANCHOR_PARAMS_NOTE = "rolling_z=1.0 (float, not an int); no time-trend rails"
ANCHOR_WINDOW_DAYS = 90

IN_SAMPLE_LABEL = (
    "IN-SAMPLE: every separation is fit against the same detected turns it is "
    "measured on, at every bar with a valid z. This calibrates indicator windows "
    "to detected history; it is NOT out-of-sample predictive skill and the "
    "holdout stays spent and untouched."
)

WINDOWS_LABEL = (
    "detector turns -> +/-45d cycle windows (turns_to_cycle_windows). A SCORING "
    "TARGET only: no exposure floor, no execution period, no perfect-strategy "
    "oracle."
)


def load_fits_harness() -> Any:
    """Load the Plan-19 fitting harness by file path (it is a script, not a module)."""
    spec = importlib.util.spec_from_file_location("fit_gold_indicators", FITS_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the frozen fitting harness from {FITS_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_constants_agree(fitter: Any) -> None:
    """Fail loudly if the frozen constants have drifted apart.

    The dead-zone width is restated in the shipped module (the owning harness is
    a research script, not importable), so the two copies must be checked
    against each other rather than trusted.
    """
    if fitter.DEGENERATE_MEAN_ABS != DEGENERATE_MEAN_ABS:
        raise ValueError(
            f"dead-zone width drifted: {FITS_SCRIPT.name} says "
            f"{fitter.DEGENERATE_MEAN_ABS}, sensitivity_consolidate says {DEGENERATE_MEAN_ABS} "
            "— both are frozen; change them together"
        )
    if fitter.ANCHOR_ROLLING_WINDOW != ANCHOR_PARAMS["rolling_window"]:
        raise ValueError(
            f"anchor rail drifted: {FITS_SCRIPT.name} fits on rolling "
            f"{fitter.ANCHOR_ROLLING_WINDOW}, this script assumes "
            f"{ANCHOR_PARAMS['rolling_window']}"
        )


def _row_from_fit(fitter: Any, name: str, fit: Any) -> IndicatorCaptureRow:
    """One indicator's BEST frozen-grid row at one level, as a capture row.

    An unscoreable indicator (a staged source that starts after every window at
    this level, say) still gets a row, with ``separation=None`` and the harness's
    own reason — listed, never silently absent.
    """
    best = fit.best_overall
    if best is None:
        grid = fitter.indicator_grid(name)
        return IndicatorCaptureRow(
            name=name,
            params={},
            params_note=(
                f"no scored row of {len(grid)}; frozen grid: "
                f"{[dict(point.params) for point in grid]}"
            ),
            window_days=grid[0].window_days,
            separation=None,
            mean_peak_z=None,
            mean_trough_z=None,
            peak_negative_share=None,
            trough_positive_share=None,
            zero_z_share=None,
            degenerate=False,
            coverage=0.0,
            scored_days=0,
            status=fit.status,
            reason=fit.reason,
        )
    return IndicatorCaptureRow(
        name=name,
        params=dict(best.params),
        window_days=best.window_days,
        separation=best.separation,
        mean_peak_z=best.mean_peak_z,
        mean_trough_z=best.mean_trough_z,
        peak_negative_share=best.peak_negative_share,
        trough_positive_share=best.trough_positive_share,
        zero_z_share=best.zero_z_share,
        degenerate=best.degenerate,
        coverage=best.coverage,
        scored_days=best.scored_days,
        status=fit.status,
        reason=fit.reason,
    )


def _anchor_row(
    fitter: Any, dates: list[date], windows: Any, date_s: Any, price_s: Any
) -> IndicatorCaptureRow:
    """The no-trend valuation anchor, scored against this level's windows."""
    score = fitter.separation(dates, fitter.anchor_z(date_s, price_s), windows)
    return IndicatorCaptureRow(
        name=ANCHOR_NAME,
        params=dict(ANCHOR_PARAMS),
        params_note=ANCHOR_PARAMS_NOTE,
        window_days=ANCHOR_WINDOW_DAYS,
        separation=score.separation,
        mean_peak_z=score.mean_peak_z,
        mean_trough_z=score.mean_trough_z,
        peak_negative_share=score.peak_negative_share,
        trough_positive_share=score.trough_positive_share,
        zero_z_share=score.zero_z_share,
        degenerate=score.degenerate,
        coverage=score.coverage,
        scored_days=score.scored_days,
        status="scored" if score.separation is not None else "unscoreable",
        reason=score.reason,
    )


def run_level(
    fitter: Any,
    min_move_pct: float,
    dates: list[date],
    price_s: pl.Series,
    sources: Any,
    date_s: pl.Series,
) -> tuple[SensitivityLevelRow, dict[str, Any]]:
    """Detect turns at one frozen level, then score every frozen grid against them."""
    config = TurnDetectionConfig(
        min_move_pct=min_move_pct,
        min_separation_days=FROZEN_SEPARATION_DAYS,
        confirmation_bars=FROZEN_CONFIRMATION_BARS,
        window_half_width_days=WINDOW_HALF_WIDTH_DAYS,
    )
    turnset = detect_turns(dates, price_s.to_list(), config)
    windows = turns_to_cycle_windows(turnset, WINDOW_HALF_WIDTH_DAYS)

    rows = [
        _row_from_fit(
            fitter, name, fitter.fit_indicator(name, dates, date_s, price_s, sources, windows)
        )
        for name in fitter.FITTED_INDICATORS
    ]
    rows.append(_anchor_row(fitter, dates, windows, date_s, price_s))
    level = SensitivityLevelRow(
        min_move_pct=min_move_pct,
        n_turns=len(turnset.turns),
        n_peaks=turnset.n_peaks,
        n_troughs=turnset.n_troughs,
        window_day_share=turnset.window_day_share,
        indicators=tuple(rows),
    )
    detail = {
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
        "drop_reason_counts": _drop_counts(turnset),
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
    return level, detail


def _drop_counts(turnset: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in turnset.dropped:
        key = str(record.reason)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _level_payload(level: SensitivityLevelRow, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "min_move_pct": level.min_move_pct,
        "n_turns": level.n_turns,
        "n_peaks": level.n_peaks,
        "n_troughs": level.n_troughs,
        "window_day_share": level.window_day_share,
        "capture_count": level.capture_count,
        "capturing": list(level.capturing),
        "non_capturing": [row.name for row in level.indicators if not row.captures],
        "indicators": [
            {
                **row.model_dump(mode="json"),
                "captures": row.captures,
            }
            for row in level.indicators
        ],
        "detector": detail,
    }


def _choice_payload(choice: SensitivityChoice) -> dict[str, Any]:
    return {
        "capture_bar": choice.capture_bar,
        "chosen_min_move_pct": choice.chosen_min_move_pct,
        "chosen_n_turns": choice.chosen_n_turns,
        "capture_count": choice.capture_count,
        "capturing_indicators": list(choice.capturing_indicators),
        "non_capturing_indicators": list(choice.non_capturing_indicators),
        "capture_rule": choice.capture_rule,
        "choice_rule": choice.choice_rule,
        "rationale": choice.rationale,
        "dropped_at_finer_levels": [
            {
                "min_move_pct": entry.min_move_pct,
                "n_turns": entry.n_turns,
                "capture_count": entry.capture_count,
                "qualifies": entry.qualifies,
                "dropped": [drop.model_dump(mode="json") for drop in entry.dropped],
            }
            for entry in choice.dropped_at_finer_levels
        ],
    }


def print_matrix(levels: list[SensitivityLevelRow], choice: SensitivityChoice) -> None:
    """The owner's read: the three levels side by side, best separation per indicator.

    The choice rule is NOT restated here — this reads the counts the frozen rule
    already consumed, plus the ``qualifies`` verdict the module recorded for each
    finer level, so the table cannot drift from the decision it explains.
    """
    finer = {entry.min_move_pct: entry.qualifies for entry in choice.dropped_at_finer_levels}
    chosen = {
        level.min_move_pct: level.min_move_pct == choice.chosen_min_move_pct for level in levels
    }

    def cells(label: str, value: Any) -> None:
        print(f"{label:<22}" + "".join(f"{value(level):>30}" for level in levels))

    print()
    print("SENSITIVITY CONSOLIDATION (Plan 22 Engine 2) — best frozen grid row per level")
    cells("level", lambda level: f"@{format(level.min_move_pct, 'g')}%")
    cells(
        "turns (peaks/troughs)",
        lambda level: f"{level.n_turns} ({level.n_peaks}/{level.n_troughs})",
    )
    cells("window-day share", lambda level: f"{level.window_day_share:.4f}")
    cells(f"# capturing (bar {format(CAPTURE_BAR, 'g')})", lambda level: level.capture_count)
    cells(
        "verdict",
        lambda level: (
            "<= CHOSEN"
            if chosen[level.min_move_pct]
            else ("qualifies, coarser tie" if finer.get(level.min_move_pct) else "loses")
        ),
    )
    for name in [row.name for row in levels[0].indicators]:
        cells(
            name,
            lambda level, name=name: _cell(
                next(row for row in level.indicators if row.name == name)
            ),
        )
    print()
    print("  * captures this level (separation >= bar, sign-correct, not one-sided);")
    print("  [w] is the row's window_days; DEGENERATE = one side's mean inside the dead zone")
    print(
        f"  chosen: min_move_pct={choice.chosen_min_move_pct} ({choice.chosen_n_turns} turns), "
        f"capturing {choice.capture_count} — {choice.rationale}"
    )
    print()
    print("DROPPED AT FINER LEVELS (the owner's evidence table)")
    if not choice.dropped_at_finer_levels:
        print("  none — the chosen level is the finest on the ladder")
    for entry in choice.dropped_at_finer_levels:
        print(
            f"  min_move_pct={entry.min_move_pct} ({entry.n_turns} turns, "
            f"captures {entry.capture_count}, qualifies={entry.qualifies})"
        )
        if not entry.dropped:
            print("    nothing dropped")
        for drop in entry.dropped:
            print(
                f"    {drop.name:<16} sep {_signed(drop.separation_at_chosen_level)} -> "
                f"{_signed(drop.separation_at_finer_level)}  {drop.reason}"
            )


def _cell(row: IndicatorCaptureRow) -> str:
    """One matrix cell: the separation, the capture mark and the window it was read at."""
    if row.separation is None:
        return f"unscoreable [{row.window_days}d]"
    flag = " DEGENERATE" if row.degenerate else ""
    return f"{row.separation:+.4f}{flag}{' *' if row.captures else '  '} [{row.window_days}d]"


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


def main() -> int:
    fitter = load_fits_harness()
    _assert_constants_agree(fitter)

    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars, price column 'close')")
    print(
        f"grid: min_move_pct {list(MOVE_PCT_LEVELS)} x min_separation_days "
        f"[{FROZEN_SEPARATION_DAYS}], confirmation_bars {FROZEN_CONFIRMATION_BARS}, "
        f"windows +/-{WINDOW_HALF_WIDTH_DAYS}d"
    )
    print(f"capture bar {CAPTURE_BAR} z-units, dead zone +/-{DEGENERATE_MEAN_ABS} (frozen)")
    print(f"indicators scored: {list(fitter.FITTED_INDICATORS)} + {ANCHOR_NAME} anchor")
    print(CAPTURE_RULE)
    print(CHOICE_RULE)
    print(f"windows: {WINDOWS_LABEL}")

    levels: list[SensitivityLevelRow] = []
    details: dict[str, Any] = {}
    for min_move_pct in MOVE_PCT_LEVELS:
        level, detail = run_level(fitter, min_move_pct, dates, price_s, sources, date_s)
        levels.append(level)
        details[str(level.min_move_pct)] = detail

    choice = select_sensitivity_level(levels)
    print_matrix(levels, choice)

    payload = {
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
        },
        "frozen_inputs": {
            "capture_bar": CAPTURE_BAR,
            "degenerate_mean_abs": DEGENERATE_MEAN_ABS,
            "separator": (
                "fit_gold_indicators.separation — mean(z | trough windows) - "
                "mean(z | peak windows); abs() never applied"
            ),
            "grids": (
                "fit_gold_indicators.indicator_grid — the Plan-19 frozen grids, "
                "imported not restated; no grid changed after seeing output"
            ),
            "anchor": (
                f"{ANCHOR_NAME} = shipped rolling_z rails, rolling "
                f"{ANCHOR_PARAMS['rolling_window']}d / z 1.0, scored as one more row"
            ),
            "harness": str(FITS_SCRIPT),
        },
        "windows_label": WINDOWS_LABEL,
        "in_sample": True,
        "in_sample_label": IN_SAMPLE_LABEL,
        "levels": [_level_payload(level, details[str(level.min_move_pct)]) for level in levels],
        "choice": _choice_payload(choice),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(IN_SAMPLE_LABEL)
    print()
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
