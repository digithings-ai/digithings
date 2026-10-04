#!/usr/bin/env python3
"""Fit the SDCA indicator weights against BOTH approved gold pin sets and compare (#4804).

Plan 22's last piece. Two gold cycle-window pin sets ship: ``gold_v1()`` (Set A,
six close-based pins the owner approved by hand) and ``gold_v2()`` (the 20
algorithmic turns at ``min_move_pct=15.0``). This script asks the same question of
both — "does this indicator read cheap inside the trough windows and rich inside
the peak windows?" — and reports the answer side by side.

**The frozen Plan-19 harness is IMPORTED, not restated, and not modified.**
``digiquant/scripts/fit_gold_indicators.py`` is loaded by file path (it is a
research script, not a package module — the same way
``run_gold_sensitivity_consolidation.py`` loads it) and its pipeline is run
twice through its own entry points: ``run_fit`` → ``run_selection`` →
``fits_payload`` / ``selection_payload``. So every knob stays in one place:

* the grids (``LEVEL_WINDOWS``, ``ROC_DAYS``, ``ROC_WINDOWS``, ``RSI_LENGTHS``,
  ``MACD_SPANS``, ``MACD_Z_WINDOWS``, ``SMA_BAND_WINDOWS``,
  ``SMA_BAND_MIN_SAMPLES``), the medium/long bands, the 0.06 dead zone, the
  signed ``mean(trough) - mean(peak)`` separation, the ``best_overall`` /
  ``best_medium`` / ``best_long`` reads, the ``keep``/``drop``/``degenerate_pass``
  verdicts, the anchor (``rolling_z`` 90d / z 1.0 at equal weight 1.0), the
  candidate pool and the greedy equal-weight rule;
* the capture bar (0.5), the dead zone and the capture test come from
  ``sensitivity_consolidate``, the same module and the same constants that chose
  ``gold_v2``'s granularity — so "captures" here means exactly what it meant there.

**Only the window set differs between the two runs.** Same series, same date
range, same staged sources, same grids, same bar, same rule. That makes the
comparison a controlled one, and it makes ``gold_v2`` a strict REFINEMENT of the
same target rather than a rival one: every ``gold_v1`` pin is inside a
``gold_v2`` window with the same kind (asserted in the spec file), so v2
interpolates the turns between Set A's picks rather than contradicting them.

**Two selection reads, kept apart on purpose.** The greedy equal-weight
selection is the frozen Plan-19 rule and runs on the harness's own
``best_overall`` (max SIGNED separation) exactly as the single-set run does —
that is why ``gold_v1``'s greedy keep list here is identical to the one the
single-set run writes. The capture read (which set the indicators fit better) is
Engine 2b's Ruling 2 read: the row that speaks for an indicator is the largest
``|separation|`` in its grid, ``direction`` is FITTED from that row's sign, and a
capture is ``|separation| >= 0.5`` and not degenerate. Both are reported per
indicator, because they answer different questions and can pick different rows.

**IN-SAMPLE, and partly a selected upper bound.** Every number here is fitted on
the same price history it is scored against: each row is a MAX over the frozen
grid, scored against windows derived from the very same series. Capture counts
and capture depths are therefore a partly-selected upper bound, not
out-of-sample evidence. Windows are a scoring target, not execution periods; there
is no exposure floor, no return, no Sharpe and no trade count anywhere here.

Usage (research venv + src on PYTHONPATH):

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_pin_set_fits.py

Writes ``digiquant/.scratch/gold_pin_set_fits.json`` and
``digiquant/.scratch/gold_pin_set_selection.json`` (both UNTRACKED). Touches
nothing outside ``.scratch/`` and reads nothing the two run scripts already read.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.sensitivity_consolidate import (
    CAPTURE_BAR,
    CAPTURE_RULE,
    DEGENERATE_MEAN_ABS,
    IndicatorCaptureRow,
    best_grid_row,
    captures_level,
    fitted_direction,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = DIGIQUANT_ROOT / "scripts" / "fit_gold_indicators.py"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_pin_set_fits.json"
SELECTION_OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_pin_set_selection.json"

SYMBOL = "GLD-USD"

# The frozen knobs, re-exported BY REFERENCE from the harness and the consolidation
# module. These lines are an alias, never a second copy: `is` identity is asserted
# in the spec file, so a restated literal fails instead of drifting silently.
_HARNESS_MODULE: ModuleType | None = None


def load_harness() -> ModuleType:
    """Load the frozen Plan-19 harness by file path. No module-level execution.

    A research script rather than a package module, so the sibling gold runner's
    by-path load is the pattern. Cached, so the identity re-exports below name one
    instance rather than a fresh copy per call.
    """
    global _HARNESS_MODULE
    if _HARNESS_MODULE is not None:
        return _HARNESS_MODULE
    spec = importlib.util.spec_from_file_location("fit_gold_indicators", HARNESS_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover — loader contract
        raise ImportError(f"cannot load the frozen harness at {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fit_gold_indicators", module)
    spec.loader.exec_module(module)
    _HARNESS_MODULE = module
    return module


_HARNESS = load_harness()

LEVEL_WINDOWS = _HARNESS.LEVEL_WINDOWS
ROC_DAYS = _HARNESS.ROC_DAYS
ROC_WINDOWS = _HARNESS.ROC_WINDOWS
RSI_LENGTHS = _HARNESS.RSI_LENGTHS
MACD_SPANS = _HARNESS.MACD_SPANS
MACD_Z_WINDOWS = _HARNESS.MACD_Z_WINDOWS
SMA_BAND_WINDOWS = _HARNESS.SMA_BAND_WINDOWS
SMA_BAND_MIN_SAMPLES = _HARNESS.SMA_BAND_MIN_SAMPLES
MEDIUM_WINDOW_MAX = _HARNESS.MEDIUM_WINDOW_MAX
LONG_WINDOW_MIN = _HARNESS.LONG_WINDOW_MIN
ANCHOR_NAME = _HARNESS.ANCHOR_NAME
EQUAL_WEIGHT = _HARNESS.EQUAL_WEIGHT

# The two approved gold pin sets, in report order. Each entry is the LABEL used
# throughout the artifacts plus the shipped factory it names.
PIN_SETS: tuple[tuple[str, str], ...] = (
    ("gold_v1", "SdcaCycleWindows.gold_v1()"),
    ("gold_v2", "SdcaCycleWindows.gold_v2()"),
)

IN_SAMPLE_LABEL = (
    "IN-SAMPLE: every number here is fitted on the SAME price history it is scored "
    "against. Each row is a MAX over the frozen grid, scored against cycle windows "
    "derived from that same series, so capture counts and capture depths are a "
    "PARTLY-SELECTED UPPER BOUND — not out-of-sample predictive skill and not a "
    "performance claim. Windows are a scoring target, not execution periods: no "
    "exposure floor, no return, no Sharpe, no trade count."
)

PIN_SET_LABEL = (
    "The two gold pin sets are comparable rather than competing: gold_v1() (Set A, "
    "six hand-approved close-based pins) is a PROPER SUBSET of gold_v2() (20 "
    "algorithmic turns at min_move_pct=15.0), same turns and same kinds. gold_v2 "
    "therefore REFINES the same target by interpolating the turns between Set A's "
    "picks — it is not a rival target, and a separation that moves between them is "
    "the granularity speaking, not a contradiction."
)

UPPER_BOUND_CAVEAT = (
    "UPPER-BOUND CAVEAT: every per-indicator row is the maximum over a frozen grid, "
    "scored against windows derived from the same price history the z-series are "
    "built from. The maximum is chosen knowing the scores, so the capture count and "
    "capture depth reported for each pin set are a partly-selected upper bound. Read "
    "them as 'the best this grid can do on its own history', never as out-of-sample "
    "evidence."
)

COMPARISON_RULE = (
    "WHICH SET FITS BETTER is decided by capture DEPTH, not headcount — the owner's "
    f"frozen ranking key ({CAPTURE_BAR} bar), applied across pin sets instead of "
    "across min_move_pct levels. depth = the summed |separation| of the capturing "
    "indicators. Headcount is reported beside it, never ranked on. A depth tie goes "
    "to the COARSER pin set (fewer windows, more robust), the same tie-break the "
    "granularity choice uses."
)


# --------------------------------------------------------------------------- #
# Pure reads (no price history — the spec file drives these on synthetic rows)
# --------------------------------------------------------------------------- #


class WindowDayShare(BaseModel):
    """How much of the calendar a pin set covers, in days rather than pins.

    ``overlap_days`` is reported because ``gold_v2()`` has two window pairs that
    overlap by ~30 days: ``kind_on`` resolves an overlapping day to the EARLIER
    pin, so the share counts such a day ONCE, under the earlier side. A share that
    summed window lengths would over-report gold_v2 and make the two sets look
    incomparable. ``overlap_days`` counts days inside MORE THAN ONE window, so it
    is exact whatever the overlap graph looks like.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    calendar_days: int = Field(ge=0)
    window_days: int = Field(ge=0)
    overlap_days: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)


