#!/usr/bin/env python3
"""Gold (GLD) per-indicator z-window fitting — Plan-19 Task 1 harness (#4804).

Research-only. ZERO production edits: every z-series below comes from a SHIPPED
function in ``indicator_catalog`` / ``price_oscillators``, called with a
parameter. This harness never restates indicator math — it only sweeps the
frozen grids and scores them.

**Frozen fit metric (Plan-19 Ruling 1 — the pre-registration sign was a
CORRECTNESS BUG, corrected here):**
``separation = mean(z | trough windows) - mean(z | peak windows)``; higher is
better, and **positive = the z votes CHEAP at bottoms**. That is the convention
every shipped z already uses: ``composite_risk.py:57`` maps ``risk =
50 - composite_z*50/3`` so ``+z`` = buy = cheap, and the shipped Stage-A
objective ``stage_a.py:88-99`` (``mean_risk(peaks) - mean_risk(troughs)``) is
algebraically ``+(50/3) * separation``. ``abs()`` is FORBIDDEN anywhere on this
metric: it would reward a leg that votes backwards. Every bar with a valid z is
IN-SAMPLE: this fits windows to the pinned ``SdcaCycleWindows.gold_v1()``
history, it does not measure out-of-sample skill. The holdout stays spent and
untouched.

**Shares and the degenerate gate (Ruling 1):** the two shares
(``peak_negative_share``, ``trough_positive_share``) are counted off the RAW z
vectors, per side. The old single ``sign_share`` aggregate is not recoverable
from them as ``1 - x`` — a dead-zone oscillator sits at exactly ``0.0``, which
would read as perfect agreement it never cast — so ``zero_z_share`` is recorded
beside them. A row is ``degenerate`` when ONE side's window mean never leaves
the ±``DEGENERATE_MEAN_ABS`` dead zone (its pass then rests on the other side
alone); an indicator whose every scored row is degenerate AND whose best
separation is strictly positive is a ``degenerate_pass`` — listed separately,
never in a keep list without an explicit owner look.

**Frozen grids (plan header):**

* level-z legs (``uup``, ``real_rate``, ``gvz``, ``hy_oas``, ``ig_oas``,
  ``breakeven_5y``, ``nfci``, ``gdx_gld``, ``gld_slv``): ``window`` ∈
  {90, 180, 270, 378, 504, 756, 1260} (7 rows). ``min_samples`` is NOT swept —
  it stays at the shipped default (20) so the only varying input is the frozen
  window.
* growth legs (``m2``, ``walcl``): ``roc_days`` ∈ {90, 180, 365, 730} ×
  ``window`` ∈ {180, 378, 756, 1260} (16 rows).
* oscillators: ``rsi_length`` ∈ {14, 21} (2 rows); MACD fast/slow ∈
  {(12, 26), (8, 34)} × ``macd_z_window`` ∈ {90, 378} (4 rows); ``sma_band``
  ``window`` ∈ {200, 378, 1000} × ``min_samples`` ∈ {30, 60} (6 rows).

**VERIFIED against ``price_oscillators.py`` / ``SdcaOscillatorSpec``** (read
before writing this file — the plan's named oscillator sets were guesses):

* The spec fields are ``rsi_length``, ``macd_fast``, ``macd_slow``,
  ``macd_signal``, ``macd_z_window``, ``sma_band_window``,
  ``sma_band_min_samples``. There is **no band multiple ``k``** — recorded
  DEVIATION: the plan's ``sma_band k ∈ {2, 3}`` is impossible against the
  shipped fields, so the second dimension is swept over the closest VERIFIED
  analogue ``sma_band_min_samples`` (the shipped default 30 and one longer
  warm-up 60). The catalog was NOT extended.
* ``weekly_macd_z`` opens with ``del signal, z_window, min_samples`` — the
  shipped log-MACD is a sloped-top-cap map, not a windowed histogram z, so
  ``macd_z_window`` (and ``macd_signal``) are INERT parameters. The frozen
  4-row MACD grid is kept verbatim for completeness, but rows differing only in
  ``macd_z_window`` produce byte-identical z and the tie-break (shorter window)
  resolves them to 90.
* ``weekly_rsi`` / ``mtf_rsi_z`` expose no window knob beyond ``rsi_length``,
  so its two rows differ only there. Each grid point carries a ``window_days``
  key — the one number the frozen medium/long split is read from — which for
  RSI is the spec's own documented calendar footprint
  ``(rsi_length + 1) * 7`` days (``documented_warmup_calendar_days``), and for
  every other leg is the z ``window`` itself.
* Tie-break: higher ``separation`` first (highest corrected = votes cheapest at
  the pinned bottoms), then the SHORTER window (parsimony). Medium read = best
  row with ``window_days`` ≤ 378; long read = best row with ``window_days``
  ≥ 504. Both are reported per indicator; a band with no row is ``null`` (never
  a guess).
* Unscoreable legs (the staged ``hy_oas``/``ig_oas`` CSVs start 2023-09-30 while
  the last ``gold_v1`` trough window ends 2022-12-05, so they only ever see the
  current-top window) come back with ``status="unscoreable"`` and a REASON —
  listed, not silently skipped.

``dxy`` is deliberately absent from ``FITTED_INDICATORS``: the plan's frozen
architecture line enumerates the z-functions to fit and names ``uup_z``, not
``dxy_z`` (``uup_z``'s own docstring calls the leg "a refreshability swap for
the unstageable DTWEXBGS file, not a new independent vote").

Usage (research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/fit_gold_indicators.py --fit

Writes ``digiquant/.scratch/gold_indicator_fits.json`` (UNTRACKED). Touches
nothing outside ``.scratch/``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import date
from itertools import product
from pathlib import Path
from typing import Any, Callable

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    ExtraIndicatorSources,
    breakeven_5y_z,
    gdx_gld_z,
    gld_slv_z,
    gvz_z,
    hy_oas_z,
    ig_oas_z,
    m2_liquidity_z,
    nfci_z,
    real_rate_z,
    uup_z,
    walcl_liquidity_z,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    documented_warmup_calendar_days,
    price_oscillator_z_vectors,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_fits.json"

SYMBOL = "GLD-USD"

# --------------------------------------------------------------------------- #
# Frozen grids (plan header — do not edit without a plan change)
# --------------------------------------------------------------------------- #

LEVEL_WINDOWS: tuple[int, ...] = (90, 180, 270, 378, 504, 756, 1260)
ROC_DAYS: tuple[int, ...] = (90, 180, 365, 730)
ROC_WINDOWS: tuple[int, ...] = (180, 378, 756, 1260)
RSI_LENGTHS: tuple[int, ...] = (14, 21)
MACD_SPANS: tuple[tuple[int, int], ...] = ((12, 26), (8, 34))
MACD_Z_WINDOWS: tuple[int, ...] = (90, 378)
SMA_BAND_WINDOWS: tuple[int, ...] = (200, 378, 1000)
# VERIFIED analogue of the plan's `k ∈ {2, 3}` (no band multiple in the spec).
SMA_BAND_MIN_SAMPLES: tuple[int, ...] = (30, 60)

MEDIUM_WINDOW_MAX = 378
LONG_WINDOW_MIN = 504

# Ruling 1: a window-side mean inside +/- this band is a DEAD ZONE — the z has no
# opinion there, so a positive separation resting on it is one-sided.
DEGENERATE_MEAN_ABS = 0.06

METRIC_DEFINITION = (
    "separation = mean(z | trough windows) - mean(z | peak windows); "
    "positive = votes cheap at bottoms (composite_risk.py:57 maps +z to buy)"
)
METRIC_READ = (
    "higher is better; positive = the z runs HIGHER in the pinned trough windows "
    "and LOWER in the pinned peak windows, i.e. it votes cheap at bottoms; "
    "abs() is never applied to this metric"
)
DEGENERATE_LABEL = (
    f"DEGENERATE: a grid row is degenerate when one side's window mean never "
    f"leaves the +/-{DEGENERATE_MEAN_ABS} dead zone (pass rests on the other side "
    f"alone); an indicator is degenerate_pass when EVERY scored row is degenerate "
    f"and its best separation is strictly positive. Degenerate legs are listed "
    f"separately and never enter a keep list without an explicit owner look."
)

IN_SAMPLE_LABEL = (
    "IN-SAMPLE: separation is fit against the same pinned gold_v1 windows it is "
    "measured on (every bar with a valid z) — it calibrates indicator windows to "
    "pinned history and is NOT out-of-sample predictive skill; the holdout stays "
    "spent and untouched."
)

# --------------------------------------------------------------------------- #
# Indicator registry — which shipped z-function backs each wired name
# --------------------------------------------------------------------------- #

# Level-z legs: z(dates, src_dates, src_values, *, window=...)
_LEVEL_Z: dict[str, Callable[..., pl.Series]] = {
    "uup": uup_z,
    "real_rate": real_rate_z,
    "gvz": gvz_z,
    "hy_oas": hy_oas_z,
    "ig_oas": ig_oas_z,
    "breakeven_5y": breakeven_5y_z,
    "nfci": nfci_z,
}
# Ratio legs: z(dates, gld_price, src_dates, src_close, *, window=...)
_RATIO_Z: dict[str, Callable[..., pl.Series]] = {
    "gdx_gld": gdx_gld_z,
    "gld_slv": gld_slv_z,
}
# Growth legs: z(dates, src_dates, src_values, *, roc_days=, window=...)
_ROC_Z: dict[str, Callable[..., pl.Series]] = {
    "m2": m2_liquidity_z,
    "walcl": walcl_liquidity_z,
}
_OSCILLATORS: tuple[str, ...] = ("weekly_rsi", "weekly_macd", "sma_band")

FITTED_INDICATORS: tuple[str, ...] = (
    "uup",
    "real_rate",
    "gvz",
    "hy_oas",
    "ig_oas",
    "breakeven_5y",
    "nfci",
    "gdx_gld",
    "gld_slv",
    "m2",
    "walcl",
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
)

# ExtraIndicatorSources field pair per name (values are closed by the loader).
_SOURCE_FIELDS: dict[str, tuple[str, str]] = {
    "uup": ("uup_dates", "uup_close"),
    "real_rate": ("real_rate_dates", "real_rate_values"),
    "gvz": ("gvz_dates", "gvz_values"),
    "hy_oas": ("hy_oas_dates", "hy_oas_values"),
    "ig_oas": ("ig_oas_dates", "ig_oas_values"),
    "breakeven_5y": ("breakeven_5y_dates", "breakeven_5y_values"),
    "nfci": ("nfci_dates", "nfci_values"),
    "gdx_gld": ("gdx_dates", "gdx_close"),
    "gld_slv": ("slv_dates", "slv_close"),
    "m2": ("m2_dates", "m2_values"),
    "walcl": ("walcl_dates", "walcl_values"),
}


class GridPoint(BaseModel):
    """One frozen grid cell: the shipped-call kwargs plus the medium/long key."""

    model_config = ConfigDict(frozen=True, strict=True)

    params: dict[str, int]
    window_days: int = Field(ge=2)


class SeparationScore(BaseModel):
    """Frozen metric result for one z-series against the pinned windows (Ruling 1).

    ``separation`` is the SIGNED ``mean(trough) - mean(peak)``: positive votes
    cheap at bottoms. The two shares are counted per side off the RAW z — they
    are deliberately NOT derivable from each other (``1 - x`` is invalid because
    a dead-zone oscillator sits at exactly ``0.0``) — and ``degenerate`` records
    that one side never leaves the dead zone.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    separation: float | None
    mean_peak_z: float | None
    mean_trough_z: float | None
    peak_negative_share: float | None
    trough_positive_share: float | None
    zero_z_share: float | None
    degenerate: bool
    coverage: float = Field(ge=0.0, le=1.0)
    peak_days: int = Field(ge=0)
    trough_days: int = Field(ge=0)
    scored_days: int = Field(ge=0)
    reason: str | None


