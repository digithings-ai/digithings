#!/usr/bin/env python3
"""GOLD wiring for the generic SDCA period optimizer (#4804, Plan 20 Task 3).

Runs the medium and long horizons on the cached GLD closes, combines them
(long sells override medium buys), prices both comparators, and writes one
JSON carrying every metric, the split-sample pairs and the CEILING label:

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_period_optimization.py

Writes only ``digiquant/.scratch/gold_period_optimization.json`` (UNTRACKED).
All search machinery lives in the generic modules — this file is the gold
wiring plus the console ladder; ``optimize_sdca_periods.py`` is the same
ladder for any other symbol and carries the shared read-layer rules (the
Ruling 2 Calmar epsilon, the ceiling sentence, the table/row formatting), so
both scripts can never drift apart on how a number is presented.

**``--long-first`` (Plan 21, Task 3) is a second mode, not a replacement.** With
no flag the script runs exactly the Plan-20 every-swing-pivot ladder above and
writes the Plan-20 record to the same path, because that record is the argument
the long-first model is being tested against. With ``--long-first`` it selects
the secular LONG set first, then grades MEDIUM windows onto it one rung at a
time, and writes ``.scratch/gold_period_ladder.json`` instead:

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_period_optimization.py --long-first

Nothing here re-implements search: ``select_long_term_periods`` picks the long
regime, ``window_is_hit`` grades each window, ``grade_medium_overlay`` runs the
ladder under the frozen objective and the frozen floor, ``score_periods`` prices
every rung. The long selection runs at the FROZEN DEFAULT half-width only — this
is a wiring task, not a width sweep, and a width can change the set qualitatively
(wider costs more days under the same cap, so it can refuse below the minima).
The medium rungs carry whatever widths ``discover_candidate_periods`` already
derives; that ladder IS the run.

**The honest frame, printed before every table.** The oracle is an IN-SAMPLE
CEILING on the same history the periods were fit on: it buys the entire book
all-in on each pinned buy date and sells all-out on each pinned sell date, so
it measures period *quality*, never achievable performance. The split-sample
read (fit periods on the first half, score on the unseen second half) is the
only out-of-sample-ish number here, and both sides are reported together.

**Nothing is tuned in this file.** The objective, the 70% time-in-market floor
and the two grids are frozen module constants. A width whose pivot count falls
below the minima is reported as dropped, and a candidate that misses the floor
is reported as ineligible: neither minimum is lowered to make a run succeed.
When nothing is eligible, the highest-ranked ineligible candidate is still
printed — labeled ``rank1 diagnostic, NOT a selection`` — so the owner can see
what the floor cost without it ever being quotable as a result.

Research-only. No engine call, no backtest, no ``nautilus_trader`` import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import (  # noqa: E402
    CEILING_LABEL,
    OBJECTIVE_LABEL,
    RISK_FREE_LABEL,
    calmar_or_none,
    fmt_opt,
    grid_label,
    horizon_by_name,
    horizon_payload,
    load_closes,
    metrics_row,
    print_candidate_table,
    print_table,
    run_horizon,
    score_row,
    split_sample_payload,
)

from digiquant.strategies.sdca.dca_metrics import (  # noqa: E402
    flat_dca_mark_to_market,
    lump_mark_to_market,
)
from digiquant.strategies.sdca.period_optimize import (  # noqa: E402
    DEFAULT_INITIAL_CASH,
    EXPOSURE_FLOOR_PCT,
    LONG_MIN_MOVE_PCT,
    MEDIUM_MIN_MOVE_PCT,
    LongTermSelection,
    OverlayGrade,
    PeriodScore,
    combine_periods,
    discover_candidate_periods,
    grade_medium_overlay,
    score_periods,
    select_long_term_periods,
    split_sample_check,
    window_is_hit,
)
from digiquant.strategies.sdca.risk_metrics import equity_metrics  # noqa: E402

SYMBOL = "GLD-USD"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / f"{SYMBOL}.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_period_optimization.json"
LADDER_OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_period_ladder.json"

SPLIT = 0.5

# Frozen Plan-21 cap, passed explicitly rather than left to the default so the
# JSON records what shaped the set. It is the module default, not a tuned knob.
MAX_PEAK_DAYS_PCT = 25.0

HOLDOUT_NOTE = (
    "in-sample by construction: this run scores the FULL cached GLD history, the same "
    "history the periods are derived from. No separate holdout segment was carved out "
    "or touched; the split-sample pair below is the only out-of-sample-ish read."
)

LONG_FIRST_MODEL_LABEL = (
    "long-first period model (Plan 21): the LONG secular set is selected FIRST as the "
    f"primary regime — prominence-ranked pivots under a {MAX_PEAK_DAYS_PCT:.1f}% peak-day "
    "cap at the frozen default half-width — then MEDIUM windows are added ONE RUNG AT A "
    "TIME (shorter window first, earlier date breaking ties). A rung is kept only when it "
    f"is HIT (caught a real move), strictly improves oracle Sharpe, and clears the frozen "
    f"{EXPOSURE_FLOOR_PCT:.1f}% floor; the first failure stops the ladder. The floor is "
    "NEVER relaxed, and peak/trough day shares are SEPARATE quantities — only peak days "
    "bound the floor."
)

LONG_FIRST_CEILING_LABEL = (
    CEILING_LABEL + " The long-first rebuild changes WHICH periods are chosen, not what the number "
    "means: selecting on prominence and capping covered days is still selection on the "
    "same history, so pure-long and every graded rung are the same kind of ceiling."
)

SPLIT_DEFECT_NOTE = (
    "the out-of-sample side of a split-sample is structurally binary — a filed 1-bit "
    "defect: a fitted window straddling the split collapses its enter onto the first "
    "unseen bar, so the book is either all-in at the split or flat forever. Both sides "
    "are printed anyway (the fit half's own ladder, and the unseen-half score of the "
    "windows it kept) so the out-of-sample read is visible rather than null."
)

SOURCES = (
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "period_optimize.py",
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "risk_metrics.py",
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "perfect_strategy.py",
    DIGIQUANT_ROOT / "scripts" / "optimize_sdca_periods.py",
    DIGIQUANT_ROOT / "scripts" / "run_gold_period_optimization.py",
)


def sha256(path: Path) -> str:
    """Full-file digest, so every number in the JSON is traceable to its inputs."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header(symbol: str, dates: Sequence[date], data_path: Path) -> None:
    """Print the honesty frame once, above every table."""
    print(f"=== GOLD PERIOD OPTIMIZATION ({symbol}) — Plan 20 Task 3 (#4804) ===")
    print(f"{symbol} {dates[0]}..{dates[-1]} ({len(dates)} daily bars) from {data_path}")
    print(CEILING_LABEL)
    print(OBJECTIVE_LABEL)
    print(RISK_FREE_LABEL)
    print(HOLDOUT_NOTE)
    print("")