def window_day_share(dates: Sequence[date], windows: SdcaCycleWindows) -> WindowDayShare:
    """Days inside ANY window, counted once each, over the scored calendar."""
    window_days = 0
    overlapped = 0
    for day in dates:
        covering = sum(1 for window in windows.windows if window.contains(day))
        if covering:
            window_days += 1
        if covering > 1:
            overlapped += 1
    calendar_days = len(dates)
    return WindowDayShare(
        calendar_days=calendar_days,
        window_days=window_days,
        overlap_days=overlapped,
        share=window_days / calendar_days if calendar_days else 0.0,
    )


def pin_set(label: str) -> SdcaCycleWindows:
    """The shipped factory for one approved gold pin-set label."""
    factories = {
        "gold_v1": SdcaCycleWindows.gold_v1,
        "gold_v2": SdcaCycleWindows.gold_v2,
    }
    if label not in factories:
        raise KeyError(f"no approved gold pin set named {label!r}; have {sorted(factories)}")
    return factories[label]()


class IndicatorRead(BaseModel):
    """One indicator's capture read against one pin set (Engine 2b Ruling 2).

    ``separation`` is the SIGNED separation of the row that speaks for this
    indicator — the largest ``|separation|`` in its frozen grid, ties to the
    shorter window — and ``direction`` is FITTED from its sign (``+1`` expected
    polarity, ``-1`` inverted). ``captures`` is that row's frozen capture verdict:
    ``|separation| >= CAPTURE_BAR`` and not degenerate. An unscoreable leg has
    ``separation``/``direction`` ``None`` and never captures.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    params: dict[str, int]
    window_days: int = Field(ge=2)
    separation: float | None
    abs_separation: float = Field(ge=0.0)
    direction: int | None
    mean_peak_z: float | None
    mean_trough_z: float | None
    degenerate: bool
    captures: bool
    coverage: float = Field(ge=0.0, le=1.0)
    scored_days: int = Field(ge=0)
    status: str
    reason: str | None


def capture_read(name: str, rows: Sequence[IndicatorCaptureRow]) -> IndicatorRead:
    """The capture read for one indicator, from its whole scored grid."""
    row = best_grid_row(list(rows))
    captures = captures_level(row)
    separation = row.separation
    return IndicatorRead(
        name=name,
        params=dict(row.params),
        window_days=row.window_days,
        separation=separation,
        abs_separation=abs(separation) if separation is not None else 0.0,
        direction=fitted_direction(separation),
        mean_peak_z=row.mean_peak_z,
        mean_trough_z=row.mean_trough_z,
        degenerate=row.degenerate,
        captures=captures,
        coverage=row.coverage,
        scored_days=row.scored_days,
        status=row.status,
        reason=row.reason,
    )


class CaptureSummary(BaseModel):
    """One pin set's capture count / depth / sign mix, on the frozen bar.

    ``capture_depth`` sums ``|separation|`` over CAPTURING legs only, regardless
    of direction — a mirrored leg that clears the bar contributes its magnitude
    (Engine 2b Ruling 2). ``non_capturing`` names the rest, so a summary can never
    hide a leg it declined to count.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    capture_count: int = Field(ge=0)
    capture_depth: float = Field(ge=0.0)
    expected_sign_count: int = Field(ge=0)
    inverted_sign_count: int = Field(ge=0)
    capturing: tuple[str, ...]
    non_capturing: tuple[str, ...]