class GridRow(BaseModel):
    """One scored grid cell (params + metric), as written to the fits file."""

    model_config = ConfigDict(frozen=True, strict=True)

    params: dict[str, int]
    window_days: int = Field(ge=2)
    separation: float | None
    mean_peak_z: float | None
    mean_trough_z: float | None
    peak_negative_share: float | None
    trough_positive_share: float | None
    zero_z_share: float | None
    degenerate: bool
    coverage: float = Field(ge=0.0, le=1.0)
    z_coverage: float = Field(ge=0.0, le=1.0)
    peak_days: int = Field(ge=0)
    trough_days: int = Field(ge=0)
    scored_days: int = Field(ge=0)
    reason: str | None


class IndicatorFits(BaseModel):
    """Every scored grid row for one indicator, plus the three frozen reads.

    ``degenerate`` is True only when EVERY scored row is degenerate (an unscored
    indicator is never flagged); ``degenerate_pass`` additionally requires a
    strictly positive best separation, i.e. a positive pass resting on a dead
    side. Both are listed separately from any keep list.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    family: str
    grid_rows: int = Field(ge=0)
    status: str
    reason: str | None
    rows: tuple[GridRow, ...]
    best_overall: GridRow | None
    best_medium: GridRow | None
    best_long: GridRow | None
    degenerate: bool
    degenerate_pass: bool
    verdict: str


# This harness is loaded by file path in tests (importlib module_from_spec without
# a sys.modules entry), where pydantic cannot resolve the sibling annotation at
# class-creation time. Rebuild once the module namespace holds GridRow.
IndicatorFits.model_rebuild()


# --------------------------------------------------------------------------- #
# The frozen metric
# --------------------------------------------------------------------------- #


def row_is_degenerate(
    *,
    separation: float | None,
    mean_peak_z: float | None,
    mean_trough_z: float | None,
) -> bool:
    """True when ONE window side's mean never leaves the dead zone.

    Ruling 1's degenerate rule: a pass that rests on a side whose mean sits
    inside ±``DEGENERATE_MEAN_ABS`` is one-sided — the z has no opinion on that
    side at all (the RSI dead zone / log-MACD dead band put every pinned window
    day at exactly 0.0). An unscored row has no pass to rest on, so it is never
    degenerate.
    """
    if separation is None or mean_peak_z is None or mean_trough_z is None:
        return False
    return abs(mean_peak_z) <= DEGENERATE_MEAN_ABS or abs(mean_trough_z) <= DEGENERATE_MEAN_ABS


def separation(
    dates: Sequence[date],
    z_values: Sequence[float | None],
    windows: SdcaCycleWindows,
) -> SeparationScore:
    """``mean(z | troughs) - mean(z | peaks)``; positive = votes cheap at bottoms.

    Ruling 1 flipped the pre-registered sign: ``composite_risk.py:57`` maps
    ``+z`` to buy/cheap and the shipped Stage-A objective is ``+(50/3) *
    (mean z|troughs - mean z|peaks)``, so a leg that votes cheap at the bottoms
    must score POSITIVE. ``abs()`` is never applied — a mirrored z scores the
    exact negation.

    Null z is skipped (never zero-filled). A window side with no valid z leaves
    ``separation`` ``None`` and records WHY — the staged credit legs (hy_oas /
    ig_oas) start after the last pinned trough window, so they are unscoreable
    by construction rather than silently dropped.

    The shares are counted per side off the RAW z: ``peak_negative_share`` is the
    share of peak window days below zero and ``trough_positive_share`` the share
    of trough window days above zero. They are not collapsible into ``1 - x``
    because a dead-zone oscillator sits at exactly ``0.0`` (neither below nor
    above), which ``zero_z_share`` records.
    """
    if len(dates) != len(z_values):
        raise ValueError("dates and z_values must be the same length")
    peak_vals: list[float] = []
    trough_vals: list[float] = []
    window_days = 0
    for day, raw in zip(dates, z_values, strict=True):
        kind = windows.kind_on(day)
        if kind is None:
            continue
        window_days += 1
        if raw is None:
            continue
        (peak_vals if kind is CycleKind.PEAK else trough_vals).append(float(raw))

    scored = len(peak_vals) + len(trough_vals)
    coverage = scored / window_days if window_days else 0.0
    if not peak_vals and not trough_vals:
        return SeparationScore(
            separation=None,
            mean_peak_z=None,
            mean_trough_z=None,
            peak_negative_share=None,
            trough_positive_share=None,
            zero_z_share=None,
            degenerate=False,
            coverage=0.0,
            peak_days=0,
            trough_days=0,
            scored_days=0,
            reason=(
                "no valid z inside any pinned window "
                f"({window_days} window days, 0 scored) — series starts after "
                "the pins, or the window is inside the z warm-up"
            ),
        )
    peak_share = sum(1 for v in peak_vals if v < 0.0) / len(peak_vals) if peak_vals else None
    trough_share = (
        sum(1 for v in trough_vals if v > 0.0) / len(trough_vals) if trough_vals else None
    )
    zero_share = sum(1 for v in (*peak_vals, *trough_vals) if v == 0.0) / scored if scored else None
    if not peak_vals or not trough_vals:
        missing = "trough" if not trough_vals else "peak"
        return SeparationScore(
            separation=None,
            mean_peak_z=(sum(peak_vals) / len(peak_vals)) if peak_vals else None,
            mean_trough_z=(sum(trough_vals) / len(trough_vals)) if trough_vals else None,
            peak_negative_share=peak_share,
            trough_positive_share=trough_share,
            zero_z_share=zero_share,
            degenerate=False,
            coverage=coverage,
            peak_days=len(peak_vals),
            trough_days=len(trough_vals),
            scored_days=scored,
            reason=(
                f"no valid z in any pinned {missing} window "
                f"(peak days {len(peak_vals)}, trough days {len(trough_vals)}) — "
                f"separation needs both sides; {missing} side unscoreable"
            ),
        )
    mean_peak = sum(peak_vals) / len(peak_vals)
    mean_trough = sum(trough_vals) / len(trough_vals)
    separation_value = mean_trough - mean_peak
    return SeparationScore(
        separation=separation_value,
        mean_peak_z=mean_peak,
        mean_trough_z=mean_trough,
        peak_negative_share=peak_share,
        trough_positive_share=trough_share,
        zero_z_share=zero_share,
        degenerate=row_is_degenerate(
            separation=separation_value,
            mean_peak_z=mean_peak,
            mean_trough_z=mean_trough,
        ),
        coverage=coverage,
        peak_days=len(peak_vals),
        trough_days=len(trough_vals),
        scored_days=scored,
        reason=None,
    )


def _z_coverage(z_values: Sequence[float | None]) -> float:
    if not z_values:
        return 0.0
    return sum(1 for v in z_values if v is not None) / len(z_values)


# --------------------------------------------------------------------------- #
# Grids + dispatch
# --------------------------------------------------------------------------- #


def indicator_grid(name: str) -> tuple[GridPoint, ...]:
    """Frozen grid for one wired indicator (empty for an unwired name)."""
    if name in _LEVEL_Z or name in _RATIO_Z:
        return tuple(GridPoint(params={"window": w}, window_days=w) for w in LEVEL_WINDOWS)
    if name in _ROC_Z:
        return tuple(
            GridPoint(params={"roc_days": r, "window": w}, window_days=w)
            for r, w in product(ROC_DAYS, ROC_WINDOWS)
        )
    if name == "weekly_rsi":
        return tuple(
            GridPoint(
                params={"rsi_length": n},
                window_days=documented_warmup_calendar_days(SdcaOscillatorSpec(rsi_length=n)),
            )
            for n in RSI_LENGTHS
        )
    if name == "weekly_macd":
        return tuple(
            GridPoint(
                params={"macd_fast": fast, "macd_slow": slow, "macd_z_window": z_window},
                window_days=z_window,
            )
            for (fast, slow), z_window in product(MACD_SPANS, MACD_Z_WINDOWS)
        )
    if name == "sma_band":
        return tuple(
            GridPoint(params={"sma_band_window": w, "sma_band_min_samples": m}, window_days=w)
            for w, m in product(SMA_BAND_WINDOWS, SMA_BAND_MIN_SAMPLES)
        )
    return ()


def _source_pair(name: str, sources: ExtraIndicatorSources) -> tuple[pl.Series, pl.Series]:
    fields = _SOURCE_FIELDS.get(name)
    if fields is None:
        raise ValueError(f"no grid for {name!r}")
    src_dates = getattr(sources, fields[0])
    src_values = getattr(sources, fields[1])
    if src_dates is None or src_values is None:
        raise ValueError(f"no staged source series for {name!r} ({fields[0]} is None)")
    return src_dates, src_values


def build_z(
    name: str,
    params: Mapping[str, int],
    dates: pl.Series,
    price: pl.Series | None,
    sources: ExtraIndicatorSources | None,
) -> list[float | None]:
    """Call the SHIPPED z-function for ``name`` with ``params`` and nothing else.

    ``price`` is the asset close (GLD) — required by the ratio legs and the
    oscillators, unused by the level-z and growth legs.
    """
    if name in _OSCILLATORS:
        if price is None:
            raise ValueError(f"{name!r} needs the asset close")
        spec = SdcaOscillatorSpec(**dict(params))
        vectors = price_oscillator_z_vectors(dates, price, oscillators=spec)
        return list(vectors[name])
    if sources is None:
        raise ValueError(f"no grid for {name!r}")
    src_dates, src_values = _source_pair(name, sources)
    if name in _LEVEL_Z:
        return _LEVEL_Z[name](dates, src_dates, src_values, **dict(params)).to_list()
    if name in _RATIO_Z:
        if price is None:
            raise ValueError(f"{name!r} needs the asset close")
        return _RATIO_Z[name](dates, price, src_dates, src_values, **dict(params)).to_list()
    if name in _ROC_Z:
        return _ROC_Z[name](dates, src_dates, src_values, **dict(params)).to_list()
    raise ValueError(f"no grid for {name!r}")


def _family(name: str) -> str:
    if name in _LEVEL_Z:
        return "level_z"
    if name in _RATIO_Z:
        return "ratio_z"
    if name in _ROC_Z:
        return "growth_z"
    if name in _OSCILLATORS:
        return "oscillator"
    return "unwired"


# --------------------------------------------------------------------------- #
# Frozen reads: best row, medium (<= 378), long (>= 504)
# --------------------------------------------------------------------------- #


def best_row(rows: Sequence[GridRow]) -> GridRow | None:
    """Highest ``separation`` (best corrected = cheapest at the pinned bottoms);
    ties break to the SHORTER window (parsimony)."""
    scored = [r for r in rows if r.separation is not None]
    if not scored:
        return None
    return min(scored, key=lambda r: (-float(r.separation), r.window_days))


def degenerate_verdict(rows: Sequence[GridRow]) -> tuple[bool, bool]:
    """``(degenerate, degenerate_pass)`` for one indicator's grid (Ruling 1).

    ``degenerate``: EVERY scored row is degenerate (a dead-side pass on every
    window setting). No scored row → ``False`` — an unscoreable leg is listed
    with its reason, never silently flagged.

    ``degenerate_pass``: ``degenerate`` AND the best row's separation is
    STRICTLY positive, i.e. a pass that exists only because one side is dead.
    Such a leg is reported separately and never enters a keep list without an
    explicit owner look.
    """
    scored = [r for r in rows if r.separation is not None]
    if not scored:
        return (False, False)
    degenerate = all(
        row_is_degenerate(
            separation=r.separation,
            mean_peak_z=r.mean_peak_z,
            mean_trough_z=r.mean_trough_z,
        )
        for r in scored
    )
    best = best_row(scored)
    return (degenerate, bool(degenerate and best is not None and float(best.separation) > 0.0))


def best_row_in_band(
    rows: Sequence[GridRow],
    *,
    max_window_days: int | None = None,
    min_window_days: int | None = None,
) -> GridRow | None:
    band = [
        r
        for r in rows
        if r.separation is not None
        and (max_window_days is None or r.window_days <= max_window_days)
        and (min_window_days is None or r.window_days >= min_window_days)
    ]
    return best_row(band)


# --------------------------------------------------------------------------- #
# Fit one indicator
# --------------------------------------------------------------------------- #


def fit_indicator(
    name: str,
    dates: Sequence[date],
    date_s: pl.Series,
    price_s: pl.Series,
    sources: ExtraIndicatorSources,
    windows: SdcaCycleWindows,
) -> IndicatorFits:
    """Sweep the frozen grid for ``name`` and score every row against ``windows``.

    A leg whose staged source is absent, or whose z cannot reach both window
    sides, comes back ``status="unscoreable"`` with a reason — the grid rows are
    still listed so the omission is visible rather than silent.

    ``verdict`` is the Ruling-1 read of the corrected metric and is the ONLY
    thing Task 2/3 should branch on: ``keep`` (votes cheap at bottoms), ``drop``
    (votes backwards — no abs(), so a negative separation stays negative),
    ``degenerate_pass`` (a pass resting on a dead side: listed separately, never
    a keep without an explicit owner look) or ``unscoreable``.
    """
    grid = indicator_grid(name)
    if not grid:
        raise ValueError(f"no grid for {name!r}")
    rows: list[GridRow] = []
    missing_reason: str | None = None
    for point in grid:
        build_error: str | None = None
        try:
            z = build_z(name, point.params, date_s, price_s, sources)
        except ValueError as exc:
            build_error = str(exc)
            missing_reason = missing_reason or build_error
            z = [None] * len(dates)
        score = separation(dates, z, windows)
        rows.append(
            GridRow(
                params=dict(point.params),
                window_days=point.window_days,
                separation=score.separation,
                mean_peak_z=score.mean_peak_z,
                mean_trough_z=score.mean_trough_z,
                peak_negative_share=score.peak_negative_share,
                trough_positive_share=score.trough_positive_share,
                zero_z_share=score.zero_z_share,
                degenerate=score.degenerate,
                coverage=score.coverage,
                z_coverage=_z_coverage(z),
                peak_days=score.peak_days,
                trough_days=score.trough_days,
                scored_days=score.scored_days,
                # A dispatch failure is the real reason; never let the
                # all-null fallback read like "the pins are unreachable".
                reason=build_error or score.reason,
            )
        )
    scored_rows = [r for r in rows if r.separation is not None]
    if not scored_rows:
        reason = missing_reason or next((r.reason for r in rows if r.reason), "no scored grid row")
        return IndicatorFits(
            name=name,
            family=_family(name),
            grid_rows=len(rows),
            status="unscoreable",
            reason=reason,
            rows=tuple(rows),
            best_overall=None,
            best_medium=None,
            best_long=None,
            degenerate=False,
            degenerate_pass=False,
            verdict="unscoreable",
        )
    overall = best_row(rows)
    medium = best_row_in_band(rows, max_window_days=MEDIUM_WINDOW_MAX)
    long_read = best_row_in_band(rows, min_window_days=LONG_WINDOW_MIN)
    gap_reason: str | None = None
    if medium is None or long_read is None:
        absent = []
        if medium is None:
            absent.append(f"medium (<= {MEDIUM_WINDOW_MAX}d)")
        if long_read is None:
            absent.append(f"long (>={LONG_WINDOW_MIN}d)")
        gap_reason = (
            f"no grid row in the {' and '.join(absent)} band — "
            f"frozen windows for {name} are {sorted({r.window_days for r in rows})}"
        )
    degenerate, degenerate_pass = degenerate_verdict(rows)
    return IndicatorFits(
        name=name,
        family=_family(name),
        grid_rows=len(rows),
        status="scored",
        reason=gap_reason,
        rows=tuple(rows),
        best_overall=overall,
        best_medium=medium,
        best_long=long_read,
        degenerate=degenerate,
        degenerate_pass=degenerate_pass,
        verdict=_verdict(overall, degenerate_pass),
    )


def _verdict(row: GridRow | None, degenerate_pass: bool) -> str:
    """Ruling-1 verdict for one indicator: keep / drop / degenerate_pass."""
    if row is None or row.separation is None:
        return "unscoreable"
    if degenerate_pass:
        return "degenerate_pass"
    return "keep" if row.separation > 0.0 else "drop"


def run_fit(
    dates: Sequence[date],
    date_s: pl.Series,
    price_s: pl.Series,
    sources: ExtraIndicatorSources,
    windows: SdcaCycleWindows,
) -> dict[str, IndicatorFits]:
    """Fit every wired indicator (frozen order = ``FITTED_INDICATORS``)."""
    return {
        name: fit_indicator(name, dates, date_s, price_s, sources, windows)
        for name in FITTED_INDICATORS
    }


# --------------------------------------------------------------------------- #
# Report + CLI
# --------------------------------------------------------------------------- #


def fits_payload(
    dates: Sequence[date],
    fits: Mapping[str, IndicatorFits],
    *,
    windows_label: str,
) -> dict[str, Any]:
    keep = [name for name, fit in fits.items() if fit.verdict == "keep"]
    drop = [name for name, fit in fits.items() if fit.verdict == "drop"]
    return {
        "symbol": SYMBOL,
        "calendar": f"{dates[0]}..{dates[-1]} ({len(dates)} daily bars)",
        "windows": windows_label,
        "metric": METRIC_DEFINITION,
        "metric_read": METRIC_READ,
        "abs_forbidden": True,
        "degenerate_rule": DEGENERATE_LABEL,
        "degenerate_mean_abs": DEGENERATE_MEAN_ABS,
        "in_sample": True,
        "in_sample_label": IN_SAMPLE_LABEL,
        "tie_break": "higher separation, then the shorter window (parsimony)",
        "medium_band": f"window_days <= {MEDIUM_WINDOW_MAX}",
        "long_band": f"window_days >= {LONG_WINDOW_MIN}",
        "grids": {
            "level_z_windows": list(LEVEL_WINDOWS),
            "roc_days": list(ROC_DAYS),
            "roc_windows": list(ROC_WINDOWS),
            "rsi_lengths": list(RSI_LENGTHS),
            "macd_spans": [list(s) for s in MACD_SPANS],
            "macd_z_windows": list(MACD_Z_WINDOWS),
            "sma_band_windows": list(SMA_BAND_WINDOWS),
            "sma_band_min_samples": list(SMA_BAND_MIN_SAMPLES),
        },
        "deviations": DEVIATIONS,
        "not_fitted": {
            "dxy": (
                "excluded by the plan's frozen architecture line (it names uup_z, not "
                "dxy_z; uup_z is documented as a refreshability swap for DTWEXBGS)"
            ),
            "rs_eth": "BTC-plugin leg, not in the gold profile's extra-indicator allowlist",
            "valuation": "the selection ANCHOR (rolling90/z1.0), built in Task 2, not a fit candidate",
        },
        "indicators": {name: fit.model_dump(mode="json") for name, fit in fits.items()},
        "keep": keep,
        "drop": drop,
        # Listed SEPARATELY: never inside `keep`, never counted without an
        # explicit owner look (Ruling 1).
        "degenerate_passes": [
            {
                "name": name,
                "params": fit.best_overall.params if fit.best_overall else None,
                "window_days": fit.best_overall.window_days if fit.best_overall else None,
                "separation": fit.best_overall.separation if fit.best_overall else None,
            }
            for name, fit in fits.items()
            if fit.degenerate_pass
        ],
        "degenerate": [name for name, fit in fits.items() if fit.degenerate],
        "unscoreable": [
            {"name": name, "reason": fit.reason}
            for name, fit in fits.items()
            if fit.status != "scored"
        ],
    }


DEVIATIONS: tuple[str, ...] = (
    "Ruling 1 (Plan 19): the pre-registered metric sign was a CORRECTNESS BUG and is "
    "corrected here — separation = mean(z|troughs) - mean(z|peaks), positive = cheap at "
    "bottoms, abs() forbidden. Evidence: composite_risk.py:57 risk = 50 - composite_z*50/3 "
    "(+z = buy = cheap) and stage_a.py:88-99 mean_risk(peaks)-mean_risk(troughs) = "
    "+(50/3)*(mean z|troughs - mean z|peaks). ALL fitted best_* params change under it.",
    "Ruling 1: `sign_share` is GONE. The single aggregate is not recoverable as `1 - x` "
    "from raw z (a dead-zone oscillator sits at exactly 0.0, which 1-x would read as a "
    "perfect vote), so peak_negative_share / trough_positive_share / zero_z_share are all "
    "counted per side off the raw vectors.",
    "sma_band: the plan's `k in {2, 3}` band multiple does not exist in "
    "SdcaOscillatorSpec; swept `sma_band_min_samples in {30, 60}` (shipped default "
    "30 plus one longer warm-up) as the closest verified analogue. Catalog NOT extended.",
    "weekly_macd: the shipped weekly_macd_z deletes signal/z_window/min_samples, so "
    "`macd_z_window in {90, 378}` is an INERT dimension — those row pairs are identical "
    "and the shorter-window tie-break resolves them to 90. The 4-row grid is kept verbatim.",
    "weekly_rsi: no window knob beyond rsi_length; each grid point's window_days is the "
    "spec's documented calendar footprint (rsi_length + 1) * 7 via documented_warmup_calendar_days.",
    "dxy is not fitted: the plan's frozen architecture line names uup_z, not dxy_z.",
)


def _row_text(row: GridRow | None) -> str:
    if row is None:
        return "—"
    params = ",".join(f"{k}={v}" for k, v in sorted(row.params.items()))
    sep = "—" if row.separation is None else f"{row.separation:+.4f}"
    pk = "—" if row.peak_negative_share is None else f"{row.peak_negative_share:.3f}"
    tr = "—" if row.trough_positive_share is None else f"{row.trough_positive_share:.3f}"
    flag = " DEGENERATE" if row.degenerate else ""
    return (
        f"{params} | sep {sep} | p<0 {pk} | t>0 {tr} | cov {row.coverage:.3f} "
        f"| w {row.window_days}{flag}"
    )


def print_fits_table(fits: Mapping[str, IndicatorFits]) -> None:
    print("")
    print(
        f"{'indicator':<14} {'rows':>4} {'best params':<34} {'w':>5} {'sep':>9} "
        f"{'p<0':>6} {'t>0':>6} {'zero':>6} {'cov':>6}  verdict"
    )
    for name, fit in fits.items():
        row = fit.best_overall
        if row is None:
            print(f"{name:<14} {fit.grid_rows:>4} UNSCOREABLE — {fit.reason}")
            continue
        params = ",".join(f"{k}={v}" for k, v in sorted(row.params.items()))
        assert row.separation is not None
        print(
            f"{name:<14} {fit.grid_rows:>4} {params:<34} {row.window_days:>5} "
            f"{row.separation:>+9.4f} {(row.peak_negative_share or 0.0):>6.3f} "
            f"{(row.trough_positive_share or 0.0):>6.3f} {(row.zero_z_share or 0.0):>6.3f} "
            f"{row.coverage:>6.3f}  {fit.verdict}"
        )
    print("")
    for name, fit in fits.items():
        print(f"{name}: medium {_row_text(fit.best_medium)}")
        print(f"{name}: long   {_row_text(fit.best_long)}")
    print("")
    degenerate = [name for name, fit in fits.items() if fit.degenerate]
    passes = [name for name, fit in fits.items() if fit.degenerate_pass]
    keep = [name for name, fit in fits.items() if fit.verdict == "keep"]
    drop = [name for name, fit in fits.items() if fit.verdict == "drop"]
    print(f"keep: {keep}")
    print(f"drop: {drop}")
    print(f"degenerate: {degenerate}   degenerate_pass: {passes}")
    print(DEGENERATE_LABEL)
    print("")
    print(IN_SAMPLE_LABEL)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fit",
        action="store_true",
        help="sweep every frozen grid and write the fits file (the only mode)",
    )
    args = parser.parse_args(argv)
    if not args.fit:
        parser.error("this harness has one mode: pass --fit")

    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")

    sources = load_sdca_extra_sources(DATA_PATH.parent)
    present: list[str] = []
    absent: list[str] = []
    for name in FITTED_INDICATORS:
        if name in _OSCILLATORS:  # oscillators read the GLD close itself
            present.append(name)
            continue
        date_field = _SOURCE_FIELDS[name][0]
        staged = getattr(sources, date_field) is not None
        (present if staged else absent).append(name)
    print(f"staged sources present: {present}")
    if absent:
        print(f"staged sources ABSENT (unscoreable, listed): {absent}")

    windows = SdcaCycleWindows.gold_v1()
    print(f"pins: {len(windows.peaks())} peaks / {len(windows.troughs())} troughs, ±45d")

    fits = run_fit(dates, date_s, price_s, sources, windows)
    print_fits_table(fits)

    payload = fits_payload(dates, fits, windows_label="SdcaCycleWindows.gold_v1() ±45d")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