def print_pivot_table(name: str, rows: Sequence[dict[str, Any]]) -> None:
    """Pivot counts per candidate width (identical per width; see pivot_rows docstring)."""
    print(f"{name} pivots per candidate width:")
    for row in rows:
        mark = "scored" if row["scored"] else "DROPPED"
        print(
            f"  pm{row['half_width_days']:<4} {row['n_peaks']:>4} peaks / "
            f"{row['n_troughs']:>4} troughs  {mark}"
            + (f" — {row['drop_reason']}" if row["drop_reason"] else "")
        )
    print("")


def print_selection(name: str, block: dict[str, Any]) -> None:
    """The verdict for one horizon (or the combination), with the reason spelled out."""
    best = block["selection"]["best"]
    if best is not None:
        print(
            f"{name} SELECTION: {best['label']} — sharpe {best['sharpe']:.4f} | calmar "
            f"{fmt_opt(best['calmar'], '.3f') or '(blank: dd < eps)'} | cagr "
            f"{best['cagr_pct']:.2f}% | exposure {best['exposure_pct']:.2f}%"
        )
        return
    print(f"{name} SELECTION: NONE — {block['selection']['best_absent_reason']}")
    diagnostic = block["selection"].get("rank1_ineligible_diagnostic")
    if diagnostic and diagnostic.get("candidate"):
        row = diagnostic["candidate"]
        print(
            f"  rank1 diagnostic (NOT a selection): {row['label']} — sharpe {row['sharpe']:.4f}"
            f" | calmar {fmt_opt(row['calmar'], '.3f') or '(blank: dd < eps)'} | cagr "
            f"{row['cagr_pct']:.2f}% | maxdd {row['max_drawdown_pct']:.2f}% | exposure "
            f"{row['exposure_pct']:.2f}% | {row['rejection']}"
        )
    print("")