def capture_summary(reads: Sequence[IndicatorRead]) -> CaptureSummary:
    """Count and depth over the capturing reads, plus the sign mix."""
    capturing = [read for read in reads if read.captures]
    return CaptureSummary(
        capture_count=len(capturing),
        capture_depth=sum(read.abs_separation for read in capturing),
        expected_sign_count=sum(1 for read in capturing if read.direction == 1),
        inverted_sign_count=sum(1 for read in capturing if read.direction == -1),
        capturing=tuple(read.name for read in capturing),
        non_capturing=tuple(read.name for read in reads if not read.captures),
    )


class BetterVerdict(BaseModel):
    """Which pin set the indicators fit better, and by how much."""

    model_config = ConfigDict(frozen=True, strict=True)

    better_label: str
    tied: bool
    depth_margin: float
    count_margin: int
    reason: str


def fits_better(
    first: tuple[str, CaptureSummary],
    second: tuple[str, CaptureSummary],
) -> BetterVerdict:
    """Depth decides; the coarser pin set takes a tie. Ranks ``second`` against ``first``.

    ``first`` is the reference and ``second`` is the challenger, so ``depth_margin``
    is ``second - first``. Depth is a float, so an exact tie is common when two
    sets capture the same legs; the tie is not a rounding artefact and is broken by
    pin count (fewer windows wins), then by label so the verdict is deterministic.
    """
    label_a, summary_a = first
    label_b, summary_b = second
    if summary_b.capture_depth > summary_a.capture_depth:
        return BetterVerdict(
            better_label=label_b,
            tied=False,
            depth_margin=summary_b.capture_depth - summary_a.capture_depth,
            count_margin=summary_b.capture_count - summary_a.capture_count,
            reason=(
                f"capture_depth {summary_b.capture_depth:.4f} > {summary_a.capture_depth:.4f} "
                f"(+{summary_b.capture_depth - summary_a.capture_depth:.4f}); depth is the "
                "ranking key, headcount is reported only"
            ),
        )
    if summary_b.capture_depth < summary_a.capture_depth:
        return BetterVerdict(
            better_label=label_a,
            tied=False,
            depth_margin=summary_b.capture_depth - summary_a.capture_depth,
            count_margin=summary_b.capture_count - summary_a.capture_count,
            reason=(
                f"capture_depth {summary_b.capture_depth:.4f} < {summary_a.capture_depth:.4f} "
                f"({summary_b.capture_depth - summary_a.capture_depth:+.4f}); depth is the "
                "ranking key, headcount is reported only"
            ),
        )
    counts = {label_a: len(pin_set(label_a).windows), label_b: len(pin_set(label_b).windows)}
    winner = min((label_a, label_b), key=lambda label: (counts[label], label))
    return BetterVerdict(
        better_label=winner,
        tied=True,
        depth_margin=0.0,
        count_margin=summary_b.capture_count - summary_a.capture_count,
        reason=(
            f"capture_depth tied at {summary_a.capture_depth:.4f}; the coarser pin set wins "
            f"({counts[label_a]} vs {counts[label_b]} windows) — same tie-break the "
            "granularity choice uses"
        ),
    )


class ComparisonRow(BaseModel):
    """One indicator, read against both pin sets, in the frozen indicator order."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    by_set: dict[str, IndicatorRead]
    captures_by_set: dict[str, bool]
    direction_by_set: dict[str, int | None]
    flipped: bool


def comparison_rows(sets: Mapping[str, Mapping[str, IndicatorRead]]) -> tuple[ComparisonRow, ...]:
    """The comparison table: every fitted indicator, read against every pin set.

    A missing indicator on either side is an ERROR, never a blank cell — a silent
    gap in a comparison table is exactly how a flipped verdict goes unread. Order
    follows the harness's frozen ``FITTED_INDICATORS``, so the table does not move
    when a dict does.
    """
    labels = list(sets)
    names: list[str] = []
    for label in labels:
        for name in sets[label]:
            if name not in names:
                names.append(name)
    ordered = [name for name in _HARNESS.FITTED_INDICATORS if name in names]
    ordered += [name for name in names if name not in ordered]
    rows: list[ComparisonRow] = []
    for name in ordered:
        by_set: dict[str, IndicatorRead] = {}
        for label in labels:
            read = sets[label].get(name)
            if read is None:
                raise ValueError(
                    f"{name!r} has no read against {label!r} — a comparison row that cannot "
                    "be filled is an error, not a blank cell"
                )
            by_set[label] = read
        rows.append(
            ComparisonRow(
                name=name,
                by_set=by_set,
                captures_by_set={label: read.captures for label, read in by_set.items()},
                direction_by_set={label: read.direction for label, read in by_set.items()},
                flipped=len(set(row_captures(by_set, labels))) > 1
                or len({by_set[label].direction for label in labels}) > 1,
            )
        )
    return tuple(rows)


def row_captures(by_set: Mapping[str, IndicatorRead], labels: Sequence[str]) -> list[bool]:
    """The capture verdict of one row across the pin sets, in label order."""
    return [by_set[label].captures for label in labels]


def verdict_flips(sets: Mapping[str, Mapping[str, IndicatorRead]]) -> list[dict[str, Any]]:
    """Indicators whose capture VERDICT or fitted DIRECTION changed between sets.

    A separation that merely moved is not a flip. A flip is a change of what the
    owner would have to decide: does this leg capture, and which way does it vote.
    """
    rows = comparison_rows(sets)
    flips: list[dict[str, Any]] = []
    for row in rows:
        changes: list[str] = []
        if len(set(row.captures_by_set.values())) > 1:
            changes.append("captures")
        if len(set(row.direction_by_set.values())) > 1:
            changes.append("direction")
        if not changes:
            continue
        first, last = list(row.by_set)[0], list(row.by_set)[-1]
        flips.append(
            {
                "name": row.name,
                "changes": changes,
                f"{first}_separation": row.by_set[first].separation,
                f"{last}_separation": row.by_set[last].separation,
                f"{first}_direction": row.by_set[first].direction,
                f"{last}_direction": row.by_set[last].direction,
                f"{first}_captures": row.by_set[first].captures,
                f"{last}_captures": row.by_set[last].captures,
            }
        )
    return flips


# --------------------------------------------------------------------------- #
# The run: the frozen harness, twice
# --------------------------------------------------------------------------- #


def capture_rows_for(name: str, fit: Any) -> tuple[IndicatorCaptureRow, ...]:
    """The harness's whole grid for one indicator, as capture rows.

    EVERY row is handed over, not just ``best_overall``: the capture read selects
    on ``|separation|`` while the harness selects on the signed value, so passing
    only the harness's winner would silently re-impose the old polarity rule here.
    """
    grid_rows = list(fit.rows)
    if not grid_rows:
        raise ValueError(
            f"{name!r} fit returned no grid rows — the frozen harness populates them on "
            "every path, so this is a broken harness, not an indicator with nothing to say"
        )
    return tuple(
        IndicatorCaptureRow(
            name=name,
            params=dict(row.params),
            window_days=row.window_days,
            separation=row.separation,
            mean_peak_z=row.mean_peak_z,
            mean_trough_z=row.mean_trough_z,
            peak_negative_share=row.peak_negative_share,
            trough_positive_share=row.trough_positive_share,
            zero_z_share=row.zero_z_share,
            degenerate=row.degenerate,
            coverage=row.coverage,
            scored_days=row.scored_days,
            status=fit.status,
            reason=row.reason or fit.reason,
        )
        for row in grid_rows
    )


class PinSetFit(BaseModel):
    """Everything one pin set's run produced."""

    model_config = ConfigDict(frozen=True, strict=True)

    label: str
    factory: str
    windows_label: str
    pins: int = Field(ge=0)
    peaks: int = Field(ge=0)
    troughs: int = Field(ge=0)
    coverage: WindowDayShare
    fits: dict[str, Any]
    reads: dict[str, IndicatorRead]
    summary: CaptureSummary
    anchor_separation: float | None
    greedy_kept: tuple[str, ...]
    greedy_dropped: tuple[str, ...]
    greedy_final_separation: float | None