def rank1(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Highest-ranked candidate row, whatever its eligibility (diagnostics only)."""
    return rows[0] if rows else None


def diagnostic_score(
    dates: Sequence[date],
    prices: Sequence[float],
    windows: Sequence[Any],
    *,
    label: str,
    half_width_days: int | None,
    exposure_floor_pct: float,
    initial_cash: float,
) -> dict[str, Any]:
    """Score a NON-selected window set (a floor-failing rank-1, a combined diagnostic).

    Every such row carries the ``diagnostic`` warning so it can never be mistaken for
    a selection in the JSON, in the console, or in a Task-4 chart.
    """
    score = score_periods(
        dates,
        prices,
        windows,
        exposure_floor_pct=exposure_floor_pct,
        initial_cash=initial_cash,
        half_width_days=half_width_days,
    )
    row = score_row(score, label=label)
    row["diagnostic"] = (
        "NOT a selection: this window set does not clear the frozen time-in-market floor "
        "and therefore may not be quoted as the optimizer's best."
    )
    return row


def comparators(prices: Sequence[float], initial_cash: float) -> dict[str, dict[str, Any]]:
    """``lump_mark_to_market`` + ``flat_dca_mark_to_market`` on the same calendar.

    Both are invested on every bar from day 0 (lump deploys at the first close; flat
    DCA spends ``cash / (n - i) > 0`` on bar 0), so ``exposure_pct`` is exactly 100.0
    for both — that is a property of the two paths, not an assumption.
    """
    paths = {
        "lump_mark_to_market": lump_mark_to_market,
        "flat_dca_mark_to_market": flat_dca_mark_to_market,
    }
    out: dict[str, dict[str, Any]] = {}
    for name, build in paths.items():
        values = build(prices, initial_cash)
        out[name] = metrics_row(
            name,
            equity_metrics(values),
            exposure_pct=100.0,
            eligible=None,
            rejection=None,
            extra={
                "comparator": True,
                "exposure_basis": "invested on every bar from day 0 by construction",
            },
        )
    return out


def combined_block(
    dates: Sequence[date],
    prices: Sequence[float],
    medium_rows: Sequence[dict[str, Any]],
    long_rows: Sequence[dict[str, Any]],
    medium_windows: Sequence[Any],
    long_windows: Sequence[Any],
    *,
    initial_cash: float,
) -> dict[str, Any]:
    """Combine the two horizons with the module's precedence and report the verdict.

    ``combine_periods`` emits long peaks, medium peaks, long troughs, medium troughs,
    and ``SdcaCycleWindows.kind_on`` returns the first match — so **long sells override
    medium buys** on a shared date.
    """
    combined = combine_periods(medium_windows, long_windows)
    block: dict[str, Any] = {
        "precedence": (
            "combine_periods order = long peaks, medium peaks, long troughs, medium "
            "troughs; SdcaCycleWindows.kind_on returns the first match, so LONG SELLS "
            "OVERRIDE MEDIUM BUYS on a shared date (flat = the conservative read of an "
            "ambiguous pin, matching the oracle's own sell-beats-buy rule)"
        ),
        "inputs": {
            "medium": rank1(medium_rows)["label"] if rank1(medium_rows) else None,
            "long": rank1(long_rows)["label"] if rank1(long_rows) else None,
        },
        "n_windows": len(combined.windows),
        "n_peaks": len(combined.peaks()),
        "n_troughs": len(combined.troughs()),
        "selection": {
            "best": None,
            "best_absent_reason": (
                "both horizons returned no eligible candidate under the frozen "
                f"{EXPOSURE_FLOOR_PCT:.1f}% time-in-market floor, so there is no selected "
                "medium/long set to combine; nothing here is a selection"
            ),
        },
        "windows": [window.model_dump(mode="json") for window in combined.windows],
    }
    block["rank1_ineligible_diagnostic"] = diagnostic_score(
        dates,
        prices,
        combined.windows,
        label="combined(rank1)",
        half_width_days=None,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        initial_cash=initial_cash,
    )
    return block


def combined_split_sample(
    dates: Sequence[date],
    prices: Sequence[float],
    medium_fit_windows: Sequence[Any],
    long_fit_windows: Sequence[Any],
    *,
    split: float,
    initial_cash: float,
) -> dict[str, Any]:
    """Fit-half medium+long rank-1 windows, scored on the unseen half (diagnostic).

    ``split_sample_check`` is per-horizon by design, so the combined pair is assembled
    here from the same two fit halves at the same ``int(len(dates) * split)`` index the
    module uses — the arithmetic is duplicated verbatim rather than re-derived.
    """
    split_at = int(len(dates) * split)
    combined = combine_periods(medium_fit_windows, long_fit_windows)
    out_of_sample = diagnostic_score(
        dates[split_at:],
        prices[split_at:],
        combined.windows,
        label="combined(rank1)",
        half_width_days=None,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        initial_cash=initial_cash,
    )
    return {
        "note": (
            "assembled in this wiring script from the two fit halves at the module's own "
            f"split index int(len(dates) * {split}) = {split_at}; split_sample_check is "
            "per-horizon by design"
        ),
        "split": split,
        "fit_days": split_at,
        "score_days": len(dates) - split_at,
        "fit_windows": len(combined.windows),
        "out_of_sample": out_of_sample,
        "out_of_sample_eligible": bool(out_of_sample["eligible"]),
    }


def calendar_bound_pins(
    selection: LongTermSelection,
    first_day: date,
    last_day: date,
) -> dict[str, Any]:
    """Is any selected pin calendar-bound? Derived here — the model does not carry it.

    Ruling 1's carry-forward asks the report to state whether the trailing pivot entered
    the set on a to-end-of-calendar bound, and ``LongTermSelection`` does not record it.
    So it is DERIVED, not guessed: a pin is calendar-bound when ``pin +/- half_width_days``
    falls beyond EITHER calendar edge — the first bar or the last bar. Both edges are
    checked, because a to-start pin is exactly as much an artifact of where the sample
    begins as a to-end one. Reported per window, so a reader can see which pin it was and
    not just that "some" pin was.
    """
    offset = timedelta(days=selection.half_width_days)
    rows: list[dict[str, Any]] = []
    for window in selection.windows:
        pin = window.start + offset
        before_first = pin - offset < first_day
        after_last = pin + offset > last_day
        rows.append(
            {
                "window": window.name,
                "kind": str(window.kind),
                "pin": pin.isoformat(),
                "window_start": window.start.isoformat(),
                "window_end": window.end.isoformat(),
                "pin_before_first_bar": before_first,
                "pin_after_last_bar": after_last,
                "calendar_bound": before_first or after_last,
            }
        )
    return {
        "rule": (
            "a selected pin is calendar-bound when pin +/- half_width_days falls beyond "
            "either calendar edge (first bar or last bar); derived here from "
            "LongTermSelection.half_width_days because the model does not carry it"
        ),
        "half_width_days": selection.half_width_days,
        "first_bar": first_day.isoformat(),
        "last_bar": last_day.isoformat(),
        "n_windows": len(rows),
        "n_calendar_bound": sum(1 for row in rows if row["calendar_bound"]),
        "any_calendar_bound": any(row["calendar_bound"] for row in rows),
        "windows": rows,
    }


def long_selection_payload(
    dates: Sequence[date],
    prices: Sequence[float],
    selection: LongTermSelection,
) -> dict[str, Any]:
    """The long regime as read off the record: windows, kinds, hit verdicts, day shares.

    ``peak_days_pct`` and ``trough_days_pct`` are reported as SEPARATE quantities because
    the cap is applied per kind (Task-1 review LOW-1): only peak days are the flat time
    that bounds the exposure floor, so reading ``trough_days_pct`` through the same
    reasoning would be wrong. Hit verdicts are measured on the full calendar at the frozen
    long threshold and quote the OBSERVED move, so an unhit window can say what it caught.
    """
    verdicts = [
        window_is_hit(dates, prices, window, min_move_pct=LONG_MIN_MOVE_PCT).model_dump(mode="json")
        for window in selection.windows
    ]
    return {
        "half_width_days": selection.half_width_days,
        "half_width_note": (
            "frozen default half-width (min of the long grid), passed as None so the "
            "default is what runs; this task does not sweep widths"
        ),
        "max_peak_days_pct": selection.max_peak_days_pct,
        "calendar_days": selection.calendar_days,
        "selected": selection.selected,
        "reason": selection.reason,
        "n_peaks": selection.n_peaks,
        "n_troughs": selection.n_troughs,
        "peak_days": selection.peak_days,
        "peak_days_pct": selection.peak_days_pct,
        "trough_days": selection.trough_days,
        "trough_days_pct": selection.trough_days_pct,
        "day_share_note": (
            "peak and trough day shares are SEPARATE (the cap is applied per kind); only "
            "peak days are the flat time that bounds the exposure floor"
        ),
        "detected_peak_pins": [day.isoformat() for day in selection.peak_pins],
        "detected_trough_pins": [day.isoformat() for day in selection.trough_pins],
        "peak_prominence_pct": list(selection.peak_prominence_pct),
        "trough_prominence_pct": list(selection.trough_prominence_pct),
        "windows": [window.model_dump(mode="json") for window in selection.windows],
        "hit_min_move_pct": LONG_MIN_MOVE_PCT,
        "hit": verdicts,
        "n_unhit": sum(1 for verdict in verdicts if not verdict["hit"]),
        "calendar_bound_pins": calendar_bound_pins(selection, dates[0], dates[-1]),
    }


def print_hit_table(title: str, verdicts: Sequence[dict[str, Any]]) -> None:
    """Hit verdicts with the observed move quoted beside the threshold it missed."""
    print_table(
        title,
        ("window", "kind", "bars", "max_move%", "dir", "min_move%", "hit"),
        [
            (
                str(verdict["window"]),
                str(verdict["kind"]),
                str(verdict["bars"]),
                fmt_opt(verdict["max_move_pct"], ".2f"),
                str(verdict["direction"]),
                fmt_opt(verdict["min_move_pct"], ".1f"),
                "yes" if verdict["hit"] else "NO",
            )
            for verdict in verdicts
        ],
    )


def _blanked_calmar(max_drawdown_pct: float | None, calmar: float | None) -> float | None:
    """Calmar unless the drawdown is float dust (Ruling 2), or the rung was never scored."""
    if max_drawdown_pct is None or calmar is None:
        return None
    return calmar_or_none(max_drawdown_pct, calmar)


def _trajectory_row(
    index: int,
    label: str,
    *,
    n_windows: int,
    added: int,
    all_added_hit: bool | None,
    sharpe: float | None,
    calmar: float | None,
    cagr_pct: float | None,
    max_drawdown_pct: float | None,
    exposure_pct: float | None,
    floor_pct: float,
    verdict: str,
    reason: str | None,
) -> dict[str, Any]:
    """One rung of the exposure trajectory — the headline column of the whole run."""
    meets_floor = None if exposure_pct is None else exposure_pct >= floor_pct
    return {
        "rung": index,
        "label": label,
        "n_windows": n_windows,
        "added_windows": added,
        "all_added_hit": all_added_hit,
        "exposure_pct": exposure_pct,
        "meets_exposure_floor": meets_floor,
        "exposure_gap_pp": None if exposure_pct is None else exposure_pct - floor_pct,
        "sharpe": sharpe,
        "calmar": _blanked_calmar(max_drawdown_pct, calmar),
        "cagr_pct": cagr_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "verdict": verdict,
        "reason": reason,
    }


def exposure_trajectory(grade: OverlayGrade) -> list[dict[str, Any]]:
    """The ladder as one table, rung 0 = pure long, then every rung that was tried.

    Exposure is the HEADLINE column because it is the quantity the whole long-first
    rebuild is about: Plan 20 pinned it near 55% whatever the width, because pivot
    DENSITY rather than width decided the flat time. The question this table answers is
    whether adding graded medium windows CLIMBS toward the frozen floor.

    A rung abandoned before scoring (unhit, duplicate) carries ``None`` metrics, never
    0.0 — nothing was measured there, and zero would read as a measurement of zero.
    """
    floor = grade.exposure_floor_pct
    baseline = grade.baseline
    rows = [
        _trajectory_row(
            0,
            "pure_long",
            n_windows=len(baseline.windows),
            added=0,
            all_added_hit=None,
            sharpe=baseline.sharpe,
            calmar=baseline.calmar,
            cagr_pct=baseline.cagr_pct,
            max_drawdown_pct=baseline.max_drawdown_pct,
            exposure_pct=baseline.exposure_pct,
            floor_pct=floor,
            verdict="base (kept: the secular regime)" if baseline.eligible else "base",
            reason=baseline.rejection,
        )
    ]
    for step in grade.steps:
        added = len(step.added)
        if added == 0:
            verdict, all_hit = "ABANDON", None
        elif step.sharpe is None:
            verdict, all_hit = "ABANDON", None
        else:
            verdict = "KEEP" if step.kept else "ABANDON"
            all_hit = all(hit.hit for hit in step.hit)
        rows.append(
            _trajectory_row(
                step.index,
                f"pm{step.half_width_days}",
                n_windows=len(step.kept_windows),
                added=added,
                all_added_hit=all_hit,
                sharpe=step.sharpe,
                calmar=step.calmar,
                cagr_pct=step.cagr_pct,
                max_drawdown_pct=step.max_drawdown_pct,
                exposure_pct=step.exposure_pct,
                floor_pct=floor,
                verdict=verdict,
                reason=step.reason,
            )
        )
    return rows


def print_trajectory(title: str, rows: Sequence[dict[str, Any]]) -> None:
    """Print the ladder with exposure right after the hit verdict — the key column."""
    print_table(
        title,
        (
            "rung",
            "candidate",
            "wins",
            "added",
            "hit",
            "expo%",
            "vs_floor",
            "sharpe",
            "calmar",
            "cagr%",
            "maxdd%",
            "verdict",
        ),
        [
            (
                str(row["rung"]),
                str(row["label"]),
                str(row["n_windows"]),
                str(row["added_windows"]),
                "n/a"
                if row["all_added_hit"] is None
                else ("yes" if row["all_added_hit"] else "NO"),
                fmt_opt(row["exposure_pct"], ".2f"),
                "n/a" if row["meets_exposure_floor"] is None else f"{row['exposure_gap_pp']:+.2f}",
                fmt_opt(row["sharpe"], ".4f"),
                fmt_opt(row["calmar"], ".3f"),
                fmt_opt(row["cagr_pct"], ".2f"),
                fmt_opt(row["max_drawdown_pct"], ".2f"),
                str(row["verdict"]),
            )
            for row in rows
        ],
    )


HIT_DETAIL_SAMPLE = 3


def _hit_summary(hits: Sequence[dict[str, Any]]) -> str:
    """Complete counts plus a few named examples — the FULL list stays in the JSON.

    A real medium candidate carries EVERY swing pivot (GLD: 642 windows at each width),
    so printing every name would bury the exposure column this run exists to show. Every
    count below is complete and the examples are named; ``overlay.steps[].added`` and
    ``overlay.steps[].hit`` in the JSON carry every window and every observed move.
    """
    unhit = [hit for hit in hits if not hit["hit"]]
    hit_examples = [hit for hit in hits if hit["hit"]]
    moves = [float(hit["max_move_pct"]) for hit in hits]
    parts = [
        f"{len(hit_examples)}/{len(hits)} HIT, {len(unhit)}/{len(hits)} UNHIT",
        f"observed moves {min(moves):.2f}%..{max(moves):.2f}%",
    ]
    if unhit:
        first = unhit[0]
        parts.append(
            f"first unhit {first['window']} {first['max_move_pct']:.2f}% over "
            f"{first['bars']} bars ({first['direction']})"
        )
    for hit in hit_examples[:HIT_DETAIL_SAMPLE]:
        parts.append(f"{hit['window']} {hit['max_move_pct']:.2f}% {hit['direction']} HIT")
    for hit in unhit[:HIT_DETAIL_SAMPLE]:
        parts.append(f"{hit['window']} {hit['max_move_pct']:.2f}% {hit['direction']} UNHIT")
    return "; ".join(parts)


def print_ladder_details(grade: OverlayGrade) -> None:
    """Each rung spelled out: what it added, the hit verdicts, and the keep/abandon reason."""
    for step in grade.steps:
        print(
            f"rung {step.index} pm{step.half_width_days}: added {len(step.added)} medium "
            f"window(s) -> book {len(step.kept_windows)} window(s) | "
            f"{'KEEP' if step.kept else 'ABANDON'}" + (f" — {step.reason}" if step.reason else "")
        )
        if step.added:
            print(
                f"  added: {len(step.added)} window(s), every name in the JSON at "
                f"overlay.steps[{step.index - 1}].added"
            )
        if step.hit:
            verdicts = [hit.model_dump(mode="json") for hit in step.hit]
            print(f"  hit verdicts at {step.hit[0].min_move_pct:.1f}%: {_hit_summary(verdicts)}")
        if step.sharpe is None:
            print("  not scored (abandoned before any oracle call — metrics are None, not 0)")
        else:
            print(
                f"  scored: sharpe {step.sharpe:.4f} | calmar "
                f"{fmt_opt(_blanked_calmar(step.max_drawdown_pct, step.calmar), '.3f') or '(blank: dd < eps)'} | "
                f"cagr {step.cagr_pct:.2f}% | maxdd {step.max_drawdown_pct:.2f}% | exposure "
                f"{step.exposure_pct:.2f}% (floor {grade.exposure_floor_pct:.1f}%)"
            )
        print("")


def long_first_split_sample(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    split: float,
    max_peak_days_pct: float,
) -> dict[str, Any]:
    """Fit the WHOLE long-first model on the first half, score its kept windows unseen.

    The fit half selects its OWN secular set and grades its OWN medium ladder, because
    re-running selection on the full history and then scoring it split would leak the
    unseen half into the fit. This mirrors ``split_sample_check``'s read (fit first half,
    carry the fitted window dates onto the unseen half, report both sides) in the
    long-first model's terms. Both sides are always reported; a refusal or an empty ladder
    on the fit half is a result, and the out-of-sample number is printed regardless.
    """
    split_at = int(len(dates) * split)
    fit_dates, fit_prices = dates[:split_at], prices[:split_at]
    out: dict[str, Any] = {
        "split": split,
        "fit_days": split_at,
        "score_days": len(dates) - split_at,
        "note": (
            "the long-first fit half selects its own long set and grades its own medium "
            "ladder, then the windows it kept are scored on the unseen half; a window "
            "falling before the split does not act there (the oracle ignores "
            "out-of-calendar pins)"
        ),
        "defect_note": SPLIT_DEFECT_NOTE,
        "fit_long_selection": None,
        "fit_ladder": None,
        "fit_kept_windows": [],
        "out_of_sample": None,
        "out_of_sample_eligible": False,
    }
    fit_selection = select_long_term_periods(
        fit_dates, fit_prices, max_peak_days_pct=max_peak_days_pct
    )
    out["fit_long_selection"] = {
        "selected": fit_selection.selected,
        "reason": fit_selection.reason,
        "half_width_days": fit_selection.half_width_days,
        "n_peaks": fit_selection.n_peaks,
        "n_troughs": fit_selection.n_troughs,
        "peak_days_pct": fit_selection.peak_days_pct,
        "trough_days_pct": fit_selection.trough_days_pct,
    }
    if not fit_selection.selected:
        out["fit_absent_reason"] = (
            "the fit half carries no long-term window set, so there is nothing to carry "
            "onto the unseen half; the minimums are never relaxed to manufacture one"
        )
        return out

    fit_medium = discover_candidate_periods(fit_dates, fit_prices, horizon_by_name("medium"))
    fit_grade = grade_medium_overlay(
        fit_dates,
        fit_prices,
        fit_selection.windows,
        fit_medium,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        min_move_pct=MEDIUM_MIN_MOVE_PCT,
    )
    out["fit_ladder"] = {
        "fit_baseline": score_row(fit_grade.baseline, label="pure_long@fit"),
        "steps": [
            {
                "index": step.index,
                "half_width_days": step.half_width_days,
                "added_windows": len(step.added),
                "hit": [hit.model_dump(mode="json") for hit in step.hit],
                "sharpe": step.sharpe,
                "calmar": _blanked_calmar(step.max_drawdown_pct, step.calmar),
                "cagr_pct": step.cagr_pct,
                "max_drawdown_pct": step.max_drawdown_pct,
                "exposure_pct": step.exposure_pct,
                "kept": step.kept,
                "reason": step.reason,
            }
            for step in fit_grade.steps
        ],
        "stop_reason": fit_grade.stop_reason,
        "n_kept_rungs": len(fit_grade.ladder),
        "n_medium_candidates_offered": len(fit_medium),
    }
    fit_kept = fit_grade.kept_windows
    out["fit_kept_windows"] = [window.model_dump(mode="json") for window in fit_kept]
    out["fit_kept_window_names"] = [window.name for window in fit_kept]

    out_of_sample = score_periods(
        dates[split_at:],
        prices[split_at:],
        fit_kept,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        half_width_days=fit_selection.half_width_days,
    )
    out_row = score_row(out_of_sample, label="long_first_kept->unseen")
    out_row["diagnostic"] = (
        "NOT a selection: the unseen-half score of windows fitted on the fit half. It is "
        "the only out-of-sample-ish number in this run and it carries the same frozen "
        "floor."
    )
    out["out_of_sample"] = out_row
    out["out_of_sample_eligible"] = bool(out_of_sample.eligible)
    out["acted_dates_out_of_sample"] = len(out_of_sample.edges.buy_dates) + len(
        out_of_sample.edges.sell_dates
    )
    return out


def long_first_ladder() -> int:
    """Plan 21 mode: long regime first, then the graded medium ladder. Writes the ladder JSON."""
    dates, prices = load_closes(SYMBOL, DATA_PATH)
    print(f"=== GOLD LONG-FIRST PERIOD LADDER ({SYMBOL}) — Plan 21 Task 3 (#4804) ===")
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars) from {DATA_PATH}")
    print(LONG_FIRST_CEILING_LABEL)
    print(OBJECTIVE_LABEL)
    print(RISK_FREE_LABEL)
    print(LONG_FIRST_MODEL_LABEL)
    print(HOLDOUT_NOTE)
    print(grid_label(horizon_by_name("long")))
    print("")

    selection = select_long_term_periods(dates, prices, max_peak_days_pct=MAX_PEAK_DAYS_PCT)
    long_block = long_selection_payload(dates, prices, selection)
    print(
        f"LONG SELECTION: {selection.n_peaks} peaks / {selection.n_troughs} troughs at the "
        f"frozen default half-width {selection.half_width_days}d | detected long pivots "
        f"{len(selection.peak_pins)} / {len(selection.trough_pins)} | peak-day cap "
        f"{MAX_PEAK_DAYS_PCT:.1f}% of {selection.calendar_days} bars"
    )
    print(
        f"  day shares (SEPARATE quantities, cap is per kind): peak_days "
        f"{selection.peak_days} = {selection.peak_days_pct:.2f}%  |  trough_days "
        f"{selection.trough_days} = {selection.trough_days_pct:.2f}%"
    )
    print("  only PEAK days are the flat time that bounds the exposure floor")
    bound = long_block["calendar_bound_pins"]
    print(
        f"  calendar-bound pins: {bound['n_calendar_bound']} of {bound['n_windows']} "
        f"(any={bound['any_calendar_bound']}) — a pin is calendar-bound when pin +/- "
        f"{selection.half_width_days}d falls beyond either calendar edge "
        f"({bound['first_bar']} .. {bound['last_bar']})"
    )
    for row in bound["windows"]:
        if row["calendar_bound"]:
            print(
                f"    {row['window']} pin {row['pin']}: "
                f"{'past the last bar' if row['pin_after_last_bar'] else ''}"
                f"{' and ' if row['pin_after_last_bar'] and row['pin_before_first_bar'] else ''}"
                f"{'before the first bar' if row['pin_before_first_bar'] else ''}"
            )
    print_hit_table(
        "long window hit verdicts (measured before any oracle call):", long_block["hit"]
    )
    print(
        f"  unhit long windows: {long_block['n_unhit']} "
        f"(long threshold is {LONG_MIN_MOVE_PCT:.1f}%)"
    )
    print("")

    payload: dict[str, Any] = {
        "issue": 4804,
        "plan": 21,
        "task": 3,
        "kind": "gold-long-first-period-ladder",
        "mode": "long-first",
        "symbol": SYMBOL,
        "data_path": str(DATA_PATH),
        "data_sha256": sha256(DATA_PATH),
        "source_sha256": {path.name: sha256(path) for path in SOURCES},
        "calendar": {
            "first": dates[0].isoformat(),
            "last": dates[-1].isoformat(),
            "bars": len(dates),
        },
        "ceiling_label": LONG_FIRST_CEILING_LABEL,
        "objective_label": OBJECTIVE_LABEL,
        "risk_conventions_label": RISK_FREE_LABEL,
        "model_label": LONG_FIRST_MODEL_LABEL,
        "holdout_note": HOLDOUT_NOTE,
        "exposure_floor_pct": EXPOSURE_FLOOR_PCT,
        "floor_note": "the time-in-market floor is NEVER relaxed in this run",
        "initial_cash": DEFAULT_INITIAL_CASH,
        "long_selection": long_block,
        "split": SPLIT,
    }

    if not selection.selected:
        print(f"PURE LONG: NONE — {selection.reason}")
        print(
            "  no long-term window set exists for this series, so there is no ladder; "
            "nothing is substituted to fill the gap"
        )
        payload["pure_long"] = None
        payload["overlay"] = None
        payload["exposure_trajectory"] = []
        payload["kept_set"] = None
        payload["comparators"] = comparators(prices, DEFAULT_INITIAL_CASH)
        payload["split_sample"] = long_first_split_sample(
            dates, prices, split=SPLIT, max_peak_days_pct=MAX_PEAK_DAYS_PCT
        )
        LADDER_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LADDER_OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
        print(LONG_FIRST_CEILING_LABEL)
        print(f"wrote {LADDER_OUT_PATH}")
        return 0

    medium = discover_candidate_periods(dates, prices, horizon_by_name("medium"))
    print(
        f"MEDIUM CANDIDATES: {len(medium)} derived set(s) from the medium grid "
        f"(widths {[candidate.half_width_days for candidate in medium]}); the ladder "
        "grades them one at a time, shortest window first"
    )
    print("")
    grade = grade_medium_overlay(
        dates,
        prices,
        selection.windows,
        medium,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        min_move_pct=MEDIUM_MIN_MOVE_PCT,
    )
    trajectory = exposure_trajectory(grade)

    pure_row = score_row(grade.baseline, label="pure_long")
    print("PURE LONG ORACLE (rung 0, the secular regime alone):")
    print_candidate_table("pure-long candidate row:", [pure_row])
    print(
        f"  eligible={grade.baseline.eligible}"
        + ("" if grade.baseline.eligible else f" | {grade.baseline.rejection}")
    )
    print("")

    print(
        "EXPOSURE TRAJECTORY (headline column — the whole point of the long-first "
        f"rebuild; floor {grade.exposure_floor_pct:.1f}% is never relaxed):"
    )
    print_trajectory("long-first ladder:", trajectory)
    print_ladder_details(grade)
    print(f"LADDER STOP: {grade.stop_reason or 'every rung was kept'}")
    print("")

    print(f"KEPT SET: {len(grade.kept_windows)} window(s)")
    print(
        f"  long {selection.n_peaks} peaks / {selection.n_troughs} troughs + "
        f"{sum(len(step.added) for step in grade.ladder)} kept medium window(s) "
        f"across {len(grade.ladder)} kept rung(s)"
    )
    for window in grade.kept_windows:
        origin = "long" if window.name.startswith("long_") else "medium"
        print(f"  {origin:>6} {window.kind} {window.start}..{window.end}  {window.name}")
    print("")

    comparator_rows = comparators(prices, DEFAULT_INITIAL_CASH)
    print("comparators on the same calendar (dca_metrics, risk_metrics conventions):")
    print_candidate_table(
        "lump / flat comparator table:",
        [comparator_rows[name] for name in ("lump_mark_to_market", "flat_dca_mark_to_market")],
    )

    split_block = long_first_split_sample(
        dates, prices, split=SPLIT, max_peak_days_pct=MAX_PEAK_DAYS_PCT
    )
    print(f"split-sample ({SPLIT:.0%} fit) — {SPLIT_DEFECT_NOTE}")
    if split_block.get("fit_absent_reason"):
        print(f"  fit half: {split_block['fit_absent_reason']}")
    else:
        fit_selection_block = split_block["fit_long_selection"]
        fit_ladder = split_block["fit_ladder"]
        fit_base = fit_ladder["fit_baseline"]
        print(
            f"  fit side {split_block['fit_days']} bars: long "
            f"{fit_selection_block['n_peaks']}p / {fit_selection_block['n_troughs']}t, "
            f"{fit_ladder['n_kept_rungs']} rung(s) kept of "
            f"{fit_ladder['n_medium_candidates_offered']} candidate(s) offered; pure-long@fit "
            f"sharpe {fmt_opt(fit_base['sharpe'], '.4f')} | exposure "
            f"{fmt_opt(fit_base['exposure_pct'], '.2f')}% | "
            f"{fit_base['rejection'] or 'eligible'}"
        )
        print(f"  fit ladder stop: {fit_ladder['stop_reason'] or 'every rung was kept'}")
        out_row = split_block["out_of_sample"]
        print(
            f"  unseen side {split_block['score_days']} bars: "
            f"{split_block['fit_kept_window_names']} -> sharpe "
            f"{fmt_opt(out_row['sharpe'], '.4f')} | exposure "
            f"{fmt_opt(out_row['exposure_pct'], '.2f')}% | acted dates "
            f"{split_block['acted_dates_out_of_sample']} | eligible="
            f"{split_block['out_of_sample_eligible']} | {out_row['rejection'] or 'eligible'}"
        )
    print("")

    print(LONG_FIRST_CEILING_LABEL)
    print(f"ceiling sentence: {CEILING_LABEL}")

    payload["pure_long"] = pure_row
    payload["pure_long_eligible"] = bool(grade.baseline.eligible)
    payload["pure_long_rejection"] = grade.baseline.rejection
    payload["medium_candidates"] = {
        "n_candidates": len(medium),
        "widths": [candidate.half_width_days for candidate in medium],
        "windows_per_candidate": [
            {"half_width_days": candidate.half_width_days, "windows": len(candidate.windows)}
            for candidate in medium
        ],
        "min_move_pct": MEDIUM_MIN_MOVE_PCT,
    }
    payload["overlay"] = {
        "exposure_floor_pct": grade.exposure_floor_pct,
        "min_move_pct": grade.min_move_pct,
        "baseline": score_row(grade.baseline, label="pure_long"),
        "steps": [
            {
                "index": step.index,
                "half_width_days": step.half_width_days,
                "added": [window.model_dump(mode="json") for window in step.added],
                "kept_windows": [window.model_dump(mode="json") for window in step.kept_windows],
                "hit": [hit.model_dump(mode="json") for hit in step.hit],
                "sharpe": step.sharpe,
                "calmar": _blanked_calmar(step.max_drawdown_pct, step.calmar),
                "cagr_pct": step.cagr_pct,
                "max_drawdown_pct": step.max_drawdown_pct,
                "exposure_pct": step.exposure_pct,
                "degenerate": step.degenerate,
                "kept": step.kept,
                "reason": step.reason,
            }
            for step in grade.steps
        ],
        "ladder_kept_indices": [step.index for step in grade.ladder],
        "stop_reason": grade.stop_reason,
        "exposure_floor_never_relaxed": True,
    }
    payload["exposure_trajectory"] = trajectory
    payload["kept_set"] = [window.model_dump(mode="json") for window in grade.kept_windows]
    payload["comparators"] = comparator_rows
    payload["split_sample"] = split_block

    LADDER_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LADDER_OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {LADDER_OUT_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--long-first",
        action="store_true",
        help=(
            "Plan 21 long-first mode: select the secular LONG set first, then grade MEDIUM "
            "windows onto it one rung at a time, and write .scratch/gold_period_ladder.json. "
            "Without this flag the Plan-20 every-swing-pivot ladder runs and writes "
            ".scratch/gold_period_optimization.json, unchanged."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.long_first:
        return long_first_ladder()
    return plan20_ladder()


def plan20_ladder() -> int:
    """The Plan-20 record: every-swing-pivot discovery on both horizons, combined."""
    dates, prices = load_closes(SYMBOL, DATA_PATH)
    header(SYMBOL, dates, DATA_PATH)

    horizon_blocks: dict[str, dict[str, Any]] = {}
    rank1_windows: dict[str, Sequence[Any]] = {}
    split_blocks: dict[str, dict[str, Any]] = {}
    fit_rank1_windows: dict[str, Sequence[Any]] = {}

    for name in ("medium", "long"):
        horizon = horizon_by_name(name)
        result, error = run_horizon(dates, prices, horizon, initial_cash=DEFAULT_INITIAL_CASH)
        block = horizon_payload(
            SYMBOL,
            horizon,
            result,
            error,
            dates=dates,
            prices=prices,
            initial_cash=DEFAULT_INITIAL_CASH,
        )
        horizon_blocks[name] = block

        rows = block["candidates"]
        print(grid_label(horizon))
        print_pivot_table(name, block["pivot_counts_per_width"])
        print_candidate_table(
            f"{name} candidate table (best-first under the frozen objective):", rows
        )
        print_selection(name, block)
        print(
            f"{name} exact-sharpe tie pairs (the only way Calmar can affect the order): "
            f"{block['exact_sharpe_tie_pairs']}"
        )
        print("")

        split = split_sample_check(dates, prices, horizon, split=SPLIT)
        split_blocks[name] = split_sample_payload(split)
        print(
            f"{name} split-sample ({SPLIT:.0%} fit): fit side {split.fit_days} bars -> "
            f"{(split_blocks[name]['fit_best'] or {}).get('label', 'NONE')} "
            f"({split_blocks[name]['fit_best_absent_reason'] or 'eligible'}); unseen side "
            f"{split.score_days} bars -> "
            f"{(split_blocks[name]['out_of_sample'] or {}).get('label', 'NONE')} "
            f"({split_blocks[name]['out_of_sample_absent_reason'] or 'eligible'}), "
            f"eligible={split.out_of_sample_eligible}"
        )
        if result is not None:
            top: PeriodScore | None = result.scores[0] if result.scores else None
            if result.best is not None:
                rank1_windows[name] = result.best.windows
            elif top is not None:
                rank1_windows[name] = top.windows

        # Diagnostic pair: the fit half's own rank-1 (floor-failing here) carried onto
        # the unseen half. This is the informative read when the floor leaves the
        # module's pair null, and it is labeled a diagnostic so it is never a selection.
        split_at = int(len(dates) * SPLIT)
        fit_result, fit_error = run_horizon(
            dates[:split_at], prices[:split_at], horizon, initial_cash=DEFAULT_INITIAL_CASH
        )
        fit_top: PeriodScore | None = (
            (fit_result.best or fit_result.scores[0])
            if fit_result is not None and (fit_result.best or fit_result.scores)
            else None
        )
        if fit_top is not None:
            fit_rank1_windows[name] = fit_top.windows
            fit_label = f"pm{fit_top.half_width_days}@fit"
            out_row = diagnostic_score(
                dates[split_at:],
                prices[split_at:],
                fit_top.windows,
                label=f"{fit_label}->unseen",
                half_width_days=fit_top.half_width_days,
                exposure_floor_pct=EXPOSURE_FLOOR_PCT,
                initial_cash=DEFAULT_INITIAL_CASH,
            )
            fit_row = score_row(fit_top, label=fit_label)
            fit_row["diagnostic"] = "NOT a selection: misses the frozen floor on the fit half."
            split_blocks[name]["diagnostic_pair"] = {
                "warning": (
                    "diagnostic only: neither side is a selection (both miss the frozen "
                    "floor). The pair exists so the out-of-sample read is visible instead "
                    "of null."
                ),
                "fit_rank1": fit_row,
                "out_of_sample": out_row,
                "out_of_sample_eligible": bool(out_row["eligible"]),
                "acted_dates_out_of_sample": (out_row["n_buy_dates"] or 0)
                + (out_row["n_sell_dates"] or 0),
            }
            print(
                f"  diagnostic pair (NOT a selection): fit rank1 {fit_label} -> unseen sharpe "
                f"{fmt_opt(out_row['sharpe'], '.4f')} | exposure "
                f"{fmt_opt(out_row['exposure_pct'], '.2f')}% | acted dates "
                f"{split_blocks[name]['diagnostic_pair']['acted_dates_out_of_sample']} | "
                f"{out_row['rejection'] or 'eligible'}"
            )
        elif fit_error:
            split_blocks[name]["diagnostic_pair"] = {"error": fit_error}
            print(f"  diagnostic pair unavailable: {fit_error}")
        print("")

    medium_windows = rank1_windows.get("medium", ())
    long_windows = rank1_windows.get("long", ())
    combined = combined_block(
        dates,
        prices,
        horizon_blocks["medium"]["candidates"],
        horizon_blocks["long"]["candidates"],
        medium_windows,
        long_windows,
        initial_cash=DEFAULT_INITIAL_CASH,
    )
    print("COMBINED (medium + long, long sells override medium buys):")
    print(
        f"  windows {combined['n_windows']} "
        f"({combined['n_peaks']} peaks / {combined['n_troughs']} troughs) from "
        f"{combined['inputs']['medium']} + {combined['inputs']['long']}"
    )
    print_candidate_table(
        "combined candidate table:",
        [combined["rank1_ineligible_diagnostic"]],
    )
    print_selection("combined", combined)
    print(combined["precedence"])
    print("")

    comparator_rows = comparators(prices, DEFAULT_INITIAL_CASH)
    print("comparators on the same calendar (dca_metrics, risk_metrics conventions):")
    print_candidate_table(
        "lump / flat comparator table:",
        [comparator_rows[name] for name in ("lump_mark_to_market", "flat_dca_mark_to_market")],
    )
    print(
        "read the ladder against these: an oracle ceiling may beat lump/flat and still be "
        "unachievable — the ceiling sentence above is the binding caveat."
    )
    print("")

    combined_split = (
        combined_split_sample(
            dates,
            prices,
            fit_rank1_windows.get("medium", ()),
            fit_rank1_windows.get("long", ()),
            split=SPLIT,
            initial_cash=DEFAULT_INITIAL_CASH,
        )
        if fit_rank1_windows.get("medium") and fit_rank1_windows.get("long")
        else {
            "note": "a fit half produced no candidate at all, so no combined pair exists",
            "out_of_sample": None,
            "out_of_sample_eligible": False,
        }
    )
    split_blocks["combined"] = combined_split
    print(
        "combined split-sample: fit side "
        f"{combined_split.get('fit_days')} bars / {combined_split.get('fit_windows')} windows "
        f"-> unseen side {(combined_split.get('out_of_sample') or {}).get('label', 'NONE')} "
        f"(sharpe "
        f"{fmt_opt((combined_split.get('out_of_sample') or {}).get('sharpe'), '.4f') or 'n/a'}"
        f", exposure "
        f"{fmt_opt((combined_split.get('out_of_sample') or {}).get('exposure_pct'), '.2f')}%), "
        f"eligible={combined_split.get('out_of_sample_eligible')}"
    )
    print("")
    print(CEILING_LABEL)

    payload = {
        "issue": 4804,
        "plan": 20,
        "task": 3,
        "kind": "gold-period-optimization",
        "symbol": SYMBOL,
        "data_path": str(DATA_PATH),
        "data_sha256": sha256(DATA_PATH),
        "source_sha256": {path.name: sha256(path) for path in SOURCES},
        "calendar": {
            "first": dates[0].isoformat(),
            "last": dates[-1].isoformat(),
            "bars": len(dates),
        },
        "ceiling_label": CEILING_LABEL,
        "objective_label": OBJECTIVE_LABEL,
        "risk_conventions_label": RISK_FREE_LABEL,
        "holdout_note": HOLDOUT_NOTE,
        "exposure_floor_pct": EXPOSURE_FLOOR_PCT,
        "initial_cash": DEFAULT_INITIAL_CASH,
        "split": SPLIT,
        "cross_grid_contest": False,
        "horizons": horizon_blocks,
        "combined": combined,
        "split_sample": split_blocks,
        "comparators": comparator_rows,
        "sharpe_tie_pairs": {
            name: horizon_blocks[name]["exact_sharpe_tie_pairs"] for name in horizon_blocks
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