def run_pin_set(
    label: str,
    factory_label: str,
    dates: Sequence[date],
    date_s: pl.Series,
    price_s: pl.Series,
    sources: Any,
) -> tuple[PinSetFit, Any]:
    """Run the ENTIRE frozen pipeline once, against one pin set.

    Returns the run plus the harness's ``SelectionOutcome``, because the selection
    artifact is built from the outcome rather than from the run alone.
    """
    windows = pin_set(label)
    windows_label = f"{factory_label} ±45d"
    fits = _HARNESS.run_fit(dates, date_s, price_s, sources, windows)
    reads = {name: capture_read(name, capture_rows_for(name, fit)) for name, fit in fits.items()}
    outcome = _HARNESS.run_selection(dates, date_s, price_s, sources, windows, fits)
    return PinSetFit(
        label=label,
        factory=factory_label,
        windows_label=windows_label,
        pins=len(windows.windows),
        peaks=len(windows.peaks()),
        troughs=len(windows.troughs()),
        coverage=window_day_share(dates, windows),
        fits=fits,
        reads=reads,
        summary=capture_summary(tuple(reads.values())),
        anchor_separation=outcome.run.anchor_separation,
        greedy_kept=outcome.run.kept,
        greedy_dropped=outcome.run.dropped,
        greedy_final_separation=outcome.run.final_separation,
    ), outcome


def fits_payload_for(run: PinSetFit, dates: Sequence[date]) -> dict[str, Any]:
    """The harness's own fits artifact for this pin set, verbatim."""
    return _HARNESS.fits_payload(dates, run.fits, windows_label=run.windows_label)


def selection_payload_for(
    run: PinSetFit,
    dates: Sequence[date],
    outcome: Any,
) -> dict[str, Any]:
    """The harness's own selection artifact for this pin set, verbatim."""
    return _HARNESS.selection_payload(dates, run.fits, outcome, windows_label=run.windows_label)


# --------------------------------------------------------------------------- #
# Report + CLI
# --------------------------------------------------------------------------- #


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


def _params_text(params: Mapping[str, int]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(params.items()))


def _direction(value: int | None) -> str:
    return "—" if value is None else f"{value:+d}"


def _capture(value: bool) -> str:
    return "Y" if value else "."


def print_comparison(
    runs: Sequence[PinSetFit],
    rows: Sequence[ComparisonRow],
    flips: Sequence[Mapping[str, Any]],
    verdict: BetterVerdict,
) -> None:
    """The owner's table: one row per indicator, both pin sets, then the summary."""
    labels = [run.label for run in runs]
    first, second = labels[0], labels[1]
    print("")
    print("GOLD INDICATOR FITS — BOTH APPROVED PIN SETS, SIDE BY SIDE")
    print(
        f"{'indicator':<14} {'sep@' + first:>10} {'dir':>4} {'cap':>4} "
        f"{'sep@' + second:>10} {'dir':>4} {'cap':>4} {'w1/w2':>10}  "
        f"params@{first} | params@{second}"
    )
    for row in rows:
        read_a = row.by_set[first]
        read_b = row.by_set[second]
        print(
            f"{row.name:<14} {_signed(read_a.separation):>10} "
            f"{_direction(read_a.direction):>4} {_capture(read_a.captures):>4} "
            f"{_signed(read_b.separation):>10} {_direction(read_b.direction):>4} "
            f"{_capture(read_b.captures):>4} "
            f"{read_a.window_days:>4}/{read_b.window_days:<5}  "
            f"{_params_text(read_a.params)} | {_params_text(read_b.params)}"
            f"{'  DEGENERATE' if read_a.degenerate or read_b.degenerate else ''}"
        )
        print(
            f"{'':<14} mean peak/trough z {_signed(read_a.mean_peak_z)}/"
            f"{_signed(read_a.mean_trough_z)} | {_signed(read_b.mean_peak_z)}/"
            f"{_signed(read_b.mean_trough_z)}"
        )
    print("")
    for run in runs:
        print(
            f"{run.label}: {run.pins} pins ({run.peaks} peak / {run.troughs} trough), "
            f"window-day share {run.coverage.share:.4f} "
            f"({run.coverage.window_days}/{run.coverage.calendar_days} days, "
            f"{run.coverage.overlap_days} overlapping), "
            f"anchor separation {_signed(run.anchor_separation)}"
        )
        print(
            f"  captures {run.summary.capture_count} {list(run.summary.capturing)} | "
            f"depth {run.summary.capture_depth:.4f} | "
            f"sign mix {run.summary.expected_sign_count}+/"
            f"{run.summary.inverted_sign_count}- | "
            f"greedy kept {list(run.greedy_kept)} | final {_signed(run.greedy_final_separation)}"
        )
    print("")
    print(f"VERDICT: {verdict.better_label} fits better — {verdict.reason}")
    print(f"flips: {[entry['name'] for entry in flips] or 'none'}")
    for entry in flips:
        print(
            f"  {entry['name']}: {' + '.join(entry['changes'])} "
            f"({list(labels)} separation {_signed(entry[f'{labels[0]}_separation'])} -> "
            f"{_signed(entry[f'{labels[1]}_separation'])})"
        )
    print("")
    print(PIN_SET_LABEL)
    print("")
    print(COMPARISON_RULE)
    print("")
    print(f"capture bar {CAPTURE_BAR} z-units, dead zone +/-{DEGENERATE_MEAN_ABS} (frozen)")
    print(CAPTURE_RULE)
    print("")
    print(UPPER_BOUND_CAVEAT)
    print("")
    print(IN_SAMPLE_LABEL)


def main() -> int:
    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    print(f"capture bar {CAPTURE_BAR} z-units, dead zone +/-{DEGENERATE_MEAN_ABS} (frozen)")

    runs: list[PinSetFit] = []
    outcomes: dict[str, Any] = {}
    for label, factory_label in PIN_SETS:
        print(f"fitting {label} ({factory_label}) …", flush=True)
        run, outcome = run_pin_set(label, factory_label, dates, date_s, price_s, sources)
        runs.append(run)
        outcomes[label] = outcome
        print(
            f"  {run.pins} pins, share {run.coverage.share:.4f}, captures "
            f"{run.summary.capture_count}, depth {run.summary.capture_depth:.4f}, "
            f"greedy kept {list(run.greedy_kept)}"
        )

    sets = {run.label: run.reads for run in runs}
    rows = comparison_rows(sets)
    flips = verdict_flips(sets)
    verdict = fits_better((runs[0].label, runs[0].summary), (runs[1].label, runs[1].summary))
    print_comparison(runs, rows, flips, verdict)

    shared = {
        "symbol": SYMBOL,
        "calendar": f"{dates[0]}..{dates[-1]} ({len(dates)} daily bars)",
        "metric": _HARNESS.METRIC_DEFINITION,
        "metric_read": _HARNESS.METRIC_READ,
        "in_sample": True,
        "in_sample_label": IN_SAMPLE_LABEL,
        "upper_bound_caveat": UPPER_BOUND_CAVEAT,
        "pin_set_label": PIN_SET_LABEL,
        "comparison_rule": COMPARISON_RULE,
        "capture_bar": CAPTURE_BAR,
        "capture_rule": CAPTURE_RULE,
        "degenerate_mean_abs": DEGENERATE_MEAN_ABS,
        "frozen_knobs": {
            "grids": {
                "level_z_windows": list(LEVEL_WINDOWS),
                "roc_days": list(ROC_DAYS),
                "roc_windows": list(ROC_WINDOWS),
                "rsi_lengths": list(RSI_LENGTHS),
                "macd_spans": [list(span) for span in MACD_SPANS],
                "macd_z_windows": list(MACD_Z_WINDOWS),
                "sma_band_windows": list(SMA_BAND_WINDOWS),
                "sma_band_min_samples": list(SMA_BAND_MIN_SAMPLES),
            },
            "medium_band": f"window_days <= {MEDIUM_WINDOW_MAX}",
            "long_band": f"window_days >= {LONG_WINDOW_MIN}",
            "anchor": f"{ANCHOR_NAME} = rolling_z 90d / z 1.0 at equal weight {EQUAL_WEIGHT}",
            "source": (
                "every grid, band and anchor constant is re-exported BY REFERENCE from "
                "digiquant/scripts/fit_gold_indicators.py; the bar and dead zone come from "
                "digiquant.strategies.sdca.sensitivity_consolidate. Only the WINDOW SET "
                "differs between the two runs."
            ),
        },
        "sets": {
            run.label: {
                "factory": run.factory,
                "windows": run.windows_label,
                "pins": run.pins,
                "peaks": run.peaks,
                "troughs": run.troughs,
                "window_day_share": run.coverage.share,
                "window_days": run.coverage.window_days,
                "overlap_days": run.coverage.overlap_days,
                "capture_count": run.summary.capture_count,
                "capture_depth": run.summary.capture_depth,
                "sign_mix": {
                    "expected": run.summary.expected_sign_count,
                    "inverted": run.summary.inverted_sign_count,
                },
                "capturing": list(run.summary.capturing),
                "non_capturing": list(run.summary.non_capturing),
                "anchor_separation": run.anchor_separation,
                "greedy_kept": list(run.greedy_kept),
                "greedy_dropped": list(run.greedy_dropped),
                "greedy_final_separation": run.greedy_final_separation,
                "indicator_reads": {
                    name: read.model_dump(mode="json") for name, read in run.reads.items()
                },
                # The harness's OWN artifact for this pin set, nested verbatim.
                "fits": fits_payload_for(run, dates),
            }
            for run in runs
        },
        "comparison": {
            "rows": [
                {
                    "name": row.name,
                    "by_set": {
                        label: read.model_dump(mode="json") for label, read in row.by_set.items()
                    },
                    "captures_by_set": row.captures_by_set,
                    "direction_by_set": row.direction_by_set,
                    "flipped": row.flipped,
                }
                for row in rows
            ],
            "flips": flips,
            "verdict": verdict.model_dump(mode="json"),
        },
    }

    selection = {key: value for key, value in shared.items() if key != "sets"} | {
        "sets": {
            run.label: {
                "factory": run.factory,
                "windows": run.windows_label,
                "pins": run.pins,
                "greedy_kept": list(run.greedy_kept),
                "greedy_dropped": list(run.greedy_dropped),
                # The harness's OWN selection artifact for this pin set, verbatim.
                "selection": selection_payload_for(run, dates, outcomes[run.label]),
            }
            for run in runs
        }
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(shared, indent=2) + "\n")
    SELECTION_OUT_PATH.write_text(json.dumps(selection, indent=2) + "\n")
    print(f"wrote {OUT_PATH}")
    print(f"wrote {SELECTION_OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
